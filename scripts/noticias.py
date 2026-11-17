#!/usr/bin/env python3
"""
Coletor de noticias (camada Fatos): feeds RSS/Atom de economia dos portais.

So' stdlib (urllib + xml.etree), sem IA e sem julgamento: le os feeds, limpa o
HTML da linha fina e grava pelos caminhos de sempre (varredura.grava_resultado),
em arquivos proprios para nao disputar arquivo com os outros coletores:

  dados/AAAA-MM-DD-noticias.json   status e itens da execucao, por feed
  dados/novidades_noticias.json    o que apareceu pela primeira vez
  dados/historico.json             indice acumulado (chave = portais.base.chave)

Cada item leva tipo "noticia" (o que o distingue de publicacao oficial em todo
o codigo: a raia de leitura as ignora e a lacuna nunca as segura). So' entra
noticia publicada ha' no maximo JANELA_H horas (feed velho nao inunda o
historico); item sem data entra. Um feed que falha registra `erro` e os outros
seguem.

Uso: python3 scripts/noticias.py
Saida: 0 se ao menos um feed respondeu, 1 se todos falharam.
"""
import datetime
import email.utils
import gzip
import html
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portais.base import UA, chave

TIMEOUT_S = 20
JANELA_H = 36
TETO_EMENTA = 600

try:
    from zoneinfo import ZoneInfo
    TZ_BR = ZoneInfo("America/Sao_Paulo")
except Exception:  # sem base de fusos: o Brasil nao tem horario de verao desde 2019
    TZ_BR = datetime.timezone(datetime.timedelta(hours=-3))

# Feeds testados ao vivo em 17/11/2026. `filtro` (opcional) e' um regex casado
# contra "<caminho da URL> | <categorias do item>" — nunca contra o dominio —
# para tirar de um feed geral o que nao e' economia; `excluir` (opcional), o
# mesmo, para descartar (ex.: conteudo patrocinado).
#
# Descartados (17/11/2026):
#   CNN Brasil economia: /economia/feed/ e variantes dao 404 -> feed geral com filtro
#   Exame economia: /economia/feed/ da' 404 -> feed geral com filtro
#   Poder360 economia: /economia/feed/ redireciona para HTML; /category/economia/feed/
#     parou em 2025 -> feed geral com filtro pela categoria "Poder Economia"
#   Agencia Gov (agenciagov.ebc.com.br/noticias/rss.xml): itens sem link, ultimo de
#     marco/2026; gov.br/agenciagov/RSS da' 404
#   Agencia Senado: nao ha' feed por tema (rss/temas/economia da' 404) -> feed geral
#     (15 itens, muita pauta fiscal/tributaria), sem filtro
#   IstoE Dinheiro: resposta vazia
FEEDS = [
    {"fonte": "g1 Economia", "url": "https://g1.globo.com/rss/g1/economia/"},
    {"fonte": "Folha Mercado", "url": "https://feeds.folha.uol.com.br/mercado/rss091.xml"},
    {"fonte": "Estadão Economia",
     "url": "https://www.estadao.com.br/arc/outboundfeeds/feeds/rss/sections/economia/"},
    {"fonte": "InfoMoney", "url": "https://www.infomoney.com.br/feed/"},
    {"fonte": "Valor Econômico", "url": "https://valor.globo.com/rss/valor",
     "excluir": r"^/patrocinado/"},
    {"fonte": "CNN Brasil Economia", "url": "https://www.cnnbrasil.com.br/feed/",
     "filtro": r"^/economia/"},
    {"fonte": "Agência Brasil Economia",
     "url": "https://agenciabrasil.ebc.com.br/rss/economia/feed.xml"},
    {"fonte": "Exame", "url": "https://exame.com/feed/",
     "filtro": r"^/(economia|invest|negocios|pme|brasil|mercado-imobiliario|agro)/"},
    {"fonte": "UOL Economia", "url": "https://rss.uol.com.br/feed/economia.xml"},
    {"fonte": "Poder360 Economia", "url": "https://www.poder360.com.br/feed/",
     "filtro": r"^/poder-economia/|Poder Economia"},
    {"fonte": "Agência Senado", "url": "https://www12.senado.leg.br/noticias/rss"},
    {"fonte": "Agência Câmara Economia",
     "url": "https://www.camara.leg.br/noticias/rss/dinamico/ECONOMIA"},
]

