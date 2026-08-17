#!/usr/bin/env python3
"""
Varredura das fontes oficiais da reforma tributaria do consumo.

Roda no GitHub Actions (runner com acesso normal a .gov.br) e grava:
  dados/AAAA-MM-DD.json  -> tudo que foi visto na execucao do dia
  dados/historico.json   -> indice acumulado {chave: {primeira_vez, titulo, url, fonte}}
  dados/novidades.json   -> so o que apareceu pela primeira vez nesta execucao

A deteccao de novidade e' por comparacao com o historico, nao por data:
paginas oficiais frequentemente publicam com data errada (o CGIBS ja listou
um ato de 2026 como 2025), entao "nunca vi este link antes" e' criterio mais
confiavel do que "a data e' recente".

Uso:  python scripts/varredura.py
"""
import json, os, re, sys, datetime, hashlib
from pathlib import Path
from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"
DADOS.mkdir(exist_ok=True)

# (nome, url, precisa_de_js)
FONTES = [
    ("CGIBS - Noticias",             "https://www.cgibs.gov.br/noticias", True),
    ("CGIBS - Leis",                 "https://www.cgibs.gov.br/leis", True),
    ("CGIBS - Resolucoes",           "https://www.cgibs.gov.br/resolucoes", True),
    ("CGIBS - Regulamentos",         "https://www.cgibs.gov.br/regulamentos", True),
    ("CGIBS - Portarias",            "https://www.cgibs.gov.br/portarias", True),
    ("CGIBS - Atos Conjuntos",       "https://www.cgibs.gov.br/atos-conjuntos", True),
    ("CGIBS - Relatorios",           "https://www.cgibs.gov.br/relatorios", True),
    ("CGIBS - Atos Tecnicos Conj.",  "https://www.cgibs.gov.br/atos-tecnicos-conjuntos", True),
    ("RFB - Noticias 2026",          "https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2026", False),
    ("RFB - Reforma do Consumo",     "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/acoes-e-programas/programas-e-atividades/reforma-tributaria-do-consumo/noticias", False),
    ("Portal NF-e - Informes/NTs",   "https://www.nfe.fazenda.gov.br/portal/informe.aspx?ehCTG=false", False),
    ("Portal DF-e SVRS - Noticias",  "https://dfe-portal.svrs.rs.gov.br/Nfe/Noticias", False),
]

# Termos que qualificam um item como relevante para a reforma do consumo.
RELEVANTE = re.compile(
    r"\b(ibs|cbs|imposto seletivo|\bis\b|reforma tribut|lc\s*214|lc\s*227|ec\s*132|"
    r"cgibs|split payment|nfs-?e|nf-?e|dere|df-?e|nota t[ée]cnica|cr[ée]dito presumido|"
    r"regime espec[íi]fico|conformidade|al[íi]quota|cashback|simples nacional)\b",
    re.I,
)

MESES = {"janeiro":1,"fevereiro":2,"marco":3,"março":3,"abril":4,"maio":5,"junho":6,
         "julho":7,"agosto":8,"setembro":9,"outubro":10,"novembro":11,"dezembro":12}
RE_NUM = re.compile(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})")
RE_EXT = re.compile(r"(\d{1,2})\s+DE\s+([A-Za-zÇçÃãÉé]+)\s+DE\s+(\d{4})", re.I)
RE_PASTA = re.compile(r"/(20\d{2})(0[1-9]|1[0-2])/")   # .../upload/arquivos/202608/...


def extrai_data(texto, url=""):
    """Data declarada no titulo. Devolve (iso, origem) ou (None, None)."""
    for rx, conv in ((RE_NUM, lambda m: (int(m.group(3)), int(m.group(2)), int(m.group(1)))),
                     (RE_EXT, lambda m: (int(m.group(3)), MESES.get(m.group(2).lower(), 0), int(m.group(1))))):
        m = rx.search(texto)
        if m:
            a, mes, d = conv(m)
            if mes:
                try:
                    return datetime.date(a, mes, d).isoformat(), "titulo"
                except ValueError:
                    pass
    return None, None


def data_do_arquivo(url):
    """Ano/mes da pasta de upload — usado para conferir data suspeita."""
    m = RE_PASTA.search(url or "")
    return f"{m.group(1)}-{m.group(2)}" if m else None


def chave(item):
    base = (item.get("url") or "") + "|" + (item.get("titulo") or "")
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def coleta(page, nome, url, precisa_js):
    try:
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000 if precisa_js else 1500)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        brutos = page.eval_on_selector_all(
            "a",
            "els => els.map(e => ({t:(e.innerText||'').trim().replace(/\\s+/g,' '), h:e.href}))",
        )
    except Exception as e:
        return {"fonte": nome, "url": url, "erro": str(e)[:220], "itens": []}

    itens, vistos = [], set()
    for b in brutos:
        t, h = b["t"], b["h"]
        if not t or len(t) < 12 or len(t) > 350 or h in vistos:
            continue
        if not RELEVANTE.search(t) and not RELEVANTE.search(h):
            continue
        vistos.add(h)
        data, origem = extrai_data(t, h)
        pasta = data_do_arquivo(h)
        alerta = None
        if data and pasta and not data.startswith(pasta):
            alerta = (f"data declarada {data} nao bate com a pasta do arquivo ({pasta}); "
                      "conferir o texto oficial antes de reportar")
        itens.append({"titulo": t, "url": h, "data": data,
                      "data_origem": origem, "pasta_arquivo": pasta, "alerta": alerta})
    return {"fonte": nome, "url": url, "erro": None,
            "total": len(itens), "itens": itens[:60]}


def main():
    hoje = os.environ.get("DATA_REF") or datetime.date.today().isoformat()
    resultado = []
    with sync_playwright() as p:
        nav = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = nav.new_context(
            locale="pt-BR",
            user_agent=("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"),
        )
        pg = ctx.new_page()
        for nome, url, js in FONTES:
            r = coleta(pg, nome, url, js)
            resultado.append(r)
            status = f"ERRO: {r['erro'][:60]}" if r["erro"] else f"{r['total']} itens"
            print(f"  {nome:32} {status}", file=sys.stderr)
        nav.close()

    hist_path = DADOS / "historico.json"
    historico = json.loads(hist_path.read_text("utf-8")) if hist_path.exists() else {}

    novidades = []
    for f in resultado:
        for it in f["itens"]:
            k = chave(it)
            if k not in historico:
                historico[k] = {"primeira_vez": hoje, "fonte": f["fonte"], **it}
                novidades.append(historico[k])

    falhas = [f["fonte"] for f in resultado if f["erro"]]
    vazias = [f["fonte"] for f in resultado if not f["erro"] and f["total"] == 0]

    (DADOS / f"{hoje}.json").write_text(
        json.dumps({"data": hoje, "fontes": resultado}, ensure_ascii=False, indent=1), "utf-8")
    hist_path.write_text(json.dumps(historico, ensure_ascii=False, indent=1), "utf-8")
    (DADOS / "novidades.json").write_text(
        json.dumps({"data": hoje, "quantidade": len(novidades), "itens": novidades,
                    "fontes_com_erro": falhas, "fontes_sem_itens": vazias},
                   ensure_ascii=False, indent=1), "utf-8")

    print(f"\n{len(novidades)} novidade(s). "
          f"{len(falhas)} fonte(s) com erro, {len(vazias)} sem itens relevantes.", file=sys.stderr)
    if falhas:
        print("ERRO em: " + ", ".join(falhas), file=sys.stderr)


if __name__ == "__main__":
    main()
