#!/usr/bin/env python3
"""
Aplica a proposta de atualizacao da camada curada do painel (estado.json:
prazos em destaque, placar de pendencias, linha do tempo).

Por que existe: o estado.json so' era editado a mao e ficou parado desde
17/08/2026 — a prorrogacao da opcao pelo Simples/regime regular do IBS-CBS
(Resolucao CGSN 194, 29/09) saiu e o painel continuou mostrando o prazo
velho. Agora a analise propoe o estado inteiro em dados/estado_proposta.json
e este script decide, de forma deterministica, se aplica:

  {"estado": {...estado.json completo...},
   "mudancas": [{"secao", "tipo", "descricao", "fonte"}]}

Proposta invalida e' descartada e o estado atual fica — o painel nunca
quebra por um JSON mal formado, e nada some sem estar declarado em
`mudancas`. Cada mudanca aplicada vai para dados/estado_mudancas.json, o
historico de alteracoes que o painel mostra.

Uso: python scripts/atualizar_estado.py DATA TURNO   (normalmente chamado
por fechar_analise.py, depois que a analise foi validada)
"""
import datetime, json, re, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATA_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STATUS = ("critical", "serious", "warning", "good")
SECOES = {
    # secao: (campos obrigatorios, campo que identifica o item, campos de data)
    "prazos_destaque": (("rotulo", "data", "status"), "rotulo", ("data",)),
    "pendencias": (("item", "situacao", "status"), "item", ("prazo",)),
    "linha_do_tempo": (("data", "titulo"), "titulo", ("data",)),
}
TIPOS = ("incluido", "alterado", "removido", "concluido")
MAX_HISTORICO = 200


def _data_ok(v):
    if not isinstance(v, str) or not DATA_RX.match(v):
        return False
    try:
        datetime.date.fromisoformat(v)
        return True
    except ValueError:
        return False


def valida(proposta, atual):
    """Lista de erros (vazia = pode aplicar)."""
    if not isinstance(proposta, dict):
        return ["proposta nao e' um objeto JSON"]
    estado, mudancas = proposta.get("estado"), proposta.get("mudancas")
    if not isinstance(estado, dict):
        return ["falta o objeto 'estado'"]
    if not isinstance(mudancas, list) or not mudancas:
        return ["'mudancas' vazio: proposta sem mudanca declarada nao e' aplicada"]
    erros = []
    for i, m in enumerate(mudancas):
        if not isinstance(m, dict):
            erros.append(f"mudanca {i} nao e' objeto"); continue
        if m.get("secao") not in SECOES:
            erros.append(f"mudanca {i}: secao invalida {m.get('secao')!r}")
        if m.get("tipo") not in TIPOS:
            erros.append(f"mudanca {i}: tipo invalido {m.get('tipo')!r}")
        if not str(m.get("descricao") or "").strip():
            erros.append(f"mudanca {i}: sem descricao")
    for secao, (obrig, chave, datas) in SECOES.items():
        itens = estado.get(secao)
        if not isinstance(itens, list):
            erros.append(f"secao {secao} ausente ou nao e' lista"); continue
        for j, it in enumerate(itens):
            if not isinstance(it, dict):
                erros.append(f"{secao}[{j}] nao e' objeto"); continue
            for c in obrig:
                if it.get(c) in (None, ""):
                    erros.append(f"{secao}[{j}] sem '{c}'")
            for c in datas:
                v = it.get(c)
                if v is not None and not _data_ok(v):
                    erros.append(f"{secao}[{j}].{c} data invalida {v!r} (use AAAA-MM-DD)")
            if "status" in it and it["status"] not in STATUS:
                erros.append(f"{secao}[{j}] status invalido {it['status']!r} (use {', '.join(STATUS)})")
        # Item que some sem mudanca declarada na secao: o leitor perderia a
        # informacao sem saber. Renomear conta como alterado.
        antes = {str(x.get(chave)) for x in (atual or {}).get(secao, []) if isinstance(x, dict)}
        depois = {str(x.get(chave)) for x in itens if isinstance(x, dict)}
        sumiram = antes - depois
        declaradas = sum(1 for m in mudancas if isinstance(m, dict)
                         and m.get("secao") == secao and m.get("tipo") != "incluido")
        if len(sumiram) > declaradas:
            erros.append(f"{secao}: {len(sumiram)} item(ns) removido(s)/renomeado(s) "
                         f"sem mudanca declarada: {sorted(sumiram)[:3]}")
    return erros


