# Revalidação de prontidão pessoal — 2026-11-10

## Veredito

**Não declarar prontidão de trading contínuo.** O código validado localmente **não corresponde** ao release atualmente Live no Render. Ainda faltam evidências atuais de reconciliação PAPER e prontidão dos workers. O serviço registra bloqueios deliberados de tarefas históricas pela política `STATIC_OPERATIONAL_RUNTIME`; o health check do Render ainda não está configurado como HTTP.

Esta revalidação não alterou variáveis de produção, Registry, C3, dados de `/data` nem enviou ordens.

## Identidade e release

- Repositório: `C:\cqintegrated`, remoto `giulio-attilio/8---Central-Quant`.
- Branch: `codex/personal-readiness-runtime-fix-20261110`.
- Branch de validação: `codex/personal-readiness-runtime-fix-20261110`. Em `2026-11-10T17:38Z`, o HEAD local é `86edee4e90e05458f9bedf5ca153d39908552e6e`; o ref local de `origin` permanece em `3f7a353a3f474aac509ce1e7b20f3125c71aa5e8`, e a branch local não possui upstream configurado. Logo, `86edee4` ainda não foi enviado ao GitHub.
- Os guards de preço e o watchdog de ticker prolongadamente indisponível foram validados localmente offline. O commit `86edee4` acrescenta retry de alerta Telegram quando a entrega falha e atualiza este relatório.
- O Render continua em `4c2ff20`; nem `63b2002` nem `86edee4` estão implantados.
- Render service: `central-robos-bingx` (`srv-d8rtuv9o3t8c73ehav5g`).
- Deploy: `dep-dbphh9ff3r2c73865ebg`, SHA `4c2ff20db31584ab23f74a2f76073a02881fb90d`, `status=live`, deploy manual, concluído em `2026-11-10T13:15:38Z`.
- Reconsulta Render somente de leitura em `2026-11-10`: confirma o mesmo deploy como mais recente e Live. O branch configurado no serviço é `codex/personal-readiness-20261103`, diferente da branch local/remota validada `codex/personal-readiness-runtime-fix-20261110`. Como `autoDeploy=no`, isso não altera o release atual, mas requer escolher e documentar o branch de origem antes de uma publicação futura para evitar divergência.
- Nova consulta somente de leitura às `2026-11-10T15:19Z`: o deploy mais recente continuava `4c2ff20`/`dep-dbphh9ff3r2c73865ebg`, `status=live`; configuração observada: uma instância, `/data` 4 GB, `healthCheckPath` vazio, auto-deploy desligado.
- Reconsulta somente de leitura às `2026-11-10T15:45Z`: serviço ainda aponta para o deploy Live `4c2ff20`; permanece uma instância, `healthCheckPath` vazio, `autoDeploy=off`, com `/data` montado em 4 GB. Nos 60 minutos medidos, CPU oscilou aproximadamente entre 23% e 47% de um vCPU; memória entre 0,88 e 1,08 GB de 2 GB. Métricas de `/healthz` mostraram uma requisição por intervalo de cinco minutos, com latências agregadas de 4–624 ms; como a série não informa o status HTTP, isso não confirma por si só o resultado do endpoint. Sem resposta de erro HTTP 502 na série consultada. Métricas de recurso aceitáveis não demonstram saúde dos workers.
- Reconsulta somente de leitura às `2026-11-10T16:07Z`: continua uma instância e o mesmo deploy `4c2ff20`, `healthCheckPath` vazio, `autoDeploy=off`, `/data` 4 GB. No intervalo de 30 minutos, CPU variou de 0,18 a 0,47 vCPU e memória de aproximadamente 0,86 a 1,03 GB de 2 GB. A série mostrou respostas 200, sem 502; uma amostra agregada de latência HTTP chegou a 5,18 s e não deve ser tratada como p95 confiável do endpoint sem granularidade/volume adicionais.
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
- Nova leitura filtrada do intervalo `15:37Z–16:07Z` encontrou outra rajada às `16:05:33Z`: erro `'NoneType' object is not subscriptable` durante gestão Donkey para BNB, TRX, NEAR, FIL e PENDLE. Esses eventos também estão marcados como `info`; as buscas paralelas por `error/warn/warning` e HTTP 500/502/503 ficaram vazias. Isso confirma que a falha se repetiu no release em produção. Não indica, por si só, que ordens tenham sido enviadas ou posições alteradas.
- Atualização somente de leitura às `16:25Z`: serviço ainda na configuração/deploy acima. As buscas filtradas até `16:25Z` retornaram apenas a mesma rajada das `16:05:33Z`, sem ocorrência posterior de `NoneType`/`ERRO GESTÃO DONKEY`; buscas `error/warn/warning` e HTTP 500/502/503 também vazias. O intervalo sem novos eventos é curto e o release não mudou, então não comprova recuperação.
- Reconsulta somente de leitura às `17:02Z`: serviço ainda no deploy Live `4c2ff20`, uma instância e sem `healthCheckPath`. A busca da última hora encontrou nova rajada `ERRO GESTÃO DONKEY ... 'NoneType' object is not subscriptable` às `16:50:33Z` em nove símbolos (BTC, ETH, SOL, XRP, BNB, TRX, NEAR, FIL e PENDLE); uma rajada anterior às `16:05:33Z` atingiu BNB, TRX, NEAR, FIL e PENDLE. Os eventos aparecem como `info`, não exceções de nível error. Não surgiu `DONKEY_TICKER_STALE`, coerente com o watchdog ainda não estar no release. Também persistiram bloqueios `STATIC_OPERATIONAL_RUNTIME_BLOCKED` para `predator_heavy_watchdog_audit` às `16:15:33Z` e `smartpredator_large_redis_snapshot` às `16:30:33Z`. Isso demonstra recorrência da falha Donkey na produção e suspensão de tarefas; não demonstra, por si só, alteração de posição ou ordem executada.
- Nova consulta somente de leitura até `17:15Z`: deploy e configuração não mudaram; às `17:05:33Z` houve outra rajada Donkey nos mesmos nove símbolos, em duas passagens registradas com menos de 1 ms de diferença. A busca não encontrou `DONKEY_TICKER_STALE`, `PRIVATE_HTTP_AUTH_NOT_CONFIGURED` ou `Traceback` no período `17:00Z–17:15Z`. A API de eventos após o deploy retornou apenas `deploy_ended` bem-sucedido às `13:15:38Z` (sem restart/escala adicional no resultado consultado); `list_services` encontrou apenas este serviço Central no workspace. No SHA Live, `BOT_CONFIGS` declara uma entrada DONKEY, `start_enabled_bots()` tem um callsite e o bot inicia o scanner por um único start hook. Portanto, as duas passagens são uma anomalia que ainda precisa ser atribuída; estes dados não provam dois processos, segundo serviço, escritores concorrentes ou necessidade de C3. A contagem de processos apresentada manualmente antes não é uma observação simultânea a este intervalo. A ausência dos marcadores tampouco comprova configuração de credenciais, recuperação do worker ou ausência de alteração de posições. O guard candidato segue importante, sujeito aos gates de custo e operação.
- Busca somente de leitura por `PREDATOR_AUDIT_` nos logs de aplicação de 1 a 10/11/2026 não encontrou eventos. Portanto não há, nessa janela, telemetria de produção de duração/RSS da auditoria pesada para justificar removê-la do bloqueio.

