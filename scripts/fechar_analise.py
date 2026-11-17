#!/usr/bin/env python3
"""
Fecha uma execucao da analise: confere que ela de fato produziu saida e so'
entao marca os itens da lacuna como analisados e incorpora a triagem.

A ordem importa. Se o Claude bateu no limite de uso ou recusou, nao ha
analises/DATA-TURNO.md (ou o status e' de outra execucao); marcar os itens
nesse caso faria eles sumirem da proxima lacuna sem nunca terem sido lidos.
Por isso a validacao vem antes de qualquer escrita, e e' deterministica: o
Claude so' escreve arquivos, quem decide o que conta como feito e' este script.

Uso: python scripts/fechar_analise.py DATA TURNO ARQUIVO_LACUNA_JSON
     (ARQUIVO_LACUNA_JSON e' a saida de lacuna_analise.py salva pelo wrapper;
     as chaves vem de itens[].chave)
Sai 1 se a analise nao pode ser fechada.

Noticia (tipo "noticia") da lacuna que a analise nao escolheu fica sem
veredito: aqui ela e' fechada como ruido. O resumo estruturado
(analises/resumos/DATA-TURNO.json) e' opcional: se vier torto, so' avisa no
stderr -- a analise da reforma continua valendo e o painel pula o resumo.
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import atualizar_estado

RAIZ = Path(__file__).resolve().parent.parent
VEREDITOS = ("relevante", "contexto", "ruido")
TEMAS = ("empreendedor", "pessoas", "reforma")
ORIGENS = ("rss", "busca", "oficial")
MOTIVO_NAO_SELECIONADA = "não selecionada para o resumo"


def _le_json(caminho, padrao):
    if not caminho.exists():
        return padrao
    return json.loads(caminho.read_text("utf-8"))


def _grava_json(caminho, dados):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=1), "utf-8")


def valida(raiz, data, turno):
    """Devolve None se a execucao DATA/TURNO produziu saida, ou o motivo."""
    md = raiz / "analises" / f"{data}-{turno}.md"
    if not md.exists() or not md.read_text("utf-8").strip():
        return f"analise {md.name} ausente ou vazia"
    try:
        status = _le_json(raiz / "dados" / "analise_status.json", None)
    except ValueError:
        return "analise_status.json invalido"
    if not isinstance(status, dict):
        return "analise_status.json ausente"
    # status de outra execucao = o Claude nao chegou a atualizar o status desta
    if status.get("data") != data or status.get("turno") != turno:
        return (f"analise_status.json e' de outra execucao (data/turno "
                f"{status.get('data')}/{status.get('turno')}, "
                f"esperado {data}/{turno})")
    return None


def le_triagem_pendente(caminho, existentes):
    """Linhas validas de triagem_pendente.json. Linha ruim (veredito fora da
    lista, chave que nao existe no historico, formato errado) e' descartada
    sozinha — um erro do Claude em um item nao pode custar a triagem dos
    outros. Arquivo ilegivel inteiro vale como vazio."""
    try:
        linhas = _le_json(caminho, [])
    except ValueError:
        print("aviso: triagem_pendente.json ilegivel, ignorado", file=sys.stderr)
        return []
    if not isinstance(linhas, list):
        print("aviso: triagem_pendente.json nao e' lista, ignorado", file=sys.stderr)
        return []
    validas = []
    for ln in linhas:
        if (isinstance(ln, dict) and ln.get("chave") in existentes
                and ln.get("veredito") in VEREDITOS):
            motivo = ln.get("motivo")
            validas.append((ln["chave"], ln["veredito"],
                            motivo if isinstance(motivo, str) else ""))
        else:
            print(f"aviso: linha de triagem ignorada: {ln!r}"[:300], file=sys.stderr)
    return validas


def _texto(v):
    return isinstance(v, str) and bool(v.strip())


def valida_resumo(resumo, data=None, turno=None):
    """Erros do resumo estruturado (contrato 2 do desenho de 17/11/2026);
    lista vazia = valido. Com data/turno, confere que e' desta execucao.
    Usado tambem por notificar.py (e pode ser pelo painel)."""
    if not isinstance(resumo, dict):
        return ["resumo nao e' objeto JSON"]
    erros = []
    if data is not None and resumo.get("data") != data:
        erros.append(f"data {resumo.get('data')!r} difere de {data!r}")
    if turno is not None and resumo.get("turno") != turno:
        erros.append(f"turno {resumo.get('turno')!r} difere de {turno!r}")
    if not _texto(resumo.get("manchete")):
        erros.append("manchete ausente ou vazia")
    linhas = resumo.get("em_30_segundos")
    if (not isinstance(linhas, list) or not linhas
            or not all(_texto(x) for x in linhas)):
        erros.append("em_30_segundos precisa ser lista nao vazia de textos")
    noticias = resumo.get("noticias")
    if not isinstance(noticias, list):
        erros.append("noticias precisa ser lista")
        noticias = []
    for i, n in enumerate(noticias):
        if not isinstance(n, dict):
            erros.append(f"noticias[{i}] nao e' objeto")
            continue
        if n.get("tema") not in TEMAS:
            erros.append(f"noticias[{i}].tema {n.get('tema')!r} fora de {TEMAS}")
        for campo in ("titulo", "url", "linha"):
            if not _texto(n.get(campo)):
                erros.append(f"noticias[{i}].{campo} ausente ou vazio")
        if "origem" in n and n["origem"] not in ORIGENS:
            erros.append(f"noticias[{i}].origem {n.get('origem')!r} fora de {ORIGENS}")
    lidas = resumo.get("lidas")
    if lidas is not None and (isinstance(lidas, bool) or not isinstance(lidas, int)):
        erros.append("lidas precisa ser inteiro")
    return erros


def confere_resumo(raiz, data, turno):
    """Le analises/resumos/DATA-TURNO.json. Devolve None se o arquivo nao
    existe, senao a lista de erros (vazia = ok). Nunca levanta: o resumo e'
    acessorio, e o arquivo invalido fica onde esta' (o painel o pula)."""
    caminho = raiz / "analises" / "resumos" / f"{data}-{turno}.json"
    if not caminho.exists():
        return None
    try:
        resumo = json.loads(caminho.read_text("utf-8"))
    except (OSError, ValueError) as e:
        return [f"{caminho.name} ilegivel: {e}"]
    return valida_resumo(resumo, data, turno)


