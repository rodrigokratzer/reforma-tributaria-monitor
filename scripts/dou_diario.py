#!/usr/bin/env python3
"""
Coleta so' o DOU (INLABS), em workflow proprio, separado dos outros 12
portais.

Roda antes deles (2h da manha) de proposito: o login do INLABS pode levar
ate' 30 tentativas com espera crescente (dou.abre_sessao) para superar
manutencao programada, e isso nao pode competir por horario nem por
orcamento de tempo com a varredura dos outros portais as 6h40.

Grava em arquivos proprios (dados/AAAA-MM-DD-dou.json,
dados/novidades_dou.json) para nunca sobrescrever o que a varredura
principal grava — so' dados/historico.json e' compartilhado entre as duas,
e e' seguro (chave() e' um hash do conteudo do item, nao depende de quem
encontrou primeiro).
"""
import datetime, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from varredura import coleta_dou, grava_resultado


def main():
    hoje = os.environ.get("DATA_REF") or datetime.date.today().isoformat()
    r_dou = coleta_dou(hoje)
    print(f"  {'DOU (INLABS)':32} metodo={r_dou['metodo'] or 'PULADO':7} "
          f"itens={r_dou['total']:3}", file=sys.stderr)
    if r_dou.get("erro"):
        print(f"      {r_dou['erro'][:200]}", file=sys.stderr)
    grava_resultado(hoje, [r_dou], f"{hoje}-dou.json", "novidades_dou.json")


if __name__ == "__main__":
    main()
