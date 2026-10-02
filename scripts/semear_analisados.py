#!/usr/bin/env python3
"""Marca como analisados os itens antigos de fontes recem-incluidas.

Uma fonte nova (ex.: listas de NTs do Portal NF-e) traz anos de historico na
primeira coleta. Sem isto, tudo cairia de uma vez na proxima analise. Os
itens semeados continuam no historico e continuam sendo lidos pela raia de
leitura — so' nao vao para a analise. Itens com data nos ultimos --dias
ficam de fora da semeadura e sao analisados normalmente.

Uso (rode sem --aplicar primeiro e confira a lista):
  python3 scripts/semear_analisados.py --fonte "Portal NF-e - Notas Tecnicas" [--fonte ...] [--dias 30] [--aplicar]
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _le(p, padrao):
    return json.loads(p.read_text("utf-8")) if p.exists() else padrao


def candidatas(raiz, fontes, hoje, dias):
    hist = _le(raiz / "dados" / "historico.json", {})
    feitas = set(_le(raiz / "dados" / "analisados.json", {}).get("chaves", []))
    corte = (datetime.date.fromisoformat(hoje) - datetime.timedelta(days=dias)).isoformat()
    return [k for k, it in hist.items()
            if it.get("fonte") in fontes and k not in feitas
            and (not it.get("data") or it["data"] < corte)]


def main(argv=None, raiz=RAIZ, hoje=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonte", action="append", required=True)
    ap.add_argument("--dias", type=int, default=30)
    ap.add_argument("--aplicar", action="store_true")
    a = ap.parse_args(argv)
    hoje = hoje or datetime.date.today().isoformat()
    ks = candidatas(raiz, set(a.fonte), hoje, a.dias)
    hist = _le(raiz / "dados" / "historico.json", {})
    for k in sorted(ks, key=lambda k: hist[k].get("data") or ""):
        print(f"{hist[k].get('data') or '----------'}  {hist[k].get('fonte')[:30]:30}  "
              f"{(hist[k].get('titulo') or '')[:80]}")
    print(f"{len(ks)} item(ns) {'marcados' if a.aplicar else 'seriam marcados (use --aplicar)'}",
          file=sys.stderr)
    if a.aplicar and ks:
        arq = raiz / "dados" / "analisados.json"
        feitas = set(_le(arq, {}).get("chaves", []))
        arq.write_text(json.dumps({"chaves": sorted(feitas | set(ks))}, ensure_ascii=False, indent=1),
                       "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
