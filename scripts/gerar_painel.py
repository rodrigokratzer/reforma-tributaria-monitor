#!/usr/bin/env python3
"""
Monta docs/index.html e docs/historico.json a partir de:
  estado.json                camada curada (prazos, pendencias, linha do tempo)
  dados/AAAA-MM-DD.json      status das fontes na ultima varredura
  dados/AAAA-MM-DD-dou.json  status do DOU (workflow proprio) (opcional)
  dados/novidades.json       o que apareceu pela primeira vez (16 portais)
  dados/novidades_dou.json   o que apareceu pela primeira vez (DOU) (opcional)
  dados/historico.json       indice acumulado
  dados/triagem.json         veredito da IA por item (opcional)
  dados/analise_status.json  ultima checagem da analise (opcional)
  analises/*.md              analises escritas pelo Claude, uma por dia/turno (opcional)

A analise e' opcional por design: o painel precisa ficar em pe' sozinho,
so' com os fatos, mesmo em dia que nenhuma analise foi publicada.

O painel embute so' os ultimos 3 dias do historico; o historico completo vai
para docs/historico.json e e' lido sob demanda (fetch) quando o filtro de data
recua. Assim o index.html nao cresce sem limite com o tempo.
"""
import json, re, datetime, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portais.base import chave as chave_item

RAIZ = Path(__file__).resolve().parent.parent
DADOS, ANALISES, DOCS = RAIZ / "dados", RAIZ / "analises", RAIZ / "docs"
TEMPLATE = Path(__file__).resolve().parent / "painel_template.html"

DIAS_EMBUTIDOS = 3

# Parse local de proposito (e nao import de lacuna_analise): o painel nao pode
# depender do script da raia da analise para ficar em pe'.
RE_STEM = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:-(matinal|noturna))?$")
ORDEM_TURNO = {"unica": 0, "matinal": 1, "noturna": 2}


def ler_json(p, padrao):
    try:
        return json.loads(Path(p).read_text("utf-8"))
    except Exception:
        return padrao


def id_analise(stem):
    """AAAA-MM-DD -> (data, "unica"); AAAA-MM-DD-matinal|noturna -> (data, turno).

    Qualquer outro nome (README, turno desconhecido, data invalida) -> None,
    para que um arquivo solto em analises/ nao vire entrada no seletor.
    """
    m = RE_STEM.match(stem)
    if not m:
        return None
    try:
        datetime.date.fromisoformat(m.group(1))
    except ValueError:
        return None
    return m.group(1), m.group(2) or "unica"


def _sem_texto(it):
    """Tira o campo `texto` (corpo integral do artigo).

    O `texto` existe so' para a analise ler direto de dados/historico.json —
    o painel publico nunca o renderiza. Deixa-lo no payload so' incha o arquivo.
    """
    return {k: v for k, v in it.items() if k != "texto"}


def fonte_base(nome):
    return re.sub(r"\s*\((revisar|forte)\)\s*$", "", nome or "")


def md_para_html(texto):
    try:
        import markdown
        return markdown.markdown(texto, extensions=["extra", "sane_lists"])
    except ImportError:
        # fallback minimo: paragrafos, sem depender do pacote
        blocos = [b.strip() for b in texto.split("\n\n") if b.strip()]
        return "".join(f"<p>{b}</p>" for b in blocos)


def _resumo(md):
    """Primeira linha nao vazia, se for toda em negrito (padrao do brief)."""
    for linha in md.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        if linha.startswith("**") and linha.endswith("**") and len(linha) > 4:
            return linha[2:-2].strip()
        return ""
    return ""


def _br(data):
    a, m, d = data.split("-")
    return f"{d}/{m}/{a}"


def lista_analises(pasta):
    """Todas as analises validas, da mais recente para a mais antiga
    (data desc; no mesmo dia noturna > matinal > unica)."""
    pasta = Path(pasta)
    if not pasta.is_dir():
        return []
    out = []
    for p in pasta.glob("*.md"):
        ident = id_analise(p.stem)
        if not ident:
            continue
        data, turno = ident
        md = p.read_text("utf-8")
        out.append({
            "id": p.stem,
            "data": data,
            "turno": turno,
            "rotulo": _br(data) + ("" if turno == "unica" else f" · {turno}"),
            "resumo": _resumo(md),
            "html": md_para_html(md),
        })
    out.sort(key=lambda a: (a["data"], ORDEM_TURNO[a["turno"]]), reverse=True)
    return out


def anexa_triagem(itens, triagem):
    """{chave: item} -> lista de itens sem `texto`, com `chave` e `triagem`
    (dict do veredito ou None). Nao muta a entrada."""
    out = []
    for k, it in itens.items():
        novo = _sem_texto(it)
        novo["chave"] = k
        novo["triagem"] = triagem.get(k)
        out.append(novo)
    return out


