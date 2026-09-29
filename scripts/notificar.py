#!/usr/bin/env python3
"""
Alerta do fim do ciclo: push pelo ntfy.sh e e-mail por SMTP.

Uso:
  python3 scripts/notificar.py                  # alerta da analise do ciclo
  python3 scripts/notificar.py --falha "msg"    # alerta urgente de falha

Le dados/analise_status.json e analises/<data>-<turno>.md (ou <data>.md no
formato antigo). Configuracao so por variavel de ambiente (o repositorio e
publico; segredo fica no .env, carregado pelo systemd):
  NTFY_TOPICO, NTFY_SERVIDOR (padrao https://ntfy.sh),
  SMTP_HOST, SMTP_PORTA (587), SMTP_USUARIO, SMTP_SENHA, EMAIL_PARA (virgulas),
  PAINEL_URL.
Canal sem configuracao e pulado. Sempre sai 0: alerta e acessorio, nunca pode
derrubar o ciclo que o chamou -- o que aconteceu vai para o stderr.
"""
import html
import json
import os
import re
import smtplib
import sys
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PAINEL_PADRAO = "https://rodrigokratzer.github.io/reforma-tributaria-monitor/"
NTFY_PADRAO = "https://ntfy.sh"
# ntfy aceita ate 4096 bytes de mensagem; folga para acento (2 bytes em UTF-8)
LIMITE_CORPO = 3500
LIMITE_TRECHO = 600
PRIORIDADES = {"min": 1, "low": 2, "default": 3, "high": 4, "urgent": 5}
TITULO_FALHA = "Monitor da Reforma: falha no ciclo"


def log(texto):
    print(f"notificar: {texto}", file=sys.stderr)


def _corta(texto, limite):
    if len(texto) <= limite:
        return texto
    return texto[:limite - 1].rstrip() + "…"


def _sem_markdown(texto):
    texto = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", texto)  # [t](url) -> t
    texto = texto.replace("**", "").replace("`", "")
    texto = re.sub(r"^#+\s*", "", texto, flags=re.M)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def trecho_acao(md):
    """Texto da secao "Acao requerida" (ate o proximo titulo), sem markdown."""
    if not md:
        return ""
    m = re.search(r"^#+\s*A[çc][ãa]o requerida\s*$(.*?)(?=^#+\s|\Z)", md,
                  flags=re.M | re.S | re.I)
    if not m:
        return ""
    return _corta(_sem_markdown(m.group(1)), LIMITE_TRECHO)


def _data_curta(data):
    # "2026-09-30" -> "30/09"; qualquer outra coisa passa como veio
    m = re.match(r"^\d{4}-(\d{2})-(\d{2})$", data or "")
    return f"{m.group(2)}/{m.group(1)}" if m else (data or "?")


def _acoes(status):
    # status antigo nao tem "acoes"; valor torto vale 0 em vez de derrubar
    try:
        return max(int(status.get("acoes") or 0), 0)
    except (TypeError, ValueError):
        return 0


def _turno(status):
    turno = status.get("turno") or ""
    return "" if turno == "unica" else turno


def _id_analise(status):
    turno = _turno(status)
    data = status.get("data") or ""
    return f"{data}-{turno}" if turno else data


def monta_mensagem(status, md_texto, painel_url):
    acoes = _acoes(status)
    situacao = status.get("situacao") or ""
    if acoes > 0:
        prioridade = "high"
        descricao = f"{acoes} exige ação" if acoes == 1 else f"{acoes} exigem ação"
    elif situacao == "sem_novidade":
        prioridade = "low"
        descricao = "sem novidade"
    else:
        prioridade = "default"
        descricao = {"publicada": "análise publicada",
                     "dados_pendentes": "dados pendentes"}.get(situacao, situacao or "análise")

    quando = " ".join(p for p in (_data_curta(status.get("data")), _turno(status)) if p)
    click = painel_url + "#analise=" + _id_analise(status)
    resumo = (status.get("resumo_curto") or "").strip() or descricao
    partes = [_corta(resumo, 1000)]
    trecho = trecho_acao(md_texto)
    if trecho:
        partes.append(trecho)
    corpo = "\n\n".join(partes)
    corpo = _corta(corpo, LIMITE_CORPO - len(click) - 2) + "\n\n" + click

    return {
        "titulo": f"Reforma Tributária · {quando} — {descricao}",
        "assunto": ("⚠ " if acoes > 0 else "") + f"[Reforma Tributária] {quando} — {descricao}",
        "corpo": corpo,
        "prioridade": prioridade,
        "click": click,
        "tags": ["warning"] if acoes > 0 else [],
        # sem o .md (arquivo nao existe), o e-mail usa o proprio corpo
        "md": md_texto,
    }


def monta_falha(mensagem, painel_url):
    corpo = _corta(mensagem or "falha sem detalhe", LIMITE_CORPO - len(painel_url) - 2)
    return {
        "titulo": TITULO_FALHA,
        "assunto": "⚠ " + TITULO_FALHA,
        "corpo": corpo + "\n\n" + painel_url,
        "prioridade": "urgent",
        "click": painel_url,
        "tags": ["warning"],
        "md": None,
    }


