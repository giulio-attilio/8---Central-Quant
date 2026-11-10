# Revalidação de prontidão pessoal — 2026-11-10

## Veredito

**Não declarar prontidão de trading contínuo.** O código validado localmente corresponde ao release atualmente Live no Render, e as suítes offline abaixo passaram. Ainda faltam evidências atuais de reconciliação PAPER e prontidão dos workers. O serviço registra bloqueios deliberados de tarefas históricas pela política `STATIC_OPERATIONAL_RUNTIME`; o health check do Render ainda não está configurado como HTTP.

Esta revalidação não alterou variáveis de produção, Registry, C3, dados de `/data` nem enviou ordens.

## Identidade e release

- Repositório: `C:\cqintegrated`, remoto `giulio-attilio/8---Central-Quant`.
- Branch: `codex/personal-readiness-runtime-fix-20261110`.
- HEAD-base antes da rodada atual: `dc85306ecd8a78518740421d87182d6088043caf`, branch `codex/personal-readiness-runtime-fix-20261110`.
- Rodada atual ainda não commitada: oito arquivos modificados (`bots/cobra.py`, `bots/donkey.py`, `bots/falcon.py`, `bots/meme.py`, `bots/predator.py`, `bots/trendpro.py`, `bots/turtle.py` e `tests/test_exchange_manager_throttle_v1.py`). `git diff --check` passou. Portanto, estes ajustes mais recentes ainda não foram publicados no GitHub.
- O Render continua em `4c2ff20`; nem o HEAD-base `dc85306` nem as alterações locais mais recentes estão implantados.
- Render service: `central-robos-bingx` (`srv-d8rtuv9o3t8c73ehav5g`).
- Deploy: `dep-dbphh9ff3r2c73865ebg`, SHA `4c2ff20db31584ab23f74a2f76073a02881fb90d`, `status=live`, deploy manual, concluído em `2026-11-10T13:15:38Z`.
- Reconsulta Render somente de leitura em `2026-11-10`: confirma o mesmo deploy como mais recente e Live. O branch configurado no serviço é `codex/personal-readiness-20261103`, diferente da branch local/remota validada `codex/personal-readiness-runtime-fix-20261110`. Como `autoDeploy=no`, isso não altera o release atual, mas requer escolher e documentar o branch de origem antes de uma publicação futura para evitar divergência.
- Nova consulta somente de leitura às `2026-11-10T15:19Z`: o deploy mais recente continuava `4c2ff20`/`dep-dbphh9ff3r2c73865ebg`, `status=live`; configuração observada: uma instância, `/data` 4 GB, `healthCheckPath` vazio, auto-deploy desligado.
- Reconsulta somente de leitura às `2026-11-10T15:45Z`: serviço ainda aponta para o deploy Live `4c2ff20`; permanece uma instância, `healthCheckPath` vazio, `autoDeploy=off`, com `/data` montado em 4 GB. Nos 60 minutos medidos, CPU oscilou aproximadamente entre 23% e 47% de um vCPU; memória entre 0,88 e 1,08 GB de 2 GB. Métricas de `/healthz` mostraram uma requisição por intervalo de cinco minutos, com latências agregadas de 4–624 ms; como a série não informa o status HTTP, isso não confirma por si só o resultado do endpoint. Sem resposta de erro HTTP 502 na série consultada. Métricas de recurso aceitáveis não demonstram saúde dos workers.
- Serviço: uma instância, Standard, disco persistente `/data` de 4 GB, auto-deploy desligado.
- `healthCheckPath` está vazio; o Render está usando o probe TCP padrão, que não comprova readiness HTTP nem execução de workers.
- Não foi verificado o custo efetivamente cobrado. O deploy foi autorizado pelo usuário com limite de US$ 5.

## Evidência de runtime após o deploy

Consulta somente de leitura dos logs de aplicação após o deploy:

- `2026-11-10T13:20:32Z`: `STATIC_OPERATIONAL_RUNTIME_BLOCKED` para `central_daily_historical_report`.
- `2026-11-10T13:20:32Z`: `STATIC_OPERATIONAL_RUNTIME_BLOCKED` para `smartpredator_large_redis_snapshot`.
- Logs anteriores da mesma implantação também registraram `predator_heavy_watchdog_audit` bloqueado.
- A consulta de logs de nível `error`, `warn` e `warning` após o deploy não retornou eventos.
- Uma leitura adicional dos logs encontrou, em `2026-11-10T14:50:33Z`, avisos de cooldown do throttle compartilhado e várias mensagens `ERRO GESTÃO DONKEY ... 'NoneType' object is not subscriptable`. O provider classificou essas mensagens como `info`; por isso não apareciam na busca apenas por severidade `error/warn`. O código em `bots/donkey.py` confirma o caminho: `safe_fetch_ticker()` retorna `None` no throttle e o loop de gestão indexava `ticker["last"]` sem validar.
- Consulta de logs filtrada encontrou nova rajada em `2026-11-10T15:35:33Z`: `NoneType` durante a gestão Donkey em oito símbolos (classificados pelo Render como `info`); nenhuma ocorrência adicional desses filtros entre `15:35:30Z` e `15:45Z`. Consulta por severidade `error/warn/warning` no período `15:15Z–15:45Z` veio vazia. A ausência de novas linhas numa janela curta não prova recuperação nem gestão integral das posições; o release `4c2ff20` ainda não contém o guard local validado.
- Busca somente de leitura por `PREDATOR_AUDIT_` nos logs de aplicação de 1 a 10/11/2026 não encontrou eventos. Portanto não há, nessa janela, telemetria de produção de duração/RSS da auditoria pesada para justificar removê-la do bloqueio.

