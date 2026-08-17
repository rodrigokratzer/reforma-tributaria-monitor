#!/usr/bin/env python3
"""
Varredura das fontes oficiais da reforma tributaria do consumo.

v2 — mudancas em relacao a primeira versao:
  * uma aba nova por fonte (na v1 uma falha derrubava as 11 seguintes com
    "Navigation is interrupted by another navigation", escondendo o erro real)
  * 2 tentativas por fonte, com espera entre elas
  * fallback HTTP puro (urllib) quando o navegador falha — serve tanto de
    plano B quanto de diagnostico: se o navegador reseta mas o urllib
    responde 200, o problema e' o navegador; se os dois falham igual,
    o bloqueio e' de rede (IP de datacenter recusado pelo site)
  * cada fonte registra o metodo que funcionou e o codigo HTTP obtido

Grava:
  dados/AAAA-MM-DD.json  status e itens da execucao
  dados/historico.json   indice acumulado {chave: item}
  dados/novidades.json   o que apareceu pela primeira vez
"""
import json, os, re, sys, time, ssl, datetime, hashlib
import urllib.parse
import urllib.request, urllib.error
from html.parser import HTMLParser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"
DADOS.mkdir(exist_ok=True)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

# (nome, url, precisa_de_javascript)
FONTES = [
    ("CGIBS - Noticias",             "https://www.cgibs.gov.br/noticias", True),
    ("CGIBS - Resolucoes",           "https://www.cgibs.gov.br/resolucoes", True),
    ("CGIBS - Atos Conjuntos",       "https://www.cgibs.gov.br/atos-conjuntos", True),
    ("CGIBS - Atos Tecnicos Conj.",  "https://www.cgibs.gov.br/atos-tecnicos-conjuntos", True),
    ("CGIBS - Portarias",            "https://www.cgibs.gov.br/portarias", True),
    ("RFB - Noticias 2026",          "https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2026", False),
    ("RFB - Reforma do Consumo",     "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/acoes-e-programas/programas-e-atividades/reforma-tributaria-do-consumo/noticias", False),
    ("Portal DF-e SVRS - Noticias",  "https://dfe-portal.svrs.rs.gov.br/Nfe/Noticias", False),
    ("Portal NF-e - Informes/NTs",   "https://www.nfe.fazenda.gov.br/portal/informe.aspx?ehCTG=false", False),
    ("CGIBS - Regulamentos",         "https://www.cgibs.gov.br/regulamentos", True),
    ("CGIBS - Leis",                 "https://www.cgibs.gov.br/leis", True),
    ("CGIBS - Relatorios",           "https://www.cgibs.gov.br/relatorios", True),
]

# Orcamento de tempo. O job do GitHub tem limite; sem um teto proprio o script
# e' morto no meio e nao grava nada — nem dado, nem diagnostico. Com o teto,
# ele sempre fecha, grava o que conseguiu e marca o resto como nao tentado.
ORCAMENTO_S = 600
GOTO_MS_1, GOTO_MS_2 = 25000, 18000
HTTP_TIMEOUT_S = 15

RELEVANTE = re.compile(
    r"\b(ibs|cbs|imposto seletivo|reforma tribut|lc\s*214|lc\s*227|ec\s*132|"
    r"cgibs|split payment|nfs-?e|nf-?e|dere|df-?e|nota t[ée]cnica|cr[ée]dito presumido|"
    r"regime espec[íi]fico|conformidade|al[íi]quota|cashback|simples nacional|"
    r"resolu[çc][ãa]o|portaria|ato conjunto|regulamento)\b",
    re.I,
)

MESES = {"janeiro":1,"fevereiro":2,"marco":3,"março":3,"abril":4,"maio":5,"junho":6,
         "julho":7,"agosto":8,"setembro":9,"outubro":10,"novembro":11,"dezembro":12}
RE_NUM = re.compile(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})")
RE_EXT = re.compile(r"(\d{1,2})\s+DE\s+([A-Za-zÇçÃãÉé]+)\s+DE\s+(\d{4})", re.I)
RE_PASTA = re.compile(r"/(20\d{2})(0[1-9]|1[0-2])/")


# ---------------------------------------------------------------- utilidades

def extrai_data(texto):
    m = RE_NUM.search(texto)
    if m:
        d, mes, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime.date(a, mes, d).isoformat()
        except ValueError:
            pass
    m = RE_EXT.search(texto)
    if m:
        mes = MESES.get(m.group(2).lower())
        if mes:
            try:
                return datetime.date(int(m.group(3)), mes, int(m.group(1))).isoformat()
            except ValueError:
                pass
    return None


