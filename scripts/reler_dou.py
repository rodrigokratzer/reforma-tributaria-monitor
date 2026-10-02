#!/usr/bin/env python3
"""Backfill: texto integral dos itens antigos do DOU, buscado de novo no INLABS.

Os itens de 17 a 24/08/2026 entraram antes da Parte A (sem texto), e os de
28/08 em diante guardaram `texto` cortado em 20.000 caracteres. Este script
baixa de novo as edicoes dessas datas, recalcula a chave de cada materia e,
quando ela bate com um item do historico, grava o texto integral em
dados/textos/<chave>.txt. Nao escreve dados/leituras.json (o unico escritor
e' ler_textos.py, que reconhece o arquivo novo na proxima execucao).

Materia que nao casa (o titulo foi montado diferente na epoca) e' listada no
fim, para conferencia manual. Uso: INLABS_EMAIL=... INLABS_SENHA=... python3 scripts/reler_dou.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dou
import textos
from portais.base import chave

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"


def alvos(dados):
    hist = json.loads((dados / "historico.json").read_text("utf-8"))
    p = dados / "leituras.json"
    leit = json.loads(p.read_text("utf-8")) if p.exists() else {}
    out = {}
    for k, it in hist.items():
        if not (it.get("fonte") or "").startswith("DOU"):
            continue
        if textos.existe(dados, k) and leit.get(k, {}).get("origem") != "coleta_cortada":
            continue
        out[k] = it
    return out


def main():
    email, senha = os.environ.get("INLABS_EMAIL"), os.environ.get("INLABS_SENHA")
    if not email or not senha:
        print("defina INLABS_EMAIL e INLABS_SENHA", file=sys.stderr)
        return 2
    pend = alvos(DADOS)
    dias = sorted({it.get("data") or it["primeira_vez"] for it in pend.values()})
    print(f"{len(pend)} item(ns) do DOU em {len(dias)} dia(s): {', '.join(dias)}", file=sys.stderr)
    itens, diag = dou.coleta(dias, email, senha)
    print(f"INLABS: {diag.get('lidas')} materias lidas; sem edicao: {diag.get('sem_edicao')}; "
          f"erros: {diag.get('erros')}", file=sys.stderr)
    achados = 0
    for it in itens:
        k = chave(it)
        integral = it.get("texto_integral") or ""
        if k in pend and integral.strip():
            textos.grava(DADOS, k, integral)
            pend.pop(k)
            achados += 1
    print(f"{achados} texto(s) gravado(s); {len(pend)} sem correspondencia:", file=sys.stderr)
    for k, it in pend.items():
        print(f"  {k} {it.get('data')} {(it.get('titulo') or '')[:90]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
