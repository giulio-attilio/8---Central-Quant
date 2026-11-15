# Revalidação de prontidão pessoal — Central Quant/Falcon (2026-11-15)

## Resultado

**Ainda não pronto para operação PAPER contínua autônoma.** O serviço está Live,
mas o endpoint de saúde do executor PAPER integrado reporta
`PAPER_STATE_FILES_MISSING`, sem contagens de posições/idempotência. Não criar
arquivos vazios nem importar registros do Registry para esse ledger: são stores
com autoridades e formatos distintos, e não há reconciliação de identidade que
autorize essa migração.

## Evidência de produção somente de leitura

- Render `My Workspace` / serviço `central-robos-bingx`
  (`srv-d8rtuv9o3t8c73ehav5g`): deploy Live em
  `8c02d37607d1f85540a069ffff03a9d221e74504`, revisão
  `fix(paper): report missing enabled ledger unhealthy`.
- Configuração observada pelo Render MCP em 2026-11-15: uma instância Standard,
  disco persistente de 4 GB em `/data`, auto-deploy desligado, branch configurado
  `codex/personal-readiness-20261103`, `healthCheckPath` vazio.
- Health JSON fornecido pelo operador, gerado em 2026-11-15 11:27 BRT: executor
  PAPER habilitado, real desabilitado, `ok=false`, estado
  `PAPER_STATE_FILES_MISSING`, arquivos `paper_integrated_positions.json` e
  `paper_integrated_seen.json` ausentes; posições/contagens `null`.
- Logs de aplicação Render consultados para 2026-11-14 00:00 UTC a
  2026-11-15 14:29 UTC: 57 ocorrências de
  `STATIC_OPERATIONAL_RUNTIME_BLOCKED` — 39 auditorias pesadas do Predator e 18
  snapshots grandes do Smart Predator. Isso confirma que essas tarefas não
  executaram nesse intervalo; não identifica a causa-raiz de eventuais scanners
  parados nem prova falha de entrada/gestão PAPER.
- Os logs continham 22 marcadores `SIGNAL_PAPER` no intervalo consultado, último
  em 2026-11-15 02:16:46 UTC. Marcadores de sinal não comprovam trades, fill,
  ledger íntegro, posições abertas ou gestão completa.
- Foram observados 40 `TELEGRAM_NOTIFICATION_BLOCKED` do Falcon por
  `LIVE_ONLY_POLICY`: 5 sinais PAPER, 3 TP50, 6 break-even, 20 trailing e 6
  fechamentos PAPER. São bloqueios de notificação, não rejeições de ordens; os
  eventos também não substituem a confirmação do estado no ledger.
- Métricas Render em 2026-11-15 13:28–14:29 UTC: uma instância, limite de 1 CPU
  e 2 GiB; CPU variou de 0,07 a 0,92 vCPU e memória de cerca de 0,81 a 0,96 GiB.
  O pico de CPU ficou próximo do limite. Isso não prova que seja a causa dos
  bloqueios do runtime, mas reforça não liberar as tarefas pesadas sem análise.
- Recheck Render MCP em 2026-11-15: workspace confirmado como `My Workspace`;
  serviço ainda Live em `8c02d37`, uma instância Standard, disco `/data` de 4 GB,
  auto-deploy desligado e `healthCheckPath` vazio. Na janela de métricas
  13:51–14:51 UTC, CPU ficou entre 0,29 e 0,65 vCPU e memória entre cerca de
  0,87 e 1,04 GB; contagem de instâncias permaneceu 1. Houve requisições HTTP
  200, mas isso não identifica quais rotas responderam nem valida o executor
  PAPER. A primeira consulta de logs retornou 503, mas consultas filtradas
  posteriores foram concluídas: na janela 14:00–15:00 UTC não houve logs de
  aplicação em nível `error` nem requisições registradas para
  `/paper_integrated/health`; a métrica HTTP filtrada para esse path também não
  teve pontos. Esses vazios não provam funcionamento ou ausência absoluta de
  chamadas fora da janela. Os logs de aplicação registraram às 14:22 UTC os
  bloqueios de `smartpredator_large_redis_snapshot` e
  `predator_heavy_watchdog_audit` por `STATIC_OPERATIONAL_RUNTIME`.
