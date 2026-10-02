#!/usr/bin/env python3
"""Portal Nacional da NF-e (nfe.fazenda.gov.br).

Duas formas de publicacao, nenhuma delas um link comum:
  * informe.aspx — os avisos ficam inline, cada um num <div class="divInforme">
    (<a name="N"> + <p>DD/MM/AAAA - titulo</p> + corpo). O coletor generico
    pegava o menu do site em vez deles.
  * listaConteudo.aspx?tipoConteudo=... — Atos RFB/CGIBS, Atos Tecnicos, NTs,
    Informes Tecnicos: <span class="tituloConteudo"> dentro de um link
    exibirArquivo.aspx (o PDF), seguido da ementa. O PDF e' lido pela raia
    de leitura (scripts/ler_textos.py).

O site exige cookie de sessao (sem ele, 302 em loop): tudo via
leitura.baixar.Sessao.
"""
import re
import urllib.parse
from html.parser import HTMLParser

from leitura.baixar import ErroDownload, Sessao
from portais.base import Portal, REFORMA, extrai_data, monta_item


def _limpa(t):
    return re.sub(r"\s+", " ", t or "").strip()


class _Informes(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.informes, self._atual, self._prof, self._no_p = [], None, 0, False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "div":
            if self._atual is None and "divInforme" in (a.get("class") or "").split():
                self._atual, self._prof = {"id": "", "cab": [], "corpo": []}, 1
            elif self._atual is not None:
                self._prof += 1
        elif self._atual is not None:
            if tag == "a" and a.get("name") and not self._atual["id"]:
                self._atual["id"] = a["name"]
            elif tag == "p" and not self._atual["cab"]:
                self._no_p = True
            elif tag == "br":
                self._atual["corpo"].append("\n")

    def handle_endtag(self, tag):
        if self._atual is None:
            return
        if tag == "p":
            self._no_p = False
        elif tag == "div":
            self._prof -= 1
            if self._prof == 0:
                cab = _limpa("".join(self._atual["cab"]))
                m = re.match(r"(\d{2}/\d{2}/\d{4})\s*-\s*(.*)", cab)
                self.informes.append({
                    "id": self._atual["id"],
                    "data": extrai_data(m.group(1)) if m else None,
                    "titulo": m.group(2) if m else cab,
                    "corpo": re.sub(r"\n\s*\n\s*(\n\s*)*", "\n\n",
                                    re.sub(r"[ \t]+", " ", "".join(self._atual["corpo"]))).strip()})
                self._atual = None

    def handle_data(self, data):
        if self._atual is not None:
            self._atual["cab" if self._no_p else "corpo"].append(data)


def extrai_informes(html):
    p = _Informes()
    try:
        p.feed(html or "")
        p.close()
    except Exception:
        pass
    return [i for i in p.informes if i["titulo"]]


class _Lista(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base, self.itens = base, []
        self._href, self._tit, self._em_tit, self._em_p = None, [], False, False
        self._ementa = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "p":
            self._fecha()
            self._em_p = True
        elif tag == "a" and "exibirarquivo.aspx" in (a.get("href") or "").lower():
            self._fecha()
            self._href = urllib.parse.quote(
                urllib.parse.urljoin(self.base, a["href"]), safe=":/?=&%+#")
        elif tag == "span" and "tituloConteudo" in (a.get("class") or ""):
            self._em_tit = True

    def handle_endtag(self, tag):
        if tag == "span":
            self._em_tit = False
        elif tag == "p":
            self._fecha()
            self._em_p = False

    def handle_data(self, data):
        if self._em_tit:
            self._tit.append(data)
        elif self._href:
            self._ementa.append(data)

    def _fecha(self):
        if self._href and _limpa("".join(self._tit)):
            self.itens.append({"titulo": _limpa("".join(self._tit)), "url": self._href,
                               "ementa": _limpa("".join(self._ementa))})
        self._href, self._tit, self._ementa = None, [], []

    def close(self):
        super().close()
        self._fecha()


def extrai_lista(html, base):
    p = _Lista(base)
    try:
        p.feed(html or "")
        p.close()
    except Exception:
        pass
    return p.itens


class _NFePortal(Portal):
    precisa_js = False

    def _html(self, reg):
        try:
            html, _ = Sessao().baixa_html(self.url)
        except ErroDownload as e:
            reg["erro"] = f"http: {e}"
            return None
        reg["metodo"], reg["http_status"] = "http", 200
        return html


class NFeInformesPortal(_NFePortal):
    def coletar(self, ctx, limite=None):
        reg = self._registro_vazio()
        html = self._html(reg)
        if html is None:
            return reg
        for n in extrai_informes(html):
            if not (REFORMA.search(n["titulo"]) or REFORMA.search(n["corpo"])):
                continue
            it = monta_item(n["titulo"], f"{self.url}#{n['id']}")
            it["data"] = n["data"] or it["data"]
            it["texto_integral"] = f"{n['titulo']}\n\n{n['corpo']}"
            reg["itens"].append(it)
        reg["total"] = len(reg["itens"])
        return reg


class NFeListaPortal(_NFePortal):
    def coletar(self, ctx, limite=None):
        reg = self._registro_vazio()
        html = self._html(reg)
        if html is None:
            return reg
        for n in extrai_lista(html, self.url):
            if not (REFORMA.search(n["titulo"]) or REFORMA.search(n["ementa"])):
                continue
            it = monta_item(n["titulo"], n["url"])
            it["ementa"] = n["ementa"]
            reg["itens"].append(it)
        reg["total"] = len(reg["itens"])
        return reg