O código em `static_operational_runtime.py` define esse bloqueio como uma política intencional para suspender cargas históricas automáticas. A evidência confirma que algumas tarefas não executam; não demonstra crash. Não consultar nem desligar a variável de política por inferência: a alteração pode iniciar auditoria pesada e escrita no Registry.

`/healthz` em `main.py` é uma rota pública estreita para probe do Render e responde `HTTP_LIVE` quando o latch de runtime e o estado de drain permitem. Ela não afirma readiness de trading nem valida cada worker. Os testes em `test_personal_http_auth_gate_v1.py` cobrem a exceção pública, query string, método, origem e drain.

## Testes locais offline

Executados com `tests/run_falcon_pilot_minimal_offline.py`, cujo runner bloqueia chamadas de rede durante os testes. Dependências isoladas em venv dentro de `%TEMP%`; nenhuma dependência foi instalada globalmente ou no repositório.

| Seleção | Resultado |
|---|---:|
| `--account-client-order-authority` | 97 passed |
| `--personal-execution-safety` | 402 passed em 12m12s (reexecutado nesta continuação; runner offline) |
| `--personal-lifecycle-completeness` | 888 passed em 31m38s |
| `--personal-position-read-fail-closed` | 45 passed |
| `--upstash-sdk-contract` | 2 passed |
| `--market-data-throttle` com `ccxt==4.5.88` real | 98 passed |

