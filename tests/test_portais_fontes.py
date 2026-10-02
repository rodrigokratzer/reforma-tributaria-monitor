import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from unittest.mock import patch

from leitura import baixar
from portais import nfe, svrs
from portais.govbr import GovBrNoticiasPortal

NOT26 = "https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2026"


class TestGovBr(unittest.TestCase):
    def setUp(self):
        self.p = GovBrNoticiasPortal("RFB - Noticias 2026", NOT26)

    def test_noticia_da_reforma_passa(self):
        self.assertTrue(self.p.filtro_relevancia(
            "Receita Federal atualiza o balanco de opcao pelo Simples Nacional e IBS",
            NOT26 + "/setembro/receita-federal-atualiza-o-balanco-de-solicitacoes-de-opcao"))

    def test_noticia_fora_da_listagem_tambem_passa(self):
        p = GovBrNoticiasPortal("RFB - Reforma do Consumo",
                                "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/x/noticias")
        self.assertTrue(p.filtro_relevancia(
            "Receita Federal, CGIBS e CFC alinham diretrizes da conformidade",
            "https://www.gov.br/receitafederal/pt-br/assuntos/noticias/receita-federal-comite-gestor-do-ibs-e-cfc-alinham"))

    def test_servicos_e_menus_nao_passam(self):
        for t, u in [
            ("Escolher Regime de Apuracao de IBS e CBS",
             "https://www.gov.br/pt-br/servicos/escolher-regime-de-apuracao-de-bens-e-servicos-ibs"),
            ("Simples Nacional", "https://www8.receita.fazenda.gov.br/SimplesNacional/"),
            ("Nota Fiscal de Servico Eletronica (NFS-e)", "https://www.gov.br/nfse/pt-br"),
            ("Conformidade", "https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/paineis/conformidade"),
        ]:
            self.assertFalse(self.p.filtro_relevancia(t, u), u)

    def test_paginas_de_listagem_nao_passam(self):
        self.assertFalse(self.p.filtro_relevancia("Noticias de setembro sobre o IBS",
                                                  NOT26 + "/setembro"))
        self.assertFalse(self.p.filtro_relevancia("Noticias sobre o IBS", NOT26))

    def test_noticia_sem_termo_da_reforma_nao_passa(self):
        self.assertFalse(self.p.filtro_relevancia(
            "Receita Federal apreende mercadorias no porto de Santos",
            NOT26 + "/setembro/receita-federal-apreende-mercadorias-no-porto"))




SVRS_HTML = """
<div class="artigo__texto"><section id="pagedlistItens">
<article class="conteudo-lista__item clearfix">
  <header><ul class="lista-categoria"><li><a class="label" href="#">Coordena&#231;&#227;o T&#233;cnica do ENCAT</a></li></ul>
  <time class="conteudo-lista__item__datahora" datetime="10/09/2026">10/09/2026</time>
  <h2 class="conteudo-lista__item__titulo"><a id="#3007" href="#">Publicada NT 2025.002 v1.30 com regras do IBS e CBS</a></h2></header>
  <p><p>A NT altera o leiaute da NF-e para o IBS.</p><p>Vigencia em 01/12/2026.</p></p>
</article>
<article class="conteudo-lista__item clearfix">
  <header><time class="conteudo-lista__item__datahora" datetime="09/09/2026">09/09/2026</time>
  <h2 class="conteudo-lista__item__titulo"><a id="#3006" href="#">Novidade: Link para o MOC Online</a></h2></header>
  <p>Agora ha um link para o MOC no menu superior.</p>
</article>
</section></div>
"""

NFE_INFORMES_HTML = """
<div id="conteudoDinamico"><div class="divTituloPrincipal">Avisos</div>
<div class="divInforme"><a name="1490"></a><p>04/09/2026 -
   Publicado Informe Tecnico 2025.002 sobre o IBS e a CBS </p>Foi publicado&nbsp;Informe Tecnico com regras do IBS.<br /><br />Assinado por: Coordenacao Tecnica do ENCAT</div>
<div class="divInforme"><a name="1489"></a><p>03/09/2026 - Atualizada a tabela de NCM</p>Tabela de NCM atualizada.</div>
</div>
"""

NFE_LISTA_HTML = """
<div class="indentacaoConteudo"><p><a target="_blank" href="exibirArquivo.aspx?conteudo=esD6zF5PwcE="><span class="tituloConteudo">Ato Conjunto RFB/CGIBS n&#186; 4, de 30 de julho de 2026</span></a><br />Estabelece as datas de inicio da obrigatoriedade dos documentos fiscais do IBS<br /></p>
<p><a target="_blank" href="exibirArquivo.aspx?conteudo=5FAxxHGS5Ic="><span class="tituloConteudo">Ato Conjunto RFB/CGIBS n&#186; 1, de 22 de dezembro de 2025</span></a><br />Dispoe sobre as obrigacoes acessorias do IBS e da CBS em 2026<br /></p></div>
"""

