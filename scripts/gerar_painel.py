#!/usr/bin/env python3
"""
Monta docs/index.html e docs/historico.json a partir de:
  estado.json                camada curada (so' os prazos em destaque vao ao painel)
  dados/AAAA-MM-DD.json      status das fontes na ultima varredura
  dados/AAAA-MM-DD-dou.json  status do DOU (workflow proprio) (opcional)
  dados/AAAA-MM-DD-noticias.json  status dos feeds de noticias (opcional)
  dados/novidades.json       so' a data de referencia da ultima varredura
  dados/historico.json       indice acumulado
  dados/triagem.json         veredito da IA por item (opcional)
  dados/analise_status.json  ultima checagem da analise (opcional)
  analises/*.md              analises escritas pelo Claude, uma por dia/turno (opcional)
  analises/resumos/*.json    resumo estruturado de cada edicao (opcional; invalido e' ignorado)

A analise e' opcional por design: o painel precisa ficar em pe' sozinho,
so' com os fatos, mesmo em dia que nenhuma analise foi publicada.

O painel embute so' os ultimos 3 dias do historico; o historico completo vai
para docs/historico.json e e' lido sob demanda (fetch) quando o filtro de data
recua. Assim o index.html nao cresce sem limite com o tempo.
"""
import json, re, datetime, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

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


TEMAS = ("empreendedor", "pessoas", "reforma")
CAMPOS_NOTICIA = ("chave", "tema", "titulo", "fonte", "url", "publicado_em", "linha",
                  "trecho", "por_que_importa", "ideia_post", "origem")


def _txt(v):
    return v.strip() if isinstance(v, str) else ""


def valida_resumo(obj):
    """Resumo estruturado (analises/resumos/<stem>.json) -> dict limpo, ou None.

    Checagem minima e tolerante: precisa ser dict com `em_30_segundos` e
    `noticias` listas. Noticia sem titulo, sem URL http(s) ou com tema fora de
    TEMAS e' descartada; o resto do resumo continua valendo.
    """
    if not isinstance(obj, dict):
        return None
    bullets, noticias = obj.get("em_30_segundos"), obj.get("noticias")
    if not isinstance(bullets, list) or not isinstance(noticias, list):
        return None
    limpas = []
    for n in noticias:
        if not isinstance(n, dict):
            continue
        titulo, url, tema = _txt(n.get("titulo")), _txt(n.get("url")), _txt(n.get("tema"))
        if not titulo or not re.match(r"^https?://", url, re.I) or tema not in TEMAS:
            continue
        nova = {c: _txt(n.get(c)) for c in CAMPOS_NOTICIA}
        nova.update(titulo=titulo, url=url, tema=tema)
        limpas.append({c: v for c, v in nova.items() if v})
    lidas = obj.get("lidas")
    return {
        "manchete": _txt(obj.get("manchete")),
        "em_30_segundos": [b.strip() for b in bullets if isinstance(b, str) and b.strip()],
        "noticias": limpas,
        "lidas": lidas if isinstance(lidas, int) and not isinstance(lidas, bool) and lidas >= 0 else None,
    }


def lista_resumos(pasta):
    """{stem: resumo valido} de analises/resumos/*.json. Nunca levanta."""
    pasta = Path(pasta)
    if not pasta.is_dir():
        return {}
    out = {}
    for p in pasta.glob("*.json"):
        if not id_analise(p.stem):
            continue
        r = valida_resumo(ler_json(p, None))
        if r is None:
            print(f"aviso: resumo invalido ignorado: {p.name}", file=sys.stderr)
            continue
        out[p.stem] = r
    return out