def ordena_desc(itens):
    return sorted(itens, key=lambda h: (h.get("primeira_vez") or "", h.get("data") or "",
                                        h.get("titulo") or ""), reverse=True)


def ultimos_dias(itens, n=DIAS_EMBUTIDOS):
    """Itens cuja `primeira_vez` esta' entre as n datas distintas mais recentes."""
    datas = sorted({i.get("primeira_vez") for i in itens if i.get("primeira_vez")}, reverse=True)[:n]
    alvo = set(datas)
    return [i for i in itens if i.get("primeira_vez") in alvo]


def ultimas_mudancas(hist, n=12):
    """Ultimas alteracoes da camada curada (dados/estado_mudancas.json, mais
    recente primeiro), para o painel mostrar o que mudou e quando."""
    if not isinstance(hist, list):
        return []
    return [m for m in hist if isinstance(m, dict) and m.get("descricao")][:n]


def main():
    DOCS.mkdir(parents=True, exist_ok=True)
    estado = ler_json(RAIZ / "estado.json", {})

    novid = ler_json(DADOS / "novidades.json", {"itens": [], "data": None})
    data_ref = novid.get("data") or datetime.date.today().isoformat()
    status_diario = ler_json(DADOS / "analise_status.json", None)

    dia = ler_json(DADOS / f"{data_ref}.json", {"fontes": []})
    dia_dou = ler_json(DADOS / f"{data_ref}-dou.json", {"fontes": []})
    fontes = [{"fonte": f["fonte"], "url": f["url"],
               "erro": f.get("erro"), "total": f.get("total", 0)}
              for f in dia.get("fontes", []) + dia_dou.get("fontes", [])]

    novid_dou = ler_json(DADOS / "novidades_dou.json", {"itens": []})
    triagem = ler_json(DADOS / "triagem.json", {})
    if not isinstance(triagem, dict):
        triagem = {}

    hist_bruto = ler_json(DADOS / "historico.json", {})
    if not isinstance(hist_bruto, dict):
        hist_bruto = {}
    historico = ordena_desc(anexa_triagem(hist_bruto, triagem))

    # As novidades nao trazem a chave; casa pelo historico (url+titulo) e so'
    # recalcula o hash se o item por acaso nao estiver la'.
    por_url_tit = {(h.get("url"), h.get("titulo")): h["chave"] for h in historico}
    novidades = []
    for it in novid.get("itens", []) + novid_dou.get("itens", []):
        novo = _sem_texto(it)
        k = por_url_tit.get((it.get("url"), it.get("titulo"))) or chave_item(it)
        novo["chave"] = k
        novo["triagem"] = triagem.get(k)
        novidades.append(novo)

    analises = lista_analises(ANALISES)
    inicios = [h["primeira_vez"] for h in historico if h.get("primeira_vez")]

    payload = {
        "data": data_ref,
        "gerado_em": datetime.datetime.now(datetime.timezone.utc)
                     .strftime("%Y-%m-%d %H:%M UTC"),
        "prazos_destaque": estado.get("prazos_destaque", []),
        "pendencias": estado.get("pendencias", []),
        "linha_do_tempo": estado.get("linha_do_tempo", []),
        "novidades": novidades,
        "fontes": fontes,
        "historico_recente": ultimos_dias(historico),
        "historico_total": len(historico),
        "historico_inicio": min(inicios) if inicios else None,
        # "DOU DO1 (revisar)" e' nome antigo da mesma fonte: o filtro agrupa
        "fontes_historico": sorted({fonte_base(h["fonte"]) for h in historico if h.get("fonte")}),
        "analises": analises,
        "status_diario": status_diario,
        "estado_atualizado_em": estado.get("atualizado_em"),
        "estado_mudancas": ultimas_mudancas(ler_json(DADOS / "estado_mudancas.json", [])),
    }

    tpl = TEMPLATE.read_text("utf-8")
    if "/*__DADOS__*/null" not in tpl:
        sys.exit("Template sem o marcador /*__DADOS__*/null — abortando.")
    html = tpl.replace("/*__DADOS__*/null",
                       json.dumps(payload, ensure_ascii=False)
                           .replace("</script", "<\\/script"))

    (DOCS / "index.html").write_text(html, "utf-8")
    (DOCS / "historico.json").write_text(
        json.dumps(historico, ensure_ascii=False, separators=(",", ":")), "utf-8")
    (DOCS / ".nojekyll").write_text("", "utf-8")
    print(f"docs/index.html gerado — {len(novidades)} novidade(s), "
          f"{len(fontes)} fonte(s), {len(analises)} analise(s), "
          f"{len(payload['historico_recente'])}/{len(historico)} itens de historico embutidos")


if __name__ == "__main__":
    main()
