import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from leitura import pdf
from util_pdf import pdf_minimo

TEM_POPPLER = all(shutil.which(b) for b in ("pdfinfo", "pdftotext", "pdftoppm"))
TEM_TESSERACT = shutil.which("tesseract") is not None
LONGO = "x" * 400


class TestDecisaoPorPagina(unittest.TestCase):
    """Logica de decisao com os binarios simulados."""

    def _roda(self, textos_paginas, ocr_por_pagina, tem_ocr=True):
        with patch.object(pdf, "num_paginas", return_value=len(textos_paginas)), \
             patch.object(pdf, "texto_pagina", side_effect=lambda a, n: textos_paginas[n - 1]), \
             patch.object(pdf, "ocr_pagina", side_effect=lambda a, n, p: ocr_por_pagina[n]) as ocr, \
             patch.object(pdf, "tem_ocr", return_value=tem_ocr):
            return pdf.extrai_pdf(b"%PDF-1.4 falso"), ocr

    def test_paginas_com_texto_nao_passam_por_ocr(self):
        r, ocr = self._roda([LONGO, LONGO], {})
        self.assertEqual(r["origem"], "pdf")
        self.assertEqual(r["paginas_ocr"], [])
        self.assertEqual(r["paginas"], 2)
        ocr.assert_not_called()

    def test_pagina_so_com_carimbo_vai_para_ocr(self):
        carimbo = "FLAVIO CESAR Assinado de forma digital"
        r, _ = self._roda([carimbo], {1: "ATO CONJUNTO RFB/CGIBS " + LONGO})
        self.assertEqual(r["origem"], "pdf+ocr")
        self.assertEqual(r["paginas_ocr"], [1])
        self.assertIn("ATO CONJUNTO RFB/CGIBS", r["texto"])

    def test_pdf_misto_ocr_so_na_pagina_escaneada(self):
        r, ocr = self._roda([LONGO, "", LONGO], {2: "pagina escaneada " + LONGO})
        self.assertEqual(r["paginas_ocr"], [2])
        self.assertEqual(ocr.call_count, 1)
        self.assertIn("[pagina 2]\npagina escaneada", r["texto"])

    def test_ocr_pior_que_texto_mantem_texto(self):
        r, _ = self._roda(["curto mas real"], {1: ""})
        self.assertEqual(r["origem"], "pdf")
        self.assertIn("curto mas real", r["texto"])

    def test_sem_tesseract_e_pagina_vazia_levanta(self):
        with self.assertRaises(pdf.ErroPDF) as cm:
            self._roda([LONGO, ""], {}, tem_ocr=False)
        self.assertIn("tesseract", str(cm.exception))


@unittest.skipUnless(TEM_POPPLER, "poppler-utils ausente")
class TestPopplerReal(unittest.TestCase):
    def test_pdf_com_texto(self):
        linhas = [f"Linha {i} do Ato Conjunto RFB CGIBS sobre o IBS e a CBS" for i in range(12)]
        r = pdf.extrai_pdf(pdf_minimo(linhas))
        self.assertEqual(r["paginas"], 1)
        self.assertIn("Linha 11 do Ato Conjunto", r["texto"])
        self.assertEqual(r["origem"], "pdf")

    def test_pdf_corrompido_levanta_erro_pdf(self):
        with self.assertRaises(pdf.ErroPDF):
            pdf.extrai_pdf(b"%PDF-1.4\nlixo sem estrutura nenhuma")


@unittest.skipUnless(TEM_POPPLER and TEM_TESSERACT, "tesseract ausente")
class TestOCRReal(unittest.TestCase):
    def test_ocr_le_pagina_renderizada(self):
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d) / "a.pdf"
            arq.write_bytes(pdf_minimo(["RESOLUCAO CGIBS NUMERO SETE"], tamanho=28))
            t = pdf.ocr_pagina(arq, 1, d)
        self.assertIn("CGIBS", t.upper())


if __name__ == "__main__":
    unittest.main()