- As flags `ENABLE_REAL_TRADING=false`, `BROKER_DRY_RUN=true`,
  `FALCON_MODE=paper` e os gates `CENTRAL_REAL_EXECUTION_ENABLED=false` /
  `CENTRAL_REAL_PILOT_ENABLED=false` foram informados pelo operador em leitura
  anterior do Shell; não foram relidos neste recheck. Nenhuma variável foi
  alterada.

## Evidência local atual

Worktree: branch `codex/falcon-paper-persist-guard-20261115`, consolidado
localmente no commit `f5df2eaa49729d6b438b072bfee77242fec75e45`. O arquivo
`tests/test_paper_executor_integrated_idempotency_v1.py` ainda contém uma
alteração preexistente do operador, preservada fora do commit. Nada foi enviado
ao remoto nem implantado.

O ajuste local em `bots/falcon.py` acrescenta um latch persistente para falhas de
persistência de sinal PAPER: gravação atômica no diretório `CENTRAL_DATA_DIR` ou
`DATA_DIR`; quando a gravação é durável, o bloqueio de novas entradas sobrevive
a reinícios; leitura de latch corrompido fail-closed; e campos de diagnóstico
no health payload. Se o diretório não estiver configurado ou a gravação falhar,
o processo atual bloqueia novas entradas, mas a persistência após reinício não
fica garantida. Isso não inicializa o ledger integrado ausente nem reconcilia
entradas do Registry.

Validações locais com harness offline, rede/subprocessos bloqueados e dados
temporários:

- Após o último ajuste: `python -m pytest tests/test_falcon_lifecycle_observation_projection.py -q --tb=short` — **16 passaram em 18,24 s**, incluindo exceção/retorno inválido do gravador e preservação do bloqueio.
- Após o último ajuste: `python tests/run_falcon_pilot_minimal_offline.py --personal-lifecycle-completeness` — **892 passaram, 1 ignorado em 694,12 s**. Essa seleção não inclui o arquivo de projeção acima; por isso ele também foi executado separadamente.
- Antes do último ajuste, sem mudanças nos módulos C3/Registry: `--c3-dormant-startup` — 24 passaram e 3 subtestes passaram; `--registry-writers` — 60 passaram.
- `tests/test_falcon_single_live_execution_path_v1.py` — 59 passaram antes do último ajuste, restrito à ramificação de falha PAPER.
- `git diff --check` — sem erros de whitespace.

O pacote `ccxt==4.5.88` foi reutilizado de um diretório temporário já existente;
nenhuma dependência foi instalada e nenhuma rede foi habilitada.

## Decisão C3

Manter C3 preservado e dormente no caminho crítico. O Render ainda reporta uma
instância com disco persistente; o código usa locks locais para os writers do
Registry e os testes atuais cobrem inventário, serialização e falhas sintéticas.
Não há evidência atual de um segundo processo/serviço/operador escrevendo o mesmo
Registry que exija signer/lease distribuído. Reavaliar se a topologia mudar ou
se aparecer evidência concreta de writers concorrentes fora dos locks locais.
Isso não é aprovação de prontidão de trading.

## Gate de runtime estático

Inspeção local de `static_operational_runtime.py`, `main.py` e
`bots/predator.py` confirmou que a flag bloqueia tarefas históricas pesadas e
snapshots grandes de Redis. O loop básico do watchdog continua executando a
checagem de saúde; a auditoria automática de fechamentos do Predator é pulada
com log explícito. A gestão de posições do Predator não consulta esse gate. As
rotas de auditoria manual continuam identificadas como `MANUAL_HEAVY_AUDIT`,
separadas dos loops automáticos. Assim, os bloqueios vistos nos logs não provam
que a gestão de posições foi suspensa, mas deixam a reconciliação histórica
automática indisponível no perfil estático.

Validação focada em 2026-11-15:
`python -m pytest tests/test_static_operational_runtime_v1.py -q --tb=short` —
**35 passaram em 414,50 s**. Esses testes validam o contrato local e fixtures,
não a configuração efetiva atual do Render. Os logs recentes confirmam tarefas
barradas, mas não expõem diretamente a flag nem o estado individual dos
scanners.

## Health check HTTP do Render

