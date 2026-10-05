#!/usr/bin/env python3
"""Leis-base da reforma em texto compilado do Planalto -> normas/.

Fonte primaria das sessoes de consulta (skill consulta-reforma) e da
analise. Texto compilado = ja' com as alteracoes posteriores; o que o
Planalto mostra riscado (revogado ou redacao anterior) sai como
[NÃO VIGENTE: ...] e nunca como texto vigente.

Grava (unico escritor):
  normas/<id>.txt          texto, com cabecalho de fonte e data
  normas/indice.json       {id: {titulo, rotulo, url, baixado_em, sha256, chars}}
                           baixado_em = quando o CONTEUDO mudou pela ultima vez
  dados/normas_status.json resultado da ultima execucao; "normas": {id: {verificado_em}}
                           = ultima vez que o Planalto foi consultado com sucesso

Uso:
  python3 scripts/baixar_normas.py --se-necessario   # ciclo: >= 7 dias ou gatilho
  python3 scripts/baixar_normas.py --forcar          # sob demanda
"""
import argparse
import datetime
import hashlib
import json
import re
import sys
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textos
from leitura.baixar import ErroDownload, Sessao
from portais.base import chave

RAIZ = Path(__file__).resolve().parent.parent
BASE = "https://www.planalto.gov.br/ccivil_03/"
DIAS_ATUALIZACAO = 7

# (rotulo, regex do inicio, regex do fim, regex que precisa vir ANTES do inicio ou None)
_ART = r"(?m)^(?:\[NÃO VIGENTE: )?Art\. {}\b"
NORMAS = [
    {"id": "ec132", "rotulo": "EC 132",
     "titulo": "Emenda Constitucional nº 132, de 20 de dezembro de 2023",
     "url": BASE + "constituicao/emendas/emc/emc132.htm", "minimo_artigos": 5, "recortes": None},
    {"id": "cf-reforma", "rotulo": "CF/ADCT",
     "titulo": "Constituição Federal — arts. 145 a 162 e 195; ADCT arts. 124 a 138 (texto compilado)",
     "url": BASE + "constituicao/constituicao.htm", "minimo_artigos": 20,
     "recortes": [
         ("CONSTITUIÇÃO FEDERAL — arts. 145 a 162", _ART.format(145), _ART.format(163), None),
         ("CONSTITUIÇÃO FEDERAL — art. 195", _ART.format(195), _ART.format(196), None),
         ("ADCT — arts. 124 a 138", _ART.format(124), _ART.format(139),
          r"ATO DAS DISPOSIÇÕES CONSTITUCIONAIS TRANSITÓRIAS"),
     ]},
    {"id": "lc214", "rotulo": "LC 214",
     "titulo": "Lei Complementar nº 214, de 16 de janeiro de 2025 (texto compilado)",
     "url": BASE + "leis/lcp/lcp214.htm", "minimo_artigos": 400, "recortes": None},
    {"id": "lc227", "rotulo": "LC 227",
     "titulo": "Lei Complementar nº 227, de 13 de janeiro de 2026 (texto compilado)",
     "url": BASE + "leis/lcp/lcp227.htm", "minimo_artigos": 50, "recortes": None},
]

# Novidade que provavelmente altera uma norma-base: antecipa o download. So' o
# TITULO conta (normalizado): comeca com "lei complementar n.." ou "emenda
# constitucional n..". Corpo de noticia que cita a LC 214 nao dispara.
GATILHO = re.compile(r"^\s*(?:lei complementar|emenda constitucional) n[o.]*\s*\d")


