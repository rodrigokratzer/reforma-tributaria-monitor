#!/usr/bin/env python3
"""
MEDICAO do filtro do DOU sobre a edicao COMPLETA (INLABS).

Importa tudo de dou.py — o MESMO codigo que roda na varredura diaria. Se o
classificador vivesse em dois arquivos, esta medicao passaria a atestar um
filtro diferente do que esta' em producao e o "APROVADO" nao valeria nada.

Mede duas coisas:
  RECALL — pega os atos que sabemos que existem? Procura no CORPUS INTEIRO,
           inclusive no que o filtro descartou, para separar "nao veio na
           coleta" de "veio e a regra jogou fora".
  RUIDO  — quantos itens por dia util em cada balde.

Uso: python scripts/medir_inlabs.py [inicio AAAA-MM-DD] [fim AAAA-MM-DD]
"""
import json, os, re, sys, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dou

RAIZ = Path(__file__).resolve().parent.parent

INICIO = (sys.argv[1] if len(sys.argv) > 1 else "") or "2026-07-29"
FIM = (sys.argv[2] if len(sys.argv) > 2 else "") or datetime.date.today().isoformat()

# (nome, data de publicacao no DOU, regex). A data importa: ato publicado fora
# da janela medida nao pode ser cobrado do filtro — a primeira versao do
# relatorio marcava "PERDEU" nesses casos e produzia alarme falso.
TOLERANCIA_DOU = 3
GABARITO = [
    ("Resolucao CGIBS n 14",       "2026-07-31", r"resolu[çc][ãa]o\s+cgibs\s+n?[ºo°]?\s*14\b"),
    ("Ato Conjunto RFB/CGIBS n 4", "2026-07-31", r"ato\s+conjunto\s+rfb\s*/?\s*cgibs\s+n?[ºo°]?\s*4\b"),
    ("Ato Tecnico Conjunto n 1",   "2026-07-31", r"ato\s+t[ée]cnico\s+conjunto\s+rfb\s*/?\s*cgibs\s+n?[ºo°]?\s*1\b"),
    ("Ato Conjunto RFB/CGIBS n 5", "2026-08-14", r"ato\s+conjunto\s+rfb\s*/?\s*cgibs\s+n?[ºo°]?\s*5\b"),
]