def data_do_arquivo(url):
    m = RE_PASTA.search(url or "")
    return f"{m.group(1)}-{m.group(2)}" if m else None


def chave(item):
    return hashlib.sha1(((item.get("url") or "") + "|" +
                         (item.get("titulo") or "")).encode("utf-8")).hexdigest()[:16]


TOLERANCIA_MESES = 2   # assinar num mes e publicar ate 2 meses depois e' rotina


def monta_item(titulo, url):
    """Alerta so' quando a data declarada e' implausivel.

    A v2 marcava qualquer divergencia de mes, o que gerava falso positivo em
    toda norma assinada num mes e publicada no seguinte — rotina no CGIBS.
    Agora so' alerta quando a data e' POSTERIOR a publicacao do arquivo
    (impossivel) ou muito anterior a ela (foi o caso do Ato Conjunto n 5,
    listado como 2025 e publicado em 2026).
    """
    data = extrai_data(titulo)
    pasta = data_do_arquivo(url)
    alerta = None
    if data and pasta:
        idx_d = int(data[:4]) * 12 + int(data[5:7])
        idx_p = int(pasta[:4]) * 12 + int(pasta[5:7])
        defasagem = idx_p - idx_d
        if defasagem < 0:
            alerta = (f"data declarada ({data}) e' posterior a publicacao do arquivo "
                      f"({pasta}), o que e' impossivel; conferir o texto oficial")
        elif defasagem > TOLERANCIA_MESES:
            alerta = (f"data declarada ({data}) esta {defasagem} meses antes da "
                      f"publicacao do arquivo ({pasta}); provavel erro de cadastro na "
                      "fonte — conferir o texto oficial antes de reportar")
    return {"titulo": titulo, "url": url, "data": data,
            "pasta_arquivo": pasta, "alerta": alerta}


def caminho_normalizado(url):
    """So o path da url, com hifens/underscores virando espaco.

    Casar a regex contra a url inteira e' armadilha: o proprio dominio
    (cgibs.gov.br) contem 'cgibs', entao TODO link do site passava no filtro.
    """
    try:
        p = urllib.parse.urlparse(url).path
    except Exception:
        p = url or ""
    return re.sub(r"[-_/.]+", " ", p)


def filtra(pares):
    """pares = [(texto, href)] -> lista de itens relevantes, sem repetir url."""
    itens, vistos = [], set()
    for t, h in pares:
        t = re.sub(r"\s+", " ", (t or "")).strip()
        if not t or len(t) < 12 or len(t) > 350 or not h or h in vistos:
            continue
        if not RELEVANTE.search(t) and not RELEVANTE.search(caminho_normalizado(h)):
            continue
        vistos.add(h)
        itens.append(monta_item(t, h))
    return itens


# ------------------------------------------------------------ coleta por HTTP

class ColetorLinks(HTMLParser):
    """Extrai (texto, href) de cada <a> sem depender de biblioteca externa."""
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base, self.pares = base, []
        self._href, self._buf, self._nivel = None, [], 0

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            if self._nivel:                      # <a> aninhado: fecha o anterior
                self._fecha()
            self._href = dict(attrs).get("href")
            self._buf, self._nivel = [], 1

    def handle_data(self, data):
        if self._nivel:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._nivel:
            self._fecha()

    def _fecha(self):
        if self._href:
            self.pares.append(("".join(self._buf),
                               urllib.parse.urljoin(self.base, self._href)))
        self._href, self._buf, self._nivel = None, [], 0


