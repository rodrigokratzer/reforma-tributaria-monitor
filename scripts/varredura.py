#!/usr/bin/env python3
"""
Varredura das fontes oficiais da reforma tributaria do consumo.

v2 — mudancas em relacao a primeira versao:
  * uma aba nova por fonte (na v1 uma falha derrubava as 11 seguintes com
    "Navigation is interrupted by another navigation", escondendo o erro real)
  * 2 tentativas por fonte, com espera entre elas
  * fallback HTTP puro (urllib) quando o navegador falha — serve tanto de
    plano B quanto de diagnostico: se o navegador reseta mas o urllib
    responde 200, o problema e' o navegador; se os dois falham igual,
    o bloqueio e' de rede (IP de datacenter recusado pelo site)
  * cada fonte registra o metodo que funcionou e o codigo HTTP obtido

Parte B — a mecanica de coleta (2 tentativas via navegador, fallback HTTP,
filtro por relevancia) saiu daqui para scripts/portais/base.py, onde vive
como a classe Portal. Este modulo fica so' com a orquestracao (main), a
gravacao (grava_resultado) e o DOU (coleta_dou). As 12 fontes web sao as
instancias em portais.registro.PORTAIS.

Grava:
  dados/AAAA-MM-DD.json  status e itens da execucao
  dados/historico.json   indice acumulado {chave: item}
  dados/novidades.json   o que apareceu pela primeira vez
"""
import json, os, sys, time, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portais.base import UA, chave
from portais.registro import PORTAIS

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"
DADOS.mkdir(exist_ok=True)

# Orcamento de tempo. O job do GitHub tem limite; sem um teto proprio o script
# e' morto no meio e nao grava nada — nem dado, nem diagnostico. Com o teto,
# ele sempre fecha, grava o que conseguiu e marca o resto como nao tentado.
ORCAMENTO_S = 600


def coleta_dou(hoje):
    """DOU via INLABS, como fonte adicional.

    Roda D-1 e D: a varredura sai as 06:40 e a edicao do dia as vezes ainda
    nao subiu; alem disso as edicoes extras da vespera costumam aparecer
    depois. Reprocessar a vespera e' barato porque o historico deduplica.

    Sem credencial, a fonte e' simplesmente pulada — o DOU nao pode derrubar
    a varredura das 12 fontes que ja' funciona.
    """
    email, senha = os.environ.get("INLABS_EMAIL"), os.environ.get("INLABS_SENHA")
    if not email or not senha:
        return {"fonte": "DOU (INLABS)", "url": "https://inlabs.in.gov.br/",
                "metodo": None, "total": 0, "itens": [],
                "erro": "sem credencial: INLABS_EMAIL/INLABS_SENHA nao definidos"}
    try:
        import dou
    except ImportError as e:
        return {"fonte": "DOU (INLABS)", "url": "https://inlabs.in.gov.br/",
                "metodo": None, "total": 0, "itens": [], "erro": f"import: {e}"}
    d = datetime.date.fromisoformat(hoje)
    dias = [(d - datetime.timedelta(days=1)).isoformat(), hoje]
    try:
        itens, diag = dou.coleta(dias, email, senha)
    except Exception as e:
        return {"fonte": "DOU (INLABS)", "url": "https://inlabs.in.gov.br/",
                "metodo": None, "total": 0, "itens": [],
                "erro": f"{type(e).__name__}: {str(e)[:150]}"}
    return {"fonte": "DOU (INLABS)", "url": "https://inlabs.in.gov.br/",
            "metodo": "inlabs", "http_status": None, "erro": None,
            "total": len(itens), "itens": itens,
            "diagnostico": {k: v for k, v in diag.items() if k in ("lidas", "forte", "revisar")}}


