#!/usr/bin/env python3
"""Download com sessao (cookies), para a raia de leitura e para as fontes
que exigem sessao.

O Portal NF-e (nfe.fazenda.gov.br) responde 302 para a propria URL ate'
receber o cookie ASP.NET_SessionId que ele mesmo manda — sem cookie jar, o
cliente entra em loop de redirect (curl: "Maximum (50) redirects"). O
urllib puro de portais.base.via_http nao guarda cookie; por isso esta
classe existe.
"""
import http.cookiejar
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections import namedtuple

from portais.base import UA

TIMEOUT_S = 90
MAX_BYTES = 100 * 1024 * 1024

Resposta = namedtuple("Resposta", "dados tipo charset url")


class ErroDownload(Exception):
    pass


def eh_pdf(dados):
    return dados[:1024].lstrip().startswith(b"%PDF-")


class Sessao:
    def __init__(self, timeout=TIMEOUT_S):
        self.timeout = timeout
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()))

    def baixa(self, url):
        url = urllib.parse.quote(url, safe=":/?=&%+#")   # espaco literal em href do NF-e
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        })
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                dados = r.read(MAX_BYTES + 1)
                if len(dados) > MAX_BYTES:
                    raise ErroDownload(f"maior que {MAX_BYTES} bytes")
                return Resposta(dados, r.headers.get_content_type(),
                                r.headers.get_content_charset(), r.geturl())
        except ErroDownload:
            raise
        except urllib.error.HTTPError as e:
            raise ErroDownload(f"HTTP {e.code}") from e
        except Exception as e:
            raise ErroDownload(f"{type(e).__name__}: {str(e)[:160]}") from e

    def baixa_html(self, url):
        r = self.baixa(url)
        return r.dados.decode(r.charset or "utf-8", "replace"), r.url
