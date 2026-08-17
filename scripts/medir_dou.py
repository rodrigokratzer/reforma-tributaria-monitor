#!/usr/bin/env python3
"""
MEDICAO do filtro do DOU — nao entra na varredura ate passar neste teste.

Consulta a API da Imprensa Nacional (a mesma do in.gov.br/consulta, usada pelo
Ro-DOU do governo federal), aplica o filtro em camadas e reporta:

  RECALL  — pegou os atos que sabemos que existem? (falso negativo e' o erro caro)
  RUIDO   — quantos itens irrelevantes por dia? (falso positivo e' o erro barato)

Uso: python scripts/medir_dou.py [dias]     (default 60)
Escreve dados/medicao_dou.json e imprime o relatorio.
"""
import json, re, sys, time, datetime, urllib.parse, urllib.request
from pathlib import Path

DIAS = int(sys.argv[1]) if len(sys.argv) > 1 else 60
RAIZ = Path(__file__).resolve().parent.parent
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
BASE = "https://www.in.gov.br/consulta/-/buscar/dou"
SCRIPT_ID = "_br_com_seatecnologia_in_buscadou_BuscaDouPortlet_params"

# Termos de consulta. Nao usamos a palavra "reforma" sozinha: ela pega
# reforma trabalhista, administrativa e previdenciaria.
CONSULTAS = ['"IBS"', '"CBS"', '"Imposto Seletivo"', '"CGIBS"',
             '"Comite Gestor do IBS"', '"Lei Complementar 214"',
             '"Lei Complementar 227"', '"Emenda Constitucional 132"',
             '"Decreto 12.955"', '"reforma tributaria do consumo"',
             '"split payment"', '"DeRE"']

ORGAOS = re.compile(r"(minist[ée]rio da fazenda|receita federal|"
                    r"comit[êe] gestor do ibs|cgibs|secretaria especial da receita)", re.I)
REFS = re.compile(r"(lei complementar\s*n?[ºo°]?\s*(214|227)|"
                  r"emenda constitucional\s*n?[ºo°]?\s*132|"
                  r"decreto\s*n?[ºo°]?\s*12\.?955)", re.I)
TERMOS = re.compile(r"\b(ibs|cbs|imposto seletivo|cgibs|split payment|dere|"
                    r"nfs-?e|al[íi]quota de refer[êe]ncia|"
                    r"reforma tribut[áa]ria do consumo)\b", re.I)
# Ruido classico: mesma sigla, outro assunto.
ARMADILHAS = re.compile(r"(reforma trabalhista|reforma administrativa|"
                        r"reforma da previd[êe]ncia|instituto brasileiro de "
                        r"geografia|banco central do brasil - comunicado)", re.I)

# Atos que sabemos que existem. Se a medicao nao pegar, o filtro esta errado.
GABARITO = [
    ("Resolucao CGIBS n 14", "2026-07-29", r"resolu[çc][ãa]o.{0,40}\b14\b"),
    ("Ato Conjunto RFB/CGIBS n 4", "2026-07-30", r"ato conjunto.{0,60}\b4\b"),
    ("Ato Tecnico Conjunto n 1", "2026-07-31", r"ato t[ée]cnico conjunto"),
    ("Ato Conjunto RFB/CGIBS n 5", "2026-08-12", r"ato conjunto.{0,60}\b5\b"),
]


def busca(termo, de, ate, secao, pagina=0):
    p = {"q": termo, "s": secao, "exactDate": "personalizado",
         "publishFrom": de.strftime("%d-%m-%Y"), "publishTo": ate.strftime("%d-%m-%Y"),
         "delta": "50", "currentPage": str(pagina)}
    url = BASE + "?" + urllib.parse.urlencode(p)
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "pt-BR,pt;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            html = r.read().decode("utf-8", "replace")
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:90]}"
    m = re.search(r'id="%s"[^>]*>(.*?)</script>' % SCRIPT_ID, html, re.S)
    if not m:
        return None, "resposta sem bloco de resultados (layout mudou?)"
    try:
        return json.loads(m.group(1)).get("jsonArray", []), None
    except Exception as e:
        return None, f"json invalido: {str(e)[:70]}"