O código em `static_operational_runtime.py` define esse bloqueio como uma política intencional para suspender cargas históricas automáticas. A evidência confirma que algumas tarefas não executam; não demonstra crash. Não consultar nem desligar a variável de política por inferência: a alteração pode iniciar auditoria pesada e escrita no Registry.

`/healthz` em `main.py` é uma rota pública estreita para probe do Render e responde `HTTP_LIVE` quando o latch de runtime e o estado de drain permitem. Ela não afirma readiness de trading nem valida cada worker. Os testes em `test_personal_http_auth_gate_v1.py` cobrem a exceção pública, query string, método, origem e drain.

## Testes locais offline

Executados com `tests/run_falcon_pilot_minimal_offline.py`, cujo runner bloqueia chamadas de rede durante os testes. Dependências isoladas em venv dentro de `%TEMP%`; nenhuma dependência foi instalada globalmente ou no repositório.

| Seleção | Resultado |
|---|---:|
| `--account-client-order-authority` | 97 passed |
| `--personal-execution-safety` | 402 passed em 15m29s |
| `--personal-lifecycle-completeness` | 888 passed em 31m38s |
| `--personal-position-read-fail-closed` | 45 passed |
| `--upstash-sdk-contract` | 2 passed |
| `--market-data-throttle` com `ccxt==4.5.88` real | 98 passed |

Reexecução nesta continuação, em `2026-11-10`, de `--personal-http-auth`: **243 passed em 124.67s**, usando o runner offline com bloqueio de rede. Isso revalida os contratos locais de autenticação e o healthz mínimo; não é teste de penetração no serviço publicado.

Também reexecutada nesta continuação a seleção `--personal-position-read-fail-closed`: **45 passed em 8.99s**, com o mesmo runner offline. Isso cobre respostas seguras a leituras de posição indisponíveis nos cenários simulados; não reconcilia o estado atual da conta/corretora.

Para atualizar a decisão C3 sem ativá-lo, também foram reexecutadas `--registry-writers` (**60 passed em 92.53s**) e `--c3-dormant-startup` (**24 passed e 3 subtests em 610.20s**). A primeira verifica contratos/callsites de gravação e cenários sintéticos de RMW; a segunda mantém a instalação C3 dormente e valida o grafo/startup sem I/O nos fixtures. Nenhuma delas mede simultaneidade real ou contenção física do disco Render.

Seleção offline adicional de `test_predator_audit_memory_observability.py`, `test_predator_audit_request_cache.py` e `test_closed_trade_key_index_v1.py`: **30 passed em 1.57s**. A execução bloqueou conexões/sockets, subprocessos e acesso a `.env`, usando diretório temporário. Os testes cobrem instrumentação/cache/index e concorrência sintética, mas não medem o custo da auditoria sobre os arquivos de produção.

Após a falha Donkey observada nos logs, a revisão foi ampliada para os gestores de preço ativo em Cobra, Donkey, Falcon, Meme, Predator, Trend PRO e Turtle. Os caminhos alterados rejeitam ticker/preço ausente, malformado, não finito ou não positivo e não avançam a mutação de posição naquele ciclo. Na continuação atual, `--market-data-throttle` passou: **157 passed em 20.36s**, runner offline/rede bloqueada e persistência temporária. Os testes incluem quatro ciclos intermitentes e recuperação para Donkey e Trend PRO, guards dos gestores Cobra/Meme, validação de preço Predator, e `safe_fetch_price` Falcon/Turtle com `None`, inválido e preço válido. Isso não constitui integração com a corretora, não garante saída de emergência durante indisponibilidade prolongada e não implementa limite de staleness/alerta de 15 minutos. As mudanças permanecem locais e sem commit/push.

Reexecução nesta continuação, após ampliar os guards, de `--drain-regression`: **174 passed em 305.42s**, usando o runner que bloqueia rede e direciona persistência a diretório temporário. Essa seleção cobre contratos de drain/gestão e runtime; não é um teste end-to-end da corretora nem prova de integração de produção.

