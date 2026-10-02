import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import textos
import varredura
from portais.base import chave


class TestTextos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dados = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_grava_e_le(self):
        textos.grava(self.dados, "abc", "corpo integral")
        self.assertTrue(textos.existe(self.dados, "abc"))
        self.assertEqual(textos.le(self.dados, "abc"), "corpo integral")
        self.assertEqual(textos.caminho(self.dados, "abc"),
                         self.dados / "textos" / "abc.txt")

    def test_le_inexistente_e_none(self):
        self.assertIsNone(textos.le(self.dados, "nada"))
        self.assertFalse(textos.existe(self.dados, "nada"))

    def test_grava_sem_corte_de_tamanho(self):
        grande = "x" * 1_000_000
        textos.grava(self.dados, "g", grande)
        self.assertEqual(len(textos.le(self.dados, "g")), 1_000_000)

    def test_nao_deixa_tmp_para_tras(self):
        textos.grava(self.dados, "abc", "a")
        self.assertEqual([p.name for p in (self.dados / "textos").iterdir()], ["abc.txt"])


class TestGravaResultadoTextoIntegral(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dados = Path(self.tmp.name)
        self.p = patch.object(varredura, "DADOS", self.dados)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def _resultado(self, **extra):
        it = {"titulo": "Resolucao CGIBS n 9", "url": "https://x/r9", "data": None,
              "pasta_arquivo": None, "alerta": None, **extra}
        return [{"fonte": "F", "url": "https://x", "metodo": "http", "total": 1,
                 "erro": None, "itens": [it]}], it

    def test_texto_integral_vai_para_arquivo_e_sai_dos_json(self):
        res, it = self._resultado(texto_integral="CORPO INTEGRAL")
        k = chave(it)
        varredura.grava_resultado("2026-10-01", res, "2026-10-01.json", "novidades.json")
        self.assertEqual(textos.le(self.dados, k), "CORPO INTEGRAL")
        hist = json.loads((self.dados / "historico.json").read_text("utf-8"))
        self.assertNotIn("texto_integral", hist[k])
        dia = (self.dados / "2026-10-01.json").read_text("utf-8")
        self.assertNotIn("CORPO INTEGRAL", dia)
        nov = (self.dados / "novidades.json").read_text("utf-8")
        self.assertNotIn("CORPO INTEGRAL", nov)

    def test_item_ja_no_historico_ganha_arquivo_se_faltava(self):
        res, it = self._resultado()
        varredura.grava_resultado("2026-10-01", res, "a.json", "n.json")
        res2, it2 = self._resultado(texto_integral="AGORA COM TEXTO")
        varredura.grava_resultado("2026-10-02", res2, "b.json", "n.json")
        self.assertEqual(textos.le(self.dados, chave(it2)), "AGORA COM TEXTO")

    def test_nao_sobrescreve_arquivo_existente(self):
        res, it = self._resultado(texto_integral="PRIMEIRO")
        varredura.grava_resultado("2026-10-01", res, "a.json", "n.json")
        res2, _ = self._resultado(texto_integral="SEGUNDO")
        varredura.grava_resultado("2026-10-01", res2, "a.json", "n.json")
        self.assertEqual(textos.le(self.dados, chave(it)), "PRIMEIRO")

    def test_texto_integral_vazio_nao_cria_arquivo(self):
        res, it = self._resultado(texto_integral="   ")
        varredura.grava_resultado("2026-10-01", res, "a.json", "n.json")
        self.assertFalse(textos.existe(self.dados, chave(it)))


if __name__ == "__main__":
    unittest.main()
