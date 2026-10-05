# Consulta remota ao acervo pelo app do Claude: design

**Data:** 05/10/2026
**Objetivo:** Rodrigo consulta o acervo da reforma tributária a qualquer hora pelo app do
Claude (celular ou claude.ai/code), com o poder total do Claude Code, para responder às
perguntas da Carolina (palestrante e criadora de conteúdo sobre a reforma, formada em
ciências contábeis). As respostas se apoiam nos textos integrais (leis-base, publicações
coletadas e análises), com fonte e marca de confiança. Não é preciso reativar nada pelo
terminal.

## Contexto e decisões tomadas na conversa

- **Quem usa:** só o Rodrigo, com a conta Claude dele. A Carolina não acessa o sistema; ela
  pergunta ao Rodrigo, que pesquisa e responde. Por isso estão fora de escopo: chat no painel,
  login próprio, custo de terceiros.
- **O problema atual:** uma sessão interativa do Claude Code com controle remoto morre quando
  fica ociosa ou quando o terminal fecha, e é preciso voltar ao terminal para reativá-la.
- **Prioridade escolhida:** poder total do Claude Code. Foram descartados um Projeto do claude.ai
  sincronizado com o GitHub e um conector MCP próprio.
- **Escrita:** acesso total. As sessões podem ler, rodar scripts, editar, commitar e publicar.
- **Permissões:** `bypassPermissions`, sem restrições e com `sudo` liberado. É uma decisão
  explícita do Rodrigo, e o risco está registrado em "Riscos".
- **Leis-base:** baixadas pelo sistema **do Planalto**, em texto compilado. Não vêm da
  base do Projeto do claude.ai.
- **Atualidade:** além da compilação semanal, as normas novas coletadas pela varredura diária
  (05h e 17h) também são base das respostas, e a consulta precisa responder logo depois que
  uma norma ou alteração sai.

## Arquitetura

```
 App do Claude (celular / claude.ai/code)
            │  conta claude.ai do Rodrigo; nenhuma porta aberta no notebook
            ▼
 lenovo-claude: reforma-consulta.service (systemd, sempre ligado)
   claude remote-control --spawn worktree --no-create-session-in-dir
            │  cada sessão aberta pelo app ganha uma worktree própria,
            ▼  criada a partir do main atual do checkout de produção
   <worktree da sessão>  ← lê normas/ + dados/textos/ + analises/ + estado.json,
            │              roda scripts, edita, commita
            ▼  para publicar: merge no main + scripts/publicar.sh (como hoje)
 checkout de produção (main)  ← continua sendo do ciclo 05h/17h
```

- As sessões **nunca trabalham direto no checkout de produção**. O modo `worktree` isola cada
  conversa do `git pull`/`publicar.sh` do ciclo. Uma sessão aberta logo depois de um ciclo
  já começa com o que ele publicou.
- Uma sessão que rode o ciclo à mão usa `systemctl start reforma-ciclo.service`, que já
  tem `flock` contra execuções simultâneas.
- Todo o uso consome a assinatura pessoal do Rodrigo. É uso pessoal, então não há questão de
  termos de uso.

## Componentes

### 1. Serviço `reforma-consulta.service` (`deploy/systemd/`)

- Roda como `rodrigo`, com o login do Claude já salvo, e `WorkingDirectory` no checkout de produção.
- `ExecStart`: `claude remote-control --name "Reforma – consulta" --spawn worktree
  --no-create-session-in-dir --permission-mode bypassPermissions`.
- `Restart=always`, `RestartSec=30`, com `StartLimitIntervalSec`/`StartLimitBurst` para não
  ficar reiniciando em loop. Sobe com o boot (`WantedBy=multi-user.target`).
- `OnFailure=reforma-falha@%n.service`: se o serviço não subir (por exemplo, login do Claude
  expirado), chega o push no celular pelo `notificar.py --falha` que já existe.
- Diagnóstico: `journalctl -u reforma-consulta.service`.
- **Incerteza a validar na Etapa 0 (teste de viabilidade):** se o `remote-control` roda sem TTY sob o
  systemd, se o `bypassPermissions` pede uma confirmação interativa na primeira vez,
  onde ficam as worktrees criadas e como ele se comporta depois de horas ocioso.

### 2. Leis-base: `scripts/baixar_normas.py` → `normas/`

- **Normas**, sempre o texto compilado do Planalto:
  - EC 132/2023: `planalto.gov.br/ccivil_03/constituicao/emendas/emc/emc132.htm`
  - Constituição Federal, só os trechos da reforma: arts. 145 a 162 e 195, e ADCT arts. 124 a 138
    (`.../constituicao/constituicao.htm`)
  - LC 214/2025: `.../leis/lcp/lcp214.htm`
  - LC 227/2026: `.../leis/lcp/lcp227.htm` (confirmar a URL na implementação)
