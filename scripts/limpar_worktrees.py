#!/usr/bin/env python3
"""Limpeza semanal das worktrees das sessoes de consulta (reforma-consulta.service).

Cada sessao aberta pelo app nasce numa worktree em .claude/worktrees/. Remove
so' as que estao ao mesmo tempo: dentro de DIR_WORKTREES, fora de PROTEGIDAS,
sem mudanca pendente, sem commit fora do main e sem atividade ha'
DIAS_WORKTREE dias. Nunca usa --force. As com trabalho pendente ficam e
geram um aviso (notificar.py --aviso).

Uso: python3 scripts/limpar_worktrees.py [--aplicar]   (sem --aplicar: so' lista)
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIR_WORKTREES = ".claude/worktrees"
DIAS_WORKTREE = 7
PROTEGIDAS = {"migracao-notebook-local"}


def _git(*a, cwd):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout


def _worktrees(raiz):
    out, atual = [], {}
    for linha in _git("worktree", "list", "--porcelain", cwd=raiz).splitlines() + [""]:
        if not linha:
            if atual:
                out.append(atual)
            atual = {}
        elif linha.startswith("worktree "):
            atual["caminho"] = linha[9:]
        elif linha.startswith("branch "):
            atual["branch"] = linha[7:].removeprefix("refs/heads/")
        elif linha == "locked" or linha.startswith("locked "):
            atual["travada"] = True
        elif linha == "prunable" or linha.startswith("prunable "):
            atual["prunable"] = True
    return out


def _ultima_atividade(caminho):
    alvos = [Path(caminho)]
    try:
        alvos.append(Path(_git("rev-parse", "--git-path", "index", cwd=caminho).strip()))
        alvos.append(Path(_git("rev-parse", "--git-path", "HEAD", cwd=caminho).strip()))
    except subprocess.CalledProcessError:
        pass
    ts = []
    for p in alvos:
        p = p if p.is_absolute() else Path(caminho) / p
        if p.exists():
            ts.append(p.stat().st_mtime)
    return max(ts) if ts else 0


def _em_uso(caminho):
    """True se algum processo vivo tem o cwd dentro da worktree (sessao aberta)."""
    c = Path(caminho).resolve()
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            link = Path(os.readlink(d / "cwd"))
        except (PermissionError, FileNotFoundError, ProcessLookupError, OSError):
            continue
        if link == c or c in link.parents:
            return True
    return False


def candidatas(raiz, agora):
    raiz = Path(raiz).resolve()
    base = (raiz / DIR_WORKTREES).resolve()
    remover, pendentes = [], []
    for w in _worktrees(raiz):
        c = Path(w["caminho"]).resolve()
        if c == raiz or base not in c.parents or c.name in PROTEGIDAS:
            continue
        if w.get("prunable") or not c.exists():
            continue  # sumida: o worktree prune cuida
        if w.get("travada"):
            print(f"ignorada: {c} (travada)")
            continue
        if _em_uso(c):
            print(f"ignorada: {c} (em uso)")
            continue
        if (agora - _ultima_atividade(c)) < DIAS_WORKTREE * 86400:
            continue
        sujo = _git("status", "--porcelain", cwd=c).strip()
        fora = _git("rev-list", "--count", "main..HEAD", cwd=c).strip()
        item = {"caminho": str(c), "branch": w.get("branch")}
        if sujo or fora != "0":
            item["motivo"] = "mudanca pendente" if sujo else f"{fora} commit(s) fora do main"
            pendentes.append(item)
        else:
            item["motivo"] = "limpa e integrada"
            remover.append(item)
    return remover, pendentes


def _notifica(msg):
    subprocess.run([sys.executable, str(RAIZ / "scripts" / "notificar.py"), "--aviso", msg],
                   check=False)


def main(argv=None, raiz=RAIZ, notificar=_notifica):
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    a = ap.parse_args(argv)
    agora = float(os.environ.get("LIMPAR_AGORA") or time.time())
    remover, pendentes = candidatas(raiz, agora)
    for w in remover:
        print(f"{'removendo' if a.aplicar else 'removeria'}: {w['caminho']} ({w['motivo']})")
        if a.aplicar:
            _git("worktree", "remove", w["caminho"], cwd=raiz)
            if w.get("branch"):
                _git("branch", "-d", w["branch"], cwd=raiz)
    for w in pendentes:
        print(f"mantida: {w['caminho']} ({w['motivo']})")
    if a.aplicar:
        _git("worktree", "prune", cwd=raiz)
        if pendentes:
            notificar(f"{len(pendentes)} worktree(s) de consulta com trabalho pendente: "
                      + "; ".join(f"{Path(w['caminho']).name} ({w['motivo']})" for w in pendentes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
