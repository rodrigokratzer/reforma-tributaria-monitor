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

# Gabarito: (nome, data de publicacao no DOU, regex). A data importa porque
# um ato publicado fora da janela medida NAO pode ser cobrado do filtro — a v1
# do relatorio marcava "PERDEU" nesses casos e produzia alarme falso.
# TOLERANCIA_DOU cobre a incerteza de 1 a 2 dias entre assinatura e publicacao.
TOLERANCIA_DOU = 3
GABARITO = [
    ("Resolucao CGIBS n 14",       "2026-07-31", r"resolu[\u00e7c][\u00e3a]o\s+cgibs\s+n?[\u00ba\u00b0o]?\s*14\b"),
    ("Ato Conjunto RFB/CGIBS n 4", "2026-07-31", r"ato\s+conjunto\s+rfb\s*/?\s*cgibs\s+n?[\u00ba\u00b0o]?\s*4\b"),
    ("Ato Tecnico Conjunto n 1",   "2026-07-31", r"ato\s+t[\u00e9e]cnico\s+conjunto\s+rfb\s*/?\s*cgibs\s+n?[\u00ba\u00b0o]?\s*1\b"),
    ("Ato Conjunto RFB/CGIBS n 5", "2026-08-14", r"ato\s+conjunto\s+rfb\s*/?\s*cgibs\s+n?[\u00ba\u00b0o]?\s*5\b"),
]

# Tipos de ato que nunca carregam norma. Bloqueiam promocao por evidencia de
# corpo: um extrato de convenio que cita a LC 214 de passagem nao e' materia
# sobre a reforma. Sinal no titulo ou na ementa continua valendo acima disto.
SEM_NORMA = re.compile(r"^\s*(extratos?\b|despachos?\b|atos? declarat[\u00f3o]rios?\b|"
                       r"pauta de julgamento|atas?\b|avisos?\b|editais?\b|edital\b|"
                       r"resultado de julgamento|termo aditivo|aditamento|"
                       r"seguros? garantia|seleca?o p[\u00fau]blica)", re.I)

# Tipos que PODEM carregar norma — so' estes entram por forca do orgao.
TIPO_NORMATIVO = re.compile(r"(portaria|resolu[\u00e7c][\u00e3a]o|instru[\u00e7c][\u00e3a]o normativa|"
                            r"\bato\b|decreto|\blei\b|medida provis[\u00f3o]ria|"
                            r"solu[\u00e7c][\u00e3a]o de consulta|recomenda[\u00e7c][\u00e3a]o|"
                            r"delibera[\u00e7c][\u00e3a]o|conv[\u00eae]nio icms|ajuste sinief)", re.I)

# Quantas mencoes no corpo bastam para promover algo cujo titulo nao diz nada.
DENSIDADE_FORTE = 3

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
            bruto = r.read()
    except urllib.error.HTTPError as e:
        return None, ("sem edicao" if e.code == 404 else f"http {e.code}")
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:70]}"

    # Dia sem edicao (fim de semana, feriado) NAO devolve 404: o INLABS
    # responde 200 com uma pagina HTML. Sem esta checagem o zipfile estoura
    # com BadZipFile e derruba a execucao inteira no primeiro sabado.
    if not bruto or not bruto.startswith(b"PK"):
        amostra = bruto[:60].decode("utf-8", "replace").strip() if bruto else "vazio"
        return None, f"sem edicao (resposta nao e zip: {amostra[:40]})"
    return bruto, None