O serviço ainda usa o probe TCP padrão (`healthCheckPath` vazio). O código local
define `/healthz` como probe público mínimo: passa pela barreira de startup do
runtime, retorna `503` durante startup/drenagem e `200` após o runtime ficar
pronto; a exceção de Basic Auth limita-se a esse GET sem query. Ele não verifica
prontidão de trading nem o ledger PAPER integrado, o que evita reinícios
repetidos por `PAPER_STATE_FILES_MISSING` enquanto o modo fail-closed é mantido.
`/paper_integrated/health` é o diagnóstico de negócio autenticado, não o probe
do Render. `/healthz` é candidato coerente caso se opte por probe HTTP em vez de
TCP, mas nenhuma configuração foi alterada: probes passam a ser periódicos e o
custo zero de eventual tráfego não foi confirmado.

Testes locais focados em 2026-11-15: `-k healthz` — **2 passaram**; o teste
`runtime_routes_fail_closed_until_boot_completes` — **1 passou**. Cobrem a
exceção estreita de auth, rejeição de query/método/cross-site, modo draining e
transição runtime-not-ready (503) para ready (200). São fixtures locais, não
uma medição do estado atual do serviço.

## Risk Manager do Meme

Consulta Render MCP de logs de aplicação de nível `error` retornou cinco erros
entre 2026-11-10 e 2026-11-12. Todos eram timeouts de 10 s na consulta HTTP do
Meme a `/can_open_trade` em `central-robos-bingx.onrender.com`; o último foi em
2026-11-12 19:04 UTC. Não houve erro mais recente na página retornada, mas isso
não substitui um teste de integração atual. O código local faz a chamada
HTTP antes de registrar a entrada e bloqueia quando recebe timeout/erro, sem
abrir posição. A indisponibilidade reduz operação PAPER, embora seja fail-closed
para segurança. Não alterei o transporte nem aumentei timeout/retries, pois isso
exige avaliar o fluxo síncrono, startup e custo de chamadas repetidas.

Validação local em 2026-11-15:
`python -m pytest tests/test_live_central_risk_gate_fail_closed_v1.py -q --tb=short`
— **11 passaram em 2,02 s**, incluindo timeout sintético bloqueando a entrada.

## Pendências e limites

1. Não há evidência integrada de posição PAPER zero ou de ledger PAPER
   reconciliado. Resolver proveniência/identidade do estado antes de qualquer
   bootstrap; não copiar automaticamente as linhas do Registry.
2. A atualização local do latch Falcon ainda não foi publicada nem validada no
   Render. O release Live continua em `8c02d37` e não contém essas alterações.
3. Logs do Render às 14:22 UTC de 2026-11-15 ainda mostram bloqueios sob
   `STATIC_OPERATIONAL_RUNTIME`. O código e testes indicam que são tarefas
   históricas pesadas, não o loop básico de gestão; a leitura atual da flag e o
   estado individual dos scanners não foram obtidos.
4. A última conferência agregada BingX e as flags completas de produção não são
   evidência atual neste relatório; sinais HTTP e declarações anteriores não
   substituem reconciliação da conta.
5. Custo zero para publicação não foi confirmado. Nenhum push ou deploy foi
   executado; qualquer decisão financeira futura precisa nomear o SHA exato.
6. A configuração HTTP de health check permanece opcional/manual: o endpoint
   candidato é `/healthz`, não `/paper_integrated/health`. Nenhuma alteração foi
   aplicada por falta de confirmação de custo zero para respostas periódicas.

Nenhum secret foi consultado, nenhum controle LIVE foi alterado, nenhuma ordem
foi enviada e nenhum dado ou arquivo de produção foi modificado.

## Decisão do operador e revisão adicional — 2026-11-15

- O operador concordou com a opção de manter o executor PAPER integrado
  fail-closed enquanto `paper_integrated_positions.json` e
  `paper_integrated_seen.json` estiverem ausentes. Não criar arquivos vazios,
  não migrar/importar os registros antigos do Registry e não liberar a execução
  até haver reconciliação de identidade/proveniência. A escolha não confirma que
  a conta BingX esteja sem posições ou ordens.
