#!/usr/bin/env python3
"""Busca no acervo: leis-base (normas/) + publicacoes com texto integral (dados/textos/).

Usado pelas sessoes de consulta (skill consulta-reforma). Sem indice: o
acervo (~500 textos, ~10 MB) cabe em busca linear por segundos.

Uso:
  python3 scripts/buscar.py split payment [--fonte CGIBS] [--desde 2026-09-01]
                            [--tipo norma|publicacao] [--limite 20]
  python3 scripts/buscar.py '"lei complementar nº 214"' art. 26     # aspas = frase
  python3 scripts/buscar.py --alteracoes-de lc214 [--artigo 26]

--alteracoes-de lista as publicacoes dos ultimos JANELA_ALTERACOES_DIAS dias
antes do download da compilacao (e qualquer uma depois) que mencionam a
norma; para cada uma diz se o ato que ela traz (ex.: "Lei Complementar nº
230") ja' aparece no texto compilado -- incorporada False = o Planalto
ainda nao atualizou a compilacao, leia a redacao nova na publicacao.
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
ATO = re.compile(r"(lei complementar|emenda constitucional|medida provisoria|lei|decreto)"
                 r" n[o.]*\s*([\d.]+)")
ART = re.compile(r"(?m)^(?:\[NÃO VIGENTE: )?Art\. (\d+(?:-[A-Z])?)")


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
    padrao = re.compile(PADRAO_NORMA[norma_id])
    norma = next((d for d in docs if d["tipo"] == "norma" and d["id"] == norma_id), None)
    if norma is None:
        raise KeyError(f"norma {norma_id} nao carregada (rode baixar_normas.py)")
    base = datetime.date.fromisoformat(norma["data"]) - datetime.timedelta(days=JANELA_ALTERACOES_DIAS)
    art = re.compile(rf"\bart(igo)?s?\.?\s*{re.escape(artigo)}\b") if artigo else None
    out = []
    for d in docs:
        if d["tipo"] != "publicacao" or (d["data"] or "") < base.isoformat():
            continue
        if not padrao.search(d["_n"]) and not padrao.search(d["_nt"]):
            continue
        if art and not art.search(d["_n"]):
            continue
        atos = sorted({f"{m.group(1)} no {m.group(2).rstrip('.')}" for m in ATO.finditer(d["_nt"])})
        atos = [a for a in atos if not padrao.search(a)]      # a propria norma nao conta
        incorporada = None
        if atos:
            incorporada = all(re.search(re.escape(a).replace("no\\ ", r"n[o.]*\s*"), norma["_n"])
                              for a in atos)
        out.append({"id": d["id"], "titulo": d["titulo"], "data": d["data"], "fonte": d["fonte"],
                    "url": d["url"], "caminho": d["caminho"], "atos": atos,
                    "incorporada": incorporada})
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
    a = ap.parse_args(argv)
    docs = carrega(RAIZ)
    if a.alteracoes_de:
        res = alteracoes_de(docs, a.alteracoes_de, a.artigo)
        norma = next(d for d in docs if d["tipo"] == "norma" and d["id"] == a.alteracoes_de)
        print(f"Compilacao de {norma['rotulo']} baixada em {norma['data']}. "
              f"{len(res)} publicacao(oes) que a mencionam:")
        for r in res:
            inc = {True: "ja' incorporada", False: "NAO INCORPORADA a compilacao", None: "sem ato identificado"}
            print(f"- {r['data']} [{r['fonte']}] {r['titulo'][:110]}\n  {inc[r['incorporada']]}"
                  f"{' (' + ', '.join(r['atos']) + ')' if r['atos'] else ''} -> {r['caminho']}")
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