SVRS_URL = "https://dfe-portal.svrs.rs.gov.br/Nfe/Noticias"
NFE_URL = "https://www.nfe.fazenda.gov.br/portal/informe.aspx?ehCTG=false"
LISTA_URL = "https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=ECxaPvwFHQE="


def _sessao_com(html):
    s = patch.object(baixar.Sessao, "baixa_html", return_value=(html, "u"))
    return s


class TestSVRS(unittest.TestCase):
    def test_extrai_noticias_inline(self):
        ns = svrs.extrai_noticias(SVRS_HTML)
        self.assertEqual([n["id"] for n in ns], ["3007", "3006"])
        self.assertEqual(ns[0]["data"], "2026-09-10")
        self.assertIn("Publicada NT 2025.002", ns[0]["titulo"])
        self.assertIn("Vigencia em 01/12/2026", ns[0]["corpo"])
        self.assertNotIn("ENCAT", ns[0]["titulo"])

    def test_coletar_filtra_e_traz_texto_integral(self):
        p = svrs.SVRSNoticiasPortal("Portal DF-e SVRS - Noticias", SVRS_URL)
        with _sessao_com(SVRS_HTML):
            reg = p.coletar(None)
        self.assertEqual(reg["metodo"], "http")
        self.assertEqual(reg["total"], 1)                       # MOC Online nao e' da reforma
        it = reg["itens"][0]
        self.assertEqual(it["url"], SVRS_URL + "#3007")
        self.assertEqual(it["data"], "2026-09-10")
        self.assertIn("leiaute da NF-e para o IBS", it["texto_integral"])

    def test_limite_de_noticias(self):
        bloco = SVRS_HTML.split("<article")[1].split("</article>")[0]
        muitas = "".join(f'<article{bloco.replace("#3007", "#" + str(i))}</article>' for i in range(50))
        self.assertEqual(len(svrs.extrai_noticias(muitas)), 50)
        p = svrs.SVRSNoticiasPortal("S", SVRS_URL)
        with _sessao_com(muitas):
            self.assertEqual(p.coletar(None)["total"], svrs.MAX_NOTICIAS)

    def test_falha_de_rede_vira_erro_sem_lancar(self):
        p = svrs.SVRSNoticiasPortal("S", SVRS_URL)
        with patch.object(baixar.Sessao, "baixa_html", side_effect=baixar.ErroDownload("HTTP 503")):
            reg = p.coletar(None)
        self.assertIsNone(reg["metodo"])
        self.assertIn("HTTP 503", reg["erro"])


class TestNFeInformes(unittest.TestCase):
    def test_extrai_informes(self):
        ns = nfe.extrai_informes(NFE_INFORMES_HTML)
        self.assertEqual([n["id"] for n in ns], ["1490", "1489"])
        self.assertEqual(ns[0]["data"], "2026-09-04")
        self.assertEqual(ns[0]["titulo"], "Publicado Informe Tecnico 2025.002 sobre o IBS e a CBS")
        self.assertIn("Assinado por", ns[0]["corpo"])

    def test_coletar(self):
        p = nfe.NFeInformesPortal("Portal NF-e - Informes/NTs", NFE_URL)
        with _sessao_com(NFE_INFORMES_HTML):
            reg = p.coletar(None)
        self.assertEqual(reg["total"], 1)                       # NCM nao e' da reforma
        it = reg["itens"][0]
        self.assertEqual(it["url"], NFE_URL + "#1490")
        self.assertIn("regras do IBS", it["texto_integral"])


class TestNFeLista(unittest.TestCase):
    def test_extrai_lista(self):
        ns = nfe.extrai_lista(NFE_LISTA_HTML, LISTA_URL)
        self.assertEqual(ns[0]["url"],
                         "https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=esD6zF5PwcE=")
        self.assertEqual(ns[0]["titulo"], "Ato Conjunto RFB/CGIBS nº 4, de 30 de julho de 2026")
        self.assertIn("datas de inicio", ns[0]["ementa"])

    def test_coletar_sem_texto_integral(self):
        p = nfe.NFeListaPortal("Portal NF-e - Atos RFB/CGIBS", LISTA_URL)
        with _sessao_com(NFE_LISTA_HTML):
            reg = p.coletar(None)
        self.assertEqual(reg["total"], 2)
        self.assertNotIn("texto_integral", reg["itens"][0])
        self.assertEqual(reg["itens"][0]["data"], "2026-07-30")
        self.assertIn("ementa", reg["itens"][0])


if __name__ == "__main__":
    unittest.main()
