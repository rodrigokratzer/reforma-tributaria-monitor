#!/usr/bin/env python3
"""
Determina a lacuna de cobertura da analise: quais itens de
dados/historico.json ainda nao foram analisados.

A lacuna e' por chave de item (dados/analisados.json), nao por data. Com dois
ciclos no mesmo dia (05h e 17h), uma janela por data ou repetiria na analise
das 17h o que a das 05h ja cobriu, ou perderia o que chegou entre as duas.
A chave e' a propria chave do dicionario do historico (a mesma de
portais.base.chave), entao nao depende de qual coletor achou o item.

Itens ainda nao lidos pela raia de leitura (ler_textos.py) ficam de fora por
ate' textos.DIAS_SEM_LEITURA dias e aparecem em "aguardando_leitura"; como nao
estao em "itens", fechar_analise.py nao os marca e eles voltam no proximo ciclo.

Uso: python scripts/lacuna_analise.py [hoje AAAA-MM-DD]
Saida: JSON no stdout.
"""
import json, os, re, sys, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textos

# Texto que vai inline na lacuna. Acima disto o item traz texto_truncado e
# texto_arquivo, e o brief manda ler o arquivo (o Regulamento do IBS tem
# ~965 mil caracteres; inline estouraria o contexto da analise).
TETO_LACUNA = 60000

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


def _leituras(raiz):
    p = raiz / "dados" / "leituras.json"
    return json.loads(p.read_text("utf-8")) if p.exists() else {}


def aguardando_leitura(item, meta, tem_texto, hoje):
    """A analise espera a raia de leitura, para nao ver sem texto um item que
    so' nao foi lido ainda (OCR na fila, site fora do ar por um ciclo).

    Nunca espera: item com texto, item do DOU (texto vem do INLABS) e item
    em que a leitura desistiu. Rede de seguranca: passados DIAS_SEM_LEITURA
    dias, libera de qualquer jeito — raia parada nao pode travar a analise.
    """
    if tem_texto or (item.get("fonte") or "").startswith("DOU"):
        return False
    if meta and meta.get("status") == "desistiu":
        return False
    try:
        dias = (datetime.date.fromisoformat(hoje)
                - datetime.date.fromisoformat(item["primeira_vez"])).days
    except (KeyError, ValueError):
        return False
    return dias < textos.DIAS_SEM_LEITURA


def _anexa_texto(dados, item, meta):
    k = item["chave"]
    t = textos.le(dados, k)
    item["texto_arquivo"] = f"dados/textos/{k}.txt" if t is not None else None
    if t is None:
        t = item.get("texto") or ""
    item["texto"] = t[:TETO_LACUNA]
    item["texto_chars"] = len(t)
    item["texto_truncado"] = len(t) > TETO_LACUNA
    item["texto_origem"] = (meta or {}).get("origem") or ("coleta" if t else None)
    if meta and (not t or meta.get("anexos_falhos")):
        item["leitura"] = {"status": meta.get("status"), "erro": meta.get("erro"),
                           "anexos_falhos": meta.get("anexos_falhos", [])}
    return bool(t)


def lacuna(raiz, hoje=None):
    hoje = hoje or datetime.date.today().isoformat()
    leituras = _leituras(raiz)
    itens, aguardando = [], []
    for i in itens_pendentes(raiz, hoje):
        meta = leituras.get(i["chave"])
        tem = _anexa_texto(raiz / "dados", i, meta)
        if aguardando_leitura(i, meta, tem, hoje):
            aguardando.append({"chave": i["chave"], "fonte": i.get("fonte"),
                               "titulo": i.get("titulo"),
                               "status": (meta or {}).get("status", "nao_tentado")})
        else:
            itens.append(i)
    return {
        "ate": hoje,
        "turno": turno_atual(),
        "ultima_analise": ultima_analise(raiz),
        "dados_de_hoje_disponiveis": hoje in dados_disponiveis(raiz),
        "dias_com_dados_na_janela": sorted({i["primeira_vez"] for i in itens}),
        "itens": itens,
        "aguardando_leitura": aguardando,
    }


def main():
    hoje = sys.argv[1] if len(sys.argv) > 1 else None
    print(json.dumps(lacuna(RAIZ, hoje), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