- Revisão do diff local do latch Falcon confirmou: (a) a memória do processo é
  marcada antes da tentativa de gravação; (b) exceção/resultado inválido do
  gravador continuam bloqueando a entrada naquele processo; (c) um latch
  persistido é relido após restart e conteúdo inválido falha fechado. Limite
  residual: sem `CENTRAL_DATA_DIR` ou `DATA_DIR`, a gravação durável não é
  possível; o processo bloqueia, mas a proteção não sobrevive ao restart. O
  Render observado tem `DATA_DIR=/data` em evidência anterior, porém essa
  configuração não foi revalidada nesta revisão.
- No fim da revisão foram observados dois processos locais ainda ativos para
  `tests/run_mini_offline.py` (PIDs 15664 e 25148, iniciados às 11:49 e 12:13 em
  15/11). Na reconsulta, PID 15664 já havia terminado e PID 25148 seguia ativo,
  com CPU acumulada aumentando de 38,91 s para 351,73 s entre consultas. Foi
  deixado intacto; não iniciar outra cópia até terminar.
- A tentativa de atualizar a reconciliação da BingX pela sessão já aberta não
  chegou a exibir uma janela: o runtime de automação falhou ao inicializar. Não
  houve login, leitura de dados da conta ou ação na corretora; portanto não há
  evidência atual de posições/ordens na BingX.
- Releitura do código C3 atual confirmou montagem do writer coordinator com
  `enabled=False` e startup recovery `C3_DORMANT_STARTUP_RECOVERY_DEFERRED_DEFAULT_OFF`,
  com `startup_recovery_verified=False` e `readiness_allowed=False`. O checklist
  de prontidão trata essa condição como informativa para a topologia pessoal,
  mas ela não prova reconciliação do PAPER integrado nem prontidão para trading.
- `git diff --check` continuou sem erros. O trabalho local permanece sem commit
  e sem publicação; as alterações de `tests/test_paper_executor_integrated_idempotency_v1.py`
  já existiam no worktree e foram preservadas.

## Recheck Render — 2026-11-15 15:21 UTC

- Workspace `My Workspace` foi confirmado pela listagem do Render; o serviço
  `central-robos-bingx` continuava Live no deploy `8c02d376`, com uma instância,
  disco de 4 GB em `/data`, auto-deploy desligado e `healthCheckPath` vazio.
- Na janela 14:21–15:21 UTC, a contagem de instâncias permaneceu 1; CPU variou
  aproximadamente de 0,33 a 0,66 vCPU e memória de 0,82 a 0,97 GiB. A consulta
  de logs de nível error não retornou eventos nessa hora. Isso é telemetria de
  disponibilidade/capacidade, não prova de prontidão funcional de trading.
- Métricas de HTTP mostraram uma solicitação por intervalo de cinco minutos a
  `/healthz` e nenhum ponto para `/paper_integrated/health`. `/healthz` não
  substitui o health autenticado do executor; portanto o JSON manual recebido
  às 11:27 BRT, `PAPER_STATE_FILES_MISSING`, continua sendo a última evidência de
  negócio disponível nesta sessão.
- Os request logs detalhados identificaram 13 GETs do monitor cron-job.org a
  `/healthz`, todos HTTP 200, com latências entre 4 ms e 858 ms na janela
  consultada. Isso comprova resposta da rota pública de liveness nessa janela,
  não execução PAPER ou saúde da conta/ledger.
- Logs filtrados entre 12:00 e 15:21 UTC ainda mostraram bloqueios de
  `smartpredator_large_redis_snapshot` e `predator_heavy_watchdog_audit`, mais
  recentes às 14:22 UTC. O intervalo posterior sem novos eventos filtrados não
  prova que essas tarefas estejam habilitadas ou concluídas.
- Os documentos oficiais atuais do Render confirmam que TCP é o health check
  padrão e que um HTTP probe requer `2xx/3xx` em até cinco segundos. Nenhum
  caminho de health foi configurado nesta rechecagem; nenhuma alteração ou
  chamada ao endpoint de negócio foi feita.
- Execução local da seleção `--paper-integrated-disk-guard` após a decisão de
  manter fail-closed: **45 testes e 12 subtestes passaram em 2,85 s**. Ela inclui
  `test_paper_executor_integrated_idempotency_v1.py`, que cobre inicialização de
  ledger apenas em fixture temporária, bloqueio quando um dos arquivos está
  ausente e execução PAPER sem chamar executor de corretora. O harness bloqueia
  rede, subprocessos e acesso a `.env`; não acessa Render ou BingX.