- **Saída:** um arquivo de texto por norma (`normas/ec132.txt`, `normas/cf-reforma.txt`,
  `normas/lc214.txt`, `normas/lc227.txt`) e `normas/indice.json`, com `{id, titulo, url,
  baixado_em, sha256, chars}`, versionados no git. Um diff no git mostra o que mudou em cada
  atualização.
- **Revogados:** trecho riscado no Planalto (`<strike>`/`<s>`/`<del>`) sai marcado no texto,
  `[REVOGADO] …` ou `[REDAÇÃO ANTERIOR] …`. Nunca sai como texto vigente. Se a estrutura da
  página mudar e nenhum dispositivo for reconhecido, o download falha, e o arquivo
  anterior fica.
- **Quando roda:** `baixar_normas.py --se-necessario`, chamado no fim de `rodar_varredura.sh`.
  Ele baixa se a última atualização tiver 7 dias ou mais, **ou** se o ciclo coletou um item
  que parece alterar uma norma-base (veja "Atualidade", mecanismo 3). Também roda sob demanda
  (`baixar_normas.py --forcar`), inclusive por uma sessão do app. Uma falha aqui não derruba o
  ciclo: o erro vai para `dados/normas_status.json` e para o log, e os arquivos anteriores ficam.
- Usa a `leitura.baixar.Sessao`, que já existe, e o mesmo padrão stdlib do projeto.

### 3. Busca: `scripts/buscar.py`

- `buscar.py "split payment" [--fonte CGIBS] [--desde 2026-09-01] [--normas-so | --acervo-so]
  [--limite 20]`: procura em `normas/*.txt` (por dispositivo) e em `dados/textos/*.txt`
  (cruzando com `dados/historico.json` para pegar título, data, fonte e URL). Devolve, ranqueado:
  origem (norma ou publicação), identificação (por exemplo "LC 214, art. 26" ou o título com a data),
  um trecho com o termo e o caminho do arquivo, para a sessão ler o texto inteiro.
- `buscar.py --alteracoes-de lc214 [--artigo 26]`: lista as publicações do acervo **posteriores
  ao `baixado_em` da norma** que mencionam a norma (e o artigo, se informado). É o que
  alimenta o alerta de compilação desatualizada.
- Stdlib, sem índice persistente (461 textos e cerca de 10 MB cabem em busca linear por segundos).

### 4. Skill de consulta: `.claude/skills/consulta-reforma/SKILL.md`

- Versionada. O `.gitignore` passa de `.claude/` para `.claude/*` com `!.claude/skills/`.
- Entra em ação em perguntas sobre a reforma (IBS, CBS, IS, LC 214/227, EC 132, publicações,
  prazos, "o que mudou em…").
- **Ordem das fontes:** `normas/` → `dados/textos/` (pelo `buscar.py`) → `analises/` →
  `estado.json` → web, só em último caso.
- **Atualidade:** ao citar um dispositivo de `normas/`, roda `buscar.py --alteracoes-de`. Se
  houver publicação posterior que mencione a norma ou o artigo, a resposta mostra a data da compilação,
  a alteração e a redação nova lida em `dados/textos/`.
- **Marcas de confiança** (as mesmas do monitor e da skill `reforma-tributaria`):
  `[VERIFICADO LITERAL]` quando o texto integral foi lido, `[VERIFICADO LITERAL (OCR)]` quando
  `texto_origem` contém `ocr`, e `[PESQUISA]` quando vem de fonte que não é o texto oficial.
  Nada de número, prazo ou artigo de memória.
- **Tom:** o da skill `reforma-tributaria` (direto, sem bajulação, dizendo quando a lei é
  lacunosa ou mal escrita).
- **Formato:** uma resposta de trabalho para o Rodrigo e, quando ele pedir, uma versão
  "pronta para a Carolina" em linguagem técnica de contadora, com as fontes no fim.
- Não reaproveita a skill `reforma-tributaria` como está, porque ela depende de ferramentas do Projeto do
  claude.ai (`project_search`) que não existem no Claude Code.

### 5. Limpeza: `scripts/limpar_worktrees.py` + `reforma-limpeza.timer` (semanal)

- Remove as worktrees das sessões de consulta com mais de 7 dias **sem mudança pendente e sem
  commit fora do `main`** (`git worktree remove` + `git branch -d`). Nunca usa `--force`.
- Worktrees com trabalho pendente ficam, e o Rodrigo recebe um aviso pelo `notificar.py` com a lista.
- Só mexe nas worktrees criadas pelo `remote-control` (o caminho e o padrão de nome saem da Etapa 0).
  Outras worktrees, como `migracao-notebook-local`, ficam fora.

## Atualidade: como a consulta acompanha uma norma recém-publicada

1. **O acervo diário é base.** O que o ciclo das 05h ou das 17h coletou, com texto integral, está
   em `dados/textos/` e entra em toda sessão aberta depois.
