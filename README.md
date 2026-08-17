# Monitor da Reforma Tributária

Varredura diária das fontes oficiais da reforma tributária do consumo
(EC 132/2023, LC 214/2025, LC 227/2026), com painel público.

**Divisão de trabalho:** este repositório só coleta e publica fatos — não faz
análise e não usa IA. A leitura de impacto é escrita separadamente e entra aqui
como um arquivo em `analises/`.

---

## Instalação (uma vez, ~10 minutos)

**1. Crie o repositório.** No GitHub: *New repository* → nome `reforma-tributaria-monitor`
→ **Public** → *Create*. Público é o que dá Actions ilimitado e GitHub Pages de graça.

**2. Suba estes arquivos.** Pelo site: *Add file* → *Upload files* → arraste tudo
→ *Commit changes*. Ou pelo terminal:

```bash
git init && git add . && git commit -m "primeira versão"
git branch -M main
git remote add origin https://github.com/SEU-USUARIO/reforma-tributaria-monitor.git
git push -u origin main
```

**3. Libere a escrita do workflow.** *Settings* → *Actions* → *General* →
*Workflow permissions* → marque **Read and write permissions** → *Save*.
Sem isso o commit diário falha.

**4. Ligue o Pages.** *Settings* → *Pages* → *Source*: **Deploy from a branch** →
branch `main`, pasta `/docs` → *Save*. O painel fica em
`https://SEU-USUARIO.github.io/reforma-tributaria-monitor/`.

**5. Teste.** Aba *Actions* → *Varredura Reforma Tributária* → *Run workflow*.
Leve uns 3 minutos. Ao final, o resumo da execução mostra o que foi encontrado.

---

## Como funciona

| Quando | O que acontece |
|---|---|
| Seg–sex, 06:40 (Brasília) | `varredura.py` abre as 12 fontes num Chromium real |
| | Compara com `dados/historico.json` e separa o que nunca foi visto |
| | `gerar_painel.py` remonta `docs/index.html` |
| | Commit automático; o Pages republica sozinho |

O horário é 20 minutos antes do e-mail das 07h, para o dado já estar no ar quando
a análise for escrita. **O cron do GitHub é "melhor esforço"** — atrasa em horário
de pico. Para um resumo diário, tudo bem.

### Novidade é "nunca vi este link", não "a data é recente"

Páginas oficiais publicam com data errada. O CGIBS listou o Ato Conjunto nº 5/**2026**
como sendo de 2025 — ordenando por data, ele some no fim da lista. Por isso a
detecção é por link inédito, e o scraper ainda compara a data declarada com a pasta
de upload do arquivo (`/202608/`) e **marca o item com um alerta** quando as duas
discordam.

---

## Estrutura

```
scripts/varredura.py        coleta      — edite aqui para incluir ou tirar fontes
scripts/gerar_painel.py     montagem
scripts/painel_template.html  visual    — CSS e layout do painel
estado.json                 camada curada: prazos, pendências, linha do tempo
analises/AAAA-MM-DD.md      análise do dia (opcional)
dados/                      gerado pelo robô — não edite à mão
docs/index.html             o painel publicado — gerado, não edite à mão
```

### O que você edita à mão

**`estado.json`** — quando um prazo mudar, uma pendência for resolvida ou um marco
novo entrar. É a única parte curada do painel. Salvou e deu push? O painel se
regenera sozinho.

**`analises/`** — a análise do dia. É o único passo manual do fluxo, e é assim de
propósito: publicar automaticamente exigiria dar a este repositório uma credencial
de escrita, e essa credencial ficaria guardada onde não deveria. Um arquivo por dia,
nomeado `AAAA-MM-DD.md`. Se não houver arquivo do dia, o painel mostra a análise mais
recente e segue funcionando com os fatos.

---

## Manutenção

**Adicionar uma fonte:** entre em `scripts/varredura.py`, acrescente uma linha em
`FONTES` no formato `("Nome", "https://...", precisa_de_javascript)`. Se a página
monta o conteúdo por script, use `True`.

**Ajustar o filtro de relevância:** a regex `RELEVANTE` no mesmo arquivo. Ela é o
que separa "resolução sobre IBS" de "aviso de licitação de material de escritório".
Termo demais gera ruído; de menos, perde publicação.

**Uma fonte começou a falhar:** o painel mostra o status de cada uma com o número de
itens; erro aparece em vermelho e com aviso no bloco *Fontes varridas*. O resumo da
execução na aba *Actions* traz a mensagem de erro.

**O agendamento parou sozinho.** O GitHub desativa workflows agendados em repositório
público após 60 dias sem atividade. O passo *Sinal de vida* faz um commit por execução
para evitar isso, mas há relatos de a desativação ocorrer mesmo assim. Se o painel
congelar, confira a aba *Actions* — normalmente basta reabilitar o workflow.

---

## Limites conhecidos

- **A Resenha Diária do Planalto não está na lista.** O site bloqueia leitura
  automatizada por `robots.txt`. Isso é sinalização de política do site, não barreira
  técnica — contornar seria uma decisão sua, e antes disso vale procurar um feed ou
  API oficial do DOU.
- **O portal da NF-e (`informe.aspx`) entra em loop de redirecionamento.** Está na
  lista mesmo assim; a cobertura efetiva hoje vem do espelho da SVRS, que publica as
  mesmas Notas Técnicas.
- **Repositório público significa dados públicos.** Conteúdo oficial, tudo bem.
  Nada de anotação de cliente aqui.
