import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from leitura import baixar


class _Handler(BaseHTTPRequestHandler):
    """Imita o Portal NF-e: sem cookie de sessao, redireciona para si mesmo."""

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/sessao"):
            if "ASP.NET_SessionId=ok" not in (self.headers.get("Cookie") or ""):
                self.send_response(302)
                self.send_header("Set-Cookie", "ASP.NET_SessionId=ok; path=/")
                self.send_header("Location", self.path)
                self.end_headers()
                return
            corpo = "<html><body>informe é aqui</body></html>".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(corpo)
        elif self.path == "/doc":
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            self.wfile.write(b"%PDF-1.4\n...")
        elif self.path == "/grande":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"x" * 5000)
        else:
            self.send_response(404)
            self.end_headers()


class TestSessao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), _Handler)
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_cookie_de_sessao_resolve_o_loop_de_redirect(self):
        html, url = baixar.Sessao(timeout=5).baixa_html(self.base + "/sessao?x=1")
        self.assertIn("informe é aqui", html)
        self.assertTrue(url.endswith("/sessao?x=1"))

    def test_pdf_reconhecido_pelo_conteudo_nao_pelo_cabecalho(self):
        r = baixar.Sessao(timeout=5).baixa(self.base + "/doc")
        self.assertTrue(baixar.eh_pdf(r.dados))

    def test_404_vira_erro_download(self):
        with self.assertRaises(baixar.ErroDownload) as cm:
            baixar.Sessao(timeout=5).baixa(self.base + "/nada")
        self.assertIn("404", str(cm.exception))

    def test_arquivo_grande_demais(self):
        with patch.object(baixar, "MAX_BYTES", 1000):
            with self.assertRaises(baixar.ErroDownload):
                baixar.Sessao(timeout=5).baixa(self.base + "/grande")

    def test_host_inexistente_vira_erro_download(self):
        with self.assertRaises(baixar.ErroDownload):
            baixar.Sessao(timeout=3).baixa("http://127.0.0.1:1/x")


class TestEhPdf(unittest.TestCase):
    def test_casos(self):
        self.assertTrue(baixar.eh_pdf(b"%PDF-1.7\n"))
        self.assertTrue(baixar.eh_pdf(b"\r\n  %PDF-1.4"))
        self.assertFalse(baixar.eh_pdf(b"<html>%PDF</html>"[:4]))
        self.assertFalse(baixar.eh_pdf(b"<!DOCTYPE html>"))


if __name__ == "__main__":
    unittest.main()