def _norm_titulo(t):
    t = unicodedata.normalize("NFKD", t or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower().replace("\u00b0", "o")


LINE_THROUGH = re.compile(r"line-through", re.I)
_RAW_RISCO = re.compile(
    r"<(?:strike|s|del)\b|<[a-z][^>]*\bstyle\s*=\s*[\"'][^\"']*line-through", re.I)


class ErroNorma(Exception):
    pass


class _Texto(HTMLParser):
    IGNORA = {"script", "style", "head", "title"}
    BLOCO = {"p", "br", "div", "tr", "td", "th", "li", "h1", "h2", "h3", "h4", "h5", "h6",
             "table", "blockquote"}
    RISCO = {"strike", "s", "del"}
    VOID = {"br", "img", "hr", "meta", "link", "input", "area", "base", "col", "wbr", "param",
            "source", "track", "embed"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.buf, self._ign, self._risco = [], 0, 0
        # pilha de elementos abertos: (tag, abriu_risco_por_css)
        self._pilha = []

    def _abre_risco(self):
        if self._risco == 0:
            self.buf.append("[NÃO VIGENTE: ")
        self._risco += 1

    def _fecha_risco(self):
        self._risco -= 1
        if self._risco == 0:
            self.buf.append("]")

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORA:
            self._ign += 1
        elif tag in self.BLOCO:
            self.buf.append(self._quebra())
        elif tag in self.RISCO:
            self._abre_risco()
        if tag in self.VOID:
            return
        css = bool(LINE_THROUGH.search(dict(attrs).get("style") or ""))
        if css and not self._ign:
            self._abre_risco()
        self._pilha.append((tag, css))

    def handle_endtag(self, tag):
        if tag in self.IGNORA and self._ign:
            self._ign -= 1
        elif tag in self.RISCO and self._risco:
            self._fecha_risco()
        elif tag in self.BLOCO:
            self.buf.append(self._quebra())
        # fecha o elemento aberto correspondente (e os que ficaram sem fechar acima dele)
        for i in range(len(self._pilha) - 1, -1, -1):
            if self._pilha[i][0] == tag:
                for _, css in reversed(self._pilha[i:]):
                    if css and self._risco:
                        self._fecha_risco()
                del self._pilha[i:]
                break

    def _quebra(self):
        # risco que atravessa paragrafos: fecha e reabre a marca em cada linha,
        # para nenhuma linha do meio parecer vigente
        return "]\n[NÃO VIGENTE: " if self._risco else "\n"

    def handle_data(self, data):
        if not self._ign:
            # quebra de linha no fonte HTML e' espaco, nao quebra de paragrafo
            self.buf.append(re.sub(r"\s+", " ", data))


def html_para_texto(html):
    p = _Texto()
    p.feed(html)
    p.close()
    t = "".join(p.buf).replace("\xa0", " ")
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    t = re.sub(r"\[NÃO VIGENTE:\s*\]", "", t)          # marcas vazias
    # colchete de risco aberto no fim de um paragrafo e fechado no seguinte
    t = re.sub(r"\[NÃO VIGENTE: \n+", "\n[NÃO VIGENTE: ", t)
    t = re.sub(r"\s+\]", "]", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip() + "\n"


def recorta(texto, recortes):
    partes = []
    for rotulo, ini, fim, depois_de in recortes:
        base = 0
        if depois_de:
            m = re.search(depois_de, texto)
            if not m:
                raise ErroNorma(f"recorte '{rotulo}': marco '{depois_de}' nao encontrado")
            base = m.end()
        mi = re.compile(ini).search(texto, base)
        if not mi:
            raise ErroNorma(f"recorte '{rotulo}': inicio nao encontrado")
        mf = re.compile(fim).search(texto, mi.end())
        trecho = texto[mi.start():mf.start() if mf else len(texto)]
        partes.append(f"===== {rotulo} =====\n\n{trecho.strip()}\n")
    return "\n".join(partes)


def valida(texto, minimo):
    n = len(re.findall(r"(?m)^(?:\[NÃO VIGENTE: )?Art\. \d", texto))
    if n < minimo:
        raise ErroNorma(f"so' {n} artigo(s) reconhecido(s) (minimo {minimo}): "
                        "estrutura da pagina mudou ou pagina de erro")


def _decodifica(resp):
    for cs in filter(None, [resp.charset, "cp1252"]):
        try:
            return resp.dados.decode(cs)
        except (LookupError, UnicodeDecodeError):
            continue
    return resp.dados.decode("cp1252", "replace")


def _agora():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _le_json(p, padrao):
    try:
        return json.loads(p.read_text("utf-8")) if p.exists() else padrao
    except ValueError:
        return padrao


def _grava_atomico(p, conteudo):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(conteudo, "utf-8")
    tmp.replace(p)


def precisa_atualizar(indice, novidades, hoje, verificado=None):
    """verificado: {id: {"verificado_em": ...}} (dados/normas_status.json); a idade
    usa verificado_em e cai no baixado_em do indice."""
    verificado = verificado or {}
    datas = []
    for n in NORMAS:
        meta = indice.get(n["id"])
        if not meta:
            return True, f"{n['id']} ainda nao baixada"
        quando = (verificado.get(n["id"]) or {}).get("verificado_em") or meta["baixado_em"]
        datas.append(datetime.date.fromisoformat(quando[:10]))
    idade = (hoje - min(datas)).days
    if idade >= DIAS_ATUALIZACAO:
        return True, f"compilacao verificada ha {idade} dia(s)"
    for it in novidades:
        m = GATILHO.search(_norm_titulo(it.get("titulo", "")))
        if m:
            return True, f"gatilho '{m.group(0).strip()}' em: {it.get('titulo', '')[:120]}"
    return False, f"compilacao verificada ha {idade} dia(s), sem gatilho"


def _novidades(raiz):
    """Itens novos do ultimo ciclo (web + DOU), com o texto integral quando houver."""
    out = []
    for nome in ("novidades.json", "novidades_dou.json"):
        for it in _le_json(raiz / "dados" / nome, {}).get("itens", []):
            t = textos.le(raiz / "dados", chave(it)) or it.get("texto") or ""
            out.append({"titulo": it.get("titulo", ""), "texto": t})
    return out


def baixa_norma(sessao, norma):
    """Devolve (texto, riscados_html, marcas_nao_vigente)."""
    html = _decodifica(sessao.baixa(norma["url"]))
    texto = html_para_texto(html)
    # salvaguarda: riscado no HTML cru precisa virar [NÃO VIGENTE: ...] (antes do recorte)
    raw = len(_RAW_RISCO.findall(html))
    marcas = texto.count("[NÃO VIGENTE:")
    if raw and (marcas == 0 or marcas < raw * 0.5):
        raise ErroNorma(f"{raw} elemento(s) riscado(s) no HTML mas so' {marcas} marca(s) "
                        "[NÃO VIGENTE]: marcacao de revogado nao reconhecida")
    if norma["recortes"]:
        texto = recorta(texto, norma["recortes"])
    valida(texto, norma["minimo_artigos"])
    return texto, raw, marcas


def executa(raiz, forcar=False, sessao=None, hoje=None):
    raiz = Path(raiz)
    hoje = hoje or datetime.date.today()
    arq_idx = raiz / "normas" / "indice.json"
    indice = _le_json(arq_idx, {})
    anterior = _le_json(raiz / "dados" / "normas_status.json", {}).get("normas", {})
    status = {"executado_em": _agora(), "erros": [], "normas": dict(anterior)}
    if forcar:
        motivo = "forcado"
    else:
        precisa, motivo = precisa_atualizar(indice, _novidades(raiz), hoje, anterior)
        if not precisa:
            status.update(resultado="sem_necessidade", motivo=motivo)
            _grava_atomico(raiz / "dados" / "normas_status.json",
                           json.dumps(status, ensure_ascii=False, indent=1))
            print(f"normas: {motivo}", file=sys.stderr)
            return 0
    sessao = sessao or Sessao()
    mudou = False
    for n in NORMAS:
        try:
            texto, raw, marcas = baixa_norma(sessao, n)
        except (ErroDownload, ErroNorma) as e:
            status["erros"].append(f"{n['id']}: {type(e).__name__}: {e}")
            print(f"normas: {n['id']} FALHOU ({e}); arquivo anterior mantido", file=sys.stderr)
            continue
        quando = _agora()
        sha = hashlib.sha256(texto.encode("utf-8")).hexdigest()
        status["normas"][n["id"]] = {"verificado_em": quando}
        if (indice.get(n["id"]) or {}).get("sha256") == sha and (raiz / "normas" / f"{n['id']}.txt").exists():
            print(f"normas: {n['id']} sem mudanca ({len(texto)} chars)", file=sys.stderr)
            continue
        cab = (f"# {n['titulo']}\n# Fonte: {n['url']}\n# Texto compilado baixado em: {quando}\n"
               "# Trechos riscados no Planalto (revogados ou com redação anterior) aparecem "
               "como [NÃO VIGENTE: ...] e não estão em vigor.\n\n")
        _grava_atomico(raiz / "normas" / f"{n['id']}.txt", cab + texto)
        indice[n["id"]] = {"titulo": n["titulo"], "rotulo": n["rotulo"], "url": n["url"],
                           "baixado_em": quando, "sha256": sha, "chars": len(texto),
                           "riscados_html": raw, "marcas_nao_vigente": marcas}
        mudou = True
        print(f"normas: {n['id']} ok ({len(texto)} chars)", file=sys.stderr)
    if mudou:
        _grava_atomico(arq_idx, json.dumps(indice, ensure_ascii=False, indent=1, sort_keys=True))
    status.update(resultado="falha_parcial" if status["erros"] else "atualizado", motivo=motivo)
    _grava_atomico(raiz / "dados" / "normas_status.json",
                   json.dumps(status, ensure_ascii=False, indent=1))
    return 1 if status["erros"] else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Leis-base do Planalto -> normas/")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--se-necessario", action="store_true")
    g.add_argument("--forcar", action="store_true")
    a = ap.parse_args(argv)
    return executa(RAIZ, forcar=a.forcar)


if __name__ == "__main__":
    sys.exit(main())
