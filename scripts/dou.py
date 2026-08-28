#!/usr/bin/env python3
"""
DOU via INLABS — modulo compartilhado.

Fonte unica de verdade para login, download, leitura do XML e classificacao.
E' importado pela varredura diaria E pela medicao. Isso e' deliberado: se o
classificador vivesse em dois lugares, a medicao passaria a atestar um filtro
diferente do que roda em producao, e o "APROVADO" perderia sentido.

Credenciais vem do ambiente: INLABS_EMAIL, INLABS_SENHA.
"""
import io, re, sys, time, zipfile, urllib.parse, urllib.request, http.cookiejar
import xml.etree.ElementTree as ET

LOGIN = "https://inlabs.in.gov.br/logar.php"
DOWNLOAD = "https://inlabs.in.gov.br/index.php?p="
# Secao 2 e' ato de pessoal. "E" = edicao extra — nao e' detalhe: o Ato
# Conjunto n 5 e o Ato Tecnico Conjunto n 1 sairam em DO1E. Em 16 dias houve
# 21 edicoes extras com conteudo. Quem varre so' a edicao normal perde
# justamente o ato que tinha pressa.
SECOES = ["DO1", "DO3", "DO1E", "DO3E"]

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

# ------------------------------------------------------------------- filtro
ORGAOS = re.compile(r"(minist[ée]rio da fazenda|receita federal|"
                    r"comit[êe] gestor do ibs|cgibs|secretaria especial da receita|"
                    r"comit[êe] gestor do simples nacional)", re.I)
REFS = re.compile(r"(lei complementar\s*n?[ºo°]?\s*2(14|27)|"
                  r"lc\s*2(14|27)\s*/?\s*20(25|26)|"
                  r"emenda constitucional\s*n?[ºo°]?\s*132|"
                  r"decreto\s*n?[ºo°]?\s*12\.?955)", re.I)
TERMOS = re.compile(r"(\bibs\b|\bcbs\b|imposto seletivo|\bcgibs\b|split payment|"
                    r"\bdere\b|\bnfs-?e\b|al[íi]quota de refer[êe]ncia|"
                    r"reforma tribut[áa]ria do consumo|comit[êe] gestor do ibs)", re.I)
ROTINA = re.compile(r"(extrato de (contrato|doa[çc][ãa]o|termo|conv[êe]nio|registro|"
                    r"inexigibilidade|dispensa|rescis[ãa]o|adit)|aviso de (licita|"
                    r"homologa|dispensa)|edital de (notifica|convoca|intima)|"
                    r"ato declarat[óo]rio executivo corat|resultado de julgamento)", re.I)
SEM_NORMA = re.compile(r"^\s*(extratos?\b|despachos?\b|atos? declarat[óo]rios?\b|"
                       r"pauta de julgamento|atas?\b|avisos?\b|editais?\b|edital\b|"
                       r"resultado de julgamento|termo aditivo|aditamento|"
                       r"seguros? garantia|sele[çc][ãa]o p[úu]blica)", re.I)
TIPO_NORMATIVO = re.compile(r"(portaria|resolu[çc][ãa]o|instru[çc][ãa]o normativa|"
                            r"\bato\b|decreto|\blei\b|medida provis[óo]ria|"
                            r"solu[çc][ãa]o de consulta|recomenda[çc][ãa]o|"
                            r"delibera[çc][ãa]o|conv[êe]nio icms|ajuste sinief)", re.I)
DENSIDADE_FORTE = 3

TAG = re.compile(r"<[^>]+>")


def limpa(s):
    return re.sub(r"\s+", " ", TAG.sub(" ", s or "")).strip()