def via_http(url, timeout=HTTP_TIMEOUT_S):
    """Devolve (html, status, erro). Nao levanta excecao."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Connection": "close",
    })
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            bruto = r.read()
            cs = r.headers.get_content_charset() or "utf-8"
            return bruto.decode(cs, "replace"), r.status, None
    except urllib.error.HTTPError as e:
        return None, e.code, f"HTTP {e.code}"
    except Exception as e:
        return None, None, f"{type(e).__name__}: {str(e)[:160]}"


# -------------------------------------------------------- coleta pelo browser

def via_browser(ctx, url, precisa_js, timeout_ms=GOTO_MS_1):
    """Aba nova por chamada: falha de uma fonte nao contamina as outras."""
    page = ctx.new_page()
    try:
        page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        page.wait_for_timeout(4000 if precisa_js else 1200)
        try:
            page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            pass
        pares = page.eval_on_selector_all(
            "a", "els => els.map(e => [(e.innerText||''), e.href])")
        return pares, None
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:160]}"
    finally:
        try:
            page.close()
        except Exception:
            pass


# ------------------------------------------------------------------ principal

def coleta(ctx, nome, url, precisa_js):
    reg = {"fonte": nome, "url": url, "metodo": None, "http_status": None,
           "erro": None, "erro_browser": None, "total": 0, "itens": []}

    for tentativa, tmo in ((1, GOTO_MS_1), (2, GOTO_MS_2)):
        pares, err = via_browser(ctx, url, precisa_js, tmo)
        if pares is not None:
            reg["metodo"] = "browser"
            reg["itens"] = filtra(pares)
            reg["total"] = len(reg["itens"])
            return reg
        reg["erro_browser"] = err
        if tentativa == 1:
            time.sleep(3)

    html, status, err = via_http(url)
    reg["http_status"] = status
    if html:
        p = ColetorLinks(url)
        try:
            p.feed(html)
        except Exception:
            pass
        reg["metodo"] = "http"
        reg["itens"] = filtra(p.pares)
        reg["total"] = len(reg["itens"])
        if reg["total"] == 0 and precisa_js:
            reg["erro"] = ("browser falhou e o HTTP puro nao traz os itens "
                           "(pagina montada por script)")
        return reg

    reg["erro"] = f"browser: {reg['erro_browser']} | http: {err}"
    return reg


def main():
    hoje = os.environ.get("DATA_REF") or datetime.date.today().isoformat()
    from playwright.sync_api import sync_playwright

    resultado = []
    with sync_playwright() as p:
        nav = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = nav.new_context(locale="pt-BR", user_agent=UA,
                              extra_http_headers={"Accept-Language": "pt-BR,pt;q=0.9"})
        limite = time.monotonic() + ORCAMENTO_S
        for nome, url, js in FONTES:
            if time.monotonic() > limite:
                resultado.append({"fonte": nome, "url": url, "metodo": None,
                                  "http_status": None, "total": 0, "itens": [],
                                  "erro": "nao tentada: orcamento de tempo esgotado"})
                print(f"  {nome:32} PULADA (tempo esgotado)", file=sys.stderr)
                continue
            r = coleta(ctx, nome, url, js)
            resultado.append(r)
            print(f"  {nome:32} metodo={r['metodo'] or 'FALHOU':7} "
                  f"itens={r['total']:3} http={r['http_status']} "
                  f"[{int(limite - time.monotonic())}s restantes]", file=sys.stderr)
            if r["erro"]:
                print(f"      {r['erro'][:150]}", file=sys.stderr)
        nav.close()

    hist_path = DADOS / "historico.json"
    historico = json.loads(hist_path.read_text("utf-8")) if hist_path.exists() else {}

    novidades = []
    for f in resultado:
        for it in f["itens"]:
            k = chave(it)
            if k not in historico:
                historico[k] = {"primeira_vez": hoje, "fonte": f["fonte"], **it}
                novidades.append(historico[k])

    falhas = [f["fonte"] for f in resultado if not f["metodo"]
              and "nao tentada" not in (f.get("erro") or "")]
    puladas = [f["fonte"] for f in resultado
               if "nao tentada" in (f.get("erro") or "")]
    so_http = [f["fonte"] for f in resultado if f["metodo"] == "http"]
    vazias = [f["fonte"] for f in resultado if f["metodo"] and f["total"] == 0]

    (DADOS / f"{hoje}.json").write_text(
        json.dumps({"data": hoje, "fontes": resultado}, ensure_ascii=False, indent=1), "utf-8")
    hist_path.write_text(json.dumps(historico, ensure_ascii=False, indent=1), "utf-8")
    (DADOS / "novidades.json").write_text(
        json.dumps({"data": hoje, "quantidade": len(novidades), "itens": novidades,
                    "fontes_com_erro": falhas, "fontes_sem_itens": vazias,
                    "fontes_via_http": so_http, "fontes_puladas": puladas},
                   ensure_ascii=False, indent=1), "utf-8")

    ok = len(FONTES) - len(falhas) - len(puladas)
    print(f"\n{ok}/{len(FONTES)} fontes ok | {len(novidades)} novidade(s) | "
          f"{len(falhas)} falha(s) | {len(puladas)} pulada(s) | "
          f"{len(so_http)} via HTTP | {len(vazias)} sem itens", file=sys.stderr)

    if ok == 0:
        print("\nDIAGNOSTICO: nenhuma fonte respondeu. Navegador e http puro falharam. "
              "Se a execucao anterior funcionou, e' instabilidade do lado dos sites, "
              "nao do script — os portais .gov.br respondem de forma intermitente.",
              file=sys.stderr)
    elif falhas:
        print(f"\nParcial: {ok} fonte(s) coletadas. As que falharam entram na proxima "
              "execucao; o historico acumulado nao se perde.", file=sys.stderr)


if __name__ == "__main__":
    main()
