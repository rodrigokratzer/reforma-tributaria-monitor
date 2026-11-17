import contextlib
import datetime
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import noticias
import varredura

AGORA = datetime.datetime(2026, 11, 17, 15, 0, tzinfo=datetime.timezone.utc)

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>
<title>Portal</title><link>https://portal.example/</link>
<item>
  <title>Selic sobe para 15%</title>
  <link>https://portal.example/economia/selic-sobe</link>
  <pubDate>Tue, 17 Nov 2026 14:01:47 -0000</pubDate>
  <description><![CDATA[<img src="x.jpg"/><p>O Copom elevou a taxa &amp; o
  cr&eacute;dito fica mais caro.</p><br/>Leia mais]]></description>
  <category>Economia</category>
</item>
<item>
  <title>Noticia velha</title>
  <link>https://portal.example/economia/velha</link>
  <pubDate>Fri, 13 Nov 2026 10:00:00 -0300</pubDate>
  <description>antiga</description>
</item>
<item>
  <title>Sem data</title>
  <link>https://portal.example/economia/sem-data</link>
  <description>texto</description>
</item>
<item>
  <title>Senado em ISO</title>
  <link>https://portal.example/politica/iso</link>
  <pubDate>2026-11-17T13:55:07Z</pubDate>
</item>
</channel></rss>"""

ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom</title>
<entry>
  <title>Pix ganha regra nova</title>
  <link rel="alternate" href="https://atom.example/pix"/>
  <published>2026-11-17T08:30:00-03:00</published>
  <summary type="html">&lt;b&gt;Banco Central&lt;/b&gt; muda limite</summary>
</entry>
<entry>
  <title>Antiga</title>
  <link href="https://atom.example/antiga"/>
  <updated>2026-11-01T08:30:00Z</updated>
</entry>
</feed>"""


def por_titulo(itens):
    return {i["titulo"]: i for i in itens}


class TestParse(unittest.TestCase):
    def test_rss_campos_do_contrato(self):
        it = por_titulo(noticias.itens_do_feed(RSS.encode(), agora=AGORA))["Selic sobe para 15%"]
        self.assertEqual(it["tipo"], "noticia")
        self.assertEqual(it["url"], "https://portal.example/economia/selic-sobe")
        self.assertEqual(it["data"], "2026-11-17")
        self.assertEqual(it["publicado_em"], "2026-11-17T11:01:47-03:00")
        self.assertEqual(it["ementa"], "O Copom elevou a taxa & o crédito fica mais caro. Leia mais")
        self.assertEqual(set(it), {"tipo", "titulo", "url", "data", "publicado_em", "ementa"})

    def test_data_iso_com_z(self):
        it = por_titulo(noticias.itens_do_feed(RSS.encode(), agora=AGORA))["Senado em ISO"]
        self.assertEqual(it["publicado_em"], "2026-11-17T10:55:07-03:00")
        self.assertEqual(it["ementa"], "")

    def test_data_em_sao_paulo_vira_o_dia(self):
        rss = RSS.replace("Tue, 17 Nov 2026 14:01:47 -0000", "Tue, 17 Nov 2026 02:00:00 +0000")
        it = por_titulo(noticias.itens_do_feed(rss.encode(), agora=AGORA))["Selic sobe para 15%"]
        self.assertEqual(it["data"], "2026-11-16")

    def test_janela_descarta_velha_e_mantem_sem_data(self):
        t = por_titulo(noticias.itens_do_feed(RSS.encode(), agora=AGORA))
        self.assertNotIn("Noticia velha", t)
        self.assertIsNone(t["Sem data"]["data"])
        self.assertIsNone(t["Sem data"]["publicado_em"])

    def test_atom(self):
        t = por_titulo(noticias.itens_do_feed(ATOM.encode(), agora=AGORA))
        self.assertEqual(list(t), ["Pix ganha regra nova"])
        it = t["Pix ganha regra nova"]
        self.assertEqual(it["url"], "https://atom.example/pix")
        self.assertEqual(it["publicado_em"], "2026-11-17T08:30:00-03:00")
        self.assertEqual(it["ementa"], "Banco Central muda limite")

    def test_rfc822_menos_zero_e_utc(self):
        self.assertEqual(noticias.quando("Tue, 17 Nov 2026 14:01:47 -0000").isoformat(),
                         "2026-11-17T14:01:47+00:00")

    def test_data_ilegivel_e_none(self):
        self.assertIsNone(noticias.quando("ontem"))

    def test_data_sem_fuso_e_brasilia(self):
        self.assertEqual(noticias.quando("2026-11-17T11:20:21").utcoffset(),
                         datetime.timedelta(hours=-3))

    def test_filtro_pelo_caminho_e_categoria_nunca_dominio(self):
        t = noticias.itens_do_feed(RSS.encode(), filtro=r"^/economia/", agora=AGORA)
        self.assertNotIn("Senado em ISO", por_titulo(t))
        t = noticias.itens_do_feed(RSS.encode(), filtro=r"portal", agora=AGORA)
        self.assertEqual(t, [])
        t = noticias.itens_do_feed(RSS.encode(), filtro=r"^/nada/|\| Economia", agora=AGORA)
        self.assertEqual([i["titulo"] for i in t], ["Selic sobe para 15%"])

    def test_excluir(self):
        t = noticias.itens_do_feed(RSS.encode(), excluir=r"^/politica/", agora=AGORA)
        self.assertNotIn("Senado em ISO", por_titulo(t))
        self.assertIn("Selic sobe para 15%", por_titulo(t))

    def test_latin1_sem_declaracao(self):
        rss = ("<rss><channel><item><title>Inflação cai</title>"
               "<link>https://uol.example/a</link></item></channel></rss>").encode("latin-1")
        self.assertEqual(noticias.itens_do_feed(rss, agora=AGORA)[0]["titulo"], "Inflação cai")

    def test_redirecionador_da_folha(self):
        u = "https://redir.folha.com.br/redir/online/mercado/rss091/*https://www1.folha.uol.com.br/mercado/a.shtml"
        self.assertEqual(noticias.url_final(u), "https://www1.folha.uol.com.br/mercado/a.shtml")


