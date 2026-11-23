#!/usr/bin/env python3
"""Avisa (push/e-mail) quando a chave de 1 ano do Claude no lenovo-claude está para vencer.

Lê ~/.config/claude-token/criado_em (gravado por salvar_token_claude.sh). Avisa
com 30 e 15 dias de antecedência e todo dia a partir de 7 dias (inclusive depois
de vencida). Sem o arquivo, não faz nada. Roda pelo claude-token-aviso.timer.
"""
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CRIADO_EM = Path.home() / ".config" / "claude-token" / "criado_em"
VALIDADE = timedelta(days=365)
DIAS_DE_AVISO = {30, 15}
AVISO_DIARIO_A_PARTIR = 7


def dias_restantes(criado_em, hoje):
    return (criado_em + VALIDADE - hoje).days


def deve_avisar(dias):
    return dias in DIAS_DE_AVISO or dias <= AVISO_DIARIO_A_PARTIR


def mensagem(dias, vence):
    quando = vence.strftime("%d/%m/%Y")
    if dias < 0:
        estado = f"VENCEU em {quando}"
    elif dias == 0:
        estado = "vence HOJE"
    else:
        estado = f"vence em {dias} dia(s) ({quando})"
    return (f"A chave de 1 ano do Claude no lenovo-claude {estado}. Sem ela as análises "
            "(Reforma, painel do Instagram e robô) param. Renovar: no lenovo-claude, "
            "claude setup-token e depois scripts/salvar_token_claude.sh "
            "(pasta reforma-tributaria-monitor).")


def notificar(msg):
    subprocess.run([sys.executable, str(RAIZ / "scripts" / "notificar.py"), "--falha", msg],
                   cwd=RAIZ, timeout=120)


def main(arquivo=CRIADO_EM, hoje=None, avisar=notificar):
    hoje = hoje or date.today()
    try:
        criado_em = date.fromisoformat(Path(arquivo).read_text().strip())
    except FileNotFoundError:
        print("aviso_token_claude: sem chave de 1 ano gravada; nada a fazer")
        return 0
    except ValueError:
        avisar("Não consegui ler a data da chave do Claude no lenovo-claude "
               f"({arquivo}). Confira ou grave a chave de novo.")
        return 0
    dias = dias_restantes(criado_em, hoje)
    print(f"aviso_token_claude: chave de {criado_em}, {dias} dia(s) para vencer")
    if deve_avisar(dias):
        avisar(mensagem(dias, criado_em + VALIDADE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
