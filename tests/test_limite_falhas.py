import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import limite_falhas as lf

RAIZ = Path(__file__).resolve().parent.parent

OK = "robo-comentarios-analise.service: Deactivated successfully."
FALHA = "robo-comentarios-analise.service: Failed with result 'exit-code'."
TIMEOUT = "robo-comentarios-ciclo.service: Failed with result 'timeout'."


class FalhasSeguidas(unittest.TestCase):
    def test_conta_ate_o_ultimo_sucesso(self):
        linhas = [FALHA, FALHA, OK, "Starting x...", FALHA, "Triggering OnFailure", FALHA]
        self.assertEqual(lf.falhas_seguidas(linhas), 2)

    def test_timeout_conta_como_falha(self):
        self.assertEqual(lf.falhas_seguidas([OK, TIMEOUT, TIMEOUT, TIMEOUT]), 3)

    def test_sem_log(self):
        self.assertEqual(lf.falhas_seguidas([]), 0)


class Decidir(unittest.TestCase):
    def test_primeira_avisa(self):
        self.assertEqual(lf.decidir(1, 3), "avisar")

    def test_log_ilegivel_avisa(self):
        self.assertEqual(lf.decidir(0, 3), "avisar")

    def test_entre_a_primeira_e_o_limite_cala(self):
        self.assertEqual(lf.decidir(2, 3), "calar")
        self.assertEqual(lf.decidir(11, 12), "calar")

    def test_no_limite_e_depois_pausa(self):
        self.assertEqual(lf.decidir(3, 3), "pausar")
        self.assertEqual(lf.decidir(5, 3), "pausar")

    def test_limites(self):
        self.assertEqual(lf.limite_de("robo-comentarios-ciclo.service"), 12)
        self.assertEqual(lf.limite_de("robo-comentarios-analise.service"), 3)
        self.assertEqual(lf.limite_de("reforma-ciclo.service"), 3)


class FakeSystemd:
    """Simula systemctl/journalctl e guarda os comandos recebidos."""

    def __init__(self, linhas, gatilho="robo-comentarios-analise.timer", desde="@1795435444",
                 stop_ok=True):
        self.linhas, self.gatilho, self.desde, self.stop_ok = linhas, gatilho, desde, stop_ok
        self.cmds = []

    def __call__(self, cmd):
        self.cmds.append(cmd)
        if cmd[:2] == ["systemctl", "show"] and "TriggeredBy" in cmd:
            return 0, (self.gatilho or "") + "\n"
        if cmd[:2] == ["systemctl", "show"] and "ActiveEnterTimestamp" in cmd:
            return 0, self.desde + "\n"
        if cmd[0] == "journalctl":
            return 0, "\n".join(self.linhas) + "\n"
        if cmd[:2] == ["systemctl", "stop"]:
            return (0 if self.stop_ok else 1), ""
        raise AssertionError(cmd)

    def parou(self):
        return [c for c in self.cmds if c[:2] == ["systemctl", "stop"]]


class Main(unittest.TestCase):
    UNI = "robo-comentarios-analise.service"

    def rodar(self, fake):
        avisos = []
        cod = lf.main([self.UNI], rodar=fake, avisar=avisos.append)
        self.assertEqual(cod, 0)
        return avisos

    def test_primeira_falha_avisa_e_nao_pausa(self):
        fake = FakeSystemd([OK, FALHA])
        avisos = self.rodar(fake)
        self.assertEqual(len(avisos), 1)
        self.assertIn("com 3 falhas seguidas a rotina é pausada", avisos[0])
        self.assertEqual(fake.parou(), [])

    def test_le_o_log_so_desde_que_o_timer_foi_ligado(self):
        fake = FakeSystemd([FALHA])
        self.rodar(fake)
        journal = [c for c in fake.cmds if c[0] == "journalctl"][0]
        self.assertIn("UNIT=" + self.UNI, journal)
        self.assertEqual(journal[journal.index("--since") + 1], "@1795435444")

    def test_segunda_falha_nao_avisa(self):
        fake = FakeSystemd([OK, FALHA, FALHA])
        self.assertEqual(self.rodar(fake), [])
        self.assertEqual(fake.parou(), [])

    def test_terceira_falha_pausa_o_timer_e_avisa_como_religar(self):
        fake = FakeSystemd([FALHA, FALHA, FALHA])
        avisos = self.rodar(fake)
        self.assertEqual(fake.parou(), [["systemctl", "stop", "robo-comentarios-analise.timer"]])
        self.assertEqual(len(avisos), 1)
        self.assertIn("PAUSADA", avisos[0])
        self.assertIn("sudo systemctl start robo-comentarios-analise.timer", avisos[0])

    def test_pausa_o_path_quando_nao_ha_timer(self):
        fake = FakeSystemd([FALHA] * 3, gatilho="painel-instagram-novos.path")
        self.rodar(fake)
        self.assertEqual(fake.parou(), [["systemctl", "stop", "painel-instagram-novos.path"]])

    def test_sem_gatilho_avisa_sem_pausar(self):
        fake = FakeSystemd([FALHA] * 3, gatilho=None)
        avisos = self.rodar(fake)
        self.assertEqual(fake.parou(), [])
        self.assertEqual(len(avisos), 1)
        self.assertNotIn("PAUSADA", avisos[0])

    def test_se_nao_conseguir_parar_nao_diz_que_pausou(self):
        fake = FakeSystemd([FALHA] * 3, stop_ok=False)
        avisos = self.rodar(fake)
        self.assertNotIn("PAUSADA", avisos[0])

    def test_erro_ao_ler_log_avisa_como_antes(self):
        def quebra(cmd):
            raise OSError("sem systemctl")
        avisos = []
        lf.main([self.UNI], rodar=quebra, avisar=avisos.append)
        self.assertEqual(len(avisos), 1)

    def test_sem_argumento(self):
        self.assertEqual(lf.main([], rodar=FakeSystemd([]), avisar=lambda m: None), 2)


class Unidade(unittest.TestCase):
    def test_reforma_falha_passa_pelo_limite_como_root(self):
        s = (RAIZ / "deploy" / "systemd" / "reforma-falha@.service").read_text()
        self.assertIn("ExecStart=+/home/rodrigo/projects/reforma-tributaria-monitor/.venv/bin/python3 "
                      "scripts/limite_falhas.py %i", s)
        self.assertNotIn("notificar.py --falha", s)


if __name__ == "__main__":
    unittest.main()
