import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import semear_analisados as s


class TestSemear(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        (self.raiz / "dados").mkdir()
        h = {
            "velha": {"fonte": "Portal NF-e - Notas Tecnicas", "data": "2019-05-01"},
            "sem_data": {"fonte": "Portal NF-e - Notas Tecnicas", "data": None},
            "recente": {"fonte": "Portal NF-e - Notas Tecnicas", "data": "2026-09-20"},
            "outra_fonte": {"fonte": "CGIBS - Noticias", "data": "2019-01-01"},
            "ja_feita": {"fonte": "Portal NF-e - Notas Tecnicas", "data": "2019-01-01"},
        }
        (self.raiz / "dados" / "historico.json").write_text(json.dumps(h))
        (self.raiz / "dados" / "analisados.json").write_text(json.dumps({"chaves": ["ja_feita"]}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_candidatas(self):
        c = s.candidatas(self.raiz, {"Portal NF-e - Notas Tecnicas"}, "2026-10-01", 30)
        self.assertEqual(sorted(c), ["sem_data", "velha"])

    def test_aplicar_acrescenta_sem_apagar(self):
        s.main(["--fonte", "Portal NF-e - Notas Tecnicas", "--aplicar"],
               raiz=self.raiz, hoje="2026-10-01")
        feitas = json.loads((self.raiz / "dados" / "analisados.json").read_text())["chaves"]
        self.assertEqual(feitas, sorted(["ja_feita", "sem_data", "velha"]))

    def test_sem_aplicar_nao_grava(self):
        s.main(["--fonte", "Portal NF-e - Notas Tecnicas"], raiz=self.raiz, hoje="2026-10-01")
        feitas = json.loads((self.raiz / "dados" / "analisados.json").read_text())["chaves"]
        self.assertEqual(feitas, ["ja_feita"])


if __name__ == "__main__":
    unittest.main()
