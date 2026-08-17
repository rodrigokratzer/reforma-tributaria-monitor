#!/usr/bin/env python3
"""
MEDICAO v2 — filtro do DOU sobre a edicao COMPLETA, via INLABS.

Diferenca em relacao a v1 (que reprovou): la' eu consultava a busca do
in.gov.br e classificava pelo trecho que a propria busca devolvia — coleta
truncada em silencio na pagina 0 e raciocinio circular. Aqui nao ha consulta:
baixo a edicao inteira e classifico pelos campos estruturados do XML
(orgao, tipo de ato, identificacao, ementa, texto). Se o recall falhar agora,
a culpa e' da regra, nao da coleta.

Credenciais vem do ambiente (secrets do GitHub). NUNCA escreva no arquivo.
  INLABS_EMAIL, INLABS_SENHA

Uso: python scripts/medir_inlabs.py [inicio AAAA-MM-DD] [fim AAAA-MM-DD]
"""
import io, json, os, re, sys, time, zipfile, datetime, urllib.parse
import urllib.request, http.cookiejar
import xml.etree.ElementTree as ET
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
LOGIN = "https://inlabs.in.gov.br/logar.php"
DOWNLOAD = "https://inlabs.in.gov.br/index.php?p="
# Secao 2 e' ato de pessoal — irrelevante. "E" = edicao extra.
SECOES = ["DO1", "DO3", "DO1E", "DO3E"]

# O workflow passa string vazia quando o campo fica em branco — argv existe
# mas vale "". Por isso o "or", e nao so' o teste de comprimento.
INICIO = (sys.argv[1] if len(sys.argv) > 1 else "") or "2026-07-27"
FIM = (sys.argv[2] if len(sys.argv) > 2 else "") or datetime.date.today().isoformat()

# ------------------------------------------------------------------ filtro
ORGAOS = re.compile(r"(minist[ée]rio da fazenda|receita federal|"
                    r"comit[êe] gestor do ibs|cgibs|secretaria especial da receita)", re.I)
REFS = re.compile(r"(lei complementar\s*n?[ºo°]?\s*2(14|27)|"
                  r"lc\s*2(14|27)\s*/?\s*20(25|26)|"
                  r"emenda constitucional\s*n?[ºo°]?\s*132|"
                  r"decreto\s*n?[ºo°]?\s*12\.?955)", re.I)
TERMOS = re.compile(r"(\bibs\b|\bcbs\b|imposto seletivo|\bcgibs\b|split payment|"
                    r"\bdere\b|\bnfs-?e\b|al[íi]quota de refer[êe]ncia|"
                    r"reforma tribut[áa]ria do consumo|comit[êe] gestor do ibs)", re.I)
# Tipos de ato de rotina. So' descartam quando NAO ha sinal forte — subtracao
# cega e' como se perde norma.
ROTINA = re.compile(r"(extrato de (contrato|doa[çc][ãa]o|termo|conv[êe]nio|registro|"
                    r"inexigibilidade|dispensa|rescis[ãa]o|adit)|aviso de (licita|"
                    r"homologa|dispensa)|edital de (notifica|convoca|intima)|"
                    r"ato declarat[óo]rio executivo corat|resultado de julgamento)", re.I)

GABARITO = [
    ("Resolucao CGIBS n 14",        r"resolu[çc][ãa]o\s+cgibs\s+n?[ºo°]?\s*14\b"),
    ("Ato Conjunto RFB/CGIBS n 4",  r"ato\s+conjunto\s+rfb\s*/?\s*cgibs\s+n?[ºo°]?\s*4\b"),
    ("Ato Tecnico Conjunto n 1",    r"ato\s+t[ée]cnico\s+conjunto\s+rfb\s*/?\s*cgibs\s+n?[ºo°]?\s*1\b"),
    ("Ato Conjunto RFB/CGIBS n 5",  r"ato\s+conjunto\s+rfb\s*/?\s*cgibs\s+n?[ºo°]?\s*5\b"),
]

TAG = re.compile(r"<[^>]+>")


def limpa(s):
    return re.sub(r"\s+", " ", TAG.sub(" ", s or "")).strip()


UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")


