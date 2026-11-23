#!/usr/bin/env python3
"""Limite de tentativas das rotinas do lenovo-claude (chamado pelo reforma-falha@.service).

Toda rotina com OnFailure=reforma-falha@%n.service passa por aqui quando falha:

- 1ª falha seguida: manda o alerta de sempre (push/e-mail), avisando do limite;
- da 2ª até antes do limite: não manda nada (antes, cada falha virava um push:
  206 alertas em 22/11/2026, 159 só do ciclo do robô, que roda a cada 5 minutos);
- ao chegar no limite: PAUSA a rotina (para o timer ou o .path que a dispara) e
  manda um último alerta com o comando para religar. Assim uma rotina quebrada
  (login do Claude vencido, rede fora) não fica tentando sem fim nem gastando
  crédito do Claude.

"Seguidas" = falhas desde o último sucesso da rotina e desde que o timer foi
ligado pela última vez (religar o timer ou reiniciar o notebook zera a conta).
A conta vem do journal do systemd, sem arquivo de estado.

Roda como root (prefixo "+" no ExecStart) porque parar um timer exige root; o
alerta em si é enviado pelo notificar.py como o usuário rodrigo.

Uso:  limite_falhas.py <unidade.service>
"""
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
USUARIO = "rodrigo"

LIMITE_PADRAO = 3
# Rotinas que rodam muito seguido precisam de mais folga, senão uma queda curta
# de rede já as pausaria. O ciclo do robô roda a cada 5 min: 12 falhas = 1 hora.
LIMITES = {
    "robo-comentarios-ciclo.service": 12,
}


def limite_de(unidade):
    return LIMITES.get(unidade, LIMITE_PADRAO)


def falhas_seguidas(linhas):
    """Conta as falhas do fim do log para trás, até o último sucesso."""
    n = 0
    for linha in reversed(linhas):
        if "Failed with result" in linha:
            n += 1
        elif "Deactivated successfully" in linha:
            break
    return n


def decidir(n, limite):
    """avisar | calar | pausar."""
    if n <= 1:
        return "avisar"  # 1ª falha, ou não deu para ler o log (na dúvida, avisa)
    if n < limite:
        return "calar"
    return "pausar"


def msg_aviso(unidade, limite):
    return (f"A unidade {unidade} falhou ou estourou o tempo no lenovo-claude. "
            f"Ver journalctl -u {unidade}. Não aviso de novo das próximas falhas; "
            f"com {limite} falhas seguidas a rotina é pausada.")


def msg_pausa(unidade, n, gatilho):
    if gatilho:
        religar = f"Para religar depois de corrigir: sudo systemctl start {gatilho}"
        estado = "e foi PAUSADA para não ficar tentando sem fim nem gastar crédito do Claude"
    else:
        religar = "Ela não tem timer para pausar; confira o que a dispara"
        estado = "e continua falhando"
    return (f"A rotina {unidade} falhou {n} vezes seguidas no lenovo-claude {estado}. "
            f"Ver journalctl -u {unidade}. {religar}.")


def _rodar(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout


def gatilho_de(unidade, rodar=_rodar):
    """Timer ou .path que dispara a unidade (o primeiro que houver)."""
    cod, saida = rodar(["systemctl", "show", unidade, "-p", "TriggeredBy", "--value"])
    if cod != 0:
        return None
    for nome in saida.split():
        if nome.endswith((".timer", ".path")):
            return nome
    return None


def ligado_desde(gatilho, rodar=_rodar):
    """Momento (@segundos) em que o timer foi ligado pela última vez, ou None."""
    cod, saida = rodar(["systemctl", "show", gatilho, "-p", "ActiveEnterTimestamp",
                        "--timestamp=unix", "--value"])
    saida = saida.strip()
    if cod != 0 or not saida.startswith("@"):
        return None
    return saida


def linhas_do_log(unidade, desde, rodar=_rodar):
    cmd = ["journalctl", "_PID=1", f"UNIT={unidade}", "-o", "cat", "--no-pager"]
    if desde:
        cmd += ["--since", desde]
    cod, saida = rodar(cmd)
    return saida.splitlines() if cod == 0 else []


def notificar(msg):
    cmd = [sys.executable, str(RAIZ / "scripts" / "notificar.py"), "--falha", msg]
    if os.geteuid() == 0:
        cmd = ["runuser", "-u", USUARIO, "--"] + cmd
    subprocess.run(cmd, cwd=RAIZ, timeout=120)


def main(argv=None, rodar=_rodar, avisar=notificar):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("uso: limite_falhas.py <unidade.service>", file=sys.stderr)
        return 2
    unidade = argv[0]
    limite = limite_de(unidade)
    try:
        gatilho = gatilho_de(unidade, rodar)
        desde = ligado_desde(gatilho, rodar) if gatilho else None
        n = falhas_seguidas(linhas_do_log(unidade, desde, rodar))
    except Exception as e:  # na dúvida, avisa como antes
        print(f"limite_falhas: não li o log ({e!r}); aviso normal", flush=True)
        gatilho, n = None, 1
    decisao = decidir(n, limite)
    print(f"limite_falhas: {unidade}: {n} falha(s) seguida(s), limite {limite}, "
          f"gatilho {gatilho or 'nenhum'} -> {decisao}", flush=True)
    if decisao == "avisar":
        avisar(msg_aviso(unidade, limite))
    elif decisao == "pausar":
        pausou = False
        if gatilho:
            cod, _ = rodar(["systemctl", "stop", gatilho])
            pausou = cod == 0
            print(f"limite_falhas: parar {gatilho}: {'ok' if pausou else 'FALHOU'}", flush=True)
        avisar(msg_pausa(unidade, n, gatilho if pausou else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
