#!/usr/bin/env python3
"""Busca no acervo: leis-base (normas/) + publicacoes com texto integral (dados/textos/).

Usado pelas sessoes de consulta (skill consulta-reforma). Sem indice: o
acervo (~500 textos, ~10 MB) cabe em busca linear por segundos.

Uso:
  python3 scripts/buscar.py split payment [--fonte CGIBS] [--desde 2026-09-01]
                            [--tipo norma|publicacao] [--limite 20]
  python3 scripts/buscar.py '"lei complementar nº 214"' art. 26     # aspas = frase
  python3 scripts/buscar.py --alteracoes-de lc214 [--artigo 26] [--mencoes]

--alteracoes-de lista as ALTERACOES (nao meras mencoes) nos ultimos
JANELA_ALTERACOES_DIAS dias antes do download da compilacao (e qualquer uma
depois) que modificam de fato a norma. Para cada alteracao, diz se o ato que
ela traz (ex.: "Lei Complementar nº 230") ja' aparece no texto compilado --
incorporada False = o Planalto ainda nao atualizou a compilacao, leia a redacao
nova na publicacao. incorporada None = nenhum ato identificado no titulo.

--mencoes adiciona um bloco separado com publicacoes que MENCIONAM a norma mas
nao a alteram (apenas citam, citam entre aspas, ou o contexto e' secundario).
"""
import argparse
import datetime
import json
import re
import shlex
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textos

RAIZ = Path(__file__).resolve().parent.parent
JANELA_ALTERACOES_DIAS = 30
PESO_TITULO = 5
CONTEXTO = 180

# padroes ja' normalizados (sem acento, minusculo, "nº" -> "no")
PADRAO_NORMA = {
    "lc214": r"lei complementar n[o.]*\s*214\b|\blc\s*(n[o.]*\s*)?214\b",
    "lc227": r"lei complementar n[o.]*\s*227\b|\blc\s*(n[o.]*\s*)?227\b",
    "ec132": r"emenda constitucional n[o.]*\s*132\b|\bec\s*(n[o.]*\s*)?132\b",
    "cf-reforma": r"constituicao federal|\bart\.?\s*(156-a|156-b|195)\b",
}
# Documento tipo que pode alterar cada norma (hierarquia legal)
TIPO_QUE_ALTERA = {
    "lc214": "lei complementar",
    "lc227": "lei complementar",
    "ec132": "emenda constitucional",
    "cf-reforma": "emenda constitucional",
}
ATO = re.compile(r"(lei complementar|emenda constitucional|medida provisoria|lei|decreto)"
                 r" n[o.]*\s*([\d.]+)")
ART = re.compile(r"(?m)^(?:\[NÃO VIGENTE: )?Art\. (\d+(?:-[A-Z])?)")
VERBO = re.compile(r"\b(altera|alteram|alterando|alterado|alterada|acrescenta|acrescentam|acrescido"
                   r"|acrescida|revoga|revogam|revogado|revogada|revogados|da nova redacao|modifica"
                   r"|modificam)\b")
# ANY numbered reference ends the window: "lei no 123", "resolucao no 456", etc.
# Matches one or more words + "no" + full number (may include dots like 2.345)
ATO_REF = re.compile(r"\b[a-z][a-z ]{1,40}\s+n[o.]*\s*[\d.]+")
PASSA_VIGORAR = re.compile(r"\bpassa(?:m)?\s+a\s+vigorar\b")