def abre_sessao(email, senha, tentativas=6):
    """Login no INLABS.

    A primeira versao mandava um POST cru com User-Agent "Python-urllib" e
    levou 502 do gateway. Agora: visita a home antes para abrir sessao, manda
    cabecalhos de navegador, e repete quando o erro e' 5xx — 502/503 em portal
    .gov.br costuma ser instabilidade momentanea, nao credencial errada.
    """
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    base = {"User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"}
    ultimo = ""
    for n in range(1, tentativas + 1):
        try:
            op.open(urllib.request.Request("https://inlabs.in.gov.br/",
                                           headers=base), timeout=60).read()
            dados = urllib.parse.urlencode({"email": email, "password": senha}).encode()
            cab = dict(base)
            cab.update({"Content-Type": "application/x-www-form-urlencoded",
                        "Origin": "https://inlabs.in.gov.br",
                        "Referer": "https://inlabs.in.gov.br/"})
            op.open(urllib.request.Request(LOGIN, data=dados, headers=cab),
                    timeout=60).read()
            ck = next((c.value for c in cj if c.name == "inlabs_session_cookie"), None)
            if ck:
                return op, ck
            ultimo = ("o servidor respondeu, mas nao devolveu cookie de sessao. "
                      "Isso aponta credencial invalida — confira INLABS_EMAIL e "
                      "INLABS_SENHA nos secrets.")
            break
        except urllib.error.HTTPError as e:
            ultimo = f"HTTP {e.code} do proprio INLABS"
            if e.code < 500:
                break
        except Exception as e:
            ultimo = f"{type(e).__name__}: {str(e)[:110]}"
        if n < tentativas:
            espera = 10 * n
            print(f"  login falhou ({ultimo}); nova tentativa em {espera}s "
                  f"[{n}/{tentativas}]", file=sys.stderr)
            time.sleep(espera)
    sys.exit(f"Falha no login do INLABS apos {tentativas} tentativa(s): {ultimo}")


def baixa(op, cookie, dia, secao):
    nome = f"{dia}-{secao}.zip"
    url = DOWNLOAD + dia + "&dl=" + nome
    req = urllib.request.Request(url, headers={
        "Cookie": "inlabs_session_cookie=" + cookie, "origem": "736372697074"})
    try:
        with op.open(req, timeout=180) as r:
            if r.status != 200:
                return None, f"http {r.status}"
            return r.read(), None
    except urllib.error.HTTPError as e:
        return None, ("sem edicao" if e.code == 404 else f"http {e.code}")
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:70]}"


def artigos(conteudo):
    """Le o zip e devolve um dict por materia."""
    saida = []
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        for nome in z.namelist():
            if not nome.lower().endswith(".xml"):
                continue
            try:
                raiz = ET.fromstring(z.read(nome))
            except Exception:
                continue
            for art in raiz.iter("article"):
                a = dict(art.attrib)
                campos = {}
                for el in art.iter():
                    if el.tag in ("Identifica", "Ementa", "Titulo", "SubTitulo", "Texto", "Data"):
                        campos[el.tag] = limpa("".join(el.itertext()))
                a["_titulo"] = campos.get("Identifica", "")
                a["_ementa"] = campos.get("Ementa", "")
                a["_texto"] = campos.get("Texto", "")[:20000]
                a["_arquivo"] = nome
                saida.append(a)
    return saida


def classifica(a):
    # ATENCAO: artCategory (o orgao) fica FORA daqui de proposito. O nome do
    # orgao contem "CGIBS"/"Comite Gestor do IBS", entao incluir esse campo faz
    # todo extrato de contrato do proprio Comite virar "forte" — o termo estaria
    # se confirmando pelo remetente, nao pelo assunto. O orgao entra so' na
    # camada ORGAOS, mais abaixo.
    cabeca = " ".join([a.get("_titulo", ""), a.get("_ementa", ""), a.get("artType", "")])
    corpo = a.get("_texto", "")
    forte = bool(REFS.search(cabeca) or TERMOS.search(cabeca) or REFS.search(corpo))
    if forte:
        return "forte"
    if ROTINA.search(cabeca):
        return "descartado"
    if TERMOS.search(corpo):
        return "revisar"
    if ORGAOS.search(a.get("artCategory", "")):
        return "revisar"
    return "descartado"


