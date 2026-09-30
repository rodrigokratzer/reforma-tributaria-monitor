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