def main():
    email, senha = os.environ.get("INLABS_EMAIL"), os.environ.get("INLABS_SENHA")
    if not email or not senha:
        sys.exit("Defina INLABS_EMAIL e INLABS_SENHA (secrets do GitHub).")

    d0 = datetime.date.fromisoformat(INICIO)
    d1 = datetime.date.fromisoformat(FIM)
    # tentativas menor que o padrao de dou.py: esta medicao roda dentro de um
    # job com 45min de limite, orcamento que a coleta diaria (workflow proprio,
    # sem esse teto) nao tem.
    op, cookie = dou.abre_sessao(email, senha, tentativas=10)
    print(f"Login ok. Janela {d0} a {d1}, secoes {dou.SECOES}\n", file=sys.stderr)

    baldes = {"forte": [], "revisar": [], "descartado": 0}
    corpus, cobertura, falhas = [], [], []
    total, dias_uteis = 0, 0

    dia = d0
    while dia <= d1:
        if dia.weekday() < 5:
            dias_uteis += 1
        for secao in dou.SECOES:
            bruto, err = dou.baixa(op, cookie, dia.isoformat(), secao)
            if err:
                if "sem edicao" not in err:
                    falhas.append(f"{dia} {secao}: {err}")
                continue
            arts = dou.artigos(bruto)
            total += len(arts)
            cobertura.append({"dia": dia.isoformat(), "secao": secao,
                              "materias": len(arts), "kb": round(len(bruto) / 1024)})
            for a in arts:
                b = dou.classifica(a)
                reg = {"dia": dia.isoformat(), "secao": secao,
                       "titulo": a.get("_titulo", "")[:150],
                       "orgao": a.get("artCategory", "")[:120],
                       "ementa": a.get("_ementa", "")[:200],
                       "continuacao": bool(a.get("_continuacao"))}
                corpus.append({**reg, "balde": b})
                if b == "descartado":
                    baldes["descartado"] += 1
                else:
                    baldes[b].append(reg)
            print(f"  {dia} {secao:5} materias={len(arts):5} "
                  f"acum_forte={len(baldes['forte'])}", file=sys.stderr)
        dia += datetime.timedelta(days=1)

    recall, no_escopo = [], 0
    for nome, data_dou, rx in GABARITO:
        alvo = datetime.date.fromisoformat(data_dou)
        tol = datetime.timedelta(days=TOLERANCIA_DOU)
        if not ((d0 - tol) <= alvo <= (d1 + tol)):
            recall.append({"esperado": nome, "data_dou": data_dou,
                           "situacao": "fora da janela", "encontrado": None,
                           "balde": None, "dia": None, "secao": None, "titulo": ""})
            continue
        no_escopo += 1
        pad = re.compile(rx, re.I)
        hit = next((i for i in corpus if pad.search(i["titulo"] + " " + i["ementa"])), None)
        situacao = ("encontrado" if hit and hit["balde"] in ("forte", "revisar")
                    else "descartado pelo filtro" if hit else "ausente do corpus")
        recall.append({"esperado": nome, "data_dou": data_dou, "situacao": situacao,
                       "encontrado": bool(hit), "balde": (hit or {}).get("balde"),
                       "dia": (hit or {}).get("dia"), "secao": (hit or {}).get("secao"),
                       "titulo": (hit or {}).get("titulo", "")})

    u = max(1, dias_uteis)
    sem_titulo = sum(1 for i in baldes["forte"] if not i["titulo"].strip())
    rel = {"janela": [d0.isoformat(), d1.isoformat()], "dias_uteis": dias_uteis,
           "materias_lidas": total, "corpus_indexado": len(corpus),
           "cobertura": cobertura, "falhas": falhas,
           "forte": len(baldes["forte"]), "revisar": len(baldes["revisar"]),
           "descartado": baldes["descartado"],
           "forte_por_dia": round(len(baldes["forte"]) / u, 2),
           "revisar_por_dia": round(len(baldes["revisar"]) / u, 2),
           "forte_sem_titulo": sem_titulo,
           "recall": recall, "esperados_no_escopo": no_escopo,
           "amostra_forte": baldes["forte"][:40],
           "amostra_revisar": baldes["revisar"][:20]}

    (RAIZ / "dados").mkdir(exist_ok=True)
    (RAIZ / "dados" / "medicao_inlabs.json").write_text(
        json.dumps(rel, ensure_ascii=False, indent=1), "utf-8")

    MARCA = {"encontrado": "OK", "descartado pelo filtro": "FILTRO",
             "ausente do corpus": "AUSENTE", "fora da janela": "n/a"}
    print("\n=== RECALL ===", file=sys.stderr)
    for r in recall:
        onde = f"[{r['balde']}] {r['dia']} {r['secao']}" if r["encontrado"] else ""
        print(f"  {MARCA[r['situacao']]:8} {r['esperado']:30} DOU {r['data_dou']}  {onde}",
              file=sys.stderr)

    ausentes = sum(1 for r in recall if r["situacao"] == "ausente do corpus")
    filtrados = sum(1 for r in recall if r["situacao"] == "descartado pelo filtro")
    fracos = sum(1 for r in recall if r["balde"] == "revisar")
    fora = sum(1 for r in recall if r["situacao"] == "fora da janela")

    print("\n=== VOLUME ===", file=sys.stderr)
    print(f"  materias lidas : {total} em {dias_uteis} dias uteis", file=sys.stderr)
    print(f"  forte          : {rel['forte']} ({rel['forte_por_dia']}/dia)", file=sys.stderr)
    print(f"  revisar        : {rel['revisar']} ({rel['revisar_por_dia']}/dia)", file=sys.stderr)
    print(f"  descartado     : {rel['descartado']}", file=sys.stderr)
    print(f"  forte sem titulo: {sem_titulo}", file=sys.stderr)
    if falhas:
        print(f"\n  {len(falhas)} erro(s) de download; 1o: {falhas[0][:90]}", file=sys.stderr)

    if no_escopo == 0:
        v = "INCONCLUSIVO — nenhum ato do gabarito caiu nesta janela"
    elif ausentes:
        v = f"REPROVADO — {ausentes} ato(s) ausentes do corpus. Falha de COLETA."
    elif filtrados:
        v = f"REPROVADO — {filtrados} ato(s) descartados pelo FILTRO. Falha de regra."
    elif fracos:
        v = f"APROVADO com ressalva — {fracos} ato(s) so' em 'revisar'"
    else:
        v = "APROVADO"
    if fora:
        v += f" ({fora} fora da janela, nao contam)"
    print(f"\nVEREDITO: {v}", file=sys.stderr)


if __name__ == "__main__":
    main()