Reexecução mais recente às `17:07Z` de `--personal-http-auth`: **243 passed em 122.71s**, usando o runner offline com bloqueio de rede. Isso revalida os contratos locais de Basic Auth global (com a exceção mínima e específica de `/healthz`), a proteção contra mutações via GET, aliases/métodos e o probe HTTP mínimo; não é teste de penetração no serviço publicado.

Também reexecutada nesta continuação a seleção `--personal-position-read-fail-closed`: **45 passed em 8.99s**, com o mesmo runner offline. Isso cobre respostas seguras a leituras de posição indisponíveis nos cenários simulados; não reconcilia o estado atual da conta/corretora.

Para atualizar a decisão C3 sem ativá-lo, também foram reexecutadas `--registry-writers` (**60 passed em 92.53s**) e `--c3-dormant-startup` (**24 passed e 3 subtests em 610.20s**). A primeira verifica contratos/callsites de gravação e cenários sintéticos de RMW; a segunda mantém a instalação C3 dormente e valida o grafo/startup sem I/O nos fixtures. Nenhuma delas mede simultaneidade real ou contenção física do disco Render.

Seleção offline adicional de `test_predator_audit_memory_observability.py`, `test_predator_audit_request_cache.py` e `test_closed_trade_key_index_v1.py`: **30 passed em 1.57s**. A execução bloqueou conexões/sockets, subprocessos e acesso a `.env`, usando diretório temporário. Os testes cobrem instrumentação/cache/index e concorrência sintética, mas não medem o custo da auditoria sobre os arquivos de produção.

Após a falha Donkey observada nos logs, a revisão foi ampliada para os gestores de preço ativo em Cobra, Donkey, Falcon, Meme, Predator, Trend PRO e Turtle. Os caminhos alterados rejeitam ticker/preço ausente, malformado, não finito ou não positivo e não avançam a mutação de posição naquele ciclo. A seleção `--market-data-throttle` passou: **158 passed em 23.40s**, runner offline/rede bloqueada e persistência temporária. Os testes incluem quatro ciclos intermitentes e recuperação para Donkey e Trend PRO, guards dos gestores Cobra/Meme, validação de preço Predator, `safe_fetch_price` Falcon/Turtle e watchdog Donkey. O watchdog alerta após 900 s de falha contínua de ticker (configurável por `DONKEY_TICKER_STALE_ALERT_SECONDS`), sem inventar preço ou acionar saída; o mapa é volátil e reinicia com o processo. Isso não constitui integração com a corretora, não garante saída de emergência durante indisponibilidade e não comprova entrega efetiva do Telegram em produção. O código e os testes estão commitados em `63b2002` e publicados na branch pessoal; não estão implantados no Render.

Reexecução nesta continuação, após ampliar os guards e o watchdog Donkey, de `--drain-regression`: **174 passed em 377.47s**, usando o runner que bloqueia rede e direciona persistência a diretório temporário. Essa seleção cobre contratos de drain/gestão e runtime; não é um teste end-to-end da corretora nem prova de integração de produção.

Também aprovadas anteriormente no mesmo HEAD: `--static-runtime` (30), `--personal-safety-no-ccxt` (267), `--personal-http-auth` (243), `--c3-dormant-startup` (24 e 3 subtestes), além de seleções de locks, writers, persistência e lifecycle PAPER. Testes com broker/mocks não provam integração de produção nem execução real de ordens.

## C3 e persistência

`docs/PERSONAL_C3_NEED_ASSESSMENT_20261110.md` mantém C3 fora do caminho crítico: a topologia observada é uma instância/processo, e a contagem de callsites não prova simultaneidade de 19 writers. Não foi ativado signer, checkpoint distribuído nem C3.

Última inspeção histórica fornecida pelo usuário (não atual): Registry com 69 trades abertos, todos PAPER; os arquivos do ledger PAPER integrado consultados estavam ausentes. Essa leitura antecede o deploy atual e não demonstra reconciliação atual. O usuário confirmou ausência de operações abertas antes do deploy, não como estado permanente.

## Triagem da auditoria externa recebida

