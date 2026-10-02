# Operação local (lenovo-claude)

Este documento descreve como esta instância específica do projeto roda de
fato — não é o guia genérico de fork (esse continua em README.md, "Como
rodar uma cópia sua", e continua funcionando só com GitHub Actions).

**Estado atual (30/09/2026):** um único timer systemd, `reforma-ciclo.timer`,
roda o ciclo completo duas vezes por dia. As três unidades antigas
(`reforma-dou`, `reforma-varredura`, `reforma-analise`, 01:07/02:10/02:40)
foram desabilitadas e removidas.

## O quê roda onde

| Etapa | Onde | Quando |
|---|---|---|
| Ciclo matinal: DOU → 16 fontes web → leitura (OCR) → análise → alerta | `lenovo-claude`, systemd (`reforma-ciclo`) | 05:00, todo dia |
| Ciclo noturno: idem | `lenovo-claude`, systemd (`reforma-ciclo`) | 17:00, todo dia |
| Alerta de falha | `reforma-falha@.service` (via `OnFailure=`) | quando o ciclo falha ou estoura 4h |
| Plano B (DOU) | GitHub Actions | 07:10, todo dia, só se o notebook não coletou |
| Plano B (portais) | GitHub Actions | 07:40, todo dia, só se o notebook não coletou |

Por que 05:00 e não 01:07: à 01:07 a edição do DOU do próprio dia ainda não
existe no INLABS (0 matérias, medido em 29/09/2026) — ela só entrava na
coleta do dia seguinte. Às 05:00 já está lá.

`scripts/rodar_ciclo.sh` chama, em ordem, `rodar_dou.sh`, `rodar_varredura.sh`
e `rodar_analise.sh <turno>` (cada um faz o próprio pull/commit/push; a falha
de um não impede os seguintes) e termina com `scripts/notificar.py`. O turno
sai da hora real da execução (antes de 12h = `matinal`, senão `noturna`),
então o catch-up do `Persistent=true` cai no turno certo. Para rodar na mão:

```bash
TURNO=noturna scripts/rodar_ciclo.sh            # ciclo inteiro
sudo systemctl start reforma-ciclo.service      # idem, pelo systemd (com flock e .env)
```

A análise (`rodar_analise.sh`) congela a lacuna em
`~/.local/state/reforma/lacuna-<data>-<turno>.json`, chama `claude -p` (que só
escreve arquivos, nunca faz git), valida com `scripts/fechar_analise.py` e só
então marca os itens como analisados, regenera o painel e faz commit/push. Se
não houver item novo, não chama o Claude: grava uma análise curta "sem
publicações novas", para o histórico do painel não ter buraco.

## Leitura integral (OCR)

Depois da varredura, `rodar_varredura.sh` chama `scripts/ler_textos.py`, que
guarda o texto integral de cada publicação em `dados/textos/<chave>.txt`
(HTML, PDF por `pdftotext` e OCR nas páginas sem camada de texto). Pacotes do
sistema:

```bash
sudo apt-get install -y tesseract-ocr tesseract-ocr-por poppler-utils
tesseract --list-langs | grep -x por
```

Orçamento: 45 min por ciclo (o OCR é lento e tudo bem; o que sobra fica para o
ciclo seguinte). Falha na leitura não impede a publicação da varredura. Para
diagnóstico, `dados/leituras.json` tem o status de cada item (`lido`,
`parcial`, `falhou`, `desistiu`) e a origem do texto. Reler um item:

```bash
.venv/bin/python3 scripts/ler_textos.py --chave <chave>
.venv/bin/python3 scripts/ler_textos.py --sem-limite     # backfill manual
```

A lacuna da análise espera a leitura por até 3 dias (`aguardando_leitura`).

## Verificar status

```bash
systemctl list-timers 'reforma-*'
journalctl -u reforma-ciclo.service -n 100
ls ~/.local/state/reforma/     # lacunas e saída crua do claude de cada ciclo
```

## Alertas

`scripts/notificar.py` manda o resumo de cada ciclo:

- **Push no celular (ntfy):** app ntfy (Android/iOS) inscrito no tópico que
  está em `NTFY_TOPICO` no `.env`. O tópico é o segredo — quem souber o nome
  recebe os alertas; por isso ele não fica no repositório.
- **E-mail:** liga sozinho quando o `.env` tiver `SMTP_HOST`, `SMTP_USUARIO`,
  `SMTP_SENHA` e `EMAIL_PARA` (Gmail: `smtp.gmail.com`, porta 587, senha de
  app). Sem isso, o canal é pulado sem erro.

Prioridade alta quando a análise tem itens em "Ação requerida" (`acoes` no
status); urgente em falha do ciclo.

## Credenciais

`INLABS_EMAIL`/`INLABS_SENHA`, `NTFY_TOPICO` e as `SMTP_*` ficam em `.env` na
raiz do repo (fora do git, ver `.env.example` para o formato), lidas pelas
unidades systemd via `EnvironmentFile=`.

## Instalação inicial

Passo a passo do primeiro deploy na máquina de produção
(`/home/rodrigo/projects/reforma-tributaria-monitor`, branch `main`), na
ordem. Rodar como o usuário `rodrigo` (os passos com `sudo` pedem senha, então
precisam de um terminal interativo de verdade).

**1. Criar o venv e instalar as dependências**

```bash
cd /home/rodrigo/projects/reforma-tributaria-monitor
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install --with-deps chromium
```

(`.venv/` é ignorado pelo git. O `--with-deps` instala bibliotecas de sistema
do Chromium e pede `sudo`.)

**2. Criar o `.env` com as credenciais reais do INLABS**

```bash
cp .env.example .env
$EDITOR .env    # preencher INLABS_EMAIL e INLABS_SENHA
chmod 600 .env
```

Sem isso o `dou_diario.py` não falha — ele grava um snapshot vazio com
`"metodo": null`. Por isso o plano B do GitHub Actions checa o conteúdo, e não
só a existência do arquivo: um `.env` esquecido aqui não desliga a rede de
segurança.

**3. Confirmar que o `git push` funciona sem interação, ANTES de habilitar
qualquer timer**

Como o usuário `rodrigo` (o mesmo `User=` das unidades systemd), no terminal:

```bash
cd /home/rodrigo/projects/reforma-tributaria-monitor
git push --dry-run
```

Precisa completar sem pedir usuário/senha e sem abrir navegador. Se pedir
qualquer coisa, os timers vão falhar silenciosamente de madrugada — os
wrappers terminam em `git push`, e um prompt de credencial numa sessão sem
terminal simplesmente trava ou falha.

Vale conferir isto de novo depois de atualizações do sistema: o helper de
credencial que o `gh auth setup-git` configura fica **fixado numa revisão
específica do snap** — hoje, nesta máquina, `!/snap/gh/751/gh auth
git-credential`. Quando o snap do `gh` atualiza, aquela revisão desaparece do
disco e o `git push` não autenticado passa a falhar sem aviso claro. Se os
pushes começarem a falhar depois de uma atualização, rode `gh auth setup-git`
de novo para reapontar o helper.

**4. Instalar as unidades systemd**

```bash
cd /home/rodrigo/projects/reforma-tributaria-monitor
sudo cp deploy/systemd/reforma-*.service deploy/systemd/reforma-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
```

**5. Habilitar o timer do ciclo**

```bash
sudo systemctl enable reforma-ciclo.timer
sudo systemctl start reforma-ciclo.timer
```

Atenção: com `Persistent=true`, se o horário do dia já passou, o `--now` faz o
timer disparar quase imediatamente — inclusive a análise, que faz push num
repositório público. Habilite cada um quando estiver pronto para vê-lo rodar,
e acompanhe com `journalctl -u <unidade>.service -f`.

**6. Conferir o agendamento**

```bash
systemctl list-timers 'reforma-*'
```

Deve aparecer `reforma-ciclo.timer` com `NEXT` às 05:00 ou 17:00.

## Reinstalar as unidades systemd depois de editar os arquivos em `deploy/systemd/`

```bash
sudo cp deploy/systemd/reforma-*.service deploy/systemd/reforma-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
```

O `daemon-reload` já basta para o systemd passar a enxergar o novo conteúdo
dos unit files. **Não** reinicie os timers por reflexo: como eles são
`Persistent=true`, um `systemctl restart` de um timer cuja janela do dia já
passou pode dispará-lo na hora — inclusive o da análise, que faz push num
repositório público. Reinicie só deliberadamente, quando for isso que você
quer.
