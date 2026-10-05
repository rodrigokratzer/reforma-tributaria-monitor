import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import limpar_worktrees as lw


def git(*a, cwd):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)


class TestCandidatas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name) / "repo"
        self.raiz.mkdir()
        git("init", "-q", "-b", "main", cwd=self.raiz)
        git("config", "user.email", "t@t", cwd=self.raiz)
        git("config", "user.name", "t", cwd=self.raiz)
        (self.raiz / "a.txt").write_text("a")
        git("add", ".", cwd=self.raiz)
        git("commit", "-qm", "a", cwd=self.raiz)
        self.agora = time.time() + 30 * 86400   # "daqui a 30 dias": tudo e' antigo

    def tearDown(self):
        self.tmp.cleanup()

    def wt(self, nome, base=None):
        caminho = (base or self.raiz / ".claude" / "worktrees") / nome
        caminho.parent.mkdir(parents=True, exist_ok=True)
        git("worktree", "add", "-q", "-b", nome, str(caminho), cwd=self.raiz)
        return caminho

    def nomes(self, lista):
        return sorted(Path(x["caminho"]).name for x in lista)

    def test_remove_limpa_antiga_e_integrada(self):
        self.wt("sessao-a")
        rem, pend = lw.candidatas(self.raiz, self.agora)
        self.assertEqual(self.nomes(rem), ["sessao-a"])
        self.assertEqual(pend, [])

    def test_nunca_remove_com_mudanca_pendente(self):
        c = self.wt("sessao-suja")
        (c / "novo.txt").write_text("x")
        rem, pend = lw.candidatas(self.raiz, self.agora)
        self.assertEqual(rem, [])
        self.assertEqual(self.nomes(pend), ["sessao-suja"])

    def test_nunca_remove_com_commit_fora_do_main(self):
        c = self.wt("sessao-commit")
        (c / "b.txt").write_text("b")
        git("add", ".", cwd=c)
        git("commit", "-qm", "b", cwd=c)
        rem, pend = lw.candidatas(self.raiz, self.agora)
        self.assertEqual(rem, [])
        self.assertEqual(self.nomes(pend), ["sessao-commit"])

    def test_nunca_remove_recente(self):
        self.wt("sessao-nova")
        rem, pend = lw.candidatas(self.raiz, time.time())
        self.assertEqual(rem, [])

    def test_nunca_remove_protegida_nem_fora_do_diretorio(self):
        self.wt("migracao-notebook-local")
        self.wt("outra", base=Path(self.tmp.name) / "fora")
        rem, pend = lw.candidatas(self.raiz, self.agora)
        self.assertEqual(rem, [])

    def test_aplicar_remove_de_fato(self):
        c = self.wt("sessao-a")
        os.environ["LIMPAR_AGORA"] = str(self.agora)
        try:
            rc = lw.main(["--aplicar"], raiz=self.raiz, notificar=lambda m: None)
        finally:
            del os.environ["LIMPAR_AGORA"]
        self.assertEqual(rc, 0)
        self.assertFalse(c.exists())


if __name__ == "__main__":
    unittest.main()