- **Aceito:** “Live” e os testes offline não provam operação contínua; a ausência de telemetria do Predator não justifica ativar auditoria pesada; C3 permanece preservado e fora do caminho crítico sem evidência de concorrência distribuída necessária.
- **Donkey e bots correlatos:** o erro de `NoneType` foi confirmado novamente em produção às 16:05:33Z em cinco símbolos. A correção foi ampliada localmente para caminhos ativos Cobra, Donkey, Falcon, Meme, Predator, Trend PRO e Turtle; guards rejeitam preços inválidos e evitam mutação naquele ciclo. O watchdog agora rastreia falha consecutiva por posição e alerta depois de 900 s, usando o alerta crítico existente, sem modificar posições. Os testes offline passaram, mas não há evidência de recuperação nem de recebimento do alerta em produção porque `63b2002` ainda não foi implantado. 15 min é um limite operacional configurável adotado da hipótese oferecida na auditoria, não um limite de segurança de mercado comprovado.
- **Arquivos PAPER ausentes:** a captura de arquivos ausentes, isoladamente, não justifica criar arquivos vazios. O entrypoint Render observado é `python main.py`; `main.py` resolve `CENTRAL_DATA_DIR` usando `CENTRAL_DATA_DIR`, depois `DATA_DIR`, depois `/data` quando montado, e exporta esse caminho no ambiente antes dos imports operacionais (`main.py`, linhas 81–103 e import do executor na linha 643). Portanto, o shell com `CENTRAL_DATA_DIR=unset` não prova que o processo principal usa o diretório efêmero. `paper_executor_integrated.py` cria estado no primeiro uso autorizado e seu flag de execução PAPER tem default `false`; confirmar configuração e caminho efetivos por metadados, sem bootstrap/migração e sem confundir ausência inicial com estado reconciliado.
- **Health check:** `/healthz` só declara runtime HTTP pronto e não trading readiness. A rota está atrás do latch global de readiness de runtime, retorna 503 durante startup/drain e 200 `HTTP_LIVE` quando permitido (`main.py`, linhas 841–870). Configurá-la no Render pode melhorar detecção de falha HTTP, mas não substitui monitoramento de workers nem preflight de trading; possível reinício/downtime deve ser considerado antes de alterar infraestrutura.

## Revalidação adicional — 2026-11-10 17:25 UTC

- Consulta Render somente de leitura reconfirmou o serviço `central-robos-bingx` no deploy Live `4c2ff20db31584ab23f74a2f76073a02881fb90d` (`dep-dbphh9ff3r2c73865ebg`), uma instância, disco persistente `/data` de 4 GB, branch configurada `codex/personal-readiness-20261103`, `autoDeploy=off` e `healthCheckPath` vazio. O candidato `63b2002` segue sem deploy.
- Consulta de logs de aplicação `17:00–17:25 UTC` encontrou 18 mensagens `ERRO GESTÃO DONKEY ... 'NoneType' object is not subscriptable` às `17:05:33Z`, para nove símbolos, todas na mesma instância `srv-d8rtuv9o3t8c73ehav5g-xpm28`. Isto confirma recorrência no código Live, mas não prova múltiplos processos, alteração de posição ou ordem enviada.
- A consulta filtrada `DONKEY_TICKER_STALE` retornou zero linhas nesse intervalo, compatível com o watchdog candidato não implantado; não prova ausência de falha. A consulta do marcador `PRIVATE_HTTP_AUTH_NOT_CONFIGURED` falhou com HTTP 503 do serviço de logs (`log retrieval is currently unavailable`); portanto, não atualiza a evidência de configuração da autenticação.
- Reexecução de `--market-data-throttle` no runner offline com rede bloqueada: **158 passed em 24.61s**. O resultado valida a lógica coberta por mocks/fixtures, não a integração da corretora nem o comportamento do release Render.
- O usuário executou no Render Shell a consulta booleana para `CENTRAL_PERSONAL_HTTP_USER` e `CENTRAL_PERSONAL_HTTP_PASSWORD`; ambas retornaram `SET=True`. Nenhum valor foi exibido. Isso confirma presença não vazia no ambiente do Shell, mas não prova que as credenciais estejam corretas, que o processo da aplicação as tenha carregado ou que o Basic Auth funcione por uma requisição HTTP externa.
- Correção local do watchdog Donkey em `86edee4`: antes, `enviar_alerta_watchdog()` iniciava cooldown de uma hora mesmo quando o transporte Telegram retornava `sent=False`. Agora o cooldown só é registrado após envio confirmado; falha permite nova tentativa no próximo ciclo do watchdog. Teste sintético offline cobre falha seguida de sucesso e a classificação `WATCHDOG_STALLED` como crítica. Isso não verifica entrega real ao Telegram.
- Reexecução de `--market-data-throttle` após essa correção: **159 passed em 31.64s**; `--telegram-notification-policy`: **73 passed em 197.63s**. Ambos pelo runner offline/rede bloqueada. A primeira seleção cobre o novo contrato de retry; a segunda confirma a política genérica de notificação crítica em PAPER. Não são validação de rede nem de produção.
- Reexecução de `--personal-http-auth`: **243 passed em 196.12s**, pelo runner offline com rede bloqueada. Revalida os contratos locais do gate e exceção estreita de `/healthz`; não prova as credenciais presentes no Render nem o funcionamento do serviço público.

