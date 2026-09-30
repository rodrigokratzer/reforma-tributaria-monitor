#!/usr/bin/env python3
"""
Determina a lacuna de cobertura da analise: quais itens de
dados/historico.json ainda nao foram analisados.

A lacuna e' por chave de item (dados/analisados.json), nao por data. Com dois
ciclos no mesmo dia (05h e 17h), uma janela por data ou repetiria na analise
das 17h o que a das 05h ja cobriu, ou perderia o que chegou entre as duas.
A chave e' a propria chave do dicionario do historico (a mesma de
portais.base.chave), entao nao depende de qual coletor achou o item.

Uso: python scripts/lacuna_analise.py [hoje AAAA-MM-DD]
Saida: JSON no stdout.
"""
import json, os, re, sys, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATA_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ANALISE_RX = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:-(matinal|noturna))?$")
TURNOS = ("matinal", "noturna")
# "unica" e' o turno das analises antigas (uma por dia, sem sufixo); no mesmo
# dia, ela vem antes de qualquer turno nomeado
ORDEM_TURNO = {"unica": 0, "matinal": 1, "noturna": 2}


def id_analise(stem):
    """'AAAA-MM-DD' -> (data, 'unica'); 'AAAA-MM-DD-matinal|noturna' ->
    (data, turno); qualquer outro nome -> None."""
    m = ANALISE_RX.match(stem)
    if not m:
        return None
    return m.group(1), m.group(2) or "unica"


def turno_atual(agora=None):
    """Turno pela hora local da execucao: o catch-up do systemd
    (Persistent=true) roda atrasado, e a hora real e' o que diz a que ciclo
    ele pertence. A variavel TURNO sobrescreve (execucao manual)."""
    env = os.environ.get("TURNO", "").strip()
    if env in TURNOS:
        return env
    agora = agora or datetime.datetime.now()
    return "matinal" if agora.hour < 12 else "noturna"


def ultima_analise(raiz):
    analises = raiz / "analises"
    if not analises.exists():
        return None
    ids = [(i, p.stem) for p in analises.glob("*.md") if (i := id_analise(p.stem))]
    if not ids:
        return None
    return max(ids, key=lambda x: (x[0][0], ORDEM_TURNO[x[0][1]]))[1]


def dados_disponiveis(raiz):
    dados = raiz / "dados"
    if not dados.exists():
        return []
    return sorted(p.stem for p in dados.glob("*.json") if DATA_RX.match(p.stem))


def chaves_analisadas(raiz):
    caminho = raiz / "dados" / "analisados.json"
    if not caminho.exists():
        return set()
    return set(json.loads(caminho.read_text("utf-8")).get("chaves", []))


def itens_pendentes(raiz, ate):
    caminho = raiz / "dados" / "historico.json"
    if not caminho.exists():
        return []
    historico = json.loads(caminho.read_text("utf-8"))
    feitos = chaves_analisadas(raiz)
    itens = [{**v, "chave": k} for k, v in historico.items()
             if k not in feitos and v.get("primeira_vez")
             and v["primeira_vez"] <= ate]
    itens.sort(key=lambda i: (i["primeira_vez"], i.get("fonte", "")))
    return itens


def lacuna(raiz, hoje=None):
    hoje = hoje or datetime.date.today().isoformat()
    itens = itens_pendentes(raiz, hoje)
    return {
        "ate": hoje,
        "turno": turno_atual(),
        "ultima_analise": ultima_analise(raiz),
        "dados_de_hoje_disponiveis": hoje in dados_disponiveis(raiz),
        "dias_com_dados_na_janela": sorted({i["primeira_vez"] for i in itens}),
        "itens": itens,
    }


def main():
    hoje = sys.argv[1] if len(sys.argv) > 1 else None
    print(json.dumps(lacuna(RAIZ, hoje), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