def normaliza(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _le_json(p, padrao):
    try:
        return json.loads(p.read_text("utf-8")) if p.exists() else padrao
    except ValueError:
        return padrao


def carrega(raiz):
    raiz = Path(raiz)
    docs = []
    for nid, m in _le_json(raiz / "normas" / "indice.json", {}).items():
        p = raiz / "normas" / f"{nid}.txt"
        if p.exists():
            docs.append({"tipo": "norma", "id": nid, "rotulo": m.get("rotulo", nid),
                         "titulo": m.get("titulo", nid), "data": (m.get("baixado_em") or "")[:10],
                         "fonte": "Planalto", "url": m.get("url", ""),
                         "caminho": f"normas/{nid}.txt", "texto": p.read_text("utf-8")})
    for k, it in _le_json(raiz / "dados" / "historico.json", {}).items():
        t = textos.le(raiz / "dados", k)
        if not t:
            continue
        docs.append({"tipo": "publicacao", "id": k, "rotulo": it.get("titulo", ""),
                     "titulo": it.get("titulo", ""), "data": it.get("data") or it.get("primeira_vez") or "",
                     "fonte": it.get("fonte", ""), "url": it.get("url", ""),
                     "caminho": f"dados/textos/{k}.txt", "texto": t})
    for d in docs:
        d["_n"], d["_nt"] = normaliza(d["texto"]), normaliza(d["titulo"])
    return docs


def _termos(consulta):
    try:
        partes = shlex.split(consulta)
    except ValueError:
        partes = consulta.split()
    return [normaliza(p) for p in partes if p.strip()]


def _dispositivo(doc, pos):
    ultimo = None
    for m in ART.finditer(doc["texto"], 0, pos + 1):
        ultimo = m.group(1)
    return f"{doc['rotulo']}, art. {ultimo}" if ultimo else doc["rotulo"]


def _sem_citacoes(s):
    """Strip quoted new wording (up to 5000 chars between quotes).
    Handles ASCII, typographic and angle quotes.
    """
    # Quote pairs: opening -> closing
    # Using Unicode escapes: U+201C/U+201D (curly quotes), U+00AB/U+00BB (angles)
    quote_pairs = {}
    quote_pairs['"'] = '"'              # ASCII " to "
    quote_pairs['“'] = '”'    # U+201C to U+201D (curly quotes)
    quote_pairs['«'] = '»'    # U+00AB to U+00BB (angle quotes)

    resultado = ""
    i = 0
    while i < len(s):
        if s[i] in quote_pairs:
            opening = s[i]
            closing = quote_pairs[opening]
            # Find closing quote within 5000 chars
            j = i + 1
            found = False
            while j < min(i + 5001, len(s)):
                if s[j] == closing:
                    resultado += " "
                    i = j + 1
                    found = True
                    break
                j += 1
            if not found:
                resultado += s[i]
                i += 1
        else:
            resultado += s[i]
            i += 1
    return resultado


def _pode_alterar_por_hierarquia(titulo_norm, norma_id):
    """
    Check if the document type in titulo_norm can legally amend the target norm.
    Only Lei Complementar can amend LC 214/227.
    Only Emenda Constitucional can amend EC 132/CF-reforma.
    Everything else (Resolução, Portaria, Lei ordinária, etc.) cannot.
    """
    tipo_requerido = TIPO_QUE_ALTERA.get(norma_id, "")
    if not tipo_requerido:
        return False
    # Check if titulo starts with or contains the required document type
    return bool(re.search(r"\b" + tipo_requerido, titulo_norm))


def _trecho_alteracao(texto_n, padrao_norma):
    """
    Find if texto_n contains an amendment to the norm matching padrao_norma.
    Returns the amendment window (~300 chars) or None.

    Amendment exists if EITHER:
    (A) verb + ato_ref matching the norm within 200 chars after verb, OR
    (B) norm pattern match + "passa a vigorar" before next ato_ref within 150 chars
    """
    # Remove quoted sections
    texto = _sem_citacoes(texto_n)

    # Try Form A: verb pattern
    for m_verb in VERBO.finditer(texto):
        verb_end = m_verb.end()
        window = texto[verb_end:verb_end + 200]

        # Find first ato reference in this window
        m_ato = ATO_REF.search(window)
        if m_ato:
            ato_text = m_ato.group(0)
            ato_n = normaliza(ato_text)
            # Check if this ato matches the norm
            if re.search(padrao_norma, ato_n):
                # Found amendment: extract trecho centered on the match
                trecho_start = max(0, m_verb.start() - 50)
                trecho_end = min(len(texto), m_ato.end() + 250)
                return " ".join(texto[trecho_start:trecho_end].split())

    # Try Form B: norm pattern + passa a vigorar
    for m_norm in re.finditer(padrao_norma, texto):
        norm_end = m_norm.end()
        window = texto[norm_end:norm_end + 150]

        # Check if "passa a vigorar" appears before next ato_ref
        m_passa = PASSA_VIGORAR.search(window)
        m_ato_ref = ATO_REF.search(window)

        if m_passa and (not m_ato_ref or m_passa.start() < m_ato_ref.start()):
            # Found amendment: extract trecho
            trecho_start = max(0, m_norm.start() - 50)
            trecho_end = min(len(texto), norm_end + 300)
            return " ".join(texto[trecho_start:trecho_end].split())

    return None


def busca(docs, consulta, fonte=None, desde=None, tipo=None, limite=20):
    termos = _termos(consulta)
    if not termos:
        return []
    fonte_n = normaliza(fonte) if fonte else None
    out = []
    for d in docs:
        if tipo and d["tipo"] != tipo:
            continue
        if fonte_n and fonte_n not in normaliza(d["fonte"]):
            continue
        if desde and (d["data"] or "") < desde:
            continue
        if not all(t in d["_n"] or t in d["_nt"] for t in termos):
            continue
        score = sum(d["_n"].count(t) + PESO_TITULO * d["_nt"].count(t) for t in termos)
        pos = d["_n"].find(termos[0])
        pos = pos if pos >= 0 else 0
        a, b = max(0, pos - CONTEXTO), min(len(d["texto"]), pos + CONTEXTO)
        trecho = " ".join(d["texto"][a:b].split())
        out.append({"tipo": d["tipo"], "id": d["id"], "rotulo": d["rotulo"], "data": d["data"],
                    "fonte": d["fonte"], "url": d["url"], "caminho": d["caminho"],
                    "trecho": trecho,
                    "dispositivo": _dispositivo(d, pos) if d["tipo"] == "norma" else None,
                    "score": score})
    out.sort(key=lambda x: (x["tipo"] != "norma", -x["score"], x["data"] or ""), reverse=False)
    return out[:limite]


def alteracoes_de(docs, norma_id, artigo=None):
    """
    Return publications that AMEND (not merely mention) the norm within the window.
    Each result includes 'trecho' (the amendment context).
    incorporada=None means no act number was identified in the title.

    Hierarchy check: only documents of the correct legal type can amend each norm.
    Lei Complementar can only amend LC 214/227.
    Emenda Constitucional can only amend EC 132/CF-reforma.
    All other types (Resolução, Portaria, Lei ordinária, etc.) cannot amend any.
    """
    padrao_str = PADRAO_NORMA[norma_id]
    norma = next((d for d in docs if d["tipo"] == "norma" and d["id"] == norma_id), None)
    if norma is None:
        raise KeyError(f"norma {norma_id} nao carregada (rode baixar_normas.py)")
    base = datetime.date.fromisoformat(norma["data"]) - datetime.timedelta(days=JANELA_ALTERACOES_DIAS)
    out = []
    for d in docs:
        if d["tipo"] != "publicacao" or (d["data"] or "") < base.isoformat():
            continue
        # Hierarchy check: can this document type legally amend this norm?
        if not _pode_alterar_por_hierarquia(d["_nt"], norma_id):
            continue
        # Check if this publication contains an amendment
        trecho = _trecho_alteracao(d["_n"], padrao_str)
        if not trecho:
            continue
        # Check if artigo appears in the amendment window
        if artigo:
            artigo_pattern = (r"\bart(igo)?s?\.?[^.;]{0,80}?\b" + re.escape(artigo) + r"\b")
            if not re.search(artigo_pattern, trecho):
                continue
        # Extract atos from title
        atos = sorted({f"{m.group(1)} no {m.group(2).rstrip('.')}" for m in ATO.finditer(d["_nt"])})
        atos = [a for a in atos if not re.search(padrao_str, normaliza(a))]
        incorporada = None
        if atos:
            incorporada = all(re.search(re.escape(a).replace("no\\ ", r"n[o.]*\s*"), norma["_n"])
                              for a in atos)
        out.append({"id": d["id"], "titulo": d["titulo"], "data": d["data"], "fonte": d["fonte"],
                    "url": d["url"], "caminho": d["caminho"], "atos": atos,
                    "incorporada": incorporada, "trecho": trecho})
    out.sort(key=lambda x: x["data"], reverse=True)
    return out


def mencoes_de(docs, norma_id):
    """
    Return publications that MENTION (but do not amend) the norm within the window.
    Same fields as alteracoes_de but without incorporada.

    Includes: (a) documents that don't amend the norm, and
             (b) documents that WOULD amend it but fail hierarchy check.
    """
    padrao_str = PADRAO_NORMA[norma_id]
    norma = next((d for d in docs if d["tipo"] == "norma" and d["id"] == norma_id), None)
    if norma is None:
        raise KeyError(f"norma {norma_id} nao carregada (rode baixar_normas.py)")
    base = datetime.date.fromisoformat(norma["data"]) - datetime.timedelta(days=JANELA_ALTERACOES_DIAS)
    out = []
    for d in docs:
        if d["tipo"] != "publicacao" or (d["data"] or "") < base.isoformat():
            continue
        # Check if mentions the norm
        if not re.search(padrao_str, d["_n"]) and not re.search(padrao_str, d["_nt"]):
            continue
        # Check hierarchy: if document type can't amend, it's a mention
        if not _pode_alterar_por_hierarquia(d["_nt"], norma_id):
            # Fails hierarchy check -> it's a mention
            out.append({"id": d["id"], "titulo": d["titulo"], "data": d["data"], "fonte": d["fonte"],
                        "url": d["url"], "caminho": d["caminho"]})
            continue
        # Document passes hierarchy, but is it an amendment?
        trecho = _trecho_alteracao(d["_n"], padrao_str)
        if not trecho:
            # Passes hierarchy but no amendment pattern -> it's a mention
            out.append({"id": d["id"], "titulo": d["titulo"], "data": d["data"], "fonte": d["fonte"],
                        "url": d["url"], "caminho": d["caminho"]})
    out.sort(key=lambda x: x["data"], reverse=True)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Busca em normas/ + dados/textos/")
    ap.add_argument("termos", nargs="*")
    ap.add_argument("--fonte")
    ap.add_argument("--desde")
    ap.add_argument("--tipo", choices=["norma", "publicacao"])
    ap.add_argument("--limite", type=int, default=20)
    ap.add_argument("--alteracoes-de")
    ap.add_argument("--artigo")
    ap.add_argument("--mencoes", action="store_true", help="Tambem listar mencoes (nao alteracoes)")
    a = ap.parse_args(argv)
    docs = carrega(RAIZ)
    if a.alteracoes_de:
        try:
            res = alteracoes_de(docs, a.alteracoes_de, a.artigo)
        except KeyError:
            opcoes = ", ".join(sorted(PADRAO_NORMA.keys()))
            print(f"Erro: norma desconhecida '{a.alteracoes_de}' (opcoes: {opcoes})", file=sys.stderr)
            return 2
        norma = next(d for d in docs if d["tipo"] == "norma" and d["id"] == a.alteracoes_de)
        # Calculate window start date
        janela_inicio = datetime.date.fromisoformat(norma["data"]) - datetime.timedelta(days=JANELA_ALTERACOES_DIAS)
        if res:
            print(f"Compilacao de {norma['rotulo']} baixada em {norma['data']}. "
                  f"{len(res)} publicacao(oes) na janela desde {janela_inicio.isoformat()} que a alteram:")
            for r in res:
                inc = {True: "ja' incorporada", False: "NAO INCORPORADA a compilacao", None: "sem ato identificado"}
                print(f"- {r['data']} [{r['fonte']}] {r['titulo'][:110]}\n  {inc[r['incorporada']]}"
                      f"{' (' + ', '.join(r['atos']) + ')' if r['atos'] else ''} -> {r['caminho']}")
        else:
            print(f"Nenhuma alteracao encontrada na janela desde {janela_inicio.isoformat()} "
                  f"(compilacao baixada em {norma['data']}).")
        if a.mencoes:
            mencoes = mencoes_de(docs, a.alteracoes_de)
            if mencoes:
                print(f"\nMencoes (citam, nao alteram): {len(mencoes)} publicacao(oes)")
                for m in mencoes:
                    print(f"- {m['data']} [{m['fonte']}] {m['titulo'][:110]} -> {m['caminho']}")
        return 0
    res = busca(docs, " ".join(a.termos), a.fonte, a.desde, a.tipo, a.limite)
    if not res:
        print("Nada encontrado.")
    for r in res:
        cab = r["dispositivo"] if r["tipo"] == "norma" else f"{r['data']} [{r['fonte']}] {r['rotulo'][:100]}"
        print(f"- {cab}  (score {r['score']})\n  {r['caminho']}  {r['url']}\n  ...{r['trecho']}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
