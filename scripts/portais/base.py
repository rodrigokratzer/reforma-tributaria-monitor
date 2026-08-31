#!/usr/bin/env python3
"""Mecanica de coleta generica + classe base Portal.

As funcoes livres (via_http, via_browser, monta_item, ...) eram funcoes de
scripts/varredura.py ate' a Parte B; agora vivem aqui para que os objetos
Portal as usem. O comportamento e' identico ao da varredura v2.
"""
import re, ssl, sys, time, datetime, hashlib
import urllib.parse
import urllib.request, urllib.error
from html.parser import HTMLParser

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

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


class Portal:
    """Uma fonte web da varredura.

    A classe base reproduz exatamente o comportamento generico que valia
    para as 12 fontes ate' a Parte B: 2 tentativas via navegador, fallback
    HTTP puro, filtro por um regex global unico. Subclasses sobrescrevem
    filtro_relevancia() e/ou extrai_texto() quando uma fonte precisa de
    regra propria; adicionar uma fonte sem regra especial e' so' uma linha
    Portal(...) em portais.registro.
    """

    precisa_js = True

    def __init__(self, nome, url, precisa_js=None):
        self.nome = nome
        self.url = url
        if precisa_js is not None:
            self.precisa_js = precisa_js

    # -- pontos de extensao ----------------------------------------------

    def filtro_relevancia(self, titulo, url):
        """True se o item interessa.

        Default: o regex global RELEVANTE contra o titulo OU o caminho da
        URL (nunca o dominio — ver caminho_normalizado; casar contra o
        dominio faria todo link de cgibs.gov.br passar).
        """
        return bool(RELEVANTE.search(titulo)
                    or RELEVANTE.search(caminho_normalizado(url)))

    def extrai_texto(self, ctx, item, limite=None):
        """Corpo integral da publicacao do item, ou None.

        Default: None — ate' a Parte B nenhuma fonte web capturava texto
        completo. Chamado so' para itens que ja' passaram no filtro de
        relevancia, nunca para o volume bruto de links de uma pagina.
        `limite` e' o instante (time.monotonic) em que o orcamento da
        varredura acaba; a implementacao deve desistir se estiver perto.
        """
        return None

    # -- mecanica de coleta (identica a coleta() da varredura v2) --------

    def _filtra(self, pares):
        """pares = [(texto, href)] -> itens relevantes, sem repetir url."""
        itens, vistos = [], set()
        for t, h in pares:
            t = re.sub(r"\s+", " ", (t or "")).strip()
            if not t or len(t) < 12 or len(t) > 350 or not h or h in vistos:
                continue
            if not self.filtro_relevancia(t, h):
                continue
            vistos.add(h)
            itens.append(monta_item(t, h))
        return itens

    def coletar(self, ctx, limite=None):
        reg = {"fonte": self.nome, "url": self.url, "metodo": None,
               "http_status": None, "erro": None, "erro_browser": None,
               "total": 0, "itens": []}

        pares = None
        for tentativa, tmo in ((1, GOTO_MS_1), (2, GOTO_MS_2)):
            pares, err = via_browser(ctx, self.url, self.precisa_js, tmo)
            if pares is not None:
                reg["metodo"] = "browser"
                break
            reg["erro_browser"] = err
            if tentativa == 1:
                time.sleep(3)

        if pares is None:
            html, status, err = via_http(self.url)
            reg["http_status"] = status
            if not html:
                reg["erro"] = f"browser: {reg['erro_browser']} | http: {err}"
                return reg
            p = ColetorLinks(self.url)
            try:
                p.feed(html)
            except Exception:
                pass
            reg["metodo"] = "http"
            pares = p.pares

        reg["itens"] = self._filtra(pares)
        reg["total"] = len(reg["itens"])
        if reg["metodo"] == "http" and reg["total"] == 0 and self.precisa_js:
            reg["erro"] = ("browser falhou e o HTTP puro nao traz os itens "
                           "(pagina montada por script)")

        for it in reg["itens"]:
            try:
                txt = self.extrai_texto(ctx, it, limite)
            except Exception as e:
                txt = None
                print(f"      extrai_texto falhou em {it.get('url')}: "
                      f"{type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
            if txt:
                it["texto"] = txt

        return reg