2. **Alerta de compilação desatualizada.** Veja o componente 4. Ele cobre os dias entre a publicação no DOU e
   a atualização da compilação no Planalto.
3. **Atualização disparada pela varredura.** `baixar_normas.py --se-necessario` antecipa o
   download quando as novidades do ciclo trazem lei complementar, emenda constitucional ou texto que
   "altera a Lei Complementar nº 214/227" ou a EC 132 (regex sobre título e texto das novidades).
4. **Sob demanda.** A sessão do app pode rodar a coleta ou `baixar_normas.py --forcar` na hora.

## Falhas

| Falha | Comportamento |
|---|---|
| Serviço não sobe (login expirado, binário mudou) | `OnFailure` manda push no celular. O ciclo de coleta e análise não é afetado |
| `remote-control` cai | `Restart=always` em 30 s. As sessões abertas caem, e a próxima abre normalmente |
| Planalto fora do ar ou estrutura mudou | Ficam as normas anteriores. O erro vai para `dados/normas_status.json`, e a skill mostra a data da compilação em uso |
| Uso intenso pelo app esgota o limite da assinatura | A análise do ciclo pode bater no limite. Ela já não marca nada como analisado nesse caso (`rodar_analise.sh`), e os itens voltam no ciclo seguinte |
| Worktree com trabalho esquecido | Não é apagada. Fica a lista no aviso semanal |

## Riscos aceitos

- **Prompt injection com `bypassPermissions` e `sudo` sem senha.** As sessões leem conteúdo
  de terceiros (páginas, PDFs, web). Um texto malicioso pode induzir a execução de comandos sem
  pedir aprovação, e com `sudo` o efeito vai além do projeto. O Rodrigo escolheu esse modo sabendo
  disso. O isolamento por worktree só protege o projeto: o que passa pelo git dá para desfazer, o que passa por `sudo` não.
- **Remote Control é recurso de produto, não API estável.** Mudança de comportamento numa
  atualização do Claude Code pode exigir ajustar a unit. A Etapa 0 e o `OnFailure` existem por isso.

## Testes e aceitação

- **Etapa 0 (teste de viabilidade, antes de construir):** subir o serviço e conferir quatro pontos. Ele aparece no app.
  Uma sessão aberta pelo celular nasce numa worktree a partir do `main` atual. Ele sobrevive a algumas
  horas ocioso e a um `systemctl restart`. O `bypassPermissions` funciona sem diálogo interativo.
  Se algum ponto falhar, o trabalho para e o desenho é revisto.
- **Automatizados** (stdlib `unittest`, no padrão do projeto):
  - `baixar_normas.py`: fixture com HTML real do Planalto, com um dispositivo revogado (sai marcado e
    nunca como vigente), extração dos trechos da CF, falha quando a estrutura não é reconhecida
    (mantém o arquivo anterior) e decisão do `--se-necessario` (idade e gatilho).
  - `buscar.py`: ranking, filtros, trecho, `--alteracoes-de` respeitando `baixado_em`.
  - `limpar_worktrees.py`: nunca remove worktree com mudança pendente ou commit fora do `main`,
    e não toca em worktrees fora do padrão.
- **Aceitação pelo celular, com o Rodrigo:**
  1. "O que diz o art. 26 da LC 214?" → citação de `normas/lc214.txt`, `[VERIFICADO LITERAL]`,
     com a data da compilação.
  2. "O que diz o Ato Conjunto RFB/CGIBS nº 8?" → publicação de 01/10 lida no acervo.
  3. "O que mudou da NT 2025.002 v1.51 para a v1.52?" → comparação entre dois textos do acervo.
  4. Frescor: uma sessão aberta depois do ciclo das 17h enxerga um item coletado nele.
  5. Pedido de resposta "pronta para a Carolina".

## Entrega (ordem)

1. Etapa 0 (teste de viabilidade do serviço).
2. `baixar_normas.py` + primeira carga de `normas/`.
3. `buscar.py`.
4. Skill `consulta-reforma` + exceção no `.gitignore`.
5. Ligação do `--se-necessario` em `rodar_varredura.sh`.
6. Unit `reforma-consulta.service` + `limpar_worktrees.py` + timer, com documentação
   (`CLAUDE.md`, `docs/operacao-local.md`).
7. Aceitação pelo celular.

Nada disso altera a coleta, a leitura nem a análise. A única mudança no ciclo é a
chamada não fatal do `baixar_normas.py --se-necessario`.

## Fora de escopo

- Chat no painel, acesso da Carolina, login próprio, cobrança.
- Projeto do claude.ai sincronizado com o GitHub e conector MCP próprio (alternativas descartadas).
- Importar a base de conhecimento do Projeto do claude.ai.
- Outras normas além das listadas (decretos, outras LCs). Podem entrar depois como linhas novas
  na lista do `baixar_normas.py`. As resoluções do CGIBS já chegam pela coleta.
