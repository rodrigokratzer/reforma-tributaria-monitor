#!/usr/bin/env python3
"""Raia de leitura: texto integral de cada item do historico que ainda nao tem.

Roda depois da varredura, so' no notebook (rodar_varredura.sh; ver
docs/operacao-local.md). O GitHub Actions (plano B) nao roda esta raia: o
que ele coletar e' lido no proximo ciclo local.

Le dados/historico.json e NUNCA o escreve. Escreve so':
  dados/textos/<chave>.txt   texto integral (scripts/textos.py)
  dados/leituras.json        status de cada leitura — unico escritor e' este script

Para cada item: baixa a URL com sessao de cookies; se for PDF, pdftotext
pagina a pagina com OCR nas paginas sem texto; se for HTML, o corpo pela
regra do dominio, mais os anexos (PDF) linkados dentro do corpo.

Valores de `origem` em leituras.json: coleta, coleta_cortada, inlabs, html,
pdf, pdf+ocr e html+ocr (pagina HTML cujo anexo PDF precisou de OCR).

Itens do DOU nao sao baixados aqui: o texto deles vem do INLABS na coleta
(dou.py) ou, para os antigos, de scripts/reler_dou.py.

Uso:
  python3 scripts/ler_textos.py                  # orcamento padrao (45 min)
  python3 scripts/ler_textos.py --sem-limite     # backfill manual
  python3 scripts/ler_textos.py --chave K [--chave K2]   # rele estes, mesmo ja' lidos
"""
import argparse
import collections
import datetime
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textos
from leitura import baixar, paginas, pdf

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"

ORCAMENTO_S = 2700       # 45 min por ciclo; OCR e' lento e tudo bem
MAX_ANEXOS = 10
MINIMO_CHARS = 50        # menos que isto nao e' publicacao, e' casca de pagina
CORTE_DOU_LEGADO = 20000  # dou.py guardava `texto` cortado neste tamanho


class ErroLeitura(Exception):
    pass


def agora():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def carrega_json(p, padrao):
    return json.loads(p.read_text("utf-8")) if p.exists() else padrao


def grava_json(p, obj):
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True), "utf-8")
    tmp.replace(p)


def _eh_dou(it):
    return (it.get("fonte") or "").startswith("DOU")


def migra_legado(dados, historico, leituras):
    """Itens com `texto` dentro do historico (DOU desde a Parte A, CGIBS desde
    a Parte B) passam para dados/textos/. Texto do DOU com 20.000 caracteres
    veio cortado: fica `coleta_cortada` ate' reler_dou.py trazer o integral."""
    for k, it in historico.items():
        t = (it.get("texto") or "").strip()
        if t and not textos.existe(dados, k):
            textos.grava(dados, k, t)
            cortado = _eh_dou(it) and len(it["texto"]) >= CORTE_DOU_LEGADO
            leituras[k] = {"status": "lido",
                           "origem": "coleta_cortada" if cortado else "coleta",
                           "chars": len(t), "tentativas": 0, "lido_em": agora()}


def registra_coletados(dados, historico, leituras):
    """Arquivo gravado por um coletor (ou por reler_dou.py) sem registro aqui."""
    for k, it in historico.items():
        if not textos.existe(dados, k):
            continue
        meta = leituras.get(k)
        n = len(textos.le(dados, k))
        if meta is None:
            leituras[k] = {"status": "lido", "origem": "inlabs" if _eh_dou(it) else "coleta",
                           "chars": n, "tentativas": 0, "lido_em": agora()}
        elif meta.get("origem") == "coleta_cortada" and n > meta.get("chars", 0):
            leituras[k] = {**meta, "origem": "inlabs", "chars": n, "lido_em": agora()}


def a_ler(dados, historico, leituras, chaves=None):
    """Chaves a ler, mais recentes primeiro (o item novo nao espera o backfill)."""
    out = []
    for k, it in historico.items():
        if chaves is not None:
            if k in chaves and not _eh_dou(it):
                out.append(k)
            continue
        if _eh_dou(it):
            continue
        meta = leituras.get(k, {})
        st = meta.get("status")
        if st in ("lido", "desistiu"):
            continue
        if st == "parcial" and meta.get("tentativas", 0) >= textos.MAX_TENTATIVAS:
            continue
        if st is None and textos.existe(dados, k):
            continue
        out.append(k)
    out.sort(key=lambda k: historico[k].get("visto_em") or historico[k].get("primeira_vez") or "",
             reverse=True)
    return out


