# Monitor da Reforma Tributária

Varredura diária das fontes oficiais da reforma tributária brasileira do consumo
(EC 132/2023, LC 214/2025, LC 227/2026), com painel público e resumo por e-mail.

**Painel:** https://rodrigokratzer.github.io/reforma-tributaria-monitor/

O projeto separa deliberadamente duas camadas:

| Camada | O que é | Quem faz |
|---|---|---|
| **Fatos** | o que foi publicado, quando, em qual fonte | este repositório, sozinho |
| **Análise** | o que mudou, qual o impacto, o que fazer | escrita à parte, entra em `analises/` |

A camada de fatos não usa IA e não interpreta nada. Ela abre as páginas, compara
com o que já viu e registra o que é novo. O painel fica de pé mesmo em dia sem
análise nenhuma — mostra as publicações, os prazos e o status das fontes.

---

## O que ele varre

Doze fontes oficiais, todo dia útil às 06:40 (Brasília):

- **CGIBS** — notícias, leis, resoluções, regulamentos, portarias, atos conjuntos,
  atos técnicos conjuntos e relatórios
- **Receita Federal** — notícias gerais e a área da Reforma Tributária do Consumo
- **Portal NF-e** — informes e Notas Técnicas
- **Portal DF-e da SVRS** — espelho que publica as mesmas Notas Técnicas

Um navegador real (Playwright/Chromium) abre cada página, porque várias delas
montam o conteúdo por JavaScript e voltam vazias para um cliente HTTP comum.

---

## Como rodar uma cópia sua

1. **Fork ou novo repositório público.** Público dá GitHub Actions ilimitado e
   GitHub Pages incluído. Em repositório privado o Pages exige plano pago.
2. **Settings → Actions → General → Workflow permissions:** marque
   *Read and write permissions*. Sem isso o commit diário falha.
3. **Settings → Pages → Source:** *Deploy from a branch*, branch `main`, pasta `/docs`.
4. **Actions → Varredura Reforma Tributária → Run workflow** para a primeira carga.

Não há segredo obrigatório. As credenciais do INLABS (`INLABS_EMAIL`,
`INLABS_SENHA`) só são necessárias para a medição do DOU, que é opcional e está
descrita mais abaixo.

---

## Estrutura

```
scripts/varredura.py          coleta as 12 fontes
scripts/gerar_painel.py       monta docs/index.html
scripts/painel_template.html  layout e CSS do painel
scripts/medir_inlabs.py       medição do filtro do DOU (opcional, ver abaixo)
estado.json                   camada curada: prazos, pendências, linha do tempo
analises/AAAA-MM-DD.md        análise do dia (opcional)
dados/                        gerado pelo robô — não editar à mão
docs/index.html               o painel publicado — gerado, não editar à mão
```

**O que se edita à mão:** só `estado.json` (quando um prazo muda ou uma pendência
é resolvida) e `analises/`. Salvou e deu push? O painel se regenera sozinho.

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

---

## O DOU: por que ainda não está na varredura

O Diário Oficial da União seria uma rede de segurança para normas que não passam
pelos sites acima. Duas tentativas, e a regra é não colocar em produção antes de
medir.

**Tentativa 1 — API de busca do in.gov.br. Reprovada.** Recall de 2 em 4: perdeu o
Ato Técnico Conjunto nº 1 e o Ato Conjunto nº 5, ambos publicados dentro da
janela. Duas causas: a coleta lia só a primeira página de resultados e truncava o
resto **em silêncio**; e a classificação usava o trecho devolvido pela própria
busca, que ecoa o termo pesquisado. Precisão medida em torno de 25% — o balde
"relevante" vinha com extrato de doação e portaria de autarquia ambiental.

**Tentativa 2 — INLABS, em espera.** O [INLABS](https://inlabs.in.gov.br/) é o
portal de dados abertos da Imprensa Nacional: edição completa do DOU em XML,
gratuito mediante cadastro. Sem busca, sem paginação, sem truncagem — se um ato
foi publicado, ele está no arquivo. A medição está pronta e agendada para 05h,
mas o `logar.php` do INLABS respondeu **502 em seis tentativas seguidas** em
17/08/2026, inclusive de navegador comum com sessão válida. Quando voltar, ela
roda sozinha.

O critério de entrada é o mesmo: o filtro só vai para produção se pegar os quatro
atos do gabarito. Perder um reprova.

**E uma coisa que o DOU não resolve:** o esclarecimento do CGIBS de 06/08/2026
sobre o adiamento das regras de validação dos documentos fiscais — que mudou
materialmente o conselho a dar a um cliente — é *notícia no site do órgão*, não
ato normativo. Nunca passou pelo DOU. As duas frentes são complementares.

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
