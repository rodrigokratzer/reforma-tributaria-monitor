#!/usr/bin/env python3
"""
Determina a lacuna de cobertura da analise diaria: quais dias desde a
ultima analises/AAAA-MM-DD.md ja publicada ainda nao tem analise, e quais
itens de dados/historico.json caem nessa janela.

Uso: python scripts/lacuna_analise.py [hoje AAAA-MM-DD]
Saida: JSON no stdout.
"""
import json, re, sys, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATA_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def data_ultima_analise(raiz):
    analises = raiz / "analises"
    if not analises.exists():
        return None
    datas = sorted(p.stem for p in analises.glob("*.md") if DATA_RX.match(p.stem))
    return datas[-1] if datas else None


def dados_disponiveis(raiz):
    dados = raiz / "dados"
    if not dados.exists():
        return []
    return sorted(p.stem for p in dados.glob("*.json") if DATA_RX.match(p.stem))


def itens_da_lacuna(raiz, desde, ate):
    caminho = raiz / "dados" / "historico.json"
    if not caminho.exists():
        return []
    historico = json.loads(caminho.read_text("utf-8"))
    itens = [v for v in historico.values()
             if v.get("primeira_vez") and
             (desde is None or v["primeira_vez"] > desde) and
             v["primeira_vez"] <= ate]
    itens.sort(key=lambda i: (i["primeira_vez"], i.get("fonte", "")))
    return itens


def lacuna(raiz, hoje=None):
    hoje = hoje or datetime.date.today().isoformat()
    desde = data_ultima_analise(raiz)
    disponiveis = dados_disponiveis(raiz)
    return {
        "desde": desde,
        "ate": hoje,
        "dados_de_hoje_disponiveis": hoje in disponiveis,
        "dias_com_dados_na_janela": [d for d in disponiveis
                                      if (desde is None or d > desde) and d <= hoje],
        "itens": itens_da_lacuna(raiz, desde, hoje),
    }


def main():
    hoje = sys.argv[1] if len(sys.argv) > 1 else None
    print(json.dumps(lacuna(RAIZ, hoje), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