def grava_resultado(hoje, resultado, arquivo_dados, arquivo_novidades):
    """Atualiza o historico compartilhado e grava o instantaneo do dia e as
    novidades desta execucao nos arquivos indicados.

    historico.json e' seguro para duas execucoes por dia (ex: DOU as 2h e as
    12 fontes web as 6h40): a chave de dedup e' um hash do conteudo do item
    (chave()), entao cada execucao so adiciona o que encontrou, sem
    sobrescrever o que a outra ja gravou. arquivo_dados e arquivo_novidades
    sao proprios de cada execucao, para que uma nunca apague o resultado da
    outra.
    """
    hist_path = DADOS / "historico.json"
    historico = json.loads(hist_path.read_text("utf-8")) if hist_path.exists() else {}

    novidades = []
    for f in resultado:
        for it in f["itens"]:
            k = chave(it)
            if k not in historico:
                historico[k] = {"primeira_vez": hoje, "fonte": f["fonte"], **it}
                novidades.append(historico[k])

    falhas = [f["fonte"] for f in resultado if not f["metodo"]
              and "nao tentada" not in (f.get("erro") or "")]
    puladas = [f["fonte"] for f in resultado
               if "nao tentada" in (f.get("erro") or "")]
    so_http = [f["fonte"] for f in resultado if f["metodo"] == "http"]
    vazias = [f["fonte"] for f in resultado if f["metodo"] and f["total"] == 0]

    (DADOS / arquivo_dados).write_text(
        json.dumps({"data": hoje, "fontes": resultado}, ensure_ascii=False, indent=1), "utf-8")
    hist_path.write_text(json.dumps(historico, ensure_ascii=False, indent=1), "utf-8")
    (DADOS / arquivo_novidades).write_text(
        json.dumps({"data": hoje, "quantidade": len(novidades), "itens": novidades,
                    "fontes_com_erro": falhas, "fontes_sem_itens": vazias,
                    "fontes_via_http": so_http, "fontes_puladas": puladas},
                   ensure_ascii=False, indent=1), "utf-8")

    ok = len(resultado) - len(falhas) - len(puladas)
    print(f"\n{ok}/{len(resultado)} fontes ok | {len(novidades)} novidade(s) | "
          f"{len(falhas)} falha(s) | {len(puladas)} pulada(s) | "
          f"{len(so_http)} via HTTP | {len(vazias)} sem itens", file=sys.stderr)

    if ok == 0:
        print("\nDIAGNOSTICO: nenhuma fonte respondeu. Navegador e http puro falharam. "
              "Se a execucao anterior funcionou, e' instabilidade do lado dos sites, "
              "nao do script — os portais .gov.br respondem de forma intermitente.",
              file=sys.stderr)
    elif falhas:
        print(f"\nParcial: {ok} fonte(s) coletadas. As que falharam entram na proxima "
              "execucao; o historico acumulado nao se perde.", file=sys.stderr)


def main():
    hoje = os.environ.get("DATA_REF") or datetime.date.today().isoformat()
    from playwright.sync_api import sync_playwright

    resultado = []
    with sync_playwright() as p:
        nav = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = nav.new_context(locale="pt-BR", user_agent=UA,
                              extra_http_headers={"Accept-Language": "pt-BR,pt;q=0.9"})
        limite = time.monotonic() + ORCAMENTO_S
        for portal in PORTAIS:
            if time.monotonic() > limite:
                resultado.append({"fonte": portal.nome, "url": portal.url,
                                  "metodo": None, "http_status": None,
                                  "total": 0, "itens": [],
                                  "erro": "nao tentada: orcamento de tempo esgotado"})
                print(f"  {portal.nome:32} PULADA (tempo esgotado)", file=sys.stderr)
                continue
            r = portal.coletar(ctx, limite)
            resultado.append(r)
            print(f"  {portal.nome:32} metodo={r['metodo'] or 'FALHOU':7} "
                  f"itens={r['total']:3} http={r['http_status']} "
                  f"[{int(limite - time.monotonic())}s restantes]", file=sys.stderr)
            if r["erro"]:
                print(f"      {r['erro'][:150]}", file=sys.stderr)
        nav.close()

    # O DOU roda em workflow proprio (scripts/dou_diario.py, as 2h) — nao
    # aqui. As 6h40 os outros portais tambem estao sendo acessados por
    # muita gente; separar evita concentrar tudo no mesmo horario e da'
    # ao login do INLABS o orcamento de retentativa que ele precisa (ver
    # dou.abre_sessao) sem estourar o teto de tempo desta varredura.
    grava_resultado(hoje, resultado, f"{hoje}.json", "novidades.json")


if __name__ == "__main__":
    main()
