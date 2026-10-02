#!/usr/bin/env python3
"""Cobertura de texto integral por fonte: quanto do historico a analise pode
ler literalmente. Uso: python3 scripts/cobertura_textos.py"""
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textos

RAIZ = Path(__file__).resolve().parent.parent


def cobertura(raiz):
    dados = raiz / "dados"
    hist = json.loads((dados / "historico.json").read_text("utf-8"))
    p = dados / "leituras.json"
    leit = json.loads(p.read_text("utf-8")) if p.exists() else {}
    c = collections.defaultdict(collections.Counter)
    for k, it in hist.items():
        f = c[it.get("fonte") or "?"]
        f["total"] += 1
        meta = leit.get(k)
        if textos.existe(dados, k) or (it.get("texto") or "").strip():
            f["com_texto"] += 1
            if meta and "ocr" in (meta.get("origem") or ""):
                f["ocr"] += 1
            if meta and meta.get("status") == "parcial":
                f["parcial"] += 1
        elif meta is None:
            f["sem_tentativa"] += 1
        else:
            f[meta.get("status") or "?"] += 1
    return c


def main():
    c = cobertura(RAIZ)
    cols = ("total", "com_texto", "ocr", "parcial", "falhou", "desistiu", "sem_tentativa")
    print(f"{'fonte':40}" + "".join(f"{x:>14}" for x in cols))
    tot = collections.Counter()
    for f in sorted(c):
        tot.update(c[f])
        print(f"{f[:40]:40}" + "".join(f"{c[f][x]:>14}" for x in cols))
    print(f"{'TOTAL':40}" + "".join(f"{tot[x]:>14}" for x in cols))
    return 0


if __name__ == "__main__":
    sys.exit(main())
