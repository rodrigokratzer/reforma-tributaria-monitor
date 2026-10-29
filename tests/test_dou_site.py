import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import dou_site


def item(title, url, hier="Ministério da Saúde/Secretaria X", content="", art="Portaria", pub="DO1"):
    return {"pubName": pub, "urlTitle": url, "title": title, "titulo": title,
            "subTitulo": "", "content": content, "artType": art,
            "hierarchyStr": hier, "hierarchyList": [hier], "numberPage": "1",
            "pubDate": "22/10/2026", "editionNumber": "200", "pubOrder": "x"}


def pagina_lista(itens):
    return ('<html><body><script id="params" type="application/json">'
            + json.dumps({"jsonArray": itens}) + '</script></body></html>')


def pagina_materia(texto):
    return ('<html><body><div class="menu">menu</div><div class="texto-dou">'
            f'<div class="x"><p>{texto}</p></div><p>fim</p></div><div>rodape</div></body></html>')


LC = item("Lei Complementar nº 214, de 2025", "lc-214", content="Institui IBS")
EXTRATO = item("Extrato de Contrato nº 5", "extrato-5", content="contrato qualquer")
GENERICO = item("Portaria nº 9", "port-9", content="trata de outro assunto")
DO3_IRREL = item("Aviso de Pregão", "do3-irrel", hier="Prefeitura X", pub="DO3",
                 content="compra de material")
DO3_RF = item("Ato qualquer da receita", "do3-rf", hier="Ministério da Fazenda/Receita Federal",
              pub="DO3", content="regras do ibs")


class FakeSite:
    """Substitui _get: lista por (secao) e materia por urlTitle."""
    def __init__(self, listas, materias):
        self.listas, self.materias, self.baixados = listas, materias, []

    def __call__(self, url, timeout=30):
        if "leiturajornal" in url:
            sec = url.split("secao=")[1]
            return pagina_lista(self.listas.get(sec, []))
        ut = url.rsplit("/-/", 1)[1]
        self.baixados.append(ut)
        if ut not in self.materias:
            raise OSError("404")
        return self.materias[ut]


class TestLista(unittest.TestCase):
    def test_extrai_json_array(self):
        with patch.object(dou_site, "_get", FakeSite({"do1": [LC]}, {})):
            self.assertEqual(dou_site.lista("2026-10-22", "DO1")[0]["urlTitle"], "lc-214")

    def test_data_no_formato_do_site(self):
        urls = []
        def get(url, timeout=30):
            urls.append(url)
            return pagina_lista([])
        with patch.object(dou_site, "_get", get):
            dou_site.lista("2026-10-22", "DO1E")
        self.assertIn("data=22-10-2026&secao=do1e", urls[0])


class TestTexto(unittest.TestCase):
    def test_extrai_div_texto_dou(self):
        with patch.object(dou_site, "_get", lambda u, timeout=30: pagina_materia("Corpo &amp; mais")):
            t = dou_site.texto("abc")
        self.assertIn("Corpo & mais", t)
        self.assertIn("fim", t)
        self.assertNotIn("menu", t)
        self.assertNotIn("rodape", t)

    def test_sem_div_ou_erro_devolve_none(self):
        with patch.object(dou_site, "_get", lambda u, timeout=30: "<html>nada</html>"):
            self.assertIsNone(dou_site.texto("abc"))
        def erro(u, timeout=30):
            raise OSError("x")
        with patch.object(dou_site, "_get", erro):
            self.assertIsNone(dou_site.texto("abc"))


