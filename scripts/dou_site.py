#!/usr/bin/env python3
"""
DOU pela "Leitura do Jornal" do in.gov.br — plano B para quando o INLABS cai.

Mesma saida de dou.coleta() (itens + diagnostico) e a MESMA classificacao
(dou.classifica): nenhuma regra de relevancia nova. A diferenca e' a fonte:
  * lista do dia: https://www.in.gov.br/leiturajornal?data=DD-MM-AAAA&secao=do1
    traz um JSON em <script id="params"> com ~300 materias (DO1) ou ~2.200
    (DO3), cada uma com titulo e uma previa de ate' ~400 caracteres;
  * texto integral: https://www.in.gov.br/web/dou/-/<urlTitle>, dentro de
    <div class="texto-dou">.

Educacao com o servidor: no maximo 4 downloads simultaneos, timeout de 30 s,
2 tentativas por pagina. O DO3 tem 2.000+ itens/dia, quase tudo extrato: so'
se baixa o que tem orgao ou termo relevante (ver _precisa_baixar).
"""
import json, re, sys, time, unicodedata, urllib.request
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from html.parser import HTMLParser

import dou

BASE = "https://www.in.gov.br"
SECAO_URL = {"DO1": "do1", "DO3": "do3", "DO1E": "do1e", "DO3E": "do3e"}
PREFIXO_PLANO_B = BASE + "/web/dou/-/"
PARALELO = 4
TIMEOUT = 30
TENTATIVAS = 2
MAX_ERROS_NO_DIAG = 20

PARAMS = re.compile(r'<script[^>]*id="params"[^>]*>(.*?)</script>', re.S)


def _dorme(s):
    time.sleep(s)