def main():
    email = os.environ.get("INLABS_EMAIL")
    senha = os.environ.get("INLABS_SENHA")
    if not email or not senha:
        sys.exit("Defina INLABS_EMAIL e INLABS_SENHA (secrets do GitHub).")

    d0 = datetime.date.fromisoformat(INICIO)
    d1 = datetime.date.fromisoformat(FIM)
    op, cookie = abre_sessao(email, senha)
    print(f"Login ok. Janela {d0} a {d1}, secoes {SECOES}\n", file=sys.stderr)

    baldes = {"forte": [], "revisar": [], "descartado": 0}
    cobertura, falhas, total, dias_uteis = [], [], 0, 0
    dia = d0
    while dia <= d1:
        if dia.weekday() < 5:
            dias_uteis += 1
        for secao in SECOES:
            bruto, err = baixa(op, cookie, dia.isoformat(), secao)
            if err:
                if err != "sem edicao":
                    falhas.append(f"{dia} {secao}: {err}")
                continue
            arts = artigos(bruto)
            total += len(arts)
            cobertura.append({"dia": dia.isoformat(), "secao": secao,
                              "materias": len(arts), "kb": round(len(bruto) / 1024)})
            for a in arts:
                b = classifica(a)
                if b == "descartado":
                    baldes["descartado"] += 1
                else:
                    baldes[b].append({"dia": dia.isoformat(), "secao": secao,
                                      "titulo": a.get("_titulo", "")[:150],
                                      "orgao": a.get("artCategory", "")[:120],
                                      "ementa": a.get("_ementa", "")[:200]})
            print(f"  {dia} {secao:5} materias={len(arts):5} acum_forte={len(baldes['forte'])}",
                  file=sys.stderr)
        dia += datetime.timedelta(days=1)

    # RECALL — procura no corpus inteiro, nao so' no que o filtro aprovou
    todos = baldes["forte"] + baldes["revisar"]
    recall = []
    for nome, rx in GABARITO:
        p = re.compile(rx, re.I)
        hit = next((i for i in todos if p.search(i["titulo"] + " " + i["ementa"])), None)
        balde = "forte" if hit and hit in baldes["forte"] else ("revisar" if hit else None)
        recall.append({"esperado": nome, "encontrado": bool(hit), "balde": balde,
                       "dia": (hit or {}).get("dia"), "secao": (hit or {}).get("secao"),
                       "titulo": (hit or {}).get("titulo", "")})

    u = max(1, dias_uteis)
    rel = {"janela": [d0.isoformat(), d1.isoformat()], "dias_uteis": dias_uteis,
           "materias_lidas": total, "cobertura": cobertura, "falhas": falhas,
           "forte": len(baldes["forte"]), "revisar": len(baldes["revisar"]),
           "descartado": baldes["descartado"],
           "forte_por_dia": round(len(baldes["forte"]) / u, 2),
           "revisar_por_dia": round(len(baldes["revisar"]) / u, 2),
           "recall": recall,
           "amostra_forte": baldes["forte"][:40],
           "amostra_revisar": baldes["revisar"][:20]}

    (RAIZ / "dados").mkdir(exist_ok=True)
    (RAIZ / "dados" / "medicao_inlabs.json").write_text(
        json.dumps(rel, ensure_ascii=False, indent=1), "utf-8")

    print(f"\n=== RECALL ===", file=sys.stderr)
    for r in recall:
        marca = "OK    " if r["encontrado"] else "PERDEU"
        extra = f"[{r['balde']}] {r['dia']} {r['secao']}" if r["encontrado"] else ""
        print(f"  {marca} {r['esperado']:30} {extra}", file=sys.stderr)
    perdidos = sum(1 for r in recall if not r["encontrado"])
    fracos = sum(1 for r in recall if r["balde"] == "revisar")
    print(f"\n=== VOLUME ===", file=sys.stderr)
    print(f"  materias lidas : {total} em {dias_uteis} dias uteis", file=sys.stderr)
    print(f"  forte          : {rel['forte']} ({rel['forte_por_dia']}/dia)", file=sys.stderr)
    print(f"  revisar        : {rel['revisar']} ({rel['revisar_por_dia']}/dia)", file=sys.stderr)
    print(f"  descartado     : {rel['descartado']}", file=sys.stderr)
    if falhas:
        print(f"\n  {len(falhas)} download(s) com erro; 1o: {falhas[0]}", file=sys.stderr)
    veredito = ("REPROVADO — %d ato(s) perdido(s)" % perdidos if perdidos
                else ("APROVADO com ressalva — %d ato(s) so' no balde revisar" % fracos
                      if fracos else "APROVADO no recall"))
    print(f"\nVEREDITO: {veredito}", file=sys.stderr)


if __name__ == "__main__":
    main()
