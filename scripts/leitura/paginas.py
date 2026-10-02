#!/usr/bin/env python3
"""Corpo integral de paginas HTML, com regra por dominio.

  cgibs.gov.br    -> <div class="artigo__texto"> (veio de portais/cgibs.py)
  *.gov.br (Plone)-> resumo <div class="documentDescription"> +
                     corpo <div id="parent-fieldname-text">
  qualquer outro  -> <article>, <main>, #content, #conteudo, <body>, nessa
                     ordem, descartando nav/header/footer/aside/form

Devolve tambem os links de anexo achados DENTRO do corpo: nas noticias do
gov.br o conteudo de verdade as vezes esta' num PDF anexo, e ler so' o HTML
nao e' leitura integral.
"""
import re
import urllib.parse
from html.parser import HTMLParser

MINIMO_GENERICO = 200   # abaixo disto o "corpo" generico e' casca, nao conteudo


class _Bloco(HTMLParser):
    """Texto (e links) dentro do primeiro elemento <tag> que casa com `casa`.

    Conta a profundidade so' da propria tag-alvo para saber onde o bloco
    termina. Trade-off herdado do extrator do CGIBS: se o bloco tiver uma
    tag-alvo aberta e nunca fechada, a contagem nao zera e o extrator segue
    ate' o fim do documento — sobre-captura, nunca texto truncado.
    Links malformados (e.g. href="http://[bad") sao silenciosamente ignorados.
    """
    IGNORA_SEMPRE = {"script", "style", "noscript", "template"}
    QUEBRA = {"p", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
              "blockquote", "hr", "table", "td", "div", "section", "article"}

    def __init__(self, base, tag, casa, ignora_extra=()):
        super().__init__(convert_charrefs=True)
        self.base, self.tag, self.casa = base, tag, casa
        self.ignora = self.IGNORA_SEMPRE | set(ignora_extra)
        self._prof, self._ign = 0, 0
        self._dentro, self._feito = False, False
        self._buf, self.links = [], []

    def handle_starttag(self, tag, attrs):
        if self._feito:
            return
        a = dict(attrs)
        if not self._dentro:
            if tag == self.tag and self.casa(a):
                self._dentro, self._prof = True, 1
            return
        if tag == self.tag:
            self._prof += 1
        if tag in self.ignora:
            self._ign += 1
        if tag in self.QUEBRA:
            self._buf.append("\n")
        if tag == "a" and a.get("href") and not self._ign:
            try:
                self.links.append(urllib.parse.urljoin(self.base, a["href"]))
            except ValueError:
                pass        # href malformado, ignorado

    def handle_startendtag(self, tag, attrs):
        if self._dentro and not self._feito and tag in self.QUEBRA:
            self._buf.append("\n")

    def handle_endtag(self, tag):
        if not self._dentro or self._feito:
            return
        if tag in self.ignora and self._ign:
            self._ign -= 1
        if tag == self.tag:
            self._prof -= 1
            if self._prof <= 0:
                self._dentro, self._feito = False, True

    def handle_data(self, data):
        if self._dentro and not self._feito and not self._ign:
            self._buf.append(data)

    def texto(self):
        t = "".join(self._buf)
        t = re.sub(r"[ \t\r\f\v]+", " ", t)
        t = re.sub(r"\n[ \t]*\n[ \t]*(\n[ \t]*)*", "\n\n", t)
        return t.strip()


def _extrai(html, base, tag, casa, ignora_extra=()):
    if not html:
        return None, []
    p = _Bloco(base, tag, casa, ignora_extra)
    try:
        p.feed(html)
        p.close()
    except Exception:
        pass        # devolve o que ja' capturou
    t = p.texto()
    return (t or None), p.links


def _classe(nome):
    return lambda a: nome in (a.get("class") or "").split()


def _id(nome):
    return lambda a: a.get("id") == nome


def _qualquer(a):
    return True


def extrai_artigo_cgibs(html, base=""):
    return _extrai(html, base, "div", _classe("artigo__texto"))


def extrai_govbr(html, base=""):
    resumo, _ = _extrai(html, base, "div", _classe("documentDescription"))
    corpo, links = _extrai(html, base, "div", _id("parent-fieldname-text"))
    if not corpo:
        return None, []
    return (f"{resumo}\n\n{corpo}" if resumo else corpo), links


SEM_CONTEUDO = ("nav", "header", "footer", "aside")


def extrai_generico(html, base=""):
    for tag, casa in (("article", _qualquer), ("main", _qualquer),
                      ("div", _id("content")), ("div", _id("conteudo")),
                      ("body", _qualquer)):
        t, links = _extrai(html, base, tag, casa, SEM_CONTEUDO)
        if t and len(t) >= MINIMO_GENERICO:
            return t, links
    return None, []


def eh_anexo(url):
    p = urllib.parse.urlparse(url).path.lower()
    return (p.endswith(".pdf") or "/upload/arquivos/" in p
            or "@@download" in p or p.endswith("exibirarquivo.aspx"))


def extrai_pagina(url, html):
    """(texto | None, [anexos]) — regra pelo dominio, generico como reserva."""
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    texto, links = None, []
    if host == "cgibs.gov.br" or host.endswith(".cgibs.gov.br"):
        texto, links = extrai_artigo_cgibs(html, url)
    elif host == "gov.br" or host.endswith(".gov.br"):
        texto, links = extrai_govbr(html, url)
    if not texto:
        texto, links = extrai_generico(html, url)
    proprio = url.split("#")[0]
    anexos = []
    for l in links:
        l = l.split("#")[0]
        if eh_anexo(l) and l != proprio and l not in anexos:
            anexos.append(l)
    return texto, anexos