def lista_analises(pasta, pasta_resumos=None):
    """Todas as edicoes validas, da mais recente para a mais antiga
    (data desc; no mesmo dia noturna > matinal > unica).

    Uma edicao existe se houver a analise .md, o resumo .json, ou os dois.
    `resumo_estruturado` e' o resumo validado (ou None)."""
    pasta = Path(pasta)
    resumos = lista_resumos(pasta_resumos if pasta_resumos is not None else pasta / "resumos")
    mds = {}
    if pasta.is_dir():
        for p in pasta.glob("*.md"):
            if id_analise(p.stem):
                try:
                    mds[p.stem] = p.read_text("utf-8")
                except OSError:
                    continue
    out = []
    for stem in set(mds) | set(resumos):
        data, turno = id_analise(stem)
        md = mds.get(stem)
        res = resumos.get(stem)
        out.append({
            "id": stem,
            "data": data,
            "turno": turno,
            "rotulo": _br(data) + ("" if turno == "unica" else f" · {turno}"),
            "resumo": _resumo(md) if md else (res["manchete"] if res else ""),
            "html": md_para_html(md) if md else "",
            "resumo_estruturado": res,
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


def ultimas_mudancas(hist, n=12, secao=None):
    """Ultimas alteracoes da camada curada (dados/estado_mudancas.json, mais
    recente primeiro), para o painel mostrar o que mudou e quando. `secao`
    restringe a uma secao (o painel so' mostra os prazos)."""
    if not isinstance(hist, list):
        return []
    return [m for m in hist if isinstance(m, dict) and m.get("descricao")
            and (secao is None or m.get("secao") == secao)][:n]


def grupo_fonte(arquivo):
    return {"": "web", "-dou": "dou", "-noticias": "noticias"}[arquivo]


def conta_tipos(itens):
    """Faceta do filtro Tipo: quantos itens sao noticia e quantos publicacao oficial."""
    n = sum(1 for i in itens if i.get("tipo") == "noticia")
    return {"noticia": n, "publicacao": len(itens) - n}


def main():
    DOCS.mkdir(parents=True, exist_ok=True)
    estado = ler_json(RAIZ / "estado.json", {})
    if not isinstance(estado, dict):
        estado = {}

    novid = ler_json(DADOS / "novidades.json", {})
    if not isinstance(novid, dict):
        novid = {}
    data_ref = novid.get("data") or datetime.date.today().isoformat()
    status_diario = ler_json(DADOS / "analise_status.json", None)

    fontes = []
    for sufixo in ("", "-dou", "-noticias"):
        dia = ler_json(DADOS / f"{data_ref}{sufixo}.json", {})
        lista = dia.get("fontes") if isinstance(dia, dict) else None
        for f in lista if isinstance(lista, list) else []:
            if isinstance(f, dict) and f.get("fonte"):
                fontes.append({"fonte": f["fonte"], "url": f.get("url"),
                               "erro": f.get("erro"), "total": f.get("total", 0),
                               "grupo": grupo_fonte(sufixo)})

    triagem = ler_json(DADOS / "triagem.json", {})
    if not isinstance(triagem, dict):
        triagem = {}

    hist_bruto = ler_json(DADOS / "historico.json", {})
    if not isinstance(hist_bruto, dict):
        hist_bruto = {}
    historico = ordena_desc(anexa_triagem(hist_bruto, triagem))

    analises = lista_analises(ANALISES)
    inicios = [h["primeira_vez"] for h in historico if h.get("primeira_vez")]

    payload = {
        "data": data_ref,
        "gerado_em": datetime.datetime.now(datetime.timezone.utc)
                     .strftime("%Y-%m-%d %H:%M UTC"),
        "prazos_destaque": estado.get("prazos_destaque", []),
        "fontes": fontes,
        "historico_recente": ultimos_dias(historico),
        "historico_total": len(historico),
        "historico_inicio": min(inicios) if inicios else None,
        # "DOU DO1 (revisar)" e' nome antigo da mesma fonte: o filtro agrupa
        "fontes_historico": sorted({fonte_base(h["fonte"]) for h in historico if h.get("fonte")}),
        "tipos_historico": conta_tipos(historico),
        "analises": analises,
        "status_diario": status_diario,
        "estado_atualizado_em": estado.get("atualizado_em"),
        "estado_mudancas": ultimas_mudancas(ler_json(DADOS / "estado_mudancas.json", []),
                                            n=8, secao="prazos_destaque"),
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
    print(f"docs/index.html gerado — "
          f"{len(fontes)} fonte(s), {len(analises)} edicao(oes) "
          f"({sum(1 for a in analises if a['resumo_estruturado'])} com resumo), "
          f"{len(payload['historico_recente'])}/{len(historico)} itens de historico embutidos")


if __name__ == "__main__":
    main()