- Revalidação complementar de `--falcon-lifecycle-projection` no mesmo harness
  offline: **16 passaram em 17,47 s**, incluindo persistência temporária do
  latch, relê-lo após restart e bloqueio com arquivo inválido. O harness mantém
  sockets/subprocessos/rede bloqueados; nenhum dado de produção foi acessado.
- Regressão `--trading-mode-defaults`: **9 passaram em 36,34 s**. Os contratos
  locais cobrem `ENABLE_REAL_TRADING`, `BROKER_DRY_RUN`, modo PAPER dos bots e
  defaults do Execution Engine, incluindo falha fechada para valores ausentes
  ou malformados. Isso não revalida as variáveis atuais do Render e não altera
  a configuração de produção.

## Correção local incremental — resolução de armazenamento — 2026-11-15

- Uma verificação do caminho de armazenamento encontrou que
  `paper_executor_integrated.py`, quando importado sem passar pelo bootstrap de
  `main.py`, usava `CENTRAL_DATA_DIR` ou a pasta local padrão e ignorava
  `DATA_DIR`. O runtime principal exporta `CENTRAL_DATA_DIR` antes dos imports,
  mas consultas isoladas no Render podem ter apenas `DATA_DIR=/data`; nesse
  caso, o diagnóstico manual poderia examinar um caminho diferente do disco
  persistente.
- Alteração local: o resolvedor compartilhado PAPER agora usa, em ordem,
  `CENTRAL_DATA_DIR`, `DATA_DIR`, `/data` quando montado, e por fim uma pasta
  `data` relativa ao módulo. Executor, Lifecycle e Outcome usam o mesmo
  resolvedor; isso não cria os arquivos do ledger nem importa dados.
- Adicionado `tests/test_paper_executor_data_dir_resolution_v1.py` e incluído
  no runner offline focado. Execução em 2026-11-15:
  `python -B tests/run_falcon_pilot_minimal_offline.py --paper-integrated-disk-guard`
  — **52 passaram e 12 subtestes passaram em 2,53 s**. A seleção também revalida
  inicialização apenas em fixture temporária, ledger ausente bloqueando e
  ausência de chamada à corretora.
- `git diff --check` sem erros. A alteração está consolidada localmente no
  commit `f5df2eaa49729d6b438b072bfee77242fec75e45`, sem push ou deploy. O
  comportamento de produção continua sendo o do SHA Live observado
  anteriormente até que exista release validado e condições financeiras
  autorizadas.

## Recheck de produção somente leitura — 2026-11-15 15:39 UTC

- Render MCP, conta Central Quant e workspace confirmado `My Workspace`:
  serviço `central-robos-bingx` ainda Live no SHA
  `8c02d37607d1f85540a069ffff03a9d221e74504`; deploy de ID
  `dep-dbrg0mdg1s2s738cs32g`, concluído em 2026-11-13 12:20:52 UTC. Configuração
  observada: auto-deploy `no`, branch `codex/personal-readiness-20261103`, plano
  Standard, região Oregon e `healthCheckPath` vazio. Nenhum deploy foi iniciado.
- Métricas dos últimos ~60 minutos: uma instância; CPU entre 0,327 e 0,660
  vCPU; memória entre 906.911.740 e 1.025.096.000 bytes. São medidas recentes
  de processo/infraestrutura, não de prontidão funcional PAPER.
- Consulta explícita de erros entre 2026-11-14 15:30 UTC e 2026-11-15 15:40 UTC:
  zero registros de nível error. Na mesma janela, foram encontrados 37 eventos
  `STATIC_OPERATIONAL_RUNTIME_BLOCKED`: 24 de `predator_heavy_watchdog_audit`
  e 13 de `smartpredator_large_redis_snapshot`; o mais recente ocorreu às
  15:22:17 UTC. Logo, o gate de runtime continua barrando tarefas pesadas mesmo
  sem erros de aplicação nessa janela. Isso não prova que a gestão básica das
  posições esteja parada.
- Esta rechecagem não consultou variáveis secretas, Shell, endpoint autenticado
  de saúde, arquivos `/data` nem a conta BingX. O health PAPER fornecido pelo
  operador às 11:27 BRT continua sendo a única leitura atual do ledger nesta
  sessão e reporta arquivos de estado ausentes.
