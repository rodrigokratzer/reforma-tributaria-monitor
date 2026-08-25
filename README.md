# Monitor da Reforma Tributária

Varredura diária das fontes oficiais da reforma tributária brasileira do consumo
(EC 132/2023, LC 214/2025, LC 227/2026), com painel público e resumo diário
gerado automaticamente.

**Painel:** https://rodrigokratzer.github.io/reforma-tributaria-monitor/

O projeto separa deliberadamente duas camadas:

| Camada | O que é | Quem faz |
|---|---|---|
| **Fatos** | o que foi publicado, quando, em qual fonte | este repositório, sozinho (GitHub Actions) |
| **Análise** | o que mudou, qual o impacto, o que fazer | um agente Claude agendado, ver [Análise diária automatizada](#análise-diária-automatizada) |

A camada de fatos não usa IA e não interpreta nada. Ela abre as páginas, compara
com o que já viu e registra o que é novo. O painel fica de pé mesmo em dia sem
análise nenhuma — mostra as publicações, os prazos e o status das fontes. A
análise é IA, mas roda separada: se ela falhar ou atrasar, os fatos continuam
publicados normalmente.

---

## O que ele varre

**Doze fontes web, todo dia útil às 06:40 (Brasília):**

- **CGIBS** — notícias, leis, resoluções, regulamentos, portarias, atos conjuntos,
  atos técnicos conjuntos e relatórios
- **Receita Federal** — notícias gerais e a área da Reforma Tributária do Consumo
- **Portal NF-e** — informes e Notas Técnicas
- **Portal DF-e da SVRS** — espelho que publica as mesmas Notas Técnicas

Um navegador real (Playwright/Chromium) abre cada página, porque várias delas
montam o conteúdo por JavaScript e voltam vazias para um cliente HTTP comum.

**DOU (via INLABS), separado, às 02:00 (Brasília):** a edição completa do
Diário Oficial, em workflow próprio — não compete por horário com os outros
12 portais nem com o orçamento de tempo deles. Ver
[DOU: coleta separada, com mais retentativa](#dou-coleta-separada-com-mais-retentativa)
para o porquê e como funciona.

---

## Como rodar uma cópia sua

1. **Fork ou novo repositório público.** Público dá GitHub Actions ilimitado e
   GitHub Pages incluído. Em repositório privado o Pages exige plano pago.
2. **Settings → Actions → General → Workflow permissions:** marque
   *Read and write permissions*. Sem isso o commit diário falha.
3. **Settings → Pages → Source:** *Deploy from a branch*, branch `main`, pasta `/docs`.
4. **Actions → Varredura Reforma Tributária → Run workflow** para a primeira carga.

Não há segredo obrigatório para os 12 portais web. As credenciais do INLABS
(`INLABS_EMAIL`, `INLABS_SENHA`, cadastro gratuito em inlabs.in.gov.br) são
necessárias só para o workflow **DOU (INLABS)** — sem elas, essa fonte é
simplesmente pulada, sem derrubar o resto.

**A análise diária automatizada não vem de graça com o fork.** Ela depende de
uma rotina agendada configurada na conta Claude de quem opera o painel (skill
`/schedule` do Claude Code) — é externa a este repositório. Sem ela, o projeto
funciona igual, só que a seção "Resumo do dia" do painel fica sem atualização
automática (continua aceitando `analises/AAAA-MM-DD.md` escrito à mão). Ver
[Análise diária automatizada](#análise-diária-automatizada).

---

## Estrutura

```
scripts/varredura.py          coleta as 12 fontes web (06:40)
scripts/dou_diario.py         coleta o DOU via INLABS, separado (02:00)
scripts/dou.py                login e classificação do DOU — compartilhado por
                               dou_diario.py e scripts/medir_inlabs.py
scripts/lacuna_analise.py     identifica o que falta analisar desde a última
                               analises/AAAA-MM-DD.md publicada
scripts/analise_brief.md      critério e formato que a análise diária segue
scripts/gerar_painel.py       monta docs/index.html
scripts/painel_template.html  layout e CSS do painel
scripts/medir_inlabs.py       medição do filtro do DOU (opcional, ver abaixo)
tests/test_lacuna_analise.py  testes de scripts/lacuna_analise.py (unittest)
estado.json                   camada curada: prazos, pendências, linha do tempo
analises/AAAA-MM-DD.md        análise do dia (opcional, ver Análise diária automatizada)
dados/                        gerado pelo robô — não editar à mão
  ├─ AAAA-MM-DD.json          instantâneo dos 12 portais web do dia
  ├─ AAAA-MM-DD-dou.json      instantâneo do DOU do dia (arquivo próprio)
  ├─ novidades.json           novidades da última varredura web
  ├─ novidades_dou.json       novidades da última coleta do DOU
  ├─ historico.json           índice acumulado, compartilhado pelas duas coletas
  └─ analise_status.json      status da última execução da análise diária
docs/index.html               o painel publicado — gerado, não editar à mão
```

**O que se edita à mão:** só `estado.json` (quando um prazo muda ou uma pendência
é resolvida). `analises/` e `dados/analise_status.json` também podem ser
editados à mão, mas normalmente são escritos pela rotina de análise diária.
Salvou e deu push? O painel se regenera sozinho.

---

## Decisões de projeto que valem conhecer

Cada uma destas veio de um erro real. Estão aqui para não serem refeitas.

### Novidade é "nunca vi este link", não "a data é recente"

Fontes oficiais publicam com data errada. O CGIBS listou o **Ato Conjunto
RFB/CGIBS nº 5/2026 como sendo de 2025** — ordenando por data, ele desaparece no
fim da lista. Por isso a detecção compara links já vistos, não datas.

O scraper ainda confere a data declarada contra a pasta de upload do arquivo
(`/202608/`) e **marca o item** quando a diferença é implausível: ano diferente ou
data posterior à publicação. Divergência de um ou dois meses não gera alerta —
norma assinada em maio e publicada em junho é rotina.

### Nunca casar o filtro contra um identificador que contém o termo

Este erro apareceu três vezes no projeto, sempre disfarçado:

- casar a regex contra a URL inteira: o domínio `cgibs.gov.br` contém "cgibs",
  então **todo link do site passava no filtro**, inclusive aviso de licitação;
- casar contra o nome do órgão: "Comitê Gestor do IBS" contém "IBS", então **todo
  extrato de contrato do próprio Comitê virava item relevante**;
- classificar pelo trecho que a busca devolve: a busca ecoa o termo pesquisado, e
  o filtro **confirmava a si mesmo**.

A regra geral: o termo tem que aparecer no *assunto*, nunca no remetente nem no
endereço.

### Orçamento de tempo, e falha parcial não derruba nada

Portais `.gov.br` respondem de forma intermitente — a mesma varredura funcionou
em 2m18s e, minutos depois, deu timeout em tudo. O script tem teto próprio de 10
minutos: ele sempre fecha e grava, marcando as fontes que falharam ou que não
foram tentadas. Uma fonte fora do ar entra na execução seguinte, e o histórico
acumulado não se perde.

As fontes estão ordenadas por importância. Se o tempo acabar, sobra Relatórios,
não Resoluções.

### Verde só quando há resultado

`continue-on-error` evita que uma fonte fora do ar derrube o job, mas tem um
efeito colateral perigoso: o job reporta **sucesso** sem ter feito nada. Aconteceu
três vezes aqui — check verde, nenhum dado. Os workflows agora falham
explicitamente quando não produzem relatório.

### O agendamento se aposenta sozinho

O workflow de medição verifica se o relatório já existe e, se existir, encerra
sem rodar. Ninguém precisa lembrar de desligar.

Detalhe do GitHub: workflows agendados em repositório público são **desativados
após 60 dias sem atividade no repositório**. O passo *Sinal de vida* faz um commit
por execução para evitar isso.

### Duas coletas por dia, arquivos separados — nunca mesclar na escrita

O DOU e os 12 portais web rodam em horários e workflows diferentes, mas podem
gravar no mesmo dia. A tentação óbvia seria fazer o segundo a rodar mesclar seu
resultado no arquivo do primeiro. Não fazemos isso: cada coleta grava só o seu
próprio arquivo (`AAAA-MM-DD.json` vs `AAAA-MM-DD-dou.json`, `novidades.json`
vs `novidades_dou.json`). Mesclagem por leitura-modificação-escrita entre dois
workflows independentes é exatamente o tipo de corrida que já nos custou um bug
(ver item abaixo, "`git pull --rebase` nunca fixo numa branch"). Arquivo
separado elimina a classe inteira de problema — não existe "quem escreve por
cima de quem" quando ninguém compartilha o arquivo.

O que *é* compartilhado entre as duas coletas é `dados/historico.json`, e isso
é seguro por construção: a chave de dedup (`chave()`, em `scripts/varredura.py`)
é um hash do conteúdo do item (URL + título), não depende de qual coleta
encontrou primeiro. Cada execução só adiciona o que é novo pra ela.

### `git pull --rebase` nunca fixo numa branch

Os passos de commit automático faziam `git pull --rebase --autostash -q origin
main`, fixo. Funcionava sempre — até um push para uma branch de PR (não a
`main`) disparar o mesmo workflow: rebasear 8 commits que a `main` não tinha
contra a própria `main` gerou conflitos `add/add` artificiais (efeito do clone
raso do `actions/checkout`) e o job caiu com exit 128. Correção: `git pull
--rebase --autostash -q` sem especificar branch — usa o que o checkout já
configurou, e funciona igual rodando na `main` ou em qualquer outra branch.

### "200 sem cookie" não é sempre credencial inválida

O login do INLABS (`scripts/dou.py`) tratava qualquer resposta 200 sem cookie
de sessão como credencial recusada, e desistia na hora — sem usar as
tentativas restantes. Na prática, isso também acontece em manutenção
programada do INLABS (mesma credencial, minutos depois, funcionando). Agora
esse caso também entra no loop de retentativa (30 tentativas, até 120s entre
uma e outra); só um HTTP 4xx explícito (401/403) desiste na hora, por ser
rejeição de verdade, não instabilidade.

---

## DOU: coleta separada, com mais retentativa

O Diário Oficial da União é uma rede de segurança para normas que não passam
pelos sites acima — nem tudo que sai no DOU vira notícia no CGIBS ou na Receita.

**Duas tentativas até chegar no formato atual, e a regra sempre foi não colocar
em produção antes de medir:**

**Tentativa 1 — API de busca do in.gov.br. Reprovada.** Recall de 2 em 4: perdeu
o Ato Técnico Conjunto nº 1 e o Ato Conjunto nº 5, ambos publicados dentro da
janela. Duas causas: a coleta lia só a primeira página de resultados e truncava o
resto **em silêncio**; e a classificação usava o trecho devolvido pela própria
busca, que ecoa o termo pesquisado. Precisão medida em torno de 25% — o balde
"relevante" vinha com extrato de doação e portaria de autarquia ambiental.

**Tentativa 2 — INLABS. Aprovada, em produção.** O [INLABS](https://inlabs.in.gov.br/)
é o portal de dados abertos da Imprensa Nacional: edição completa do DOU em XML,
gratuito mediante cadastro. Sem busca, sem paginação, sem truncagem — se um ato
foi publicado, ele está no arquivo. A medição (`scripts/medir_inlabs.py`) pegou
os quatro atos do gabarito antes de ir para produção — critério de entrada era
esse, perder um reprovava.

**Login instável, resolvido com retentativa agressiva.** O `logar.php` do
INLABS responde 5xx ou "200 sem cookie" de forma intermitente — já vimos 502
seis vezes seguidas (17/08/2026) e "200 sem cookie" que se revelou manutenção,
não credencial (25/08/2026), com a mesma credencial funcionando pouco depois.
`scripts/dou.py` agora tenta até **30 vezes**, com espera crescente até um teto
de **120s** entre tentativas — e repete nos dois casos, não só em 5xx (ver
"Decisões de projeto" acima). Coleta separada dos 12 portais web, workflow
próprio às 02:00 Brasília (`.github/workflows/dou.yml`), com orçamento de tempo
de 60 minutos — dá margem para o login se recuperar sem atrapalhar a varredura
principal das 06:40 nem concentrar tudo no mesmo horário de pico de acesso aos
portais `.gov.br`.

**E uma coisa que o DOU não resolve:** o esclarecimento do CGIBS de 06/08/2026
sobre o adiamento das regras de validação dos documentos fiscais — que mudou
materialmente o conselho a dar a um cliente — é *notícia no site do órgão*, não
ato normativo. Nunca passou pelo DOU. As duas frentes são complementares.

---

## Análise diária automatizada

A camada de fatos (acima) não interpreta nada de propósito. A análise — o que
mudou, qual o impacto, o que fazer — é escrita por um agente Claude agendado,
seguindo o mesmo critério e formato que as primeiras análises manuais do
projeto (`analises/2026-08-17.md`, `analises/2026-08-20.md` são a régua de
qualidade).

**Como funciona, a cada dia útil:**

1. `scripts/lacuna_analise.py` compara `analises/*.md` já publicadas com
   `dados/historico.json` e devolve o que ainda falta analisar — sem depender
   de julgamento do agente para essa parte, é código determinístico.
2. O agente lê `scripts/analise_brief.md` (critério de relevância, estrutura
   de seções, armadilhas conhecidas do projeto — nunca classificar pelo
   remetente ou pela URL, conferir data declarada contra a pasta de upload,
   etc.) e aplica esse critério aos itens novos.
3. Sem novidade relevante: só grava `dados/analise_status.json`
   (`situacao: "sem_novidade"`), não cria arquivo em `analises/`.
4. Com novidade: escreve `analises/AAAA-MM-DD.md`, grava
   `dados/analise_status.json` com um resumo curto, comita e empurra.
5. Sempre termina com uma notificação — sucesso, sem novidade, ou erro. Nunca
   em silêncio.

**Por que não é um `workflow` do GitHub Actions:** rodar em GitHub Actions
chamando a API da Anthropic custaria por token. A rotina roda como agente
agendado na nuvem do Claude Code (skill `/schedule`), vinculado à assinatura
de quem opera — sem custo extra por execução. Isso também significa que essa
peça é externa ao repositório: quem faz fork do projeto tem a camada de fatos
completa, mas precisa configurar sua própria rotina (ou continuar escrevendo
`analises/AAAA-MM-DD.md` à mão, que o painel sempre aceitou).

**Status sempre visível, mesmo sem novidade.** O painel mostra uma faixa fixa
no topo (`dados/analise_status.json` → `scripts/painel_template.html`) com a
última checagem, para quem só olha o painel — não recebe a notificação — saber
que a rotina rodou. Fica vermelha sozinha se passar mais de um dia sem
atualização, sinal de que algo quebrou na automação.

Spec e plano de implementação completos, se quiser o histórico de decisões:
`docs/superpowers/specs/2026-08-25-analise-diaria-automatizada-design.md` e
`docs/superpowers/plans/2026-08-25-analise-diaria-automatizada.md`.

---

## Limites conhecidos

- **A Resenha Diária do Planalto não está na lista.** O `robots.txt` do site
  desautoriza leitura automatizada. Contornar seria decisão de quem opera; a
  alternativa correta é a fonte primária (DOU).
- **Os títulos das páginas de documentos do CGIBS vêm como nome de arquivo**, não
  como ementa da norma, porque é o que está no texto do link. A detecção funciona;
  a leitura fica feia. Correção pendente: extrair o texto do bloco em volta do
  link.
- **O cron do GitHub é "melhor esforço"** e atrasa em horário de pico. Para um
  resumo diário, sem problema.
- **Repositório público significa dados públicos.** Conteúdo oficial, tudo bem.
  Anotação sobre cliente, não.

---

## Manutenção

**Adicionar uma fonte:** em `scripts/varredura.py`, acrescente uma linha em
`FONTES` no formato `("Nome", "https://...", precisa_de_javascript)`.

**Ajustar a relevância:** a regex `RELEVANTE` no mesmo arquivo. Termo demais gera
ruído; de menos, perde publicação. Lembre da regra acima: ela é casada contra o
título e contra o *caminho* da URL, nunca contra o domínio.

**Uma fonte começou a falhar:** o painel mostra o status de cada uma com o número
de itens, e destaca em vermelho as que não puderam ser lidas. O resumo da execução
na aba *Actions* traz a mensagem de erro.

**Ajustar o critério da análise diária:** `scripts/analise_brief.md` — seções,
critério de relevância, armadilhas conhecidas. É o único lugar que a rotina
agendada lê para decidir o que entra na análise; mudou o critério ali, muda o
resultado no dia seguinte, sem precisar tocar em código.
