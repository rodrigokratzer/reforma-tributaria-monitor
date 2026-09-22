# Operação local (lenovo-claude)

Este documento descreve como esta instância específica do projeto roda de
fato — não é o guia genérico de fork (esse continua em README.md, "Como
rodar uma cópia sua", e continua funcionando só com GitHub Actions).

**Estado atual:** as unidades systemd descritas aqui existem como **arquivos
neste repositório** (`deploy/systemd/`) e foram testadas manualmente, mas
ainda **não estão instaladas nem habilitadas** na máquina de produção
(`/home/rodrigo/projects/reforma-tributaria-monitor`, branch `main`) — que
ainda não tem `.venv` nem `.env`. Ou seja: hoje quem coleta de verdade é o
GitHub Actions, e os horários "todo dia às 01:07/02:10/02:40" descritos
abaixo descrevem o alvo, não o que já acontece. Ativar isso é um passo de
deploy manual, supervisionado por uma pessoa — ver
"[Instalação inicial](#instalação-inicial)" abaixo, que é o próximo passo.

## O quê roda onde

| Etapa | Onde | Quando |
|---|---|---|
| DOU (INLABS) | `lenovo-claude`, systemd | 01:07, todo dia |
| 12 portais web | `lenovo-claude`, systemd | 02:10, todo dia |
| Análise diária | `lenovo-claude`, systemd, via `claude -p` | 02:40, todo dia |
| Plano B (DOU) | GitHub Actions | 04:10, todo dia, só se o notebook não coletou |
| Plano B (portais) | GitHub Actions | 05:10, todo dia, só se o notebook não coletou |

As raias do DOU e da varredura regeneram `docs/index.html` elas mesmas
(chamam `scripts/gerar_painel.py` no próprio wrapper), mas a raia da
**análise não** — quando o único resultado do dia é uma análise nova
(`analises/**` ou `dados/analise_status.json`), o painel é regenerado pelo
gatilho `push` do GitHub Actions, que já observa exatamente esses caminhos.
Isso é de propósito (é a arquitetura descrita na spec), não um esquecimento:
`rodar_analise_diaria.sh` não chama `gerar_painel.py`.

Os dois planos B só coletam de verdade quando o arquivo do dia **não existe
ou não tem conteúdo real**: o `dou.yml` checa se alguma fonte tem `metodo`
não-nulo, justamente para que um snapshot degradado (ex.: `.env` vazio no
notebook, que faz `dou_diario.py` gravar `{"metodo": null}`) não desative a
rede de segurança bem na hora em que ela é necessária.

## Verificar status

```bash
systemctl list-timers 'reforma-*'
journalctl -u reforma-dou.service -n 50
journalctl -u reforma-varredura.service -n 50
journalctl -u reforma-analise.service -n 50
```

## Credenciais

`INLABS_EMAIL`/`INLABS_SENHA` ficam em `.env` na raiz do repo (fora do git,
ver `.env.example` para o formato), lidas pelas unidades systemd via
`EnvironmentFile=`.

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

**5. Habilitar um timer de cada vez, deixando o DOU por último**

O DOU é o mais lento e o mais arriscado (login do INLABS, até 30 tentativas),
então habilite-o só depois de ver os outros dois funcionando:

```bash
sudo systemctl enable --now reforma-varredura.timer
sudo systemctl enable --now reforma-analise.timer
sudo systemctl enable --now reforma-dou.timer
```

Atenção: com `Persistent=true`, se o horário do dia já passou, o `--now` faz o
timer disparar quase imediatamente — inclusive a análise, que faz push num
repositório público. Habilite cada um quando estiver pronto para vê-lo rodar,
e acompanhe com `journalctl -u <unidade>.service -f`.

**6. Conferir o agendamento**

```bash
systemctl list-timers 'reforma-*'
```

Os três devem aparecer com `NEXT` no horário correto (01:07, 02:10 e 02:40).

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