def classifica(it):
    texto = " ".join(str(it.get(k) or "") for k in
                     ("title", "content", "artType", "hierarchyStr", "subTitulo"))
    org, ref, ter = bool(ORGAOS.search(texto)), bool(REFS.search(texto)), bool(TERMOS.search(texto))
    if ARMADILHAS.search(texto) and not (ref or ter):
        return "descartado", texto
    if ref or ter:
        return "forte", texto
    if org:
        return "revisar", texto
    return "descartado", texto


def main():
    ate = datetime.date.today()
    de = ate - datetime.timedelta(days=DIAS)
    print(f"Janela: {de} a {ate} ({DIAS} dias)\n", file=sys.stderr)

    vistos, erros = {}, []
    for termo in CONSULTAS:
        for secao in ("do1", "do2", "do3"):
            itens, err = busca(termo, de, ate, secao)
            if err:
                erros.append(f"{termo}/{secao}: {err}")
                continue
            for it in itens:
                vistos.setdefault(it.get("urlTitle") or it.get("title"), it)
            time.sleep(1.2)          # educado com a API
        print(f"  {termo:38} acumulado={len(vistos)}", file=sys.stderr)

    baldes = {"forte": [], "revisar": [], "descartado": []}
    for it in vistos.values():
        b, texto = classifica(it)
        it["_texto"] = texto[:400]
        baldes[b].append(it)

    # RECALL
    achados = []
    for nome, data, rx in GABARITO:
        p = re.compile(rx, re.I)
        hit = next((i for i in baldes["forte"] + baldes["revisar"]
                    if p.search(i.get("title", "") + " " + i.get("_texto", ""))), None)
        achados.append({"esperado": nome, "data": data, "encontrado": bool(hit),
                        "titulo": (hit or {}).get("title", "")[:110]})

    uteis = max(1, int(DIAS * 5 / 7))
    rel = {"janela": [de.isoformat(), ate.isoformat()], "dias": DIAS,
           "consultados": len(vistos),
           "forte": len(baldes["forte"]), "revisar": len(baldes["revisar"]),
           "descartado": len(baldes["descartado"]),
           "forte_por_dia_util": round(len(baldes["forte"]) / uteis, 2),
           "revisar_por_dia_util": round(len(baldes["revisar"]) / uteis, 2),
           "recall": achados, "erros": erros,
           "amostra_forte": [i.get("title", "")[:120] for i in baldes["forte"][:25]],
           "amostra_revisar": [i.get("title", "")[:120] for i in baldes["revisar"][:15]]}

    (RAIZ / "dados").mkdir(exist_ok=True)
    (RAIZ / "dados" / "medicao_dou.json").write_text(
        json.dumps(rel, ensure_ascii=False, indent=1), "utf-8")

    print("\n=== RECALL (falso negativo e' o erro caro) ===", file=sys.stderr)
    for a in achados:
        print(f"  {'OK  ' if a['encontrado'] else 'PERDEU'} {a['esperado']} ({a['data']})",
              file=sys.stderr)
    perdidos = sum(1 for a in achados if not a["encontrado"])
    print(f"\n=== RUIDO (falso positivo e' o erro barato) ===", file=sys.stderr)
    print(f"  itens unicos retornados : {len(vistos)}", file=sys.stderr)
    print(f"  forte                   : {rel['forte']} ({rel['forte_por_dia_util']}/dia util)",
          file=sys.stderr)
    print(f"  revisar                 : {rel['revisar']} ({rel['revisar_por_dia_util']}/dia util)",
          file=sys.stderr)
    print(f"  descartado              : {rel['descartado']}", file=sys.stderr)
    if erros:
        print(f"\n  {len(erros)} consulta(s) com erro; primeira: {erros[0]}", file=sys.stderr)
    print(f"\nVEREDITO: {'REPROVADO - ' + str(perdidos) + ' ato(s) perdido(s)' if perdidos else 'APROVADO no recall'}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