class TestSemHtml(unittest.TestCase):
    def test_tira_tags_entidades_e_espacos(self):
        self.assertEqual(noticias.sem_html("<p>a&nbsp;<b>b</b></p>\n\n<div>c</div>"), "a b c")

    def test_corta_na_palavra(self):
        t = noticias.sem_html("palavra " * 200)
        self.assertLessEqual(len(t), noticias.TETO_EMENTA + 1)
        self.assertTrue(t.endswith("palavra…"))


class TestColeta(unittest.TestCase):
    def roda(self, mapa, feeds):
        def falsa(url):
            v = mapa[url]
            if isinstance(v, Exception):
                raise v
            return 200, v
        with patch.object(noticias, "baixa", side_effect=falsa), \
                contextlib.redirect_stderr(io.StringIO()):
            return noticias.coleta(feeds, agora=AGORA)

    def test_feed_que_falha_nao_derruba_os_outros(self):
        feeds = [{"fonte": "A", "url": "a"}, {"fonte": "B", "url": "b"}, {"fonte": "C", "url": "c"}]
        r = self.roda({"a": OSError("timeout"), "b": b"<html><body>", "c": ATOM.encode()}, feeds)
        self.assertEqual([x["metodo"] for x in r], [None, None, "rss"])
        self.assertIn("timeout", r[0]["erro"])
        self.assertIn("ParseError", r[1]["erro"])
        self.assertEqual(r[2]["total"], 1)
        for x in r:
            self.assertEqual(set(x), {"fonte", "url", "metodo", "http_status", "total", "erro", "itens"})

    def test_dedup_na_mesma_execucao(self):
        feeds = [{"fonte": "A", "url": "a"}, {"fonte": "B", "url": "b"}]
        r = self.roda({"a": RSS.encode(), "b": RSS.encode()}, feeds)
        self.assertEqual(r[0]["total"], 3)
        self.assertEqual((r[1]["total"], r[1]["itens"]), (0, []))

    def test_main_grava_arquivos_proprios_e_codigo_de_saida(self):
        with tempfile.TemporaryDirectory() as d, \
                patch.object(varredura, "DADOS", Path(d)), \
                patch.dict("os.environ", {"DATA_REF": "2026-11-17"}), \
                patch.object(noticias, "FEEDS", [{"fonte": "A", "url": "a"}]), \
                patch.object(noticias, "baixa", return_value=(200, ATOM.encode())), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(noticias.main(), 0)
            hist = json.loads((Path(d) / "historico.json").read_text("utf-8"))
            nov = json.loads((Path(d) / "novidades_noticias.json").read_text("utf-8"))
            self.assertTrue((Path(d) / "2026-11-17-noticias.json").exists())
        (it,) = hist.values()
        self.assertEqual((it["fonte"], it["tipo"], it["primeira_vez"]), ("A", "noticia", "2026-11-17"))
        self.assertIn("visto_em", it)
        self.assertEqual(nov["quantidade"], 1)

    def test_main_sai_1_se_todos_falham(self):
        with tempfile.TemporaryDirectory() as d, \
                patch.object(varredura, "DADOS", Path(d)), \
                patch.object(noticias, "FEEDS", [{"fonte": "A", "url": "a"}]), \
                patch.object(noticias, "baixa", side_effect=OSError("x")), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(noticias.main(), 1)


if __name__ == "__main__":
    unittest.main()