def fechar(raiz, data, turno, chaves, noticias=()):
    motivo = valida(raiz, data, turno)
    if motivo:
        return {"ok": False, "motivo": motivo, "triados": 0}

    dados = raiz / "dados"
    arq_analisados = dados / "analisados.json"
    feitos = set(_le_json(arq_analisados, {}).get("chaves", []))
    _grava_json(arq_analisados, {"chaves": sorted(feitos | set(chaves))})

    existentes = _le_json(dados / "historico.json", {})
    pendente = dados / "triagem_pendente.json"
    arq_triagem = dados / "triagem.json"
    triagem = _le_json(arq_triagem, {})
    validas = le_triagem_pendente(pendente, existentes)
    julgadas = set()
    for chave, veredito, motivo_item in validas:
        triagem[chave] = {"veredito": veredito, "motivo": motivo_item,
                          "em": f"{data}-{turno}"}
        julgadas.add(chave)
    # noticia = marcada assim na lacuna ou no historico
    eh_noticia = set(noticias) | {c for c in chaves
                                  if isinstance(existentes.get(c), dict)
                                  and existentes[c].get("tipo") == "noticia"}
    auto = 0
    for chave in sorted(eh_noticia & set(chaves) - julgadas):
        triagem[chave] = {"veredito": "ruido", "motivo": MOTIVO_NAO_SELECIONADA,
                          "em": f"{data}-{turno}"}
        auto += 1
    _grava_json(arq_triagem, dict(sorted(triagem.items())))
    # apagado mesmo se ruim: sobrando, seria reaproveitado pela proxima
    # execucao com o carimbo errado
    if pendente.exists():
        pendente.unlink()

    # Camada curada do painel (prazos, pendencias, linha do tempo): so' depois
    # da analise validada. Proposta ruim e' descartada sem derrubar o
    # fechamento — a analise e a triagem continuam valendo.
    painel = atualizar_estado.aplica(raiz, data, turno)
    if painel["aplicado"]:
        st_path = dados / "analise_status.json"
        status = _le_json(st_path, {})
        # o marco incluido automaticamente (prazo -> linha do tempo) repete o
        # que a mudanca do prazo ja' diz: fica fora do alerta
        status["painel_atualizado"] = [m["descricao"] for m in painel["mudancas"]
                                       if not m.get("auto")]
        _grava_json(st_path, status)
    elif painel["motivo"] != "sem proposta":
        print(f"aviso: proposta de atualizacao do painel descartada: {painel['motivo']}",
              file=sys.stderr)

    erros_resumo = confere_resumo(raiz, data, turno)
    if erros_resumo is None:
        print(f"aviso: resumo {data}-{turno} ausente (painel usa a analise .md)",
              file=sys.stderr)
    for erro in erros_resumo or []:
        print(f"aviso: resumo {data}-{turno} invalido: {erro}"[:300], file=sys.stderr)
    situacao_resumo = ("ausente" if erros_resumo is None
                       else "invalido" if erros_resumo else "ok")
    return {"ok": True, "motivo": "", "triados": len(validas),
            "noticias_ruido": auto, "resumo": situacao_resumo, "painel": painel}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    data, turno, arq_lacuna = argv
    lac = json.loads(Path(arq_lacuna).read_text("utf-8"))
    chaves = [i["chave"] for i in lac.get("itens", [])]
    noticias = [i["chave"] for i in lac.get("itens", []) if i.get("tipo") == "noticia"]
    r = fechar(RAIZ, data, turno, chaves, noticias)
    print(json.dumps(r, ensure_ascii=False))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