def _de_resposta(resp):
    """-> (texto, origem, paginas_ocr, anexos)"""
    if baixar.eh_pdf(resp.dados):
        r = pdf.extrai_pdf(resp.dados)
        return r["texto"], r["origem"], len(r["paginas_ocr"]), []
    html = resp.dados.decode(resp.charset or "utf-8", "replace")
    texto, anexos = paginas.extrai_pagina(resp.url, html)
    return texto, "html", 0, anexos


def le_item(sessao, it):
    texto, origem, ocr, anexos = _de_resposta(sessao.baixa(it["url"]))
    partes = [texto] if texto else []
    lidos, falhos = [], []
    for a in anexos[:MAX_ANEXOS]:
        try:
            t, o, n_ocr, _ = _de_resposta(sessao.baixa(a))   # anexo de anexo nao e' seguido
        except Exception as e:     # um anexo nunca descarta o texto principal ja' extraido
            falhos.append({"url": a, "erro": f"{type(e).__name__}: {str(e)[:200]}"})
            continue
        if t and t.strip():
            partes.append(f"===== ANEXO: {a} =====\n{t}")
            lidos.append(a)
            ocr += n_ocr
        else:
            falhos.append({"url": a, "erro": "anexo sem texto legivel"})
    for a in anexos[MAX_ANEXOS:]:
        falhos.append({"url": a, "erro": "acima de MAX_ANEXOS"})
    final = "\n\n".join(partes)
    if len(final.strip()) < MINIMO_CHARS:
        raise ErroLeitura("sem conteudo legivel")
    if ocr and "ocr" not in origem:
        origem += "+ocr"
    return {"texto": final, "origem": origem, "paginas_ocr": ocr,
            "anexos": lidos, "anexos_falhos": falhos}


def executa(dados, orcamento=ORCAMENTO_S, chaves=None, sessao=None):
    dados = Path(dados)
    historico = carrega_json(dados / "historico.json", {})
    arq = dados / "leituras.json"
    leituras = carrega_json(arq, {})
    migra_legado(dados, historico, leituras)
    registra_coletados(dados, historico, leituras)
    grava_json(arq, leituras)

    pend = a_ler(dados, historico, leituras, chaves)
    sessao = sessao or baixar.Sessao()
    limite = time.monotonic() + orcamento if orcamento else None
    cont = collections.Counter()
    print(f"leitura: {len(pend)} item(ns) a ler", file=sys.stderr)
    for i, k in enumerate(pend):
        if limite is not None and time.monotonic() > limite:
            print(f"leitura: orcamento esgotado; {len(pend) - i} item(ns) ficam "
                  "para o proximo ciclo", file=sys.stderr)
            cont["adiado"] += len(pend) - i
            break
        it, ant = historico[k], leituras.get(k, {})
        tent = (0 if chaves else ant.get("tentativas", 0)) + 1
        t0 = time.monotonic()
        try:
            r = le_item(sessao, it)
        except Exception as e:      # um item nunca derruba a raia
            st = "desistiu" if tent >= textos.MAX_TENTATIVAS else "falhou"
            erro = {"tentativas": tent, "erro": f"{type(e).__name__}: {str(e)[:200]}",
                    "tentado_em": agora()}
            if ant.get("status") in ("lido", "parcial") and textos.existe(dados, k):
                st = ant["status"]     # releitura que falha nao rebaixa texto valido
                leituras[k] = {**ant, **erro}
            else:
                leituras[k] = {**ant, "status": st, **erro}
        else:
            textos.grava(dados, k, r["texto"])
            st = "parcial" if r["anexos_falhos"] else "lido"
            leituras[k] = {"status": st, "origem": r["origem"], "chars": len(r["texto"]),
                           "paginas_ocr": r["paginas_ocr"], "anexos": r["anexos"],
                           "anexos_falhos": r["anexos_falhos"], "tentativas": tent,
                           "lido_em": agora()}
        grava_json(arq, leituras)    # a cada item: interrupcao nao perde o que ja' foi lido
        cont[st] += 1
        print(f"  {st:8} {time.monotonic() - t0:6.1f}s {it.get('fonte', '')[:28]:28} "
              f"{it['url'][:90]}" + (f"  [{leituras[k].get('erro')}]"
                                     if st in ("falhou", "desistiu") else ""),
              file=sys.stderr)
    print("leitura: " + ", ".join(f"{v} {s}" for s, v in sorted(cont.items())) if cont
          else "leitura: nada a ler", file=sys.stderr)
    return cont


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--orcamento", type=int, default=ORCAMENTO_S)
    ap.add_argument("--sem-limite", action="store_true")
    ap.add_argument("--chave", action="append")
    a = ap.parse_args(argv)
    executa(DADOS, orcamento=None if a.sem_limite else a.orcamento,
            chaves=set(a.chave) if a.chave else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