class TestColeta(unittest.TestCase):
    def roda(self, listas, materias, historico=None):
        site = FakeSite(listas, materias)
        with patch.object(dou_site, "_get", site):
            with patch.object(dou_site, "_dorme", lambda s: None):
                itens, diag = dou_site.coleta(["2026-10-22"], historico, log=open("/dev/null", "w"))
        return itens, diag, site

    def test_forte_extrato_e_do3_irrelevante(self):
        itens, diag, site = self.roda(
            {"do1": [LC, EXTRATO, GENERICO], "do3": [DO3_IRREL]},
            {"lc-214": pagina_materia("texto da LC"), "port-9": pagina_materia("nada relevante")})
        self.assertEqual([i["titulo"] for i in itens], ["Lei Complementar nº 214, de 2025"])
        it = itens[0]
        self.assertEqual(it["fonte"], "DOU DO1")
        self.assertEqual(it["url"], "https://www.in.gov.br/web/dou/-/lc-214")
        self.assertEqual(it["data"], "2026-10-22")
        self.assertEqual(it["balde"], "forte")
        self.assertFalse(it["continuacao"])
        self.assertIn("texto da LC", it["texto_integral"])
        self.assertEqual(diag["lidas"], 4)
        self.assertEqual(diag["forte"], 1)
        # extrato nao baixa; DO3 irrelevante nao baixa; LC e portaria generica baixam
        self.assertEqual(sorted(site.baixados), ["lc-214", "port-9"])
        self.assertEqual(diag["baixados"], 2)
        self.assertEqual(diag["falhas_download"], 0)

    def test_corpo_promove_para_revisar(self):
        itens, diag, _ = self.roda({"do1": [GENERICO]},
                                   {"port-9": pagina_materia("cita o IBS uma vez")})
        self.assertEqual(itens[0]["balde"], "revisar")
        self.assertEqual(diag["revisar"], 1)

    def test_do3_so_baixa_se_orgao_ou_termo(self):
        itens, diag, site = self.roda(
            {"do3": [DO3_IRREL, DO3_RF]}, {"do3-rf": pagina_materia("ibs ibs ibs")})
        self.assertEqual(site.baixados, ["do3-rf"])
        self.assertEqual(itens[0]["fonte"], "DOU DO3")

    def test_download_falho_usa_previa_e_conta(self):
        itens, diag, _ = self.roda({"do1": [LC]}, {})
        self.assertEqual(diag["falhas_download"], 1)
        self.assertEqual(diag["baixados"], 0)
        self.assertEqual(itens[0]["texto_integral"], "Institui IBS")
        self.assertTrue(diag["erros"])

    def test_pagina_sem_texto_dou_conta_falha(self):
        itens, diag, _ = self.roda({"do1": [LC]}, {"lc-214": "<html>sem div</html>"})
        self.assertEqual(diag["falhas_download"], 1)
        self.assertEqual(itens[0]["texto_integral"], "Institui IBS")

    def test_dedup_contra_historico(self):
        hist = {"k": {"data": "2026-10-22", "fonte": "DOU DO1",
                      "titulo": "LEI COMPLEMENTAR Nº  214,  DE 2025",
                      "orgao": "MINISTERIO DA SAUDE/Secretaria  X"}}
        itens, diag, site = self.roda({"do1": [LC]}, {"lc-214": pagina_materia("x")}, hist)
        self.assertEqual(itens, [])
        self.assertEqual(diag["duplicados"], 1)
        self.assertEqual(site.baixados, [])

    def test_dedup_acentos_e_outra_fonte_nao_dou(self):
        hist = {"k": {"data": "2026-10-22", "fonte": "Receita", "titulo": LC["title"],
                      "orgao": LC["hierarchyStr"]}}
        itens, diag, _ = self.roda({"do1": [LC]}, {"lc-214": pagina_materia("x")}, hist)
        self.assertEqual(len(itens), 1)
        self.assertEqual(diag["duplicados"], 0)
        hist2 = {"k": {"data": "2026-10-22", "fonte": "DOU DO1E",
                       "titulo": LC["title"], "orgao": LC["hierarchyStr"]}}
        itens, diag, _ = self.roda({"do1": [LC]}, {}, hist2)
        self.assertEqual(diag["duplicados"], 1)

    def test_mesmo_titulo_orgao_diferente_nao_e_duplicata(self):
        hist = {"k": {"data": "2026-10-22", "fonte": "DOU DO1", "titulo": LC["title"],
                      "orgao": "Outro Ministerio/Outra Secretaria"}}
        itens, diag, _ = self.roda({"do1": [LC]}, {"lc-214": pagina_materia("x")}, hist)
        self.assertEqual(len(itens), 1)
        self.assertEqual(diag["duplicados"], 0)

    def test_itens_iguais_na_mesma_execucao_sobrevivem_os_dois(self):
        a = item("PORTARIA Nº 5", "p5a", hier="Org A", content="ibs")
        b = item("Portaria nº 5", "p5b", hier="ORG A", content="ibs")
        itens, diag, _ = self.roda({"do1": [a, b]}, {})
        self.assertEqual(sorted(i["url"][-3:] for i in itens), ["p5a", "p5b"])
        self.assertEqual(diag["duplicados"], 0)

    def test_historico_do_proprio_plano_b_nao_causa_skip(self):
        hist = {"k": {"data": "2026-10-22", "fonte": "DOU DO1", "titulo": LC["title"],
                      "orgao": LC["hierarchyStr"],
                      "url": "https://www.in.gov.br/web/dou/-/lc-214"}}
        itens, diag, _ = self.roda({"do1": [LC]}, {"lc-214": pagina_materia("x")}, hist)
        self.assertEqual(len(itens), 1)
        self.assertEqual(diag["duplicados"], 0)

    def test_sobreposicao_com_inlabs_com_url_de_inlabs(self):
        hist = {"k": {"data": "2026-10-22", "fonte": "DOU DO1", "titulo": LC["title"],
                      "orgao": LC["hierarchyStr"],
                      "url": "https://inlabs.in.gov.br/x/1"}}
        itens, diag, _ = self.roda({"do1": [LC]}, {}, hist)
        self.assertEqual(itens, [])
        self.assertEqual(diag["duplicados"], 1)

    def test_chave_dedup(self):
        self.assertEqual(dou_site.chave_dedup("2026-10-22", "PORTARIA  N 5", "Org  A/Sec"),
                         ("2026-10-22", "portaria n 5", "org a/sec"))

    def test_extrato_com_previa_de_nfs_e_continua_descartado(self):
        ex = item("EXTRATO DE ORDEM DE COMPRA", "oc-1", hier="Prefeitura X", pub="DO3",
                  content="aquisicao de software de nfs-e")
        itens, diag, _ = self.roda({"do1": [ex]}, {})
        self.assertEqual(itens, [])

    def test_todas_as_consultas_falham_levanta(self):
        def erro(url, timeout=30):
            raise OSError("fora")
        with patch.object(dou_site, "_get", erro), patch.object(dou_site, "_dorme", lambda s: None):
            with self.assertRaises(RuntimeError):
                dou_site.coleta(["2026-10-22"], None, log=open("/dev/null", "w"))

    def test_dia_sem_edicao(self):
        itens, diag, _ = self.roda({}, {})
        self.assertEqual(itens, [])
        self.assertTrue(diag["sem_edicao"])


class TestNormaliza(unittest.TestCase):
    def test_norm_titulo(self):
        self.assertEqual(dou_site.norm_titulo("Ação  Única\n"), "acao unica")
        self.assertEqual(dou_site.norm_titulo(" PORTARIA Nº 5 "),
                         dou_site.norm_titulo("portaria nº  5"))


if __name__ == "__main__":
    unittest.main()
