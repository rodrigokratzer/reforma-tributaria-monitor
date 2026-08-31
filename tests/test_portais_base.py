import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from portais.base import Portal


class TestFiltroRelevancia(unittest.TestCase):
    def setUp(self):
        self.p = Portal("teste", "https://exemplo.gov.br/x")

    def test_titulo_com_termo_da_reforma_passa(self):
        self.assertTrue(self.p.filtro_relevancia(
            "Portaria CGIBS no 8 sobre o IBS", "https://x/y"))

    def test_dominio_cgibs_sozinho_nao_passa(self):
        # a armadilha classica: o dominio contem "cgibs" mas o titulo e o
        # caminho nao tem termo relevante
        self.assertFalse(self.p.filtro_relevancia(
            "Pagina inicial do portal", "https://www.cgibs.gov.br/inicial"))

    def test_termo_no_caminho_da_url_passa(self):
        # o regex global RELEVANTE (copia verbatim da varredura v2) casa
        # "resolucao" no singular; o caminho normalizado vira " resolucao nova"
        self.assertTrue(self.p.filtro_relevancia(
            "Documento sem titulo util", "https://x/resolucao/nova"))

    def test_texto_irrelevante_nao_passa(self):
        self.assertFalse(self.p.filtro_relevancia(
            "Aviso de manutencao do site nesta sexta", "https://x/avisos/123"))


class TestFiltra(unittest.TestCase):
    def setUp(self):
        self.p = Portal("teste", "https://exemplo.gov.br/x")

    def test_dedup_por_href(self):
        pares = [("Resolucao CGIBS numero 1", "https://x/r/1"),
                 ("Resolucao CGIBS numero 1 (copia)", "https://x/r/1")]
        self.assertEqual(len(self.p._filtra(pares)), 1)

    def test_titulo_curto_demais_e_ignorado(self):
        self.assertEqual(self.p._filtra([("IBS", "https://x/r/2")]), [])

    def test_item_relevante_vira_dict_com_titulo_e_url(self):
        itens = self.p._filtra([("Nova resolucao sobre o IBS", "https://x/r/3")])
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0]["url"], "https://x/r/3")
        self.assertEqual(itens[0]["titulo"], "Nova resolucao sobre o IBS")


class TestExtraiTextoDefault(unittest.TestCase):
    def test_default_e_none(self):
        p = Portal("teste", "https://x/y")
        self.assertIsNone(p.extrai_texto(None, {"url": "https://x/artigo"}))


class TestColetar(unittest.TestCase):
    """coletar() com rede mockada: confirma que o fluxo browser/http e o
    filtro continuam produzindo os mesmos itens da varredura v2."""

    def test_sucesso_via_browser_nao_toca_no_http(self):
        p = Portal("teste", "https://x/lista", precisa_js=True)
        pares = [("Resolucao CGIBS sobre o IBS", "https://x/r/1"),
                 ("Link irrelevante qualquer aqui", "https://x/sobre")]
        with patch("portais.base.via_browser", return_value=(pares, None)) as vb, \
             patch("portais.base.via_http") as vh:
            reg = p.coletar(None)
        vh.assert_not_called()
        self.assertEqual(reg["metodo"], "browser")
        self.assertEqual(reg["total"], 1)
        self.assertEqual(reg["itens"][0]["url"], "https://x/r/1")

    def test_fallback_http_quando_browser_falha(self):
        p = Portal("teste", "https://x/lista", precisa_js=False)
        html = ('<a href="https://x/r/9">Nova portaria sobre o IBS</a>'
                '<a href="https://x/home">Inicio</a>')
        with patch("portais.base.via_browser", return_value=(None, "Timeout")), \
             patch("portais.base.via_http", return_value=(html, 200, None)):
            reg = p.coletar(None)
        self.assertEqual(reg["metodo"], "http")
        self.assertEqual(reg["total"], 1)

    def test_browser_e_http_falham_registra_erro(self):
        p = Portal("teste", "https://x/lista")
        with patch("portais.base.via_browser", return_value=(None, "Timeout")), \
             patch("portais.base.via_http", return_value=(None, None, "DNS")):
            reg = p.coletar(None)
        self.assertIsNone(reg["metodo"])
        self.assertIn("browser:", reg["erro"])

    def test_extrai_texto_que_lanca_nao_derruba_coleta(self):
        class Explode(Portal):
            def extrai_texto(self, ctx, item, limite=None):
                raise RuntimeError("erro proposital")

        p = Explode("teste", "https://x/lista")
        pares = [("Resolucao CGIBS sobre o IBS", "https://x/r/1")]
        with patch("portais.base.via_browser", return_value=(pares, None)):
            reg = p.coletar(None)
        self.assertEqual(reg["total"], 1)
        self.assertNotIn("texto", reg["itens"][0])


class TestRegistro(unittest.TestCase):
    def test_doze_portais_na_ordem_das_fontes(self):
        from portais.registro import PORTAIS
        nomes = [p.nome for p in PORTAIS]
        self.assertEqual(nomes, [
            "CGIBS - Noticias",
            "CGIBS - Resolucoes",
            "CGIBS - Atos Conjuntos",
            "CGIBS - Atos Tecnicos Conj.",
            "CGIBS - Portarias",
            "RFB - Noticias 2026",
            "RFB - Reforma do Consumo",
            "Portal DF-e SVRS - Noticias",
            "Portal NF-e - Informes/NTs",
            "CGIBS - Regulamentos",
            "CGIBS - Leis",
            "CGIBS - Relatorios",
        ])

    def test_cgibs_usa_a_subclasse_e_precisa_js(self):
        from portais.registro import PORTAIS
        from portais.cgibs import CGIBSPortal
        cgibs = [p for p in PORTAIS if p.nome.startswith("CGIBS")]
        self.assertEqual(len(cgibs), 8)
        self.assertTrue(all(isinstance(p, CGIBSPortal) for p in cgibs))
        self.assertTrue(all(p.precisa_js for p in cgibs))

    def test_fontes_sem_js_sao_marcadas(self):
        from portais.registro import PORTAIS
        sem_js = {p.nome for p in PORTAIS if not p.precisa_js}
        self.assertEqual(sem_js, {
            "RFB - Noticias 2026", "RFB - Reforma do Consumo",
            "Portal DF-e SVRS - Noticias", "Portal NF-e - Informes/NTs",
        })


if __name__ == "__main__":
    unittest.main()
