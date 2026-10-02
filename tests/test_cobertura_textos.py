import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import cobertura_textos
import textos


class TestCobertura(unittest.TestCase):
    def test_contagem_por_fonte(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            (raiz / "dados").mkdir()
            (raiz / "dados" / "historico.json").write_text(json.dumps({
                "a": {"fonte": "CGIBS - Portarias"}, "b": {"fonte": "CGIBS - Portarias"},
                "c": {"fonte": "CGIBS - Portarias"}, "d": {"fonte": "RFB - Noticias 2026"}}))
            (raiz / "dados" / "leituras.json").write_text(json.dumps({
                "a": {"status": "lido", "origem": "pdf+ocr"}, "b": {"status": "falhou"}}))
            textos.grava(raiz / "dados", "a", "x")
            c = cobertura_textos.cobertura(raiz)
        p = c["CGIBS - Portarias"]
        self.assertEqual((p["total"], p["com_texto"], p["ocr"], p["falhou"], p["sem_tentativa"]),
                         (3, 1, 1, 1, 1))
        self.assertEqual(c["RFB - Noticias 2026"]["sem_tentativa"], 1)


if __name__ == "__main__":
    unittest.main()