def completa_linha_do_tempo(estado):
    """Todo prazo em destaque vira marco da linha do tempo, se ainda nao ha
    marco na mesma data. Devolve (estado, mudancas_extras).

    Por que no codigo e nao so' no brief: na revisao de 30/09 a analise pos
    os prazos prorrogados do Simples (15/10, 30/10) nos cards e esqueceu a
    linha do tempo — quem olhava so' a linha nao via o prazo. Regra que o
    leitor espera sempre valer nao pode depender de a IA lembrar.
    """
    linha = list(estado.get("linha_do_tempo") or [])
    datas = {m.get("data") for m in linha if isinstance(m, dict)}
    extras = []
    for p in estado.get("prazos_destaque") or []:
        if not isinstance(p, dict) or not p.get("data") or p["data"] in datas:
            continue
        linha.append({"data": p["data"], "titulo": p.get("rotulo", ""), "detalhe": p.get("nota", "")})
        datas.add(p["data"])
        extras.append({"secao": "linha_do_tempo", "tipo": "incluido",
                       "descricao": f"Prazo \"{p.get('rotulo', '')}\" ({p['data'][8:10]}/{p['data'][5:7]}) "
                                    "incluído na linha do tempo",
                       "fonte": "", "auto": True})
    linha.sort(key=lambda m: m.get("data") or "")
    return dict(estado, linha_do_tempo=linha), extras


def _le(p, padrao):
    return json.loads(p.read_text("utf-8")) if p.exists() else padrao


def aplica(raiz, data, turno):
    prop_path = raiz / "dados" / "estado_proposta.json"
    if not prop_path.exists():
        return {"aplicado": False, "motivo": "sem proposta", "mudancas": []}
    est_path = raiz / "estado.json"
    atual = _le(est_path, {})
    try:
        proposta = json.loads(prop_path.read_text("utf-8"))
    except ValueError as e:
        proposta, erros = None, [f"JSON invalido: {e}"]
    else:
        erros = valida(proposta, atual)
    # apagada em qualquer caso: sobrando, seria reaplicada no proximo ciclo
    prop_path.unlink()
    if erros:
        return {"aplicado": False, "motivo": "; ".join(erros)[:1000], "mudancas": []}

    novo, extras = completa_linha_do_tempo(dict(proposta["estado"]))
    # _leia_me e' instrucao para humanos, nao conteudo: fica o original
    if "_leia_me" in atual:
        novo["_leia_me"] = atual["_leia_me"]
    novo["atualizado_em"] = data
    ordem = ["_leia_me", "atualizado_em", *SECOES]
    novo = {k: novo[k] for k in ordem if k in novo} | {k: v for k, v in novo.items() if k not in ordem}
    est_path.write_text(json.dumps(novo, ensure_ascii=False, indent=1) + "\n", "utf-8")

    em = f"{data}-{turno}"
    mudancas = [{"secao": m["secao"], "tipo": m["tipo"], "descricao": m["descricao"].strip(),
                 "fonte": m.get("fonte") or "", "em": em,
                 **({"auto": True} if m.get("auto") else {})}
                for m in proposta["mudancas"] + extras]
    hist_path = raiz / "dados" / "estado_mudancas.json"
    hist = mudancas + _le(hist_path, [])
    hist_path.write_text(json.dumps(hist[:MAX_HISTORICO], ensure_ascii=False, indent=1), "utf-8")
    return {"aplicado": True, "motivo": "", "mudancas": mudancas}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    r = aplica(RAIZ, *argv)
    print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