def artigos(conteudo):
    """Le o zip e devolve um dict por materia."""
    saida = []
    try:
        z = zipfile.ZipFile(io.BytesIO(conteudo))
    except zipfile.BadZipFile:
        return saida
    with z:
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
    """Devolve forte | revisar | descartado.

    Regras, em ordem:
      1. sinal no titulo/ementa  -> forte   (o assunto e' declarado)
      2. tipo sem carga normativa -> descartado (extrato, despacho, ADE...)
      3. corpo com >= 3 mencoes  -> forte   (o texto trata do tema, nao cita de passagem)
      4. corpo com 1 ou 2        -> revisar
      5. orgao relevante E tipo normativo -> revisar
      6. resto -> descartado

    artCategory (o orgao) fica FORA da deteccao de termo de proposito: o nome
    do orgao contem "CGIBS"/"Comite Gestor do IBS", entao usa-lo faria todo
    papel do proprio Comite virar "forte" — o termo se confirmando pelo
    remetente, nao pelo assunto. O orgao entra so' na regra 5.
    """
    titulo = a.get("_titulo", "")
    cabeca = " ".join([titulo, a.get("_ementa", ""), a.get("artType", "")])
    corpo = a.get("_texto", "")

    if REFS.search(cabeca) or TERMOS.search(cabeca):
        return "forte"

    if SEM_NORMA.search(titulo) or ROTINA.search(cabeca):
        return "descartado"

    mencoes = len(TERMOS.findall(corpo)) + len(REFS.findall(corpo))
    if mencoes >= DENSIDADE_FORTE:
        return "forte"
    if mencoes >= 1:
        return "revisar"

    if ORGAOS.search(a.get("artCategory", "")) and TIPO_NORMATIVO.search(cabeca):
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
    # Indice de TUDO que foi lido, inclusive descartado. Sem isto o recall nao
    # distingue "nao veio na coleta" de "veio e meu filtro jogou fora" — que e'
    # justamente a distincao pela qual escolhemos o INLABS.
    corpus = []
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
            try:
                arts = artigos(bruto)
            except Exception as e:
                falhas.append(f"{dia} {secao}: leitura do zip falhou ({type(e).__name__})")
                continue
            total += len(arts)
            cobertura.append({"dia": dia.isoformat(), "secao": secao,
                              "materias": len(arts), "kb": round(len(bruto) / 1024)})
            for a in arts:
                b = classifica(a)
                reg = {"dia": dia.isoformat(), "secao": secao,
                       "titulo": a.get("_titulo", "")[:150],
                       "orgao": a.get("artCategory", "")[:120],
                       "ementa": a.get("_ementa", "")[:200]}
                corpus.append({**reg, "balde": b})
                if b == "descartado":
                    baldes["descartado"] += 1
                else:
                    baldes[b].append(reg)
            print(f"  {dia} {secao:5} materias={len(arts):5} acum_forte={len(baldes['forte'])}",
                  file=sys.stderr)
        dia += datetime.timedelta(days=1)

    # RECALL — procura no CORPUS INTEIRO, inclusive no que foi descartado.
    # E ignora ato cuja publicacao no DOU esta' fora da janela medida: cobrar
    # isso do filtro seria alarme falso.
    recall, esperados_no_escopo = [], 0
    for nome, data_dou, rx in GABARITO:
        alvo = datetime.date.fromisoformat(data_dou)
        tol = datetime.timedelta(days=TOLERANCIA_DOU)
        no_escopo = (d0 - tol) <= alvo <= (d1 + tol)
        if not no_escopo:
            recall.append({"esperado": nome, "data_dou": data_dou,
                           "situacao": "fora da janela", "encontrado": None,
                           "balde": None, "dia": None, "secao": None, "titulo": ""})
            continue
        esperados_no_escopo += 1
        pad = re.compile(rx, re.I)
        hit = next((i for i in corpus
                    if pad.search(i["titulo"] + " " + i["ementa"])), None)
        if hit:
            situacao = "encontrado" if hit["balde"] in ("forte", "revisar") else "descartado pelo filtro"
        else:
            situacao = "ausente do corpus"
        recall.append({"esperado": nome, "data_dou": data_dou, "situacao": situacao,
                       "encontrado": bool(hit), "balde": (hit or {}).get("balde"),
                       "dia": (hit or {}).get("dia"), "secao": (hit or {}).get("secao"),
                       "titulo": (hit or {}).get("titulo", "")})

    u = max(1, dias_uteis)
    rel = {"janela": [d0.isoformat(), d1.isoformat()], "dias_uteis": dias_uteis,
           "materias_lidas": total, "cobertura": cobertura, "falhas": falhas,
           "forte": len(baldes["forte"]), "revisar": len(baldes["revisar"]),
           "descartado": baldes["descartado"],
           "forte_por_dia": round(len(baldes["forte"]) / u, 2),
           "revisar_por_dia": round(len(baldes["revisar"]) / u, 2),
           "recall": recall, "esperados_no_escopo": esperados_no_escopo,
           "corpus_indexado": len(corpus),
           "amostra_forte": baldes["forte"][:40],
           "amostra_revisar": baldes["revisar"][:20]}

    (RAIZ / "dados").mkdir(exist_ok=True)
    (RAIZ / "dados" / "medicao_inlabs.json").write_text(
        json.dumps(rel, ensure_ascii=False, indent=1), "utf-8")

    print(f"\n=== RECALL ===", file=sys.stderr)
    MARCA = {"encontrado": "OK    ", "descartado pelo filtro": "FILTRO",
             "ausente do corpus": "AUSENTE", "fora da janela": "n/a   "}
    for r in recall:
        extra = f"[{r['balde']}] {r['dia']} {r['secao']}" if r["encontrado"] else ""
        print(f"  {MARCA[r['situacao']]:7} {r['esperado']:30} DOU {r['data_dou']}  {extra}",
              file=sys.stderr)

    fora = sum(1 for r in recall if r["situacao"] == "fora da janela")
    filtrados = sum(1 for r in recall if r["situacao"] == "descartado pelo filtro")
    ausentes = sum(1 for r in recall if r["situacao"] == "ausente do corpus")
    fracos = sum(1 for r in recall if r["balde"] == "revisar")

    print(f"\n=== VOLUME ===", file=sys.stderr)
    print(f"  materias lidas : {total} em {dias_uteis} dias uteis", file=sys.stderr)
    print(f"  forte          : {rel['forte']} ({rel['forte_por_dia']}/dia)", file=sys.stderr)
    print(f"  revisar        : {rel['revisar']} ({rel['revisar_por_dia']}/dia)", file=sys.stderr)
    print(f"  descartado     : {rel['descartado']}", file=sys.stderr)
    if falhas:
        print(f"\n  {len(falhas)} dia(s)/secao(oes) sem edicao ou com erro; "
              f"1o: {falhas[0][:80]}", file=sys.stderr)

    if esperados_no_escopo == 0:
        veredito = ("INCONCLUSIVO — nenhum ato do gabarito foi publicado nesta "
                    "janela. Rode cobrindo 2026-07-29 em diante.")
    elif ausentes:
        veredito = (f"REPROVADO — {ausentes} ato(s) nao apareceram no corpus. "
                    "Problema de COLETA (secao ou dia faltando), nao de filtro.")
    elif filtrados:
        veredito = (f"REPROVADO — {filtrados} ato(s) foram coletados e o FILTRO "
                    "descartou. Problema de regra.")
    elif fracos:
        veredito = f"APROVADO com ressalva — {fracos} ato(s) so' no balde revisar"
    else:
        veredito = "APROVADO no recall"
    if fora:
        veredito += f" ({fora} ato(s) fora da janela, nao contam)"
    print(f"\nVEREDITO: {veredito}", file=sys.stderr)


if __name__ == "__main__":
    main()
