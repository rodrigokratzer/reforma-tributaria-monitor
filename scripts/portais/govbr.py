#!/usr/bin/env python3
"""Noticias da RFB no gov.br.

A pagina de listagem traz, alem das noticias, menu, servicos
(gov.br/pt-br/servicos/...), paineis e links para outros sistemas (www8,
NFS-e). Esses links passavam no filtro global por terem "IBS", "Simples
Nacional" ou "NFS-e" no titulo e entravam como publicacao — sem ser
publicacao. Aqui so' entra noticia: caminho com /noticias/ e terminando
num slug (>= 3 hifens), nunca numa pagina de listagem (/noticias/2026,
/noticias/2026/setembro).
"""
import urllib.parse

from portais.base import Portal


class GovBrNoticiasPortal(Portal):
    precisa_js = False

    def filtro_relevancia(self, titulo, url):
        caminho = urllib.parse.urlparse(url).path.rstrip("/")
        if "/noticias/" not in caminho:
            return False
        if caminho.rsplit("/", 1)[-1].count("-") < 3:
            return False
        return super().filtro_relevancia(titulo, url)
