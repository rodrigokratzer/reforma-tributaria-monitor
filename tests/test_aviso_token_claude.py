import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import aviso_token_claude as at

RAIZ = Path(__file__).resolve().parent.parent


class Regras(unittest.TestCase):
    def test_dias_restantes(self):
        self.assertEqual(at.dias_restantes(date(2026, 11, 23), date(2026, 11, 23)), 365)
        self.assertEqual(at.dias_restantes(date(2026, 11, 23), date(2027, 11, 23)), 0)

    def test_quando_avisa(self):
        avisa = [d for d in range(-3, 366) if at.deve_avisar(d)]
        self.assertEqual(avisa, [-3, -2, -1, 0, 1, 2, 3, 4, 5, 6, 7, 15, 30])

    def test_mensagens(self):
        vence = date(2027, 11, 23)
        self.assertIn("vence em 15 dia(s) (23/11/2027)", at.mensagem(15, vence))
        self.assertIn("vence HOJE", at.mensagem(0, vence))
        self.assertIn("VENCEU em 23/11/2027", at.mensagem(-2, vence))
        self.assertIn("claude setup-token", at.mensagem(7, vence))


class Main(unittest.TestCase):
    def rodar(self, conteudo, hoje):
        avisos = []
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d) / "criado_em"
            if conteudo is not None:
                arq.write_text(conteudo)
            self.assertEqual(at.main(arquivo=arq, hoje=hoje, avisar=avisos.append), 0)
        return avisos

    def test_sem_arquivo_nao_avisa(self):
        self.assertEqual(self.rodar(None, date(2027, 11, 20)), [])

    def test_longe_do_vencimento_nao_avisa(self):
        self.assertEqual(self.rodar("2026-11-23\n", date(2027, 6, 1)), [])

    def test_trinta_dias_antes_avisa(self):
        self.assertEqual(len(self.rodar("2026-11-23\n", date(2027, 10, 24))), 1)

    def test_data_ilegivel_avisa(self):
        avisos = self.rodar("ontem", date(2027, 1, 1))
        self.assertEqual(len(avisos), 1)
        self.assertIn("Não consegui ler", avisos[0])


class Unidades(unittest.TestCase):
    def ler(self, nome):
        return (RAIZ / "deploy" / "systemd" / nome).read_text()

    def test_drop_in_carrega_a_chave_sem_exigir_o_arquivo(self):
        s = self.ler("claude-token.conf")
        self.assertIn("EnvironmentFile=-/home/rodrigo/.config/claude-token/token.env", s)

    def test_timer_diario_persistente(self):
        t = self.ler("claude-token-aviso.timer")
        self.assertIn("OnCalendar=*-*-* 09:00:00", t)
        self.assertIn("Persistent=true", t)
        s = self.ler("claude-token-aviso.service")
        self.assertIn("scripts/aviso_token_claude.py", s)
        self.assertIn("User=rodrigo", s)

    def test_salvar_nao_mostra_a_chave(self):
        s = (RAIZ / "scripts" / "salvar_token_claude.sh").read_text()
        self.assertIn("read -rs token", s)
        self.assertNotIn('echo "$token"', s)
        self.assertIn("umask 077", s)


if __name__ == "__main__":
    unittest.main()