# -------------------------------------------------------------- login/download
def abre_sessao(email, senha, tentativas=30, log=sys.stderr):
    """Devolve (opener, cookie). Encerra o processo se nao conseguir.

    Repete em 5xx e tambem em "200 sem cookie": medido em 25/08/2026, o
    logar.php respondeu 200 sem cookie de sessao por causa de manutencao
    programada — nao credencial invalida, a mesma credencial funcionou
    minutos depois. So desiste na hora em 4xx (401/403), que e rejeicao
    de verdade, nao instabilidade. Espera crescente entre tentativas, com
    teto de 120s.
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
            corpo = op.open(urllib.request.Request(LOGIN, data=dados, headers=cab),
                            timeout=60).read()
            ck = next((c.value for c in cj if c.name == "inlabs_session_cookie"), None)
            if ck:
                return op, ck
            texto = corpo.decode("utf-8", "ignore").lower()
            if "manuten" in texto:
                ultimo = "pagina de manutencao programada (200 sem cookie) — repete"
            else:
                ultimo = ("200 sem cookie de sessao, sem mencao a manutencao no corpo — "
                          "pode ser credencial invalida, mas ja vimos isso ser manutencao "
                          "sem aviso explicito. Repete mesmo assim.")
        except urllib.error.HTTPError as e:
            ultimo = (f"HTTP {e.code} vindo do proprio INLABS — nao e credencial, "
                      "o servidor caiu antes de olhar o que foi enviado")
            if e.code < 500:
                break
        except Exception as e:
            ultimo = f"{type(e).__name__}: {str(e)[:110]}"
        if n < tentativas:
            espera = min(120, 10 * n)
            print(f"  login falhou ({ultimo}); nova tentativa em {espera}s "
                  f"[{n}/{tentativas}]", file=log)
            time.sleep(espera)
    raise RuntimeError(f"login do INLABS falhou apos {tentativas} tentativas: {ultimo}")


def baixa(op, cookie, dia, secao):
    """Devolve (bytes, erro). Nunca levanta."""
    url = DOWNLOAD + dia + "&dl=" + f"{dia}-{secao}.zip"
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

    # Dia sem edicao NAO devolve 404: o INLABS responde 200 com HTML. Sem esta
    # checagem o zipfile estoura com BadZipFile no primeiro sabado.
    if not bruto or not bruto.startswith(b"PK"):
        return None, "sem edicao (resposta nao e zip)"
    return bruto, None


# ------------------------------------------------------------------- leitura
CAMPOS = ("Identifica", "Ementa", "Titulo", "SubTitulo", "Texto", "Data")


def _titulo(campos, atrib, anterior):
    """Titulo legivel, com cascata de reserva.

    O DOU quebra materia longa em varias partes e so' a primeira carrega
    <Identifica>. Na medicao de 17/08, 4 dos 14 itens do balde principal
    chegaram sem titulo por causa disso — deteccao certa, apresentacao
    inutil. A cascata resolve, e a heranca do titulo anterior amarra a
    continuacao a materia de origem.
    """
    for k in ("Identifica", "Titulo", "SubTitulo"):
        if campos.get(k):
            return campos[k], False
    if anterior:
        return anterior + " (continuacao)", True
    for k in ("Ementa", "Texto"):
        if campos.get(k):
            return campos[k][:120].rstrip() + "...", False
    return (atrib.get("artType") or "materia") + " sem identificacao", False


def artigos(conteudo):
    """Le o zip do INLABS e devolve uma lista de materias."""
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
            anterior = {}          # ultimo titulo visto por orgao, dentro do arquivo
            for art in raiz.iter("article"):
                a = dict(art.attrib)
                campos = {}
                for el in art.iter():
                    if el.tag in CAMPOS:
                        campos[el.tag] = limpa("".join(el.itertext()))
                org = a.get("artCategory", "")
                tit, herdado = _titulo(campos, a, anterior.get(org))
                if not herdado and campos.get("Identifica"):
                    anterior[org] = campos["Identifica"]
                a["_titulo"] = tit
                a["_continuacao"] = herdado
                a["_ementa"] = campos.get("Ementa", "")
                a["_texto"] = campos.get("Texto", "")[:20000]
                a["_arquivo"] = nome
                saida.append(a)
    return saida


# -------------------------------------------------------------- classificacao
def classifica(a):
    """forte | revisar | descartado.

      1. sinal no titulo/ementa   -> forte    (o assunto e' declarado)
      2. tipo sem carga normativa -> descartado
      3. corpo com >= 3 mencoes   -> forte    (trata do tema, nao cita de passagem)
      4. corpo com 1 ou 2         -> revisar
      5. orgao relevante E tipo normativo -> revisar
      6. resto -> descartado

    artCategory fica FORA da deteccao de termo de proposito: o nome do orgao
    contem "CGIBS"/"Comite Gestor do IBS", entao usa-lo faria todo papel do
    proprio Comite virar forte — o termo se confirmando pelo remetente, nao
    pelo assunto. O orgao entra so' na regra 5.
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


def link(a, dia):
    """Melhor endereco disponivel para a materia."""
    for k in ("pdfPage", "urlTitle", "url"):
        v = a.get(k)
        if v and v.startswith("http"):
            return v
    # O id entra como fragmento para o link ficar unico: sem ele, todas as
    # materias de uma mesma secao/dia dividiriam a mesma chave de deduplicacao
    # e so' a primeira seria registrada como novidade.
    return (f"https://www.in.gov.br/leiturajornal?data={dia}"
            f"&secao={a.get('pubName', 'DO1')}#a{a.get('id', '')}")


def coleta(dias, email, senha, log=sys.stderr):
    """Varre os dias pedidos e devolve (itens_relevantes, diagnostico).

    Cada item sai no mesmo formato dos demais coletores da varredura, para
    entrar no historico sem tratamento especial.
    """
    op, cookie = abre_sessao(email, senha, log=log)
    itens, diag = [], {"lidas": 0, "forte": 0, "revisar": 0, "sem_edicao": [], "erros": []}
    for dia in dias:
        for secao in SECOES:
            bruto, err = baixa(op, cookie, dia, secao)
            if err:
                (diag["sem_edicao"] if "sem edicao" in err else diag["erros"]).append(
                    f"{dia} {secao}: {err}")
                continue
            try:
                arts = artigos(bruto)
            except Exception as e:
                diag["erros"].append(f"{dia} {secao}: {type(e).__name__}")
                continue
            diag["lidas"] += len(arts)
            for a in arts:
                b = classifica(a)
                if b == "descartado":
                    continue
                diag[b] += 1
                itens.append({
                    "titulo": a.get("_titulo", "")[:220],
                    "url": link(a, dia),
                    "data": dia,
                    "fonte": f"DOU {secao}",
                    "orgao": a.get("artCategory", "")[:140],
                    "ementa": a.get("_ementa", "")[:300],
                    "texto": a.get("_texto", ""),
                    "balde": b,
                    "continuacao": bool(a.get("_continuacao")),
                    "alerta": None,
                    "pasta_arquivo": None,
                })
            print(f"  DOU {dia} {secao:5} materias={len(arts):5} "
                  f"relevantes={diag['forte'] + diag['revisar']}", file=log)
    return itens, diag