ATOM = "{http://www.w3.org/2005/Atom}"
DC = "{http://purl.org/dc/elements/1.1/}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}"


# ------------------------------------------------------------------ rede

def baixa(url):
    """(status HTTP, bytes). Testes trocam esta funcao (sem rede nos testes)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        "Accept-Language": "pt-BR,pt;q=0.9"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        corpo = r.read()
        if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
            corpo = gzip.decompress(corpo)
        return r.status, corpo


# ------------------------------------------------------------------ parsing

class _Texto(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes = []

    def handle_data(self, d):
        self.partes.append(d)

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "p", "div", "li"):
            self.partes.append(" ")


def sem_html(s, teto=TETO_EMENTA):
    """Texto puro de um trecho HTML (linha fina do RSS), espacos colapsados,
    cortado em `teto` caracteres na fronteira de palavra."""
    if not s:
        return ""
    p = _Texto()
    try:
        p.feed(s)
        p.close()
        t = "".join(p.partes)
    except Exception:
        t = re.sub(r"<[^>]+>", " ", s)
    t = re.sub(r"\s+", " ", html.unescape(t)).strip()
    if len(t) > teto:
        t = t[:teto].rsplit(" ", 1)[0].rstrip(" ,;:.") + "…"
    return t


def _xml(corpo):
    """Arvore do feed. Feed em latin-1 sem declaracao (UOL) quebra o parser
    em bytes: tenta de novo decodificando como cp1252."""
    corpo = corpo.lstrip(b"\xef\xbb\xbf \t\r\n")
    try:
        return ET.fromstring(corpo)
    except ET.ParseError:
        try:
            corpo.decode("utf-8")
            raise
        except UnicodeDecodeError:
            pass
        texto = re.sub(r"^<\?xml[^>]*\?>", "", corpo.decode("cp1252", "replace"))
        return ET.fromstring(texto)


def quando(s):
    """Data do feed (RFC 822 do RSS ou ISO 8601 do Atom/dc:date) -> datetime
    com fuso. Ilegivel -> None.

    RFC 822 com "-0000" (g1, Valor) vem sem fuso do parsedate, mas e' UTC
    (conferido contra a hora da materia). ISO sem fuso (Exame) e' Brasilia."""
    s = (s or "").strip()
    if not s:
        return None
    try:
        d = email.utils.parsedate_to_datetime(s)
        return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass
    try:
        d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=TZ_BR)


def _txt(el, *tags):
    for t in tags:
        v = el.findtext(t)
        if v and v.strip():
            return v.strip()
    return ""


def _entradas(raiz):
    """[(titulo, url, data_bruta, descricao_html, categorias)] de RSS 2.0/0.91
    ou Atom."""
    out = []
    itens = list(raiz.iter("item"))
    if itens:
        for it in itens:
            cats = [c.text.strip() for c in it.findall("category") if c.text]
            out.append((_txt(it, "title"), _txt(it, "link", "guid"),
                        _txt(it, "pubDate", DC + "date"),
                        _txt(it, "description", CONTENT + "encoded"), cats))
        return out
    for e in raiz.iter(ATOM + "entry"):
        link = ""
        for l in e.findall(ATOM + "link"):
            if l.get("rel", "alternate") == "alternate" and l.get("href"):
                link = l.get("href")
                break
        cats = [c.get("term") or c.get("label") for c in e.findall(ATOM + "category")]
        out.append((_txt(e, ATOM + "title"), link,
                    _txt(e, ATOM + "published", ATOM + "updated"),
                    _txt(e, ATOM + "summary", ATOM + "content"),
                    [c for c in cats if c]))
    return out


