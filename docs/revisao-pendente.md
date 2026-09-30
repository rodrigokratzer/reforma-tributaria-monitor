# Revisão pendente — evolução do painel (29/09/2026)

Decisões que tomei sozinho durante a implementação e pontos que dependem de
você. Nada aqui bloqueia o funcionamento; tudo pode ser ajustado depois.

## Precisa de ação sua

1. **Receber o push no celular.** Instale o app **ntfy** (Android: Play Store /
   F-Droid; iPhone: App Store), toque em "+" / "Subscribe to topic" e digite o
   tópico que está em `NTFY_TOPICO` no `.env` do lenovo-claude (também foi
   informado na conversa com o Claude — não fica aqui porque o repositório é
   público e quem souber o nome do tópico recebe os alertas). Servidor padrão
   (ntfy.sh). Um push de teste já foi enviado em 29/09.
2. **E-mail (opcional).** O código está pronto e desligado. Para ligar:
   crie (ou use) uma conta Gmail, ative a verificação em duas etapas, gere
   uma *senha de app* (myaccount.google.com → Segurança → Senhas de app) e
   acrescente ao `.env` do lenovo-claude:
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORTA=587
   SMTP_USUARIO=suaconta@gmail.com
   SMTP_SENHA=<senha de app de 16 letras>
   EMAIL_PARA=rodrigo.kratzer@gmail.com
   ```
   Não precisa reiniciar nada: o próximo ciclo já lê.

## Decisões que tomei (revise se quiser outra coisa)

3. **Turnos separados, não um texto único por dia.** Cada ciclo grava
   `analises/AAAA-MM-DD-matinal.md` ou `-noturna.md`. A noturna só fala do que
   apareceu depois da matinal — juntar exigiria reescrever o texto da manhã.
   No painel, o seletor mostra "30/09/2026 · matinal". Se preferir um texto
   por dia, dá para concatenar os dois na exibição sem mudar o armazenamento.
4. **Ciclo sem nada novo não chama o Claude.** Grava uma análise curta
   "Sem publicações novas desde a última análise" (economiza uso da
   assinatura). O push sai com prioridade baixa nesse caso — se preferir não
   receber push quando não há nada, é uma linha em `rodar_ciclo.sh`.
5. **O filtro do DOU não foi apertado.** O "revisar" vem da regra 5 do
   classificador (órgão do Ministério da Fazenda + ato normativo, sem nenhuma
   menção a IBS/CBS/LC 214). É largo de propósito, para não perder norma. A
   IA agora dá um veredito por item e o painel esconde o ruído por padrão.
   Depois de ~2 semanas de triagem dá para medir e, se quiser, excluir da
   regra 5 órgãos que só geram ruído (SUSEP, CMN, CVM, Previc, Secretaria de
   Prêmios e Apostas — hoje ~80 dos 219 itens "revisar").
6. **Itens antigos ficam "não triados".** Os ~234 itens "revisar" anteriores a
   30/09 não têm veredito (você disse que não precisa refazer o passado). Se
   quiser, rodo uma triagem única desse estoque — custa uma execução longa do
   Claude.
7. **Uso da assinatura dobra.** Duas análises por dia em vez de uma (a de
   29/09 consumiu o equivalente a ~US$ 0,90 em tokens de lista, coberto pela
   assinatura). Se bater limite, o ciclo não marca nada como analisado e os
   itens entram no seguinte, com alerta de falha.
8. **Plano B do GitHub Actions mudou de horário:** DOU às 07:10 e portais às
   07:40 (antes 04:10/05:10 — agora rodariam antes do ciclo local das 05:00).
9. **Fins de semana:** o ciclo roda todo dia, como antes.
10. **Correção extra no classificador do DOU:** passa a classificar pelo texto
    integral (antes cortava em 20.000 caracteres antes de classificar; 11
    matérias já tinham batido no teto).

## O que aconteceu no deploy (30/09/2026)

11. **Rotina antiga na nuvem do Claude pausada.** Existia uma rotina agendada
    em claude.ai ("Análise diária — reforma tributária", dias úteis 07:15)
    rodando em paralelo ao notebook — era ela que mandava o push pelo app do
    Claude. Com o fluxo novo ela duplicaria a análise no formato antigo, então
    foi **pausada** (não apagada). Se o ntfy ficar bom, dá para apagá-la em
    claude.ai → Code → Routines.
12. **Primeiro ciclo falhou, segundo passou.** O push do deploy disparou o
    GitHub Actions, que regenerou `docs/index.html` e o rebase local conflitou
    nesse arquivo gerado. Corrigido na causa (o Actions não regenera mais o
    painel em push, só quando `estado.json` muda) e na consequência
    (`scripts/publicar.sh` resolve conflito em `docs/` regenerando). Você deve
    ter recebido 2 pushes de falha às 09:06 (um do script, outro do systemd) e
    depois o push normal da análise matinal.
13. **Falha gera dois pushes** (o do `rodar_ciclo.sh` e o do `OnFailure=` do
    systemd, que cobre timeout/travamento). Se incomodar, deixo só um.

## Backup

- Tag `backup-pre-evolucao-20260929-1754` e branch
  `backup/pre-evolucao-20260929-1754` no GitHub.
- `~/backups/reforma-monitor-20260929-1754/` no lenovo-claude: tarball do
  repositório (com `.env`), cópia das units systemd antigas e lista de timers.
- Para voltar: `git reset --hard backup-pre-evolucao-20260929-1754` no
  checkout, recopiar as units do backup para `/etc/systemd/system/`,
  `daemon-reload`, desabilitar `reforma-ciclo.timer` e reabilitar os três
  timers antigos.
