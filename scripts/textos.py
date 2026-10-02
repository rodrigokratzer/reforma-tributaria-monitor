#!/usr/bin/env python3
"""Texto integral das publicacoes: um arquivo por item, dados/textos/<chave>.txt.

Fica fora do historico.json de proposito:
  * sem corte de tamanho — o Regulamento do IBS tem ~965 mil caracteres, e o
    corte de 20.000 que o DOU usava no historico perderia quase tudo;
  * sem condicao de corrida — cada arquivo e' de uma chave so'; dois
    escritores (coletor e raia de leitura) nunca disputam o mesmo arquivo
    ao mesmo tempo, e a gravacao e' atomica (tmp + replace).

As constantes de tentativa ficam aqui porque ler_textos.py (quem tenta) e
lacuna_analise.py (quem espera) precisam concordar sobre elas.
"""
from pathlib import Path

PASTA = "textos"
MAX_TENTATIVAS = 4      # 2 ciclos por dia -> 2 dias tentando antes de desistir
DIAS_SEM_LEITURA = 3    # rede de seguranca: raia de leitura parada nao segura a analise


def caminho(dados, chave):
    return Path(dados) / PASTA / f"{chave}.txt"


def existe(dados, chave):
    return caminho(dados, chave).exists()


def grava(dados, chave, texto):
    p = caminho(dados, chave)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(texto, "utf-8")
    tmp.replace(p)
    return p


def le(dados, chave):
    p = caminho(dados, chave)
    return p.read_text("utf-8") if p.exists() else None
