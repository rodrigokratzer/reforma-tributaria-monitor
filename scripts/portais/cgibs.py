#!/usr/bin/env python3
"""Portal do CGIBS (cgibs.gov.br).

Alem do comportamento padrao de Portal, captura o corpo das noticias em
HTML — mesma ideia que a Parte A trouxe para o DOU, para que a analise
diaria leia o texto do repo em vez de depender de busca externa (bloqueada
no sandbox da rotina). As paginas de artigo do CGIBS vem renderizadas no
HTML, entao via_http puro basta. Links de PDF (/upload/arquivos/...) nao
sao lidos: o repo nao tem biblioteca de PDF, e o item fica sem `texto`,
como ja acontecia.
"""
import re, sys, time, urllib.parse
from html.parser import HTMLParser

from portais.base import Portal, via_http, HTTP_TIMEOUT_S

MARGEM_ORCAMENTO_S = 45   # nao inicia uma extracao se falta menos que isto
TETO_TEXTO = 20000        # teto defensivo, igual ao do DOU (dou.artigos)


class _ExtratorArtigo(HTMLParser):
    """Captura o texto dentro de <div class="artigo__texto">.

    Rastreia a profundidade de <div> desde o alvo para saber onde o corpo
    termina; ignora <script>/<style>; trata tags de bloco como quebra de
    linha para o texto nao ficar grudado.
    """
    ALVO = "artigo__texto"
    IGNORA = {"script", "style"}
    QUEBRA = {"p", "br", "li", "tr", "h1", "h2", "h3", "h4", "div"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._prof = 0
        self._dentro = False
        self._ignora = 0
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if not self._dentro:
            if tag == "div":
                classes = (dict(attrs).get("class") or "").split()
                if self.ALVO in classes:
                    self._dentro = True
                    self._prof = 1
            return
        if tag == "div":
            self._prof += 1
        if tag in self.IGNORA:
            self._ignora += 1
        if tag in self.QUEBRA:
            self._buf.append("\n")

    def handle_startendtag(self, tag, attrs):
        if self._dentro and tag in self.QUEBRA:
            self._buf.append("\n")

    def handle_endtag(self, tag):
        if not self._dentro:
            return
        if tag in self.IGNORA and self._ignora:
            self._ignora -= 1
        if tag == "div":
            self._prof -= 1
            if self._prof <= 0:
                self._dentro = False

    def handle_data(self, data):
        if self._dentro and not self._ignora:
            self._buf.append(data)

    def texto(self):
        t = "".join(self._buf)
        t = re.sub(r"[ \t]+", " ", t)
        t = re.sub(r"\n[ \t]*\n[ \t]*(\n[ \t]*)*", "\n\n", t)
        return t.strip()


def _extrai_do_html(html):
    """Corpo do artigo, ou None se a pagina nao tiver <div artigo__texto>."""
    if not html:
        return None
    p = _ExtratorArtigo()
    try:
        p.feed(html)
        p.close()
    except Exception:
        return None
    if p._dentro:            # <div artigo__texto> nunca fechou: HTML quebrado
        return None
    t = p.texto()
    return t[:TETO_TEXTO] if t else None


class CGIBSPortal(Portal):
    """As secoes do site do CGIBS. Uma instancia por URL de listagem."""

    def extrai_texto(self, ctx, item, limite=None):
        url = item.get("url") or ""
        caminho = urllib.parse.urlparse(url).path.lower()
        if caminho.endswith(".pdf") or "/upload/arquivos/" in caminho:
            return None
        if limite is not None and time.monotonic() > limite - MARGEM_ORCAMENTO_S:
            return None
        html, status, err = via_http(url, timeout=HTTP_TIMEOUT_S)
        if not html:
            print(f"      CGIBS extrai_texto: {url} -> http {status} "
                  f"{err or ''}", file=sys.stderr)
            return None
        return _extrai_do_html(html)
