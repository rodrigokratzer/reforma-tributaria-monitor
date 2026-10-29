import io
import json
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import dou
import dou_site
import urllib.error
import varredura


def zip_inlabs(texto, categoria="Ministerio da Saude", tipo="Portaria"):
    xml = (f'<xml><article artCategory="{categoria}" artType="{tipo}" id="1" '
           f'pubName="DO1"><body><Identifica>PORTARIA N 1</Identifica>'
           f'<Ementa>Dispoe sobre assunto qualquer.</Ementa>'
           f'<Texto>{escape(texto)}</Texto></body></article></xml>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("materia.xml", xml)
    return buf.getvalue()


class TestTextoIntegral(unittest.TestCase):
    def test_mencao_depois_do_corte_ainda_classifica(self):
        # o texto guardado e' cortado em 20.000 caracteres, mas a mencao ao
        # IBS la no fim da materia tem que contar na classificacao
        texto = "palavra " * 3000 + " menciona o IBS no fim"
        self.assertGreater(texto.index("IBS"), 20000)
        a = dou.artigos(zip_inlabs(texto))[0]
        self.assertEqual(len(a["_texto"]), 20000)
        self.assertNotIn("IBS", a["_texto"])
        self.assertEqual(dou.classifica(a), "revisar")

    def test_sem_mencao_continua_descartado(self):
        a = dou.artigos(zip_inlabs("palavra " * 3000))[0]
        self.assertEqual(dou.classifica(a), "descartado")

    def test_classifica_sem_texto_integral_usa_texto(self):
        # itens montados a mao (ou por codigo antigo) so tem _texto
        self.assertEqual(dou.classifica({"_titulo": "Portaria", "_texto": "trata do IBS"}),
                         "revisar")


class Resp:
    def __init__(self, corpo):
        self.corpo = corpo

    def read(self):
        return self.corpo.encode()


class OpenerFalso:
    def __init__(self, home=None, erro=None):
        self.home, self.erro, self.chamadas = home, erro, []

    def open(self, req, timeout=None):
        self.chamadas.append(req.full_url)
        if self.erro:
            raise self.erro
        return Resp(self.home)


class TestAbreSessao(unittest.TestCase):
    def roda(self, op):
        with patch.object(dou.urllib.request, "build_opener", lambda *a, **k: op), \
             patch.object(dou.time, "sleep") as sleep:
            try:
                dou.abre_sessao("a@b", "x", log=open("/dev/null", "w"))
            finally:
                self.sleep = sleep

    def test_manutencao_levanta_na_hora(self):
        op = OpenerFalso(home="<h1>Estamos em manuten\u00e7\u00e3o</h1>")
        with self.assertRaises(dou.InlabsIndisponivel) as c:
            self.roda(op)
        self.assertIn("manutencao programada", str(c.exception))
        self.sleep.assert_not_called()
        self.assertEqual(len(op.chamadas), 1)      # nao chegou ao POST do login

    def test_manutencao_programada_sem_acento(self):
        op = OpenerFalso(home="Manutencao Programada em andamento")
        with self.assertRaises(dou.InlabsIndisponivel):
            self.roda(op)

    def test_404_mensagem_nova_e_uma_tentativa(self):
        err = urllib.error.HTTPError("u", 404, "nf", {}, None)
        op = OpenerFalso(erro=err)
        with self.assertRaises(RuntimeError) as c:
            self.roda(op)
        msg = str(c.exception)
        self.assertNotIsInstance(c.exception, dou.InlabsIndisponivel)
        self.assertIn("HTTP 404 no login do INLABS (endereco de login indisponivel)", msg)
        self.assertIn("1 tentativa", msg)
        self.assertNotIn("30", msg)
        self.sleep.assert_not_called()


class TestColetaDouPlanoB(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(__import__("os").environ,
                              {"INLABS_EMAIL": "a@b", "INLABS_SENHA": "x"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.itens_site = [{"titulo": "Lei Complementar 214", "url": "https://x/1",
                            "data": "2026-10-22", "fonte": "DOU DO1", "orgao": "", "ementa": "",
                            "texto_integral": "t", "balde": "forte", "continuacao": False,
                            "alerta": None, "pasta_arquivo": None}]
        self.diag = {"lidas": 5, "forte": 1, "revisar": 0, "baixados": 1,
                     "falhas_download": 0, "duplicados": 0, "sem_edicao": [], "erros": []}

    def test_inlabs_falha_usa_leitura_do_jornal(self):
        def falha(*a, **k):
            raise dou.InlabsIndisponivel("INLABS em manutencao programada")
        with patch.object(dou, "coleta", falha), \
             patch.object(dou_site, "coleta", lambda dias, hist=None, **k: (self.itens_site, self.diag)), \
             patch.object(varredura, "_carrega_historico", lambda: {}):
            r = varredura.coleta_dou("2026-10-29", dias=["2026-10-22"])
        self.assertEqual(r["metodo"], "leiturajornal")
        self.assertIsNone(r["erro"])
        self.assertEqual(r["total"], 1)
        self.assertIn("INLABS indisponivel (", r["aviso"])
        self.assertIn("manutencao programada", r["aviso"])
        self.assertIn("coletado pela Leitura do Jornal (in.gov.br)", r["aviso"])

    def test_dias_padrao_sao_d_menos_1_e_d(self):
        vistos = []
        def inlabs(dias, *a, **k):
            vistos.append(dias)
            return [], {"lidas": 0, "forte": 0, "revisar": 0}
        with patch.object(dou, "coleta", inlabs):
            r = varredura.coleta_dou("2026-10-29")
        self.assertEqual(vistos[0], ["2026-10-28", "2026-10-29"])
        self.assertEqual(r["metodo"], "inlabs")
        self.assertNotIn("aviso", r)

    def test_inlabs_ok_nao_chama_plano_b(self):
        def boom(*a, **k):
            raise AssertionError("plano B nao deveria rodar")
        with patch.object(dou, "coleta", lambda *a, **k: ([], {"lidas": 0, "forte": 0, "revisar": 0})), \
             patch.object(dou_site, "coleta", boom):
            r = varredura.coleta_dou("2026-10-29")
        self.assertEqual(r["metodo"], "inlabs")

    def test_ambos_falham(self):
        def falha(*a, **k):
            raise RuntimeError("login falhou")
        def falha2(*a, **k):
            raise RuntimeError("rede fora")
        with patch.object(dou, "coleta", falha), patch.object(dou_site, "coleta", falha2), \
             patch.object(varredura, "_carrega_historico", lambda: {}):
            r = varredura.coleta_dou("2026-10-29")
        self.assertIsNone(r["metodo"])
        self.assertIn("login falhou", r["erro"])
        self.assertIn("rede fora", r["erro"])
        self.assertEqual(r["itens"], [])

    def test_sem_credencial_tambem_tenta_plano_b(self):
        with patch.dict(__import__("os").environ, {"INLABS_EMAIL": "", "INLABS_SENHA": ""}), \
             patch.object(dou_site, "coleta", lambda dias, hist=None, **k: (self.itens_site, self.diag)), \
             patch.object(varredura, "_carrega_historico", lambda: {}):
            r = varredura.coleta_dou("2026-10-29")
        self.assertEqual(r["metodo"], "leiturajornal")
        self.assertIn("sem credencial", r["aviso"])


class TestGravaResultadoVistoEm(unittest.TestCase):
    def test_item_novo_ganha_visto_em_e_antigo_nao_muda(self):
        with tempfile.TemporaryDirectory() as tmp:
            dados = Path(tmp)
            antigo = {"titulo": "velho", "url": "https://x/velho"}
            chave_antiga = varredura.chave(antigo)
            (dados / "historico.json").write_text(json.dumps(
                {chave_antiga: {"primeira_vez": "2026-09-28", "fonte": "F", **antigo}}), "utf-8")
            resultado = [{"fonte": "F", "metodo": "http", "total": 2, "erro": None,
                          "itens": [antigo, {"titulo": "novo", "url": "https://x/novo"}]}]
            with patch.object(varredura, "DADOS", dados), \
                    patch("sys.stderr", io.StringIO()):
                varredura.grava_resultado("2026-09-30", resultado, "d.json", "n.json")
            hist = json.loads((dados / "historico.json").read_text("utf-8"))
            self.assertNotIn("visto_em", hist[chave_antiga])
            novo = hist[varredura.chave({"titulo": "novo", "url": "https://x/novo"})]
            self.assertRegex(novo["visto_em"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
            self.assertEqual(novo["primeira_vez"], "2026-09-30")


if __name__ == "__main__":
    unittest.main()