Também aprovadas anteriormente no mesmo HEAD: `--static-runtime` (30), `--personal-safety-no-ccxt` (267), `--personal-http-auth` (243), `--c3-dormant-startup` (24 e 3 subtestes), além de seleções de locks, writers, persistência e lifecycle PAPER. Testes com broker/mocks não provam integração de produção nem execução real de ordens.

## C3 e persistência

`docs/PERSONAL_C3_NEED_ASSESSMENT_20261110.md` mantém C3 fora do caminho crítico: a topologia observada é uma instância/processo, e a contagem de callsites não prova simultaneidade de 19 writers. Não foi ativado signer, checkpoint distribuído nem C3.

Última inspeção histórica fornecida pelo usuário (não atual): Registry com 69 trades abertos, todos PAPER; os arquivos do ledger PAPER integrado consultados estavam ausentes. Essa leitura antecede o deploy atual e não demonstra reconciliação atual. O usuário confirmou ausência de operações abertas antes do deploy, não como estado permanente.

## Triagem da auditoria externa recebida

- **Aceito:** “Live” e os testes offline não provam operação contínua; a ausência de telemetria do Predator não justifica ativar auditoria pesada; C3 permanece preservado e fora do caminho crítico sem evidência de concorrência distribuída necessária.
- **Donkey e bots correlatos:** o achado de NoneType em produção é corroborado pelos logs históricos; a correção inicialmente focada em Donkey/Trend PRO foi ampliada localmente para caminhos ativos Cobra, Donkey, Falcon, Meme, Predator, Trend PRO e Turtle. Os guards rejeitam preços inválidos e evitam mutação naquele ciclo. Os testes offline passaram, mas a observação curta sem novas linhas não demonstra recuperação de produção. O limite de 15 minutos sugerido é hipótese, não requisito derivado do código/estratégia; não adicionar alerta Telegram/timeout sem mapear ordens de proteção independentes e resposta segura.
- **Arquivos PAPER ausentes:** a captura de arquivos ausentes, isoladamente, não justifica criar arquivos vazios. O entrypoint Render observado é `python main.py`; `main.py` resolve `CENTRAL_DATA_DIR` usando `CENTRAL_DATA_DIR`, depois `DATA_DIR`, depois `/data` quando montado, e exporta esse caminho no ambiente antes dos imports operacionais (`main.py`, linhas 81–103 e import do executor na linha 643). Portanto, o shell com `CENTRAL_DATA_DIR=unset` não prova que o processo principal usa o diretório efêmero. `paper_executor_integrated.py` cria estado no primeiro uso autorizado e seu flag de execução PAPER tem default `false`; confirmar configuração e caminho efetivos por metadados, sem bootstrap/migração e sem confundir ausência inicial com estado reconciliado.
- **Health check:** `/healthz` só declara runtime HTTP pronto e não trading readiness. A rota está atrás do latch global de readiness de runtime, retorna 503 durante startup/drain e 200 `HTTP_LIVE` quando permitido (`main.py`, linhas 841–870). Configurá-la no Render pode melhorar detecção de falha HTTP, mas não substitui monitoramento de workers nem preflight de trading; possível reinício/downtime deve ser considerado antes de alterar infraestrutura.

## Pendências e próximos passos seguros

1. Confirmar em leitura somente de metadados o estado atual das posições e a reconciliação entre Registry e ledger PAPER, sem imprimir conteúdo de trades nem segredos.
2. Avaliar se a rota `/healthz` é suficiente para health check de infraestrutura; ela não cobre workers. Qualquer configuração de Health Check no Render exige confirmar efeitos e custo antes; não foi alterada.
3. Investigar quais tarefas suspensas são realmente necessárias ao uso pessoal. Manter a política fail-closed até que custo, latência, memória, lock e risco de escrita sejam demonstrados seguros.
4. Donkey e Trend PRO passaram por testes locais de quatro ciclos intermitentes com recuperação. Avaliar publicação somente após fechar as pendências de reconciliação e release; os erros observados não são evidência de ordem executada, mas mostram que a gestão da posição era ignorada quando faltava preço. Não há limite de staleness por posição validado; definir um exige requisito e resposta segura, não assumir 15 minutos.
5. A prontidão de entrada/fill/posição/stop/fechamento/reconciliação permanece demonstrada somente por testes simulados; nenhuma ordem real foi enviada (intencional).
6. Antes de qualquer nova alteração externa, confirmar custo, ausência atual de operações, alvo exato, validação e rollback. Manter `ENABLE_REAL_TRADING=false`, `BROKER_DRY_RUN=true` e `FALCON_MODE=PAPER`.

**Ação manual imediata:** nenhuma para o deploy já concluído. Não há autorização para alterar LIVE ou enviar ordens reais.