def envia_ntfy(msg, topico, servidor=NTFY_PADRAO):
    # JSON publish (POST na raiz do servidor): titulo com acento num header
    # HTTP daria problema de codificacao; no corpo JSON e UTF-8 puro.
    payload = {
        "topic": topico,
        "title": msg["titulo"],
        "message": msg["corpo"],
        "priority": PRIORIDADES.get(msg["prioridade"], 3),
        "click": msg["click"],
    }
    if msg.get("tags"):
        payload["tags"] = msg["tags"]
    try:
        req = urllib.request.Request(
            (servidor or NTFY_PADRAO).rstrip("/"),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = getattr(resp, "status", 200)
            if not 200 <= int(status) < 300:
                log(f"ntfy respondeu {status}")
                return False
        return True
    except Exception as e:  # rede, DNS, HTTPError: nada disso pode subir
        log(f"ntfy falhou: {e}")
        return False


def config_email(env):
    """Configuracao SMTP a partir do ambiente, ou None se incompleta."""
    obrig = ("SMTP_HOST", "SMTP_USUARIO", "SMTP_SENHA", "EMAIL_PARA")
    if not all((env.get(k) or "").strip() for k in obrig):
        return None
    para = [e.strip() for e in env["EMAIL_PARA"].split(",") if e.strip()]
    if not para:
        return None
    try:
        porta = int(env.get("SMTP_PORTA") or 587)
    except ValueError:
        porta = 587
    return {"host": env["SMTP_HOST"].strip(), "porta": porta,
            "usuario": env["SMTP_USUARIO"].strip(), "senha": env["SMTP_SENHA"],
            "para": para}


def _html(msg):
    import markdown  # so o e-mail precisa; import tardio nao derruba o push
    md = msg.get("md") or msg["corpo"]
    conteudo = markdown.markdown(md)
    url = html.escape(msg["click"], quote=True)
    link = (f'<p style="margin-top:24px"><a href="{url}" '
            f'style="color:#1a56db">Abrir no painel</a> · {url}</p>')
    return ('<!doctype html><html><body style="margin:0;padding:16px;'
            'font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;'
            'font-size:15px;line-height:1.5;color:#1f2328;background:#ffffff">'
            f'<div style="max-width:720px">{conteudo}{link}</div></body></html>')


def envia_email(msg, cfg):
    try:
        email = MIMEMultipart("alternative")
        email["Subject"] = msg["assunto"]
        email["From"] = cfg["usuario"]
        email["To"] = ", ".join(cfg["para"])
        texto = (msg.get("md") or msg["corpo"])
        if msg["click"] not in texto:
            texto += "\n\n" + msg["click"]
        email.attach(MIMEText(texto, "plain", "utf-8"))
        email.attach(MIMEText(_html(msg), "html", "utf-8"))
        with smtplib.SMTP(cfg["host"], cfg["porta"], timeout=60) as smtp:
            smtp.starttls()
            smtp.login(cfg["usuario"], cfg["senha"])
            smtp.sendmail(cfg["usuario"], cfg["para"], email.as_string())
        return True
    except Exception as e:  # SMTP, auth, rede, markdown: nada disso pode subir
        log(f"e-mail falhou: {e}")
        return False


def _le_status(raiz):
    caminho = raiz / "dados" / "analise_status.json"
    try:
        status = json.loads(caminho.read_text("utf-8"))
    except FileNotFoundError:
        log(f"{caminho} nao existe; nada a notificar")
        return None
    except (OSError, ValueError) as e:
        log(f"{caminho} ilegivel ({e}); nada a notificar")
        return None
    if not isinstance(status, dict) or not status.get("data"):
        log(f"{caminho} sem campo data; nada a notificar")
        return None
    return status


def _le_md(raiz, status):
    caminho = raiz / "analises" / f"{_id_analise(status)}.md"
    try:
        return caminho.read_text("utf-8")
    except OSError:
        log(f"{caminho} nao encontrado; mensagem so com o status")
        return None


def _envia(msg, env):
    topico = (env.get("NTFY_TOPICO") or "").strip()
    if topico:
        ok = envia_ntfy(msg, topico, (env.get("NTFY_SERVIDOR") or "").strip() or NTFY_PADRAO)
        log("ntfy: enviado" if ok else "ntfy: falhou")
    else:
        log("ntfy: pulado (NTFY_TOPICO vazio)")
    cfg = config_email(env)
    if cfg:
        ok = envia_email(msg, cfg)
        log("e-mail: enviado" if ok else "e-mail: falhou")
    else:
        log("e-mail: pulado (SMTP_* / EMAIL_PARA incompletos)")


def main(argv=None, raiz=None, env=None):
    try:
        argv = sys.argv[1:] if argv is None else argv
        raiz = RAIZ if raiz is None else Path(raiz)
        env = os.environ if env is None else env
        painel = (env.get("PAINEL_URL") or "").strip() or PAINEL_PADRAO
        if argv and argv[0] == "--falha":
            msg = monta_falha(" ".join(argv[1:]), painel)
        else:
            status = _le_status(raiz)
            if status is None:
                return 0
            msg = monta_mensagem(status, _le_md(raiz, status), painel)
        _envia(msg, env)
    except Exception as e:  # rede de seguranca final: nunca derrubar o ciclo
        log(f"erro inesperado: {e!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