## Atualização após push — 2026-11-10 17:42 UTC

- Push fast-forward concluído para `origin/codex/personal-readiness-runtime-fix-20261110`; `git ls-remote` confirmou ref `9ac480c0763c3576135c2672b2d0e4a73a825db1`. O SHA de código testado `86edee4e90e05458f9bedf5ca153d39908552e6e` está nessa branch. Nenhum force push foi usado.
- Reconsulta Render após o push manteve `autoDeploy=off` e o deploy Live `4c2ff20db31584ab23f74a2f76073a02881fb90d`; o push não implantou nem reiniciou o serviço.
- Presença de ambas as variáveis Basic Auth confirmada pelo usuário no Shell (`SET=True`), sem revelar valores; o teste HTTP externo ainda está pendente.

## Pendências e próximos passos seguros

1. Confirmar em leitura somente de metadados o estado atual das posições e a reconciliação entre Registry e ledger PAPER, sem imprimir conteúdo de trades nem segredos.
2. Confirmar o funcionamento efetivo do Basic Auth em uma requisição externa ao serviço, sem compartilhar usuário/senha: rota privada deve rejeitar acesso sem autenticação e aceitar autenticação no navegador do proprietário; `/healthz` permanece exceção pública estreita. A presença das duas variáveis foi confirmada no Shell, mas não sua validade nem o carregamento pelo processo.
3. Avaliar se a rota `/healthz` é suficiente para health check de infraestrutura; ela não cobre workers. Qualquer configuração de Health Check no Render exige confirmar efeitos e custo antes; não foi alterada.
4. Investigar quais tarefas suspensas são realmente necessárias ao uso pessoal. Manter a política fail-closed até que custo, latência, memória, lock e risco de escrita sejam demonstrados seguros.
5. O código candidato original `63b2002` e a correção adicional `86edee4` estão enviados à branch pessoal; o candidato não está implantado. Não há decisão financeira específica para publicar o SHA exato `86edee4`, e a última confirmação de ausência de operações é anterior; ambos precisam ser atuais. Deploys Render consomem minutos de pipeline e o disco persistente desativa zero-downtime, portanto não se deve inferir custo zero nem interrupção nula. Os erros observados não demonstram ordem executada, mas mostram que a gestão da posição falhava quando o ticker era `None`. O limite de 900 s aciona apenas alerta manual, não é proteção automática contra risco de mercado.
6. A prontidão de entrada/fill/posição/stop/fechamento/reconciliação permanece demonstrada somente por testes simulados; nenhuma ordem real foi enviada (intencional).
7. Antes de qualquer nova alteração externa, confirmar custo, ausência atual de operações, alvo exato, validação e rollback. Manter `ENABLE_REAL_TRADING=false`, `BROKER_DRY_RUN=true` e `FALCON_MODE=PAPER`.

**Ação manual imediata:** testar o Basic Auth no site sem fornecer credenciais ao assistente; em janela anônima, `GET /` deve pedir autenticação, e `/healthz` deve continuar respondendo publicamente conforme previsto. Para publicar `86edee4`, ainda faltam decisão financeira específica para esse SHA (custo zero não está confirmado) e confirmação operacional atual de ausência de operações/interrupção segura. Nenhum controle LIVE foi alterado e nenhuma ordem real foi enviada; isso continua proibido pela meta.
