#!/usr/bin/env python3
"""Portal DF-e SVRS — noticias.

As noticias nao sao links: ficam inteiras na propria listagem, cada uma num
<article class="conteudo-lista__item"> com titulo <a href="#">. O coletor
generico de links pegava so' rotulos de categoria e URLs soltas no corpo;
as noticias em si nunca entravam. Aqui cada <article> vira um item, com o
corpo como texto_integral (grava_resultado o leva para dados/textos/).

A pagina traz o historico inteiro (paginacao no navegador); so' as
MAX_NOTICIAS primeiras (mais recentes) sao consideradas.
"""
import re
from html.parser import HTMLParser

from leitura.baixar import ErroDownload, Sessao
from portais.base import Portal, RELEVANTE, extrai_data, monta_item

MAX_NOTICIAS = 30


class _Noticias(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.noticias = []
        self._art = 0          # profundidade de <article>
        self._cab = False
        self._em = None        # "time" | "titulo" | None
        self._atual = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "article":
            if self._art == 0 and "conteudo-lista__item" in (a.get("class") or ""):
                self._atual = {"id": "", "titulo": [], "data": [], "corpo": []}
            if self._atual is not None:
                self._art += 1
            return
        if self._atual is None:
            return
        if tag == "header":
            self._cab = True
        elif tag == "time":
            self._em = "data"
        elif tag == "a" and self._cab and a.get("id"):
            self._atual["id"] = a["id"].lstrip("#")
            self._em = "titulo"
        elif tag in ("p", "br", "li") and not self._cab:
            self._atual["corpo"].append("\n")

    def handle_endtag(self, tag):
        if self._atual is None:
            return
        if tag == "article":
            self._art -= 1
            if self._art == 0:
                n = self._atual
                self.noticias.append({
                    "id": n["id"],
                    "titulo": _limpa("".join(n["titulo"])),
                    "data": extrai_data("".join(n["data"])),
                    "corpo": _limpa_corpo("".join(n["corpo"]))})
                self._atual = None
        elif tag == "header":
            self._cab = False
        elif tag in ("time", "a"):
            self._em = None

    def handle_data(self, data):
        if self._atual is None:
            return
        if self._em in ("titulo", "data"):
            self._atual[self._em].append(data)
        elif not self._cab:
            self._atual["corpo"].append(data)


def _limpa(t):
    return re.sub(r"\s+", " ", t).strip()


def _limpa_corpo(t):
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    return re.sub(r"\n\s*\n\s*(\n\s*)*", "\n\n", t).strip()


def extrai_noticias(html):
    p = _Noticias()
    try:
        p.feed(html or "")
        p.close()
    except Exception:
        pass
    return [n for n in p.noticias if n["titulo"]]


class SVRSNoticiasPortal(Portal):
    precisa_js = False

    def coletar(self, ctx, limite=None):
        reg = self._registro_vazio()
        try:
            html, _ = Sessao().baixa_html(self.url)
        except ErroDownload as e:
            reg["erro"] = f"http: {e}"
            return reg
        reg["metodo"], reg["http_status"] = "http", 200
        for n in extrai_noticias(html)[:MAX_NOTICIAS]:
            if not (RELEVANTE.search(n["titulo"]) or RELEVANTE.search(n["corpo"])):
                continue
            it = monta_item(n["titulo"], f"{self.url}#{n['id']}")
            it["data"] = n["data"] or it["data"]
            it["texto_integral"] = f"{n['titulo']}\n\n{n['corpo']}"
            reg["itens"].append(it)
        reg["total"] = len(reg["itens"])
        return reg