- Referências atuais do Render lidas diretamente: `deploys.md` e
  `health-checks.md`. Confirmam que deploy com disco persistente não tem
  zero-downtime e que o health check configurado vazio usa TCP; nenhum probe
  HTTP periódico foi configurado neste recheck.

## Hardening incremental de ausência do ledger — 2026-11-15

- Auditoria de `paper_lifecycle_health()` e `outcome_evaluator_health()` achou
  que ambos usavam leitura permissiva com default `[]`: quando o arquivo
  canônico estava ausente, reportavam contagens zero e `ok=true`. O Lifecycle
  também podia tratar ausência como lista vazia em atualização manual; o
  Outcome Evaluator podia iniciar avaliação sem ledger.
- `paper_state_storage.py` agora concentra o resolvedor comum de diretório e a
  leitura estrita da lista de posições. Lifecycle e Outcome reportam
  `PAPER_STATE_FILES_MISSING` ou `PAPER_STATE_FILES_INVALID`, contagens `null`
  e `ok=false` enquanto enabled; apenas um arquivo existente e válido `[]`
  significa zero posições. Atualização manual do Lifecycle e avaliação de
  Outcomes param sem gravar log/stats se o ledger estiver ausente. O Executor
  continua sem inicializar nem importar estado automaticamente.
- Validação final após o ajuste: `--paper-integrated-disk-guard` — **52 passaram
  e 12 subtestes passaram**; `--paper-lifecycle-disk-failures` — **5 passaram,
  26 deselected**; `--paper-lifecycle-integration` — **110 passaram, 1
  deselected**. Tudo rodou pelo harness offline com armazenamento temporário;
  nenhuma rede/corretora/Render foi chamada. A primeira execução da regressão
  Lifecycle revelou incompatibilidade no texto de erro de JSON corrompido; o
  contrato histórico foi preservado e as regressões passaram na repetição.
- A diferença local agora inclui também `paper_state_storage.py`,
  `paper_lifecycle.py` e `outcome_evaluator.py`. Continua sem commit/push/deploy;
  runtime e endpoint de produção ainda não refletem estes hardenings.

## Continuação da revalidação — 2026-11-15

- O operador concordou em manter o executor PAPER integrado fail-closed. O JSON
  recebido às 11:27:24 BRT confirma `paper_execution_enabled=true`,
  `real_execution_enabled=false`, `PAPER_STATE_FILES_MISSING` e contagens nulas;
  portanto não prova zero posições PAPER nem permite habilitar esse executor.
- Nova leitura somente de metadados pelo Render MCP confirma que o serviço
  permanece Live no SHA `8c02d37607d1f85540a069ffff03a9d221e74504`, deploy
  `dep-dbrg0mdg1s2s738cs32g`, finalizado em 2026-11-13 12:20:52 UTC. O serviço
  não está no código local mais novo; nenhum deploy/push foi feito.
- A revisão do endpoint de consulta do Lifecycle encontrou um último caso de
  resposta enganosa: `get_paper_lifecycle_positions()` tratava arquivo ausente
  ou inválido como lista vazia e respondia `ok=true`. A correção local agora
  retorna `PAPER_STATE_FILES_MISSING`/`INVALID`, `count=null` e `positions=null`;
  somente `[]` existente e válido responde como zero. Teste de regressão cobre
  ausência, corrupção e lista vazia legítima.
- Regressões offline após essa correção: `--paper-integrated-disk-guard` —
  **53 passaram e 12 subtestes passaram**; `--paper-lifecycle-disk-failures` —
  **5 passaram, 26 deselected**; `--paper-lifecycle-integration` —
  **110 passaram, 1 deselected**. `git diff --check` passou. Não houve chamada
  local à rede, corretora ou Render, nem leitura de secrets.
- A tentativa de abrir o Dashboard para consultar o Shell falhou durante a
  inicialização da automação (`failed to write kernel assets`); nenhuma sessão
  Shell foi aberta. A saída autenticada fornecida pelo operador às 11:27 BRT
  permanece a evidência de ledger mais recente neste trabalho.
- O estado local contém os commits `f5df2ea` (hardening PAPER) e `4e4c012`
  (documentação), mais a correção acima em validação local. A alteração
  preexistente do operador em
  `tests/test_paper_executor_integrated_idempotency_v1.py` permanece intocada.
