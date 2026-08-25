#!/usr/bin/env python3
"""
Monta docs/index.html a partir de:
  estado.json                camada curada (prazos, pendencias, linha do tempo)
  dados/AAAA-MM-DD.json      status das fontes na ultima varredura
  dados/AAAA-MM-DD-dou.json  status do DOU (workflow proprio, 02:00) (opcional)
  dados/novidades.json       o que apareceu pela primeira vez (12 portais)
  dados/novidades_dou.json   o que apareceu pela primeira vez (DOU) (opcional)
  dados/historico.json       indice acumulado
  analises/AAAA-MM-DD.md     analise escrita pelo Claude (opcional)

A analise e' opcional por design: o painel precisa ficar em pe' sozinho,
so' com os fatos, mesmo em dia nenhuma analise foi publicada.
"""
import json, datetime, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DADOS, ANALISES, DOCS = RAIZ / "dados", RAIZ / "analises", RAIZ / "docs"
DOCS.mkdir(exist_ok=True)

MAX_HISTORICO = 200


def ler_json(p, padrao):
    try:
        return json.loads(Path(p).read_text("utf-8"))
    except Exception:
        return padrao


def md_para_html(texto):
    try:
        import markdown
        return markdown.markdown(texto, extensions=["extra", "sane_lists"])
    except ImportError:
        # fallback minimo: paragrafos, sem depender do pacote
        blocos = [b.strip() for b in texto.split("\n\n") if b.strip()]
        return "".join(f"<p>{b}</p>" for b in blocos)


def main():
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

    historico = list(ler_json(DADOS / "historico.json", {}).values())
    historico.sort(key=lambda h: (h.get("primeira_vez") or "", h.get("data") or ""), reverse=True)
    historico = historico[:MAX_HISTORICO]

    # analise: a do dia, senao a mais recente disponivel
    analise_html, analise_data = None, None
    if ANALISES.exists():
        candidatos = sorted(ANALISES.glob("*.md"), reverse=True)
        alvo = ANALISES / f"{data_ref}.md"
        escolhido = alvo if alvo.exists() else (candidatos[0] if candidatos else None)
        if escolhido:
            analise_html = md_para_html(escolhido.read_text("utf-8"))
            analise_data = escolhido.stem

    payload = {
        "data": data_ref,
        "gerado_em": datetime.datetime.now(datetime.timezone.utc)
                     .strftime("%Y-%m-%d %H:%M UTC"),
        "prazos_destaque": estado.get("prazos_destaque", []),
        "pendencias": estado.get("pendencias", []),
        "linha_do_tempo": estado.get("linha_do_tempo", []),
        "novidades": novid.get("itens", []) + novid_dou.get("itens", []),
        "fontes": fontes,
        "historico": historico,
        "analise_html": analise_html,
        "analise_data": analise_data,
        "status_diario": status_diario,
    }

    tpl = (RAIZ / "scripts" / "painel_template.html").read_text("utf-8")
    if "/*__DADOS__*/null" not in tpl:
        sys.exit("Template sem o marcador /*__DADOS__*/null — abortando.")
    html = tpl.replace("/*__DADOS__*/null",
                       json.dumps(payload, ensure_ascii=False)
                           .replace("</script", "<\\/script"))

    (DOCS / "index.html").write_text(html, "utf-8")
    (DOCS / ".nojekyll").write_text("", "utf-8")
    print(f"docs/index.html gerado — {len(payload['novidades'])} novidade(s), "
          f"{len(fontes)} fonte(s), analise: {analise_data or 'nenhuma'}")


if __name__ == "__main__":
    main()