def _get(url, timeout=TIMEOUT):
    """GET com 2 tentativas; levanta a ultima excecao se as duas falharem."""
    req = urllib.request.Request(url, headers={
        "User-Agent": dou.UA,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"})
    ultimo = None
    for n in range(TENTATIVAS):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:
            ultimo = e
            if n + 1 < TENTATIVAS:
                _dorme(2)
    raise ultimo


def norm_titulo(t):
    """Minusculo, sem acento, espacos colapsados — chave de dedup por titulo."""
    return re.sub(r"\s+", " ", dou._sem_acento(t)).strip()


# -------------------------------------------------------------------- listas
def lista(dia_iso, secao):
    """Itens do jsonArray da Leitura do Jornal para (dia, secao). Levanta em erro."""
    a, m, d = dia_iso.split("-")
    html = _get(f"{BASE}/leiturajornal?data={d}-{m}-{a}&secao={SECAO_URL[secao]}")
    achou = PARAMS.search(html)
    if not achou:
        raise ValueError("pagina sem bloco params")
    return json.loads(achou.group(1)).get("jsonArray") or []


# --------------------------------------------------------------------- texto
class _TextoDou(HTMLParser):
    BLOCOS = {"p", "br", "div", "tr", "li", "h1", "h2", "h3", "h4", "table"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.prof = 0          # profundidade de <div> dentro de texto-dou; 0 = fora
        self.achou = False
        self.partes = []

    def handle_starttag(self, tag, attrs):
        if self.prof:
            if tag == "div":
                self.prof += 1
            if tag in self.BLOCOS:
                self.partes.append("\n")
        elif tag == "div" and "texto-dou" in (dict(attrs).get("class") or "").split():
            self.prof, self.achou = 1, True

    def handle_endtag(self, tag):
        if self.prof:
            if tag == "div":
                self.prof -= 1
            if tag in self.BLOCOS:
                self.partes.append("\n")

    def handle_data(self, data):
        if self.prof:
            self.partes.append(data)


def texto(url_title):
    """Texto da materia, ou None se a pagina nao tem texto-dou / deu erro."""
    try:
        html = _get(f"{BASE}/web/dou/-/{url_title}")
        p = _TextoDou()
        p.feed(html)
    except Exception:
        return None
    if not p.achou:
        return None
    linhas = [re.sub(r"[ \t\xa0]+", " ", l).strip() for l in "".join(p.partes).split("\n")]
    out = "\n".join(l for l in linhas if l)
    return out or None


# ------------------------------------------------------------------- coleta
def chave_dedup(data, titulo, orgao):
    """Chave de sobreposicao com o INLABS. Titulo sozinho colide ("PORTARIA N 5"
    de orgaos diferentes); o orgao (cortado em 140 como no historico) separa."""
    return (data, norm_titulo(titulo), norm_titulo(str(orgao)[:140]))


def _monta(it):
    """Dict `a` no formato que dou.classifica espera.

    _ementa fica vazia como nos extratos do INLABS (assim SEM_NORMA no titulo
    vence igual nas duas fontes); a previa vai em _previa e so' vira
    _texto_integral quando a pagina nao foi baixada.
    """
    titulo = dou.limpa(unescape(it.get("title") or it.get("titulo") or ""))
    return {"_titulo": titulo,
            "_ementa": "",
            "_previa": dou.limpa(unescape(it.get("content") or "")),
            "artType": it.get("artType") or "",
            "artCategory": it.get("hierarchyStr") or "",
            "_texto_integral": "",
            "_continuacao": False,
            "urlTitle": it.get("urlTitle") or ""}


def _descarte_barato(a):
    """Descarte do estagio 1 (sem baixar): extrato/aviso/ROTINA no titulo ou
    cabeca, e sem REFS/TERMOS na cabeca (essas ganham sempre, como em classifica)."""
    cabeca = " ".join([a["_titulo"], a["_previa"], a["artType"]])
    if dou.REFS.search(cabeca) or dou.TERMOS.search(cabeca):
        return False
    return bool(dou.SEM_NORMA.search(a["_titulo"]) or dou.ROTINA.search(cabeca))


def _precisa_baixar(secao, a):
    if secao in ("DO1", "DO1E"):
        return True
    cabeca = a["_titulo"] + " " + a["_previa"]
    return bool(dou.ORGAOS.search(a["artCategory"]) or dou.TERMOS.search(cabeca)
                or dou.REFS.search(cabeca))


def coleta(dias, historico=None, log=sys.stderr):
    """Mesmo contrato de dou.coleta: (itens_relevantes, diagnostico).

    Levanta RuntimeError se NENHUMA consulta de lista funcionou (site fora do
    ar ou formato mudou) — o chamador registra como falha, nao como "dia vazio".
    """
    # so' o que o INLABS coletou: reexecucao de itens do plano B ja' e' barrada
    # por chave() (url+titulo) em grava_resultado, e dois atos distintos com
    # mesmo titulo+orgao nunca podem ser descartados aqui
    conhecidos = set()
    for h in (historico or {}).values():
        if (str(h.get("fonte", "")).startswith("DOU")
                and not str(h.get("url", "")).startswith(PREFIXO_PLANO_B)):
            conhecidos.add(chave_dedup(h.get("data"), h.get("titulo", ""), h.get("orgao", "")))

    itens = []
    diag = {"lidas": 0, "forte": 0, "revisar": 0, "baixados": 0,
            "falhas_download": 0, "duplicados": 0, "sem_edicao": [], "erros": []}
    consultas_ok = 0

    def erro(msg):
        if len(diag["erros"]) < MAX_ERROS_NO_DIAG:
            diag["erros"].append(msg)

    for dia in dias:
        for secao in dou.SECOES:
            try:
                brutos = lista(dia, secao)
            except Exception as e:
                diag["erros"].append(f"{dia} {secao}: {type(e).__name__}: {str(e)[:80]}")
                print(f"  DOU* {dia} {secao:5} ERRO {type(e).__name__}", file=log)
                continue
            consultas_ok += 1
            if not brutos:
                diag["sem_edicao"].append(f"{dia} {secao}: sem materias")
                continue
            diag["lidas"] += len(brutos)

            candidatos = []          # (a, bruto, baixar?)
            for it in brutos:
                if not it.get("urlTitle"):
                    continue
                a = _monta(it)
                if _descarte_barato(a):
                    continue
                if chave_dedup(dia, a["_titulo"], a["artCategory"]) in conhecidos:
                    diag["duplicados"] += 1
                    continue
                candidatos.append((a, it, _precisa_baixar(secao, a)))

            alvo = [a for a, _, baixar in candidatos if baixar]
            if alvo:
                with ThreadPoolExecutor(max_workers=PARALELO) as ex:
                    textos = list(ex.map(lambda a: texto(a["urlTitle"]), alvo))
            else:
                textos = []
            por_id = {id(a): t for a, t in zip(alvo, textos)}

            relev0 = diag["forte"] + diag["revisar"]
            for a, it, baixar in candidatos:
                t = por_id.get(id(a)) if baixar else None
                if baixar:
                    if t:
                        diag["baixados"] += 1
                    else:
                        diag["falhas_download"] += 1
                        erro(f"{dia} {secao}: sem texto de {a['urlTitle'][:80]}")
                a["_texto_integral"] = t or a["_previa"]
                b = dou.classifica(a)
                if b == "descartado":
                    continue
                diag[b] += 1
                itens.append({
                    "titulo": a["_titulo"][:220],
                    "url": f"{BASE}/web/dou/-/{a['urlTitle']}",
                    "data": dia,
                    "fonte": f"DOU {secao}",
                    "orgao": a["artCategory"][:140],
                    "ementa": a["_previa"][:300],
                    "texto_integral": a["_texto_integral"],
                    "balde": b,
                    "continuacao": False,
                    "alerta": None,
                    "pasta_arquivo": None,
                })
            print(f"  DOU* {dia} {secao:5} materias={len(brutos):5} "
                  f"baixar={len(alvo):4} relevantes="
                  f"{diag['forte'] + diag['revisar'] - relev0}", file=log)

    if consultas_ok == 0:
        raise RuntimeError("Leitura do Jornal indisponivel: " + "; ".join(diag["erros"][:3]))
    return itens, diag