def url_final(url):
    """Folha embrulha o link num redirecionador
    (redir.folha.com.br/redir/online/mercado/rss091/*https://www1...): fica o
    destino, que e' o link estavel da materia."""
    i = url.find("/*http")
    return url[i + 2:] if i >= 0 else url


def itens_do_feed(corpo, filtro=None, agora=None, janela_h=JANELA_H, excluir=None):
    """Itens no formato do Contrato 1 (sem `fonte` e `primeira_vez`, que
    grava_resultado acrescenta), ja' filtrados pela janela de tempo."""
    agora = agora or datetime.datetime.now(datetime.timezone.utc)
    limite = agora - datetime.timedelta(hours=janela_h)
    rx = re.compile(filtro, re.I) if filtro else None
    rx_fora = re.compile(excluir, re.I) if excluir else None
    out = []
    for titulo, url, bruta, desc, cats in _entradas(_xml(corpo)):
        titulo, url = sem_html(titulo, teto=400), url_final(url)
        if not titulo or not url:
            continue
        alvo = urllib.parse.urlsplit(url).path + " | " + " ; ".join(cats)
        if (rx and not rx.search(alvo)) or (rx_fora and rx_fora.search(alvo)):
            continue
        d = quando(bruta)
        if d is not None and d < limite:
            continue
        local = d.astimezone(TZ_BR) if d else None
        out.append({"tipo": "noticia", "titulo": titulo, "url": url,
                    "data": local.date().isoformat() if local else None,
                    "publicado_em": local.isoformat(timespec="seconds") if local else None,
                    "ementa": sem_html(desc)})
    return out


# ------------------------------------------------------------------ coleta

def coleta_feed(feed, agora=None):
    """Registro da fonte no formato dos outros coletores. Nunca levanta."""
    r = {"fonte": feed["fonte"], "url": feed["url"], "metodo": None,
         "http_status": None, "total": 0, "erro": None, "itens": []}
    try:
        status, corpo = baixa(feed["url"])
        r["http_status"] = status
        itens = itens_do_feed(corpo, feed.get("filtro"), agora,
                              excluir=feed.get("excluir"))
    except Exception as e:
        r["http_status"] = r["http_status"] or getattr(e, "code", None)
        r["erro"] = f"{type(e).__name__}: {str(e)[:150]}"
        return r
    r.update(metodo="rss", itens=itens, total=len(itens))
    return r


def coleta(feeds=None, agora=None):
    """Um registro por feed; o mesmo item (mesma chave ou mesma URL) em dois
    feeds fica so' no primeiro."""
    resultado, vistos = [], set()
    for feed in FEEDS if feeds is None else feeds:
        r = coleta_feed(feed, agora)
        unicos = []
        for it in r["itens"]:
            ids = (chave(it), it["url"])
            if any(i in vistos for i in ids):
                continue
            vistos.update(ids)
            unicos.append(it)
        r["itens"], r["total"] = unicos, len(unicos)
        resultado.append(r)
        print(f"  {r['fonte']:28} metodo={r['metodo'] or 'FALHOU':6} itens={r['total']:3} "
              f"http={r['http_status']}" + (f"  [{r['erro']}]" if r["erro"] else ""),
              file=sys.stderr)
    return resultado


def main():
    import varredura  # importa so' aqui: grava em dados/ do repositorio
    hoje = os.environ.get("DATA_REF") or datetime.date.today().isoformat()
    resultado = coleta()
    varredura.grava_resultado(hoje, resultado, f"{hoje}-noticias.json",
                              "novidades_noticias.json")
    return 0 if any(r["metodo"] for r in resultado) else 1


if __name__ == "__main__":
    sys.exit(main())
