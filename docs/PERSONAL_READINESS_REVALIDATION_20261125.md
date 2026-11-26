# Central Quant/Falcon — revalidação pessoal (2026-11-25)

## Resumo atual — 2026-11-26 10:03 UTC

Render MCP foi consultado novamente em modo somente leitura no workspace
`Central Quant`: `central-robos-bingx` continua Live no deploy
`dep-dc3odps9v7es73cpao00`, SHA `455c94a56fe616a963a4ef1ce95a057c784071de`.
Configuração observada: branch `codex/prod-wsgi-20261125`, Auto-Deploy Off,
`healthCheckPath=/healthz`, uma instância Standard e disco `/data` de 4 GB. Não
houve novo deploy desde a última observação. `/healthz` é probe de runtime, não
confirma prontidão PAPER/trading nem dispara deploy. Custo atual/franquia de
build não foi confirmado; não há push nem deploy pendente em execução.

No checkout local `codex/prod-wsgi-20261125`, o HEAD é
`9f6c7913c86fc8698137e17a6c40c7cb26e4d8d4`, quatro commits à frente da
referência remota localmente observada. Os quatro commits mudam nove arquivos
Python/testes e não alteram `requirements.txt`. Dois relatórios locais continuam
modificados e preservados fora dos commits. O último commit contém somente um
teste integrado do fallback de fills malformado.

No HEAD atual, as suítes offline recentes passaram: `--close-reconciliation`
115; `--personal-http-auth` 243; `--initial-stop-containment` 79;
`--initial-stop-cancel` 85; `--entry-fill-stop` 37; e
`--live-position-risk-gate` 34. A suíte completa de ciclo (896 passou, 1
ignorado) e outros gates também estão registrados abaixo, em HEADs anteriores
cujo código de execução é igual ao atual; o HEAD posterior adicionou apenas
teste. São testes sintéticos offline, não comprovam operação real na BingX.

Bloqueios PAPER permanecem sem reconciliação factual: as últimas evidências
fornecidas pelo operador mostravam `PAPER_STATE_FILES_MISSING` e o preview
`PREVIEW_COMPLETE_NOT_MIGRATABLE`, sem match forte. Esses dados não foram
reconsultados nesta verificação. Não criar ledgers, apagar a trava ou importar
registros sem identidade comprovada. Os controles LIVE não foram alterados; a
última saída de ambiente disponível continua sendo histórica, não uma
revalidação nesta etapa.

## Escopo e segurança

Revalidação local do checkout isolado `codex/prod-wsgi-20261125`, descendente do
SHA Live observado mais recentemente `455c94a56fe616a963a4ef1ce95a057c784071de`;
esse candidato local ainda não foi enviado. O worktree principal não foi
alterado. Sem credenciais, secrets, payloads brutos, chamadas à corretora,
escritas no Render/Upstash, ordens, pushes ou deploys. Os commits locais deste
candidato preservam as alterações para revisão; não alteram a instância Live.

## Evidência de produção fornecida pelo operador

- Render Shell: um processo `python`, EUID/EGID 1000 (`render`); chamada sem
  autenticação a `/livestatus` retornou HTTP 401. Isso verifica apenas essa
  rota, não toda a superfície HTTP.
- `paper_integrated_health`: `data_mount_verified=True`, mas
  `PAPER_STATE_FILES_MISSING`; ledgers/contagens PAPER não disponíveis.
- Trava `falcon_paper_persistence_reconciliation.json`: presente, JSON/versão
  válidos, categoria `accepted_signal_reconciliation`; os marcadores consultados
  de falha de sincronização estavam falsos. A leitura do operador em 2026-11-25
  confirma novamente a existência da trava, a versão V1, a categoria
  `accepted_signal_reconciliation` e ausência dos dois marcadores classificados.
  Isso comprova que a trava continua ativa, não a causa original: o SHA Live
  `3502638` grava um motivo genérico quando não há componentes de writer
  classificados. Isso também pode ocorrer em retornos seguros distintos, como
  ID de sinal ausente, colisão de identidade ou marcador persistido inválido —
  não apenas em falha de Registry/memória. `registry_sync_failed=False` e
  `falcon_memory_sync_failed=False` significam somente que esses rótulos não
  aparecem no motivo; não provam que todos os writers concluíram com sucesso.
  O candidato local agora grava categorias de status de uma lista permitida,
  sem copiar status arbitrário, ID ou texto de exceção. Essa melhoria não está
  no Render e não explica retroativamente a trava existente. Não há prova para
  apagá-la, criar ledgers vazios ou importar registros.
- Os previews sanitizados de origem/Registry retornaram
  `PREVIEW_COMPLETE_NOT_MIGRATABLE`, sem matches fortes, com candidatos
  ambíguos/órfãos. Nenhuma importação ou escrita foi feita.

## Revalidação somente leitura do Render

Em 2026-11-25, `central-robos-bingx` (`srv-d8rtuv9o3t8c73ehav5g`) ainda estava
Live no SHA `3502638ea3d364a21078b4d687f1353ec69bdd5e`; uma instância Standard,
disco persistente de 4 GB em `/data`, auto-deploy desligado, `healthCheckPath`
vazio e start command `python main.py`. Branch configurado:
`codex/personal-readiness-20261103`. Ingress configurado para `0.0.0.0/0`; a
proteção depende da autenticação da aplicação. Nenhum segredo foi consultado.
Uma busca somente leitura por `FALCON` nos logs entre 2026-11-16 16:20 e 16:40
UTC (em torno do `created_at` sanitizado da trava) não retornou linhas. Isso não
determina a causa histórica; o intervalo não fornece evidência positiva do
evento original.

## C3 e Registry

Não há evidência concreta para signer/lease distribuído no caminho crítico da
topologia pessoal de uma instância/processo. “19 writers” representa caminhos
lógicos estáticos inventariados, não 19 processos/writers ativos ou simultâneos.
Locks locais e os testes abaixo dão cobertura dentro do processo; escritores
externos não observados continuam uma limitação. Preservar C3 dormente e
fail-closed; os antigos contratos de anchors C3 não são evidência de prontidão
para ativá-lo.

## Validação offline desta rodada

Executada sem rede pelo runner offline e com o ambiente Python preexistente; não
instalou dependências:

| Seleção | Resultado |
|---|---:|
| Ciclo pessoal (entry/fill/stop/disaster stop/close/reconciliação), reexecutado após a melhoria da trava | 892 passed, 1 skipped |
| Registry writers | 73 passed |
| Regra estática de lock do Registry | 1 passed, 72 deselected |
| C3 startup dormente | 24 passed, 3 subtests |
| HTTP auth | 243 passed |
| Guard `/data` em POSIX/WSL | 128 passed, 12 subtests |
| PAPER main storage | 9 passed |
| Registry V2 PAPER storage | 280 passed, 1 skipped |
| Broker PAPER disk guard | 47 passed |
| PAPER source preview/capture | 46 / 21 passed |
| Bootstrap Gunicorn/WSGI do candidato (inclui drain idempotente e limite temporal) | 24 passed |
| Trava PAPER Falcon (persistência, corrupção, reinício, bloqueio e categorias sanitizadas) | 11 passed |
| Reexecução offline de HTTP auth + projeção Falcon após a melhoria local, sockets bloqueados | 193 passed |

A suíte pessoal completa foi executada pelo runner offline com `ccxt 4.5.90`
preexistente no workspace (sem instalação), sockets/rede, subprocessos e leitura
de `.env` bloqueados e diretório de estado isolado em temporário. A primeira
tentativa com o Python base não coletou três módulos por falta de `ccxt`; ela
foi repetida com a cópia local existente e concluiu com os resultados acima.

O parser oficial do Gunicorn carregou a configuração no WSL: bind em `0.0.0.0:10000`,
um worker `gthread`, 16 threads, sem preload, `graceful_timeout=29` e access
log desativado. `py_compile` e `git diff --check` passaram. Isso não executa a
aplicação real nem ensaia o encerramento no Render.

## Candidato local e bloqueios

O candidato acrescenta `central_wsgi.py` e `gunicorn.conf.py`, para iniciar o
runtime fora do import WSGI e limitar a topologia a um worker. A documentação
oficial do Render recomenda Gunicorn para Flask. Porém, o serviço ainda tem
`python main.py` no painel e não há `render.yaml`/`Procfile` no checkout; só
publicar o SHA não troca o comando de inicialização. Seria necessária uma
alteração manual do start command no Dashboard, seguida de deploy com
interrupção devido ao disco persistente. O custo de build/uso não foi comprovado
como zero; portanto nada foi enviado ou implantado.

Prontidão contínua ainda não demonstrada: ledgers PAPER ausentes e reconciliação
de origem/identidade sem correspondência forte; falta integração real de boot,
persistência, entrada/fill/posição/stop/fechamento e observação pós-deploy.
Manter `ENABLE_REAL_TRADING=false`, `BROKER_DRY_RUN=true`, `FALCON_MODE=PAPER`;
não apagar a trava nem importar dados.

## Errata e evidência posterior do operador — 2026-11-25

Esta seção supersede as referências acima a `3502638`/`python main.py` como
estado Live atual. Após a coleta original do relatório, o operador forneceu
captura do Render mostrando deploy concluído no SHA `11bd1ec` e executou no
Shell do serviço atual uma requisição anônima local a `/livestatus`, que
retornou `401`. O 401 confirma rejeição anônima nessa rota, mas não valida uma
requisição autenticada, CORS/origem externa ou todas as rotas. O operador
também informou controles seguros e que não há posições abertas; ordens não
foram revalidadas nessa evidência.

Revalidação posterior pelo Render MCP (somente leitura) confirmou que o deploy
mais recente `dep-dc3imn67bikc73d92qf0` está `live` no commit completo
`11bd1ec855e694e996a59cf90ccc3ca1825906de`, igual ao HEAD deste checkout; a
branch é `codex/prod-wsgi-20261125`, auto-deploy está desligado, há uma
instância Standard em Oregon, mount `/data` e `healthCheckPath` vazio. Isso
fecha a divergência de SHA entre o candidato validado e o código Live neste
momento, mas não prova prontidão operacional nem saúde do executor PAPER. A
consulta de metadados não leu variáveis de ambiente ou logs.

O operador executou então uma nova captura de origem pelo comando
`paper_registry_source_capture.py --read-upstash --prompt-readonly-token`,
com token Read-Only digitado no prompt oculto. A saída sanitizada, gerada em
`2026-11-25T20:31:43Z`, reportou `ok=true`, todos os sete snapshots com
`source_status=OK`, `writes_performed=false` e status
`PREVIEW_COMPLETE_NOT_MIGRATABLE`. Foram observados 205 registros de origem,
75 registros abertos e 4.876 fechados no Registry; zero correspondências
fortes abertas ou fechadas; 2 correspondências abertas e 41 fechadas somente
para revisão; 62 candidatos ambíguos/conflitantes e 100 sem candidato no
Registry. O coletor marcou todos os registros inelegíveis para importação.
Nos modos, todos os 75 registros abertos do Registry continuam
`MODE_UNVERIFIED`; entre os fechados, apenas 19 foram confirmados PAPER pelas
duas capturas e 4.857 permanecem não verificados. A snapshot não é atômica
entre Upstash e Registry.

Logo, a captura está completa como diagnóstico (`ok=true`), mas **não** prova
reconciliação nem autoriza importar, descartar ou projetar registros. Ela
também não inicializa o executor integrado: a última leitura de health
fornecida pelo operador ainda é `PAPER_STATE_FILES_MISSING`, com contagens
`None`. Não criar ledgers vazios nem limpar a trava. A nova saída atualiza as
notas anteriores que diziam que nenhuma MGET havia sido feita; elas eram
verdadeiras antes desta captura.

Na mesma revisão do HEAD, o código de `bots/falcon.py` confirmou que as novas
falhas de persistência do sinal aceito são classificadas por uma lista
permitida (`ID_MISSING`, `IDENTITY_COLLISION`, `STATE_INVALID`, `REGISTRY_READ`,
`SYNC_UNCONFIRMED`, `RESULT_INVALID` ou `UNCLASSIFIED`) e componentes fixos;
nenhum texto arbitrário de exceção/status entra no motivo do latch. A seleção
offline `--falcon-lifecycle-projection` passou 32 testes em 31,26 s; ela valida
fixtures locais, não reconstrói a causa da trava atual. Como a trava existente
foi criada em 16/11 com motivo genérico e o snapshot atual mostra zero registros
na chave FALCON, não há evidência para atribuir retrospectivamente uma dessas
categorias, remover a trava ou considerar o fluxo reconciliado.

Reexecução adicional no mesmo HEAD: `--personal-execution-safety` passou 408
testes em 433,77 s com Python 3.11.9, `ccxt 4.5.88` e `pytest 9.1.1` do
ambiente offline preexistente. O runner bloqueia rede, subprocessos e leitura
de `.env`, além de isolar os arquivos de estado em diretório temporário. A
primeira tentativa com o Python padrão não coletou os testes por ausência de
`ccxt`; nenhuma dependência foi instalada. O resultado valida os caminhos
simulados sob fixtures, não uma execução ou integração real na BingX.

## Diagnóstico de aliases publicado e nova captura — 2026-11-25

A revisão do preview mostrou que `IDENTITY_ALIAS_CONFLICT` agrupava os casos
sem informar qual grupo fixo de identidade estava em conflito. O candidato
local agora agrega contagens por grupo para Registry aberto/fechado e por bot
na fonte Upstash; não emite valores, IDs, chaves, payloads ou texto arbitrário.
O algoritmo de matching não foi alterado: todos os registros continuam
inelegíveis, e a captura declara `writes_performed=false`. As seleções offline
`--paper-registry-source-preview` e `--paper-registry-source-capture` passaram
47 e 22 testes, respectivamente, pelo runner que bloqueia rede, subprocessos
e `.env`, com estado em diretório temporário. À época da captura das 20:31Z,
esta instrumentação ainda não estava Live.

O commit validado `455c94a56fe616a963a4ef1ce95a057c784071de` foi então publicado
manualmente; Render confirmou o deploy `dep-dc3kohvf3r2c738s87jg` como `live`.
O operador executou uma MGET de leitura, sem escrita, gerada em
`2026-11-25T21:03:58Z`. A captura novamente retornou `ok=true`, sete snapshots
`OK`, `PREVIEW_COMPLETE_NOT_MIGRATABLE`, 205 registros de origem, 75 abertos e
4.876 fechados no Registry, zero matches fortes, 2 matches abertos e 41
fechados apenas para revisão, 62 ambiguidades/conflitos e 100 sem candidato.
Todos continuam inelegíveis; `writes_performed=false`; a snapshot entre
Upstash e Registry não é atômica. Os 75 abertos seguem `MODE_UNVERIFIED`; 19
fechados têm PAPER confirmado por ambas as snapshots, o que não prova
identidade de lifecycle.

Os contadores adicionais apontaram conflitos literais de aliases no Registry
fechado para grupos `bot` (302) e `symbol` (3.477), no Registry aberto para
`bot` (1), e no snapshot TURTLE para `side` (5). Contagens de grupos podem se
sobrepor; não devem ser somadas para inferir registros únicos. Elas não
incluem valores nem identificam quais trades divergem.

Há uma limitação estática comprovada no diagnóstico: `_identity_alias_conflict_fields`
compara valores literais para `symbol` e `side`, enquanto
`trade_registry._normalize_symbol` e `_normalize_side` canonicalizam formatos.
Em exemplos sintéticos offline, `BTCUSDT` versus `BTC/USDT:USDT` e `LONG`
versus `BUY` são contados como conflito literal, mas normalizam ao mesmo valor.
Isso mostra potencial de falso positivo; sem payloads não se pode afirmar que
explique os conflitos capturados. Mesmo que alguns conflitos sejam apenas
formatação, nenhum dos 205 registros tem identidade forte, portanto isso não
autoriza matching/importação. O health PAPER não foi reconsultado após este
deploy; a última leitura fornecida pelo operador continuava
`PAPER_STATE_FILES_MISSING`. Não criar ledgers vazios, apagar latch ou importar
registros.

Como continuação local (ainda não publicada), acrescentei
`identity_alias_conflict_pair_counts`: contagens agregadas dos pares de nomes
de campos fixos que divergem, distinguindo origem `row` e `metadata`, sem
imprimir valores. O matching e a elegibilidade não mudam. No checkout baseado
em `455c94a` (antes do commit local atual), o runner offline com
rede/subprocessos/`.env` bloqueados passou
`--paper-registry-source-preview` (47) e
`--paper-registry-source-capture` (22); `py_compile` e `git diff --check`
passaram. O código/testes foram guardados no commit local
`9137100a20c9605021cb2ac69bcd71c82df8c762`, que não foi enviado ao remoto. O
deploy Live continua no `455c94a`, que só contém contagens por grupo; essa
versão mais detalhada requer revisão e eventual nova publicação e leitura,
sujeitas a custo. Não fiz novo push, deploy, MGET ou alteração de produção. As
alterações pré-existentes nos dois documentos continuam locais e não foram
staged.

## Reexecução de gates de segurança no HEAD local — 2026-11-25

No HEAD `9137100a20c9605021cb2ac69bcd71c82df8c762`, rodei novamente pelo
runner offline: `--personal-http-auth` terminou com 243 testes passados em
91,18 s; `--c3-dormant-startup` terminou com 24 testes e 3 subtestes passados
em 374,62 s. O runner bloqueia rede, subprocessos e `.env`, e isola os dados
em diretório temporário. Esses resultados dão confiança nos contratos de
autenticação e no default-off de C3 sob fixtures; não demonstram ausência de
writers externos nem execução real. Considerando a configuração Render
observada (uma instância e um worker), não há evidência concreta para ativar
coordenação C3 distribuída.

## Revalidação exata do SHA Live — 2026-11-25

O Render MCP foi consultado em modo somente leitura no workspace `Central
Quant`, serviço `central-robos-bingx`. O deploy Live permanece
`455c94a56fe616a963a4ef1ce95a057c784071de` (`dep-dc3kohvf3r2c738s87jg`),
branch `codex/prod-wsgi-20261125`, auto-deploy desligado, uma instância
Standard, disco de 4 GB em `/data`, start command
`GUNICORN_CMD_ARGS='' gunicorn -c gunicorn.conf.py central_wsgi:app`,
`healthCheckPath` vazio e allowlist pública `0.0.0.0/0`. Isso confirma a
configuração do serviço, não a autenticação válida, o health PAPER, o estado
da conta BingX ou todos os processos externos.

Criei um worktree temporário limpo no SHA Live exato e rodei, com rede,
subprocessos e `.env` bloqueados, as seleções offline:

- `--personal-lifecycle-completeness`: 892 passaram, 1 ignorado, em 799,73 s.
- `--personal-safety-no-ccxt`: 273 passaram em 878,70 s.

O worktree temporário foi removido após confirmar que estava limpo; o HEAD
principal permaneceu `9137100a20c9605021cb2ac69bcd71c82df8c762` e os dois
documentos já modificados permaneceram intactos. O commit `9137100` é filho
direto do Live `455c94a` e altera somente o diagnóstico sanitizado de pares de
aliases e seus testes; não altera os caminhos de execução. O release está
agora diretamente testado para o conjunto acima, mas não é igual ao HEAD local
com os diagnósticos extras.

Não publiquei `9137100`: o Render documenta que disco persistente impede
zero-downtime e que builds consomem minutos de pipeline, podendo exigir compra
adicional se a franquia estiver esgotada; saldo e custo incremental não foram
confirmados. Não houve novo deploy, MGET, leitura de `/data`, teste de login
em produção ou consulta atual à BingX. Não alterar controles LIVE nem criar,
limpar ou importar ledgers PAPER; a captura disponível continua
`PREVIEW_COMPLETE_NOT_MIGRATABLE`.

## Rechecagem de liveness e estado PAPER — 2026-11-25

- No mesmo HEAD local `9137100a20c9605021cb2ac69bcd71c82df8c762`, a suíte
  isolada `--personal-http-auth` passou novamente: 243 testes em 103,75 s.
  `--paper-integrated-disk-guard-no-flask` terminou com 115 passados, 13
  ignorados, 1 deselecionado e 12 subtestes em 210,90 s. O runner bloqueia
  rede, subprocessos e leitura de `.env`; estados ausentes foram testados em
  diretórios temporários, sem acesso ao `/data` de produção.
- Inspeção de código confirma que `read_paper_positions_state()` retorna
  `PAPER_STATE_FILES_MISSING` (não uma lista vazia), health/lifecycle/outcome
  não criam os arquivos ausentes, e Falcon trata o latch persistente como
  bloqueio após reinício. Não há procedimento de limpeza/reset do latch no
  código auditado. Isso não fornece evidência para inicializar ledgers vazios.
- O Render MCP continua reportando `healthCheckPath` vazio para o serviço
  público com uma instância e disco persistente. A rota `/healthz` é GET
  mínimo, dá 503 enquanto o runtime não está pronto ou durante drain, e é a
  única exceção pública estreita ao Basic Auth; query, POST e origem cruzada
  continuam bloqueados. Os 243 testes cobrem a exceção e as rotas protegidas.
  Aplicar o health check não foi autorizado nesta etapa: pode exigir deploy,
  breve interrupção e consumo de minutos de pipeline cujo saldo/custo não foi
  confirmado.
- A decisão C3 permanece dormente: a topologia observada é uma instância e
  um worker; não há evidência concreta de segundo writer. Testes locais não
  excluem sessões Shell ou escritores externos. A captura PAPER compartilhada
  continua sem identidade forte e não atômica; nenhum import, reset ou escrita
  de `/data` foi realizado.
- Reexecutei `--paper-integrated-disk-guard-no-flask` em Ubuntu WSL 2 com
  Python 3.14.4 e `python3 -I`: 128 passaram, 1 foi deselecionado e 12
  subtestes passaram em 29,81 s. Diferentemente da execução Windows, os casos
  POSIX de `dir_fd`/`O_NOFOLLOW` foram executados, incluindo symlink no root,
  escape por diretório aninhado/relativo e substituição atômica sem seguir um
  alvo symlink. O runner mantém rede, subprocessos e `.env` bloqueados; teste
  sintético, não prova o filesystem de produção.
- No mesmo ambiente e HEAD, `--c3-dormant-startup` passou 24 testes e 3
  subtestes em 44,55 s. Isso valida o default-off e os cenários cobertos de
  composição/startup; não exclui writers externos nem autoriza ativar C3.
- Uma busca pelos nomes conhecidos dos sidecars integrados encontrou os
  acessos em `paper_executor_integrated.py`, `paper_lifecycle.py` e
  `outcome_evaluator.py`, com wrappers de `paper_state_storage`; `main.py`
  acessa o log de lifecycle por `read_paper_lifecycle_log()`. Isso não é uma
  enumeração AST exaustiva de todo I/O arbitrário. `--paper-main-storage-guard` passou 9
  testes em 173,40 s no runner offline Windows. Uma tentativa WSL da mesma
  seleção deu 8 passados e 1 falha ambiental porque Flask não está instalado
  naquela distro; a falha não foi ocultada nem tratada como sucesso. A seleção
  Windows limpa a dúvida da cobertura do guard em fixtures, não prova
  ausência de qualquer writer externo ou módulo dinâmico em produção.
- No mesmo HEAD, os gates `--registry-writers` e `--registry-lock-audit`
  passaram sob WSL/runner isolado: 73 testes em 16,85 s; e 1 teste passou,
  com 72 fora do filtro, em 8,86 s. A inspeção mede as superfícies de escrita
  versionadas e a exigência de lock compartilhado nas chamadas diretas; não
  conta escritores de Shell, processos externos ou código dinâmico no serviço.
- `--trading-mode-defaults` passou 9 testes em 9,77 s no mesmo runner WSL
  isolado. Isso confirma defaults fail-closed no código/fixtures deste HEAD;
  não comprova os valores atuais das variáveis do serviço Render.

## Escopo da suíte de ciclo operacional — 2026-11-25

A seleção `--personal-lifecycle-completeness` do runner reúne 13 módulos
offline: `test_broker_entry_fill_stop_sizing_v1.py` e
`test_broker_managed_entry_cancel_v1.py` cobrem contrato de entrada/fill,
sizing e cancelamento; os módulos `test_*positions_read_fail_closed*` cobrem
leituras de posição; `test_falcon_initial_stop_failure_containment_v1.py`,
`test_falcon_disaster_stop_failure_forensics_v1.py` e
`test_falcon_terminal_disaster_stop_emergency_recovery_v1.py` cobrem falhas e
recuperação de proteção; os módulos de `close`, `manual_close` e
`*_reconciliation*` cobrem fechamento e reconciliação. No HEAD exato local,
essa seleção já havia terminado com 892 passados e 1 ignorado. O runner
bloqueia rede, subprocessos e `.env`: os cenários usam fixtures/autoridades
sintéticas. Não foram enviados ordens, criadas posições em exchange, testados
fills reais, stops no broker ou disaster stop na conta BingX. Essas etapas não
estão demonstradas como produção e não serão executadas com LIVE desligado.

## Revalidação adicional do HEAD local — 2026-11-25

- A aparente divergência dos SHAs é cronológica: `11bd1ec855e694e996a59cf90ccc3ca1825906de` (14:49 -03) é ancestral de `455c94a56fe616a963a4ef1ce95a057c784071de` (17:57 -03). A captura do Dashboard mostrando `11bd1ec` como Live foi feita às 15:39 -03, antes do commit `455c94a`. A última consulta Render somente leitura registrada neste relatório apontou `455c94a` como Live; isso é o último estado observado, não uma nova confirmação em tempo real. O ref local `origin/codex/prod-wsgi-20261125` aponta para `455c94a`; o HEAD `9137100a20c9605021cb2ac69bcd71c82df8c762` está um commit à frente e modifica apenas diagnósticos sanitizados do capture/preview e testes. Não houve push ou deploy de `9137100`.
- No HEAD `9137100`, com o runner offline bloqueando rede, subprocessos e `.env`, foram repetidos: `--personal-lifecycle-completeness` 892 passou/1 ignorado; `--personal-execution-safety` 408 passou; `--personal-http-auth` 243 passou; `--paper-integrated-disk-guard` 129 passou/12 subtestes; `--paper-main-storage-guard` 9 passou. CCXT 4.5.88 veio de uma cópia temporária local já existente, Flask/pytest de pacotes locais; nada foi instalado ou baixado.
- Esses resultados são fixtures e persistência temporária, não execução na BingX. A evidência PAPER recebida continua `PREVIEW_COMPLETE_NOT_MIGRATABLE`, com zero correspondências fortes; não importar, apagar, inicializar ou limpar ledgers/latch. `PAPER_STATE_FILES_MISSING` e a reconciliação sem identidade comprovada continuam bloqueios de prontidão.

## Consulta Render somente leitura após confirmação do workspace — 2026-11-25

Após o operador confirmar o workspace `Central Quant` (`tea-d8gnnuojo6nc73ep3lg0`), a listagem somente leitura confirmou o serviço `central-robos-bingx`, branch `codex/prod-wsgi-20261125`, auto-deploy desligado, uma instância Standard e disco persistente de 4 GB montado em `/data`. O start command observado é `GUNICORN_CMD_ARGS='' gunicorn -c gunicorn.conf.py central_wsgi:app`; `healthCheckPath` permanece vazio e a allowlist de IP inclui `0.0.0.0/0`, portanto as rotas públicas dependem da autenticação da aplicação. A lista de deploys confirmou `455c94a56fe616a963a4ef1ce95a057c784071de` (`dep-dc3kohvf3r2c738s87jg`) como `live`, iniciado em `2026-11-25T20:59:51Z` e concluído em `21:00:52Z`. O commit local `9137100a20c9605021cb2ac69bcd71c82df8c762` segue à frente do remoto e não foi enviado nem implantado.

Essa consulta não leu logs, variáveis, segredos, arquivos do disco, saúde PAPER ou estado BingX. Não houve alteração no Render, MGET, push ou deploy; a leitura de metadados não estabelece custo zero de uma futura publicação. O serviço continua sem health check HTTP configurado. A autenticação e o comando Gunicorn têm cobertura offline no HEAD local, mas essa consulta não substitui smoke test autenticado nem confirma o processo/rotas em execução. A reconciliação PAPER continua bloqueada por ausência de identidade forte, estado PAPER ausente e latch de persistência; não criar ledgers vazios, apagar latch nem importar registros.

A revalidação estática do release confirmou que `gunicorn.conf.py` fixa `workers=1`, `preload_app=False` e 16 threads `gthread`, rejeitando worker/preload divergente no startup. O runtime começa no hook pós-worker; o Registry continua sujeito a concorrência entre threads, coberta pelo `RLock` local. `CENTRAL_RUNTIME_READY` só é liberado depois que todos os bots habilitados iniciam. O binding de manutenção C3 começa `None`; se fosse instalado, `start_central_runtime_once()` recusaria iniciar bots. `git diff 455c94a..9137100 -- main.py gunicorn.conf.py central_wsgi.py trade_registry.py registry_v2_core.py registry_v2_paper_runtime_adapter.py` ficou vazio, então o código de execução desses caminhos coincide com o Live observado; o delta local são diagnósticos sanitizados e seus testes. Isso reforça manter C3 dormente para a topologia observada, sem excluir escritores externos/Shell não inventariados. A rota `/healthz` é uma sonda de readiness de runtime (503 antes do runtime pronto e durante drain), não verifica os ledgers PAPER nem readiness de trading.

Nesta continuação, `py -3.14 -I tests/run_falcon_pilot_minimal_offline.py --personal-http-auth` terminou no HEAD `9137100a20c9605021cb2ac69bcd71c82df8c762` com **243 testes passados em 113,32 s**. O runner isola o processo e bloqueia rede, subprocessos e `.env`; foram usadas apenas fixtures locais. Isso atualiza a evidência local da autenticação, mas não testa credenciais válidas, tráfego externo nem o comportamento da release Live.

## Reauditoria do inventário C3 de writers — 2026-11-25

O contrato C3 de reparo fechado declara 19 superfícies candidatas — 8 em `trade_registry.py` e 11 em `main.py`. Isso confirma a quantidade declarada no contrato, mas não prova que seja o inventário exaustivo dos mutadores atuais nem que as âncoras de fonte estejam sincronizadas. O teste focal `tests/test_c3_main_writer_source_anchors_offline.py`, executado isoladamente com sockets, subprocessos e `.env` bloqueados, terminou com 3 falhas: os escopos C3 dos 11 wrappers de `main.py` não são verificados e o harness interrompe em `FUNCTION_LINE_SHIFT_DENIED`; o controle negativo de drift também é mascarado pelo mesmo erro de linha. No runtime, C3 continua dormente e esses wrappers não precisam estar envolvidos por C3.

Uma enumeração AST dos usos dos métodos mutáveis V1 em `main.py` encontrou 14 funções chamadoras; pelo menos quatro caminhos alcançáveis não aparecem entre as 11 entradas C3 de `main.py`: `trade_registry_sync_v1_register_candidate` (usado por rotas/sync), `sync_trade_registry_from_open_positions` (usado por rotas), `trade_registry_reset_route` e `_fcor_v1_build_payload` (usado por rotas). A enumeração não prova execução em produção, mas impede certificar os 19 como cobertura completa sem análise de alcance e decisão explícita sobre cada caminho. A seleção `--registry-writers` (73 testes), `--registry-lock-audit` (1 passou/72 fora da seleção) e `--c3-dormant-startup` (24 testes e 3 subtestes) passaram no HEAD atual; elas validam os writers/locks cobertos e o default-off, não a completude do inventário C3. A suíte auxiliar de source-anchor mais ampla também não conseguiu construir seu preflight sintético (`synthetic preflight projection unexpectedly failed`), então seus demais resultados não são evidência válida de conformidade.

Decisão mantida: não ativar nem ampliar C3. Antes de qualquer reconsideração, atualizar/revalidar âncoras e definir se os quatro caminhos adicionais estão cobertos ou demonstravelmente fora do escopo. A alternativa atual continua sendo um processo Gunicorn, um worker, threads concorrentes e `RLock`; não há evidência concreta de segundo processo ou serviço escritor, e a lista local de métodos/callers não mede processos auxiliares externos.

### Alcance dos caminhos de escrita Registry — 2026-11-25

Inspeção adicional dos chamadores confirmou que os caminhos extras não são apenas nomes definidos sem uso: `trade_registry_sync_route` expõe GET de prévia e POST com confirmação para `sync_trade_registry_from_open_positions`; `autosync_trade_registry` usa `commit=True` no caminho de abertura; e rotas de reparo pós-execução também chamam `trade_registry_sync_v1_register_candidate(..., commit=True)`. `trade_registry_reset_route` é uma rota POST destrutiva com frase explícita de confirmação. `_fcor_v1_build_payload` é servido por GET/POST: a mutação só ocorre com POST, `commit=true` e acknowledgement específico, sob `_FCOR_V1_LOCK`. Isso demonstra múltiplas superfícies alcançáveis, mas não prova que sejam simultaneamente acionadas na produção.

O módulo `trade_registry.py` protege seus mutadores centrais por `_lock` (`threading.RLock`); muitos escritores de `main.py` resolvem e usam esse mesmo lock, enquanto alguns caminhos delegam a função que o adquire. O modo de um worker com threads torna essa coordenação local relevante; ela não coordena processos externos nem atesta que cada acesso direto a `save_registry` seja corretamente protegido. `set_trade_registry_mode` está definido/exportado em `trade_registry.py`, mas a busca local não encontrou chamadores em `main.py` ou `bots`. Portanto, os 19 C3 permanecem uma lista declarativa incompleta para alegar cobertura universal; não existe base para ativar C3 distribuído no caminho crítico. A captura de 2026-11-25 segue `PREVIEW_COMPLETE_NOT_MIGRATABLE`, sem correspondências fortes e sem escrita; continua proibido importar ou inicializar ledgers a partir dela.

Revalidação no HEAD `9137100a20c9605021cb2ac69bcd71c82df8c762`: enumeração AST encontrou 9 chamadas diretas a `save_registry` em `trade_registry.py` e 10 em `main.py`, correspondendo ao escopo estrutural verificado pelo teste de lock. `py -3.14 -I tests/run_falcon_pilot_minimal_offline.py --registry-lock-audit` passou (1 teste; 72 fora do filtro) em 64,26 s, e `--registry-writers` passou 73 testes em 182,34 s. Esses gates verificam chamadas diretas e cenários sintéticos cobertos; não provam que a lista declarativa C3 cubra todos os mutadores indiretos/rotas, que writers externos não existam ou que haja coordenação distribuída em produção.

Na continuação, `py -3.14 -I tests/run_falcon_pilot_minimal_offline.py --personal-http-auth` passou novamente: 243 testes em 106,57 s no mesmo HEAD. A seleção inclui os casos sintéticos de `/healthz` mínimo, query/POST/origem cruzada, runtime ainda não pronto e bloqueio global de rotas. Não houve smoke test HTTP na instância Render nem uso de credenciais; o health check do serviço continua sem configuração.

Revalidei o delta completo entre o commit Live `455c94a56fe616a963a4ef1ce95a057c784071de` e HEAD `9137100a20c9605021cb2ac69bcd71c82df8c762`: o HEAD é descendente do Live e muda somente `paper_registry_source_capture.py`, `paper_registry_source_preview.py` e os dois respectivos módulos de teste. Os arquivos de runtime (`main.py`, `broker.py`, `bots/falcon.py`, storage e Registry) não diferem. No runner offline isolado, `--paper-registry-source-preview` passou 47 testes em 0,41 s e `--paper-registry-source-capture` passou 22 em 0,52 s. São validações sintéticas dos diagnósticos; não consultaram Upstash nem tornam a captura real migrável.

## Health check HTTP e ciclo sem CCXT — 2026-11-26

Após confirmação do operador de que não havia operações abertas, a configuração do serviço Render `central-robos-bingx` (`srv-d8rtuv9o3t8c73ehav5g`, workspace Central Quant) foi alterada manualmente no Dashboard para `healthCheckPath=/healthz`. Como `autoDeploy=off`, a alteração não iniciou deploy; foi disparado deploy manual sem limpar cache. O deploy `dep-dc3odps9v7es73cpao00`, source commit `455c94a56fe616a963a4ef1ce95a057c784071de`, terminou `live` em `2026-11-26T01:11:36Z`. Uma leitura posterior confirmou o serviço ainda com uma instância, disco persistente `/data` de 4 GB e `healthCheckPath=/healthz`. Nenhuma alteração no código, ambiente, `/data`, Upstash, Registry ou controles de trading foi feita. O endpoint é readiness do runtime; não atesta ledgers PAPER nem prontidão de trading. Rollback da configuração: remover o health check pelo Dashboard; o release de código permanece no mesmo commit.

No checkout, `py -3.14 -I tests/run_falcon_pilot_minimal_offline.py --entry-fill-stop` não coletou testes: os dois módulos selecionados falharam na importação porque `ccxt` não está instalado nesse Python. `py -3.14 -m pip cache list ccxt` não encontrou wheels locais; nenhum pacote foi baixado ou instalado. Como evidência separada, `--personal-lifecycle-no-ccxt` terminou com 766 passados e 1 ignorado em 1128,15 s. Esse subconjunto não inclui a sequência focal de broker que depende de CCXT; portanto, não substitui a falha de coleta nem comprova execução contra a BingX real.

Reexecutei os testes usando a virtualenv local preexistente `.venv-centralquant-ccxt-20261023` (Python 3.14.5), sem instalação/transferência. No mesmo HEAD `9137100a20c9605021cb2ac69bcd71c82df8c762`, `--entry-fill-stop` passou 37 testes em 7,53 s e `--personal-lifecycle-completeness` passou 892 testes, com 1 ignorado, em 1556,65 s. O runner isolado aplica bloqueios offline; estes são testes de contrato/fixtures com dependência instalada, não ordens, fills, posições ou stops na BingX. A tentativa anterior com o Python base continua sendo uma falha de coleta ambiental e foi preservada no registro.

Na reexecução mais recente de `--personal-execution-safety`, o venv tinha `ccxt 4.5.89`, enquanto `requirements.txt` fixa `4.5.88`: 406 testes passaram e 2 testes de readback falharam somente na asserção de versão. Sem instalar nada, repeti o arquivo afetado com a cópia local preexistente de `ccxt 4.5.88`; os 2 testes passaram em 2,82 s. Em seguida, repeti toda a seleção ampla usando a mesma cópia pinada e o runner offline, que bloqueia rede, subprocessos e `.env`: **408 testes passaram em 1872,21 s (31m12s)**. A primeira tentativa continua registrada como discrepância ambiental; a execução completa pinada é a evidência válida mais recente. Nenhuma mudança de código/runtime foi feita.

Revisão estática adicional de exposição HTTP: `central_wsgi.py` exporta exclusivamente `main.app`; o `before_request` global de `main.py` exige Basic Auth para todas as rotas e caminhos desconhecidos, falhando fechado se credenciais não estiverem configuradas. A única exceção é `GET /healthz` sem query, após as verificações de origem/site; ela retorna apenas status mínimo de runtime. Os sete objetos Flask dos bots não são registrados/montados no WSGI Central e seus `app.run()` pertencem ao modo standalone. Esta conclusão é do código local, não uma enumeração do tráfego nem um smoke test de cada rota no Render. A saída anterior de `401` sem autenticação em `/livestatus` cobre só aquela rota; não foram lidos ou exibidos valores de credenciais.

Reexecutei `py -3.14 -I tests/run_falcon_pilot_minimal_offline.py --personal-http-auth` no HEAD `9137100a20c9605021cb2ac69bcd71c82df8c762`: **243 passaram em 79,04 s**. O runner manteve rede, subprocessos e leitura de `.env` bloqueados. Isso reforça os contratos locais de autenticação, origem, métodos mutáveis e readiness; não é um smoke test autenticado no Render.

Nova revalidação no mesmo HEAD do guard de estado PAPER: no Windows, `--paper-integrated-disk-guard-no-flask` passou **115**, teve **13 ignorados**, **1 deselecionado** e **12 subtestes** em 172,64 s; no WSL/Linux, a mesma seleção passou **128**, com **1 deselecionado** e **12 subtestes** em 33,54 s. O WSL executou os casos POSIX de descriptor, symlink e replace atômico. Ambos usaram runner offline com dados temporários; nenhum leu nem modificou `/data` de produção. Isso valida os cenários cobertos, não prova que o disco Render esteja íntegro ou que os ledgers estejam presentes.

## Reauditoria do I/O de metadados de Executive Policy Learning — 2026-11-26

No checkout `codex/prod-wsgi-20261125`, HEAD `9137100a20c9605021cb2ac69bcd71c82df8c762`, a busca estática encontrou chamadas `.exists()` e `.stat()` em `executive_policy_learning.py` antes/durante leituras JSONL PAPER. Embora o conteúdo já usasse `open_paper_*`, essas consultas de metadados não eram descriptor-anchored e podiam seguir symlinks; o resolver de Decision Log também avaliava candidatos em `BASE_DIR/data` no Render. A alteração local não reescrita encaminha metadata para `paper_file_exists`/`paper_file_stat`, propaga falhas de guarda em vez de convertê-las em EOF vazio e, no Render, ignora candidatos fora de `DATA_DIR`. Um erro de armazenamento na leitura da timeline devolve `TIMELINE_STORAGE_UNAVAILABLE` sem escrever estado/estatísticas nem avançar o cursor.

Depois da alteração: busca `rg` sem ocorrências de `.exists()`, `.stat()`, `.lstat()`, `.is_file()` ou `.is_dir()` em `executive_policy_learning.py`; varredura AST dos cinco módulos de estado/execução não encontrou chamadas diretas de `open`, `read_text`, `write_text`, `read_bytes`, `write_bytes` ou metadata path APIs. Os `.replace()` listados pelo AST eram normalizações de strings; `paper_executor_integrated.py` usa `shutil.disk_usage(DATA_DIR)` somente para obter espaço livre após validar o mount, sem ler conteúdo de estado. `py_compile` e `git diff --check` passaram (o Git emitiu aviso de conversão LF/CRLF no relatório). Testes focados offline com conexões socket bloqueadas: Windows, 32 passaram/1 ignorado; WSL/Linux, 33 passaram. O WSL inclui symlink real escapando do diretório PAPER temporário e verifica preservação byte a byte de cursor e estatísticas, além do filtro de fontes efêmeras. Uma rodada WSL maior teve 61 aprovados e 1 teste ambiental falhou ao importar `main.py` por ausência de Flask; sem instalar dependências, a seleção foi repetida excluindo somente esse teste e terminou 61 aprovados/1 deselecionado. Após o commit local, `py -3.14 -I tests/run_falcon_pilot_minimal_offline.py --personal-http-auth` passou 243 testes em 71,54 s. Não houve rede, leitura de segredos, uso de dados de produção, `/data`, push ou deploy.

O achado foi corrigido e commitado localmente em `1155827` (após HEAD `9137100`), mas não foi enviado ao GitHub nem ao Render. Os documentos já modificados ficaram fora do commit e preservados. O serviço Render e o código Live não foram alterados por esta continuação. `GET /healthz` é uma sonda de readiness do runtime, não dispara deploy; com `autoDeploy=off`, publicar exige ação manual separada em Deploys. C3 continua dormente. Permanecem pendentes a confirmação operacional atual da release, a reconciliação de identidade/origem PAPER e os ledgers integrados ausentes; esta correção de metadata não inicializa nem reconcilia estado.

## Revalidação do Render e dos gates PAPER — 2026-11-26

Consulta somente leitura ao workspace `Central Quant` (`tea-d8gnnuojo6nc73ep3lg0`) confirmou o serviço `central-robos-bingx` (`srv-d8rtuv9o3t8c73ehav5g`), branch `codex/prod-wsgi-20261125`, `autoDeploy=no`, `healthCheckPath=/healthz`, uma instância Standard, disco persistente de 4 GB em `/data` e start command `GUNICORN_CMD_ARGS='' gunicorn -c gunicorn.conf.py central_wsgi:app`. O deploy mais recente segue `live` em `455c94a56fe616a963a4ef1ce95a057c784071de` (`dep-dc3odps9v7es73cpao00`). Portanto, `/healthz` é a sonda HTTP configurada; ela não inicia deploy. Com auto-deploy desligado, a publicação continua manual.

No checkout local, HEAD é `11558273449a8d1c5beae67b106f69c6475d9f04`, descendente do SHA remoto/Live `455c94a56fe616a963a4ef1ce95a057c784071de`; `git ls-remote` confirmou que o branch remoto ainda aponta para `455c94a`. O HEAD local está dois commits à frente e não foi enviado. O worktree mantém dois documentos previamente modificados e preservados. Não houve push, deploy, alteração no Render, leitura de variáveis/segredos, consulta à BingX ou acesso ao `/data` de produção.

Após o commit `1155827`, o gate offline `--paper-integrated-disk-guard` passou com 116 testes, 13 ignorados e 12 subtestes; `--learning-cursor-guard` passou com 16 testes e 1 ignorado. Ambos usam o runner isolado com persistência temporária. Isso valida os cenários sintéticos cobertos, não a release Live nem a disponibilidade real dos ledgers. A última evidência operacional compartilhada ainda indicava `PAPER_STATE_FILES_MISSING`, e a última captura Upstash/Registry era `PREVIEW_COMPLETE_NOT_MIGRATABLE`, sem matches fortes; não criar arquivos vazios, limpar latch ou importar registros.

No mesmo HEAD local, as seleções offline `--paper-registry-source-preview` e `--paper-registry-source-capture` passaram com 47 e 22 testes, respectivamente. `--registry-writers` passou 73; `--registry-lock-audit` passou 1 teste e deixou 72 fora do filtro; `--c3-dormant-startup` passou 24 testes e 3 subtestes. Os resultados confirmam os contratos sintéticos selecionados, não inventariam processos externos nem demonstram necessidade de lock distribuído. Reinspeção de `gunicorn.conf.py`, `trade_registry.py` e `main.py` confirma um worker Gunicorn, 16 threads, `threading.RLock` no Registry e binding C3 de startup `None` por padrão. Não surgiu evidência concreta que justifique ativar C3; permanecem limitações sobre Shell ou writers externos não inventariados.

Na continuação, uma varredura de referências aos sidecars PAPER em fontes Python encontrou os caminhos concentrados em `paper_executor_integrated.py`, `paper_lifecycle.py`, `outcome_evaluator.py`, `execution_pipeline_status.py`, `executive_policy_learning.py` e helpers de `main.py`. Os leitores do status usam `paper_file_exists`/`read_paper_text`; helpers genéricos em `main.py` classificam caminhos `/data` e encaminham para wrappers guardados, rejeitando caminhos locais de fallback quando `RENDER=true`. A inspeção de `ensure_paper_data_dir()` confirmou que a criação só ocorre depois de `paper_data_mount_verified`; no caminho POSIX sob `/data`, usa descritores ancorados e exige o mount. O gate offline `--paper-main-storage-guard` passou 9 testes em 151 s no HEAD `1155827`. Isso cobre os casos selecionados, mas não é prova AST/dinâmica exaustiva de todos os módulos ou writers externos. A automação da sessão Render falhou antes de abrir a janela; nenhuma leitura de health PAPER atual foi feita nesta continuação.

## Esclarecimento de `/healthz` e revalidação HTTP — 2026-11-26 04:13 UTC

Após o operador configurar `/healthz` e observar que nenhum deploy começou, reconsultei somente metadados do serviço e deploys pelo Render MCP. `healthCheckPath=/healthz` está configurado, mas `autoDeploy=no/off`; o último deploy segue `live` no commit `455c94a56fe616a963a4ef1ce95a057c784071de`. Portanto, a rota de health check serve para sondar a instância e não dispara deploy; com auto-deploy desligado, novo código exige gatilho manual. O start command atual continua `GUNICORN_CMD_ARGS='' gunicorn -c gunicorn.conf.py central_wsgi:app`. Nenhuma configuração, deploy, variável, dado de `/data`, Upstash ou estado de trading foi alterado nesta revalidação.

As referências oficiais atuais do Render confirmam a distinção: health checks fazem GET periódicos e afetam readiness/roteamento/restart; deploys automáticos dependem da opção de auto-deploy, e com `Off` usa-se deploy manual. No HEAD local `11558273449a8d1c5beae67b106f69c6475d9f04`, `py -3.14 -I tests/run_falcon_pilot_minimal_offline.py --personal-http-auth` passou **243 testes em 79,33 s**. O runner é offline; isso valida fixtures/contratos de autenticação, não login autenticado nem todas as rotas em produção.

O checkout continua dois commits à frente da branch remota/Live e mantém alterações não staged nos dois relatórios. Não fiz push nem deploy: o auto-deploy está intencionalmente desligado e o custo incremental do serviço com disco persistente não foi confirmado como zero. O health PAPER não foi consultado nesta continuação; a última evidência operacional anterior permanece `PAPER_STATE_FILES_MISSING`, sem base para criar arquivos vazios ou importar registros.

Na mesma continuação, o guard PAPER foi repetido em WSL2/Linux no HEAD `11558273449a8d1c5beae67b106f69c6475d9f04`, com `PYTHONDONTWRITEBYTECODE=1` e a seleção `--paper-integrated-disk-guard-no-flask`: **128 testes passaram**, **1 foi deselecionado** por depender de Flask ausente no WSL e **12 subtestes passaram**, em 30,73 s. O runner mantém rede, subprocessos e `.env` bloqueados e usa persistência temporária. Os casos POSIX de symlink, descritores ancorados e replace atômico foram executados; isso não valida o disco `/data` de produção nem muda a ausência dos ledgers PAPER.

Como verificação adicional, a execução padrão completa do runner `tests/run_falcon_pilot_minimal_offline.py` no mesmo HEAD terminou com código 0: **360 testes passaram, 1 foi ignorado**, em 732,50 s. A chamada incluiu `--help`, opção que o runner não trata como ajuda e que acabou executando sua seleção padrão; portanto, o resultado é da suíte padrão inteira, não de um subconjunto chamado `help`. A saída capturada não identificou o motivo do skip. O runner é offline e isolado; este resultado não comprova o release Live, integração externa nem prontidão para trading.

## Reconsulta Render read-only — 2026-11-26 04:43 UTC

Consulta de metadados do workspace `Central Quant` confirmou novamente o serviço `central-robos-bingx`, branch `codex/prod-wsgi-20261125`, `autoDeploy=no/off`, `healthCheckPath=/healthz`, start command Gunicorn, uma instância Standard e disco persistente de 4 GB em `/data`. A lista de deploys apontou `455c94a56fe616a963a4ef1ce95a057c784071de` como `live`, concluído em `2026-11-26T01:11:36Z`. O HEAD local `11558273449a8d1c5beae67b106f69c6475d9f04` segue dois commits à frente do ref local remoto; não houve push ou deploy. A allowlist de rede ainda inclui `0.0.0.0/0`, portanto a superfície pública depende da autenticação da aplicação. Esta consulta não abriu logs, variáveis, `/data`, Upstash ou conta BingX, e não alterou recursos. O estado PAPER operacional segue sem revalidação nesta chamada; a última evidência compartilhada permanece `PAPER_STATE_FILES_MISSING`.

## Gates completos de ciclo de vida e segurança — 2026-11-26

O primeiro intento de `--personal-lifecycle-completeness` no Python base 3.14 não coletou os testes: três módulos de broker falharam na importação de `ccxt` (`test_broker_entry_fill_stop_sizing_v1.py`, `test_broker_managed_entry_cancel_v1.py` e `test_real_close_reconciliation_v11.py`). Sem instalar dependências nem usar rede, localizei no workspace o interpretador offline pré-existente `ccxt-offline-20261108-01\venv\Scripts\python.exe`; ele importa CCXT `4.5.88`. Repetidos no HEAD `11558273449a8d1c5beae67b106f69c6475d9f04`, com o runner que bloqueia rede, subprocessos e leitura de `.env` e usa persistência temporária:

- `--personal-lifecycle-completeness`: **892 passaram, 1 ignorado**, código de saída 0, 596,28 s. Abrange as seleções de entrada/fill/stop, fechamento e reconciliação incluídas pelo runner.
- `--personal-execution-safety`: **408 passaram**, código de saída 0, 660,46 s. Evidência sintética dos contratos de preflight, contenção de stop, risco, fechamento e autenticação de rotas.
- Verificações complementares sem CCXT no Python base: `--personal-lifecycle-no-ccxt`, **766 passaram/1 ignorado**; `--personal-safety-no-ccxt`, **273 passaram**. São subconjuntos explicitamente parciais, não substituem os gates completos acima.

Essas aprovações são locais/sintéticas e não provam fills, posições, ordens, cancelamento de stops ou reconciliação na BingX real. O motivo do único skip no gate completo de ciclo de vida não foi exibido. Nenhum segredo, dado ou integração de produção foi acessado.

## Corrida entre preflight de risco e envio de entradas — 2026-11-26

Revisão estática do HEAD local `11558273449a8d1c5beae67b106f69c6475d9f04` encontrou um risco distinto do C3 de manutenção do Registry. `can_open_trade_route()` delega a `can_open_trade_decision()`, que sincroniza/lê o Registry e calcula limites com snapshots de posições; não reserva uma vaga de exposição até o envio do broker. A proteção final `broker_real_pilot_guard_v1_validate()` também consulta `_broker_rpg_v1_open_positions_count()`, que usa `get_positions()` e conta posições não nulas; esse snapshot não enumera ordens de entrada ainda não preenchidas.

Há concorrência possível no desenho observado: Gunicorn está limitado a um worker, mas usa 16 threads, e os bots iniciam workers em threads daemon. O `RLock` do Registry protege mutações desse Registry, não torna atômica a sequência preflight → autorização → envio. A reserva persistente `account_client_order_id` torna uma tentativa factual única e bloqueia replay da mesma identidade; ela não reserva capacidade de risco para identidades/lifecycles distintos. O teste existente de concorrência em `test_execution_engine_predator_account_identity_v1.py` cobre duas chamadas com a mesma identidade, não duas entradas distintas disputando a última vaga de exposição nem ordens pendentes contadas no limite.

Conclusão e limite: a corrida é uma possibilidade demonstrada pela separação dos snapshots e da reserva, não um incidente observado nem uma reprodução de envio real. Antes de qualquer futura habilitação LIVE, falta um controle de admissão por conta que reserve atomicamente capacidade antes do broker e mantenha a reserva até estado terminal/reconciliação; testes offline devem cobrir identidades diferentes simultâneas, ordem não preenchida, resultado de envio desconhecido e liberação/reconciliação. Isso é controle do caminho de ordens, não evidência de necessidade do coordenador C3 de manutenção histórica do Registry. C3 continua preservado e dormente; LIVE permanece desligado. Nenhuma ordem, chamada a exchange, alteração de configuração ou escrita de produção foi realizada nesta auditoria.

## Confirmação operacional do operador — 2026-11-26

O operador informou que não há operações abertas e que a interrupção/reinicialização seria segura. Isso é uma declaração do operador, não uma consulta independente à BingX. O serviço continua com auto-deploy desligado segundo a última consulta Render registrada acima: `GET /healthz` verifica readiness e não dispara deploy. O HEAD local `11558273449a8d1c5beae67b106f69c6475d9f04` permanece dois commits à frente da branch remota; nenhum push/deploy foi feito. O custo incremental de pipeline/minutos do Render não foi confirmado como zero, então a publicação deste SHA permanece pendente de decisão financeira. Esta confirmação não altera os bloqueios PAPER nem autoriza execução LIVE.

## Revarredura estática de I/O dos sidecars PAPER — 2026-11-26

No mesmo HEAD, `rg` em todos os fontes Python (excluindo testes e ambientes virtuais) encontrou os quatro nomes exatos de arquivos PAPER somente em `paper_executor_integrated.py`, `paper_lifecycle.py`, `outcome_evaluator.py`, `execution_pipeline_status.py`, `executive_policy_learning.py` e `main.py`. Uma varredura AST dos cinco módulos de estado não encontrou chamadas diretas a APIs de caminho (`open`, `Path.read_text/write_text`, `exists`, `stat`, `replace`, etc.) que escapassem dos helpers. Os `f.read`/`f.write` restantes em `executive_policy_learning.py` usam handles de `open_paper_text/binary`; os demais resultados `.replace()` são normalizações de strings. Em `main.py`, as operações relacionadas a Paper/Registry identificadas pela busca usam wrappers guardados (`_open_guarded_*`, `_read_guarded_*`, `_write_guarded_*`, `_append_guarded_*`).

Limite: o rastreio por nomes de arquivo e AST é estático e não prova ausência de caminhos dinâmicos/reflexivos, I/O em extensões ou escritores fora do repositório. Os testes POSIX/Windows do guard citados acima verificam fixtures temporárias, não a árvore `/data` de produção; nenhuma leitura ou escrita de produção ocorreu nesta revarredura.

## Limite do preflight de broker persistido — 2026-11-26

Revalidação estática do HEAD `11558273449a8d1c5beae67b106f69c6475d9f04`: `_falcon_engine_pending_ledger_preflight()` é chamado por `falcon_execute_live_via_canonical_engine()` antes de delegar ao Execution Engine. O leitor `find_falcon_pending_broker_states()` falha fechado se o mount/ledger estiver ausente ou inválido e projeta somente estados Falcon `ENGINE_BROKER_CALL_PENDING` e `ENGINE_BROKER_SEND_OUTCOME_UNKNOWN`. Isso é uma proteção útil contra reiniciar e repetir uma tentativa Falcon já registrada como pendente/desconhecida.

O preflight, porém, é uma leitura seguida de decisão, não uma reserva serializada: seu `_SEEN_LOCK` protege a leitura do ledger durante a leitura, mas é liberado antes da delegação/envio; duas identidades diferentes podem observar “clear” antes de qualquer uma gravar sua própria tentativa. O registro de estado do Execution Engine e `reserve_account_client_order_attempt()` vinculam uma tentativa à sua identidade/idempotency key e impedem replay do mesmo intento; não reservam atomicamente a última vaga de exposição entre identidades distintas. O scanner também filtra apenas registros identificados como Falcon e os dois estados citados; não representa capacidade de conta compartilhada com outros bots nem ordens aceitas aguardando integração Registry/posição. O caminho direto do Predator usa a reserva por tentativa e `place_market_order()`, mas não chama esse preflight Falcon.

Assim, o preflight atual reduz replay de uma tentativa Falcon conhecida após restart, mas não fecha a corrida de admissão por conta. Isso reforça o bloqueio já registrado para LIVE: antes de qualquer habilitação, um único mecanismo de admissão precisa reservar capacidade por conta de forma atômica antes do broker e reter a reserva até reconciliação terminal, cobrindo todos os senders de entrada. Faltam testes offline com identidades diferentes concorrentes, ordem aceita ainda não refletida como posição, resultado desconhecido/restart e liberação apenas após reconciliação. Esta constatação não demonstra necessidade de C3 para writers do Registry; é um problema separado de admissão de ordens. Nenhum envio ou teste de broker real foi realizado.

Reexecutei `py -3.14 -I tests/run_falcon_pilot_minimal_offline.py --c3-dormant-startup` no mesmo HEAD: **24 testes passaram e 3 subtestes passaram**, em 377,95 s. Isso valida as fixtures de startup/dormência cobertas pelo filtro; não prova que não haja escritores concorrentes externos em produção, nem substitui a auditoria dos caminhos de ordem ou autoriza ativar C3.

Inventário estático complementar no mesmo checkout: a busca de chamadas executáveis `create_order()` encontrou uma única fronteira raw em `_create_order_with_reserved_attempt()` (`broker.py`). Os envios de entrada encontrados chegam a `broker.place_market_order()` pelo Execution Engine (`execution_engine.py`) ou pelo caminho direto de Predator (`bots/predator.py`); ambos convergem na chamada marcada com `expected_reservation_roles={ROLE_ENTRY}`. As demais chamadas ao boundary raw encontradas usam papéis de stop inicial/substituição ou fechamento. Isso delimita um ponto comum tecnicamente promissor para um futuro gate de capacidade de conta, preservando `reduce-only`/stops, mas não prova cobertura dinâmica completa nem implementa a reserva. A implementação exigiria lease persistente atômico e reconciliação de ordem/posição para todos os envios de entrada; não deve ser substituída por um `threading.Lock` local.

O módulo existente `redis_bandwidth.py` já fornece `redis_set_if_absent()` (SET NX atômico) e `redis_compare_and_delete()` (EVAL compare-and-delete sem fallback local). Portanto, há primitiva para ownership de um lock de conta sem depender de C3 ou de um lock só de processo. A função SET NX atual não dá TTL; um processo encerrado durante a seção crítica deixaria a conta bloqueada até uma recuperação explícita após reconciliação, o que é seguro contra duplicidade mas tem impacto de disponibilidade e demanda um fluxo de recuperação testado. Não existe ainda protocolo de lease/capacidade usando essas funções, nem evidência de orçamento Upstash para chamadas adicionais; não implementei nem invoquei essas operações.

## Revalidação da cobertura dos writers do Registry — 2026-11-26

No HEAD `11558273449a8d1c5beae67b106f69c6475d9f04`, sem diferenças de código do Registry em relação ao teste anterior, rodei usando a virtualenv local offline `ccxt-offline-20261108-01`: `--registry-lock-audit` passou **1 teste (72 deselecionados)** em 53,24 s; `--registry-writers` passou **73 testes** em 118,72 s. O primeiro filtro confirma estruturalmente que cada chamada direta coberta a `save_registry` está sob o lock compartilhado; a seleção ampla valida os contratos de writer/RMW exercitados pelos fixtures.

Conclusão limitada para C3: os testes apoiam coordenação dentro do código local, mas não identificam todos os escritores indiretos/dinâmicos, processos externos, nem a topologia concorrente atual do Render. A leitura estática e a evidência histórica de uma instância/um worker não provam ausência de writer fora do escopo. Assim, a necessidade de C3 distribuído continua **não comprovada**: ele fica preservado e dormente, e não se afirma que os testes provem ausência universal de concorrência. Nenhuma escrita de Registry ou chamada externa ocorreu.

## Revalidação read-only do serviço Render — 2026-11-26

No workspace confirmado `Central Quant` (`tea-d8gnnuojo6nc73ep3lg0`), a leitura MCP do serviço `central-robos-bingx` (`srv-d8rtuv9o3t8c73ehav5g`) retornou: branch `codex/prod-wsgi-20261125`; `autoDeploy=no`; web service Standard em Oregon; uma instância; disco persistente `/data` de 4 GB; health check `/healthz`; start command `GUNICORN_CMD_ARGS='' gunicorn -c gunicorn.conf.py central_wsgi:app`; allowlist `0.0.0.0/0`. O último deploy listado, `dep-dc3odps9v7es73cpao00`, está `live` no commit `455c94a56fe616a963a4ef1ce95a057c784071de` (26/11 01:11:36 UTC). O HEAD local permanece `11558273449a8d1c5beae67b106f69c6475d9f04`, dois commits à frente do remoto; portanto, as alterações locais recentes de guarda de estado ainda não estão no serviço.

O `healthCheckPath` verifica readiness HTTP conforme o comportamento documentado pelo Render; não inicia deploy e não prova a saúde do executor PAPER nem prontidão para trading. Esta consulta foi somente de metadados: não fiz GET no serviço, não li logs/variáveis/secrets, não acessei `/data`, Upstash ou BingX e não alterei recursos. A allowlist ampla deixa a autenticação da aplicação como controle crítico da superfície pública; a revisão local e os testes HTTP anteriores não substituem uma verificação HTTP autenticada recente em produção.

Reexecução do gate de entrada/fill/stop no mesmo HEAD: o Python-base `py -3.14 -I` não coletou dois módulos porque não tem `ccxt` instalado (`ModuleNotFoundError`); sem instalar ou baixar dependências, repeti com a virtualenv offline preexistente `ccxt-offline-20261108-01`, que importa a versão fixada, e `--entry-fill-stop` passou **37 testes em 1,30 s**. A falha ambiental fica registrada; o resultado da virtualenv é o teste válido deste turno. Como antes, são fixtures offline e não validam a BingX real nem a corrida de identidades distintas.

## Revalidação do bootstrap Gunicorn — 2026-11-26

No HEAD local `11558273449a8d1c5beae67b106f69c6475d9f04`, executei `tests/run_gunicorn_bootstrap_offline.py`, que bloqueia conexões de rede e subprocessos durante os testes. A primeira chamada no Python 3.14 falhou antes da coleta porque o pytest importou `pdb`/`asyncio` depois que o harness substituiu `subprocess.Popen`; não foi falha de asserção. Repeti o mesmo runner após pré-carregar apenas os módulos padrão `asyncio` e `pdb`; resultado: **24 testes passaram em 1,33 s**. Nenhum deploy ou teste em Render ocorreu nesta etapa.

## Revalidação do guard PAPER no broker — 2026-11-26

No mesmo HEAD, `tests/run_falcon_pilot_minimal_offline.py --broker-paper-disk-guard` passou **47 testes em 2,66 s**, usando a virtualenv offline preexistente `.venv-centralquant-ccxt-20261023` (CCXT 4.5.89). A tentativa inicial com `py -3.14 -I` não coletou porque esse interpretador isolado não tem `ccxt`; nenhuma dependência foi instalada e não houve acesso à rede. Os 47 testes exercitam o guard com fixtures locais, não confirmam o mount nem o ledger `/data` em produção.

Confirmei novamente que `healthCheckPath=/healthz` é apenas readiness e que a configuração Render lida anteriormente mantém `autoDeploy=no`: chamar `/healthz` não inicia deploy. A publicação do HEAD local continua pendente e não foi tentada nesta etapa.

## Revalidação dos gates de identidade e armazenamento PAPER — 2026-11-26

No mesmo HEAD e na mesma virtualenv local, executei o runner offline com `--account-client-order-authority`: **96 passaram, 1 ignorado em 0,82 s**; e com `--paper-integrated-disk-guard`: **116 passaram, 13 ignorados e 12 subtestes passaram em 211,30 s**. O segundo processo permaneceu ativo e consumindo CPU durante a execução, e terminou com código 0; não foi reiniciado. Os resultados exercitam fixtures temporárias e os contratos selecionados, mas não criam ledgers, não reconciliam registros e não comprovam a disponibilidade do PAPER integrado no Render.

## Revalidação de autenticação HTTP e startup C3 dormente — 2026-11-26

Uma primeira execução de `--personal-http-auth` fora da raiz do checkout resultou em 36 falhas de fixture por `FileNotFoundError: main.py`, porque esses testes usam caminhos relativos; nenhuma era falha de asserção de autorização. Repeti ambos os gates com cwd na raiz do repositório: `--personal-http-auth` passou **243 testes em 71,29 s** e `--c3-dormant-startup` passou **24 testes e 3 subtestes em 319,61 s**, ambos com código de saída 0. O runner de C3 continuou ativo/CPU-bound durante toda a execução e não foi reiniciado. São verificações locais de código/fixtures; não demonstram autenticação na instância Render nem necessidade/ausência universal de writers externos. C3 permanece default-off.

## Evidência do preflight de capacidade da conta — 2026-11-26

Inspeção do HEAD `11558273449a8d1c5beae67b106f69c6475d9f04`: `_broker_rpg_v1_open_positions_count()` chama `get_positions()` e conta posições não-zero; `broker_real_pilot_guard_v1_validate()` usa esse snapshot, mas não consulta `fetch_open_orders()`. O guard é chamado por `place_market_order()` antes de `_create_order_with_reserved_attempt()`/`create_order`; os chamadores de entrada observados em `execution_engine.py` e `bots/predator.py` convergem nessa função. O decorator nessa fronteira verifica drenagem do runtime, não serializa nem reserva capacidade da conta. `account_client_order_id.py` grava slots por tentativa/identidade, sem índice de reservas pendentes agregado por conta. O teste de concorrência existente cobre repetição da mesma identidade, não identidades diferentes competindo pela última vaga.

Isso confirma um bloqueio para qualquer futura habilitação LIVE, não uma necessidade de C3 para o Registry. Um lock de thread isolado não cobriria ordem pendente nem recuperação após restart; não apliquei essa correção parcial. A solução precisa de reserva durável por conta e reconciliação antes de liberar capacidade, com testes offline de identidades concorrentes, ordens abertas, resultado desconhecido/restart e encerramento confirmado. LIVE permanece desligado; nenhuma chamada de exchange foi feita.

## Reprodução isolada da corrida do guard — 2026-11-26

Compilei apenas a função AST `broker_real_pilot_guard_v1_validate()` com dependências substituídas por fixtures e sincronizei duas threads na leitura de posições. Com limite de uma posição, snapshot vazio e identidades `ENTRY-A`/`ENTRY-B`, **ambas as chamadas retornaram `allowed=True`**. A reprodução não importou `broker.py`, não leu ambiente/credenciais, não chamou exchange e não tentou `create_order`; ela prova somente que o guard em si não reserva atomicamente capacidade entre identidades distintas. O código de saída foi 0. Isso transforma a lacuna estática em uma reprodução offline, sem demonstrar qualquer incidente ou envio em produção.

## Auditoria complementar do lock dos writers do Registry — 2026-11-26

No mesmo HEAD `11558273449a8d1c5beae67b106f69c6475d9f04`, a inspeção das chamadas diretas a `save_registry()` mostrou que os ciclos de escrita conhecidos usam o `_lock` compartilhado do módulo `trade_registry.py` ou o resolver `_trpsf_v1_registry_lock()` em `main.py`. A rotina `registry_persistence_v1_restore_from_latest_snapshot()` parecia inicialmente uma exceção, mas relê e repete a operação com `_lock_held=True` dentro do lock compartilhado; o `save_registry` final ocorre nessa seção crítica. Corrijo aqui a impressão preliminar de que esse caminho não tinha reentrada protegida.

Executei `py -3.14 -I tests/run_falcon_pilot_minimal_offline.py --registry-writers`: **73 testes passaram**, código 0, em 123,96 s. A seleção cobre o inventário AST dos saves diretos, a guarda de reentrada do restore e os testes de escrita atômica durável. O runner bloqueia sockets/egress, subprocessos e leitura de `.env`, e redireciona `DATA_DIR`, `CENTRAL_DATA_DIR` e `TRADE_REGISTRY_FILE` a um diretório temporário. Isso valida os callsites e cenários cobertos localmente; não exclui writers dinâmicos, processos externos ou uma topologia de produção diferente da última observada.

Conclusão C3: até aqui não há evidência concreta de que um lock distribuído seja necessário para coordenar esses writers no caminho crítico do serviço pessoal observado com uma instância e um worker Gunicorn. O `_lock` cobre concorrência entre threads no processo; não se afirma que cubra processos externos. C3 permanece preservado, default-off e fora do caminho crítico. Nenhuma ativação, chamada de rede, escrita de Registry ou alteração de produção ocorreu.

## Revalidação offline do preview/capture PAPER — 2026-11-26

No HEAD `11558273449a8d1c5beae67b106f69c6475d9f04`, `py -3.14 -I tests/run_falcon_pilot_minimal_offline.py --paper-registry-source-preview` passou **47 testes** e `--paper-registry-source-capture` passou **22 testes**. `git diff --check` também passou. O runner bloqueia rede/egress, subprocessos e leitura de `.env`, e usa diretório temporário para estado; são fixtures locais, sem consulta Upstash ou Registry de produção.

Os testes verificam que até um match forte único permanece somente para revisão, IDs duplicados/conflitantes não viram matches elegíveis, snapshots incompletos falham fechados e resultados sanitizados mantêm `all_rows_ineligible_for_import=true` e `writes_performed=false`. Isso valida a barreira local do utilitário, não a origem/identidade das 204 linhas observadas na última captura real nem autoriza criar, importar ou descartar ledgers PAPER. O executor integrado continua bloqueado pela ausência dos arquivos de estado.

## Paridade do código de autenticação com o SHA Live registrado — 2026-11-26

Comparei o HEAD local `11558273449a8d1c5beae67b106f69c6475d9f04` ao último deploy Live registrado pelo Render MCP (`455c94a56fe616a963a4ef1ce95a057c784071de`). `main.py`, `central_wsgi.py`, `personal_http_auth.py` e `tests/test_personal_http_auth_gate_v1.py` são idênticos entre os dois commits; os sete paths diferentes são o guard de leitura do Executive Policy Learning e os utilitários/testes sanitizados de preview/capture PAPER. A seleção local `--personal-http-auth` já registrada neste mesmo HEAD passou 243 testes.

Isso reduz o risco de o código HTTP de autenticação local não corresponder ao último SHA Live conhecido. Não revalida se esse SHA continua Live agora, não verifica valores de variáveis/segredos nem testa login válido ou uma rota autenticada em produção. Não houve chamada HTTP, leitura de segredo, push ou deploy nesta comparação.

## Gate da correção de leitura do Executive Policy Learning — 2026-11-26

No HEAD `11558273449a8d1c5beae67b106f69c6475d9f04`, executei `py -3.14 -I tests/run_falcon_pilot_minimal_offline.py --policy-storage-guard`: **34 testes passaram em 3,73 s**. O runner offline bloqueia rede/egress, subprocessos e acesso a `.env` e redireciona o estado a diretório temporário. A seleção valida localmente o guard de armazenamento persistente associado à diferença `executive_policy_learning.py` em relação ao último SHA Live registrado.

O resultado não demonstra runtime ou I/O em produção, nem revalida qual commit está Live agora. Não houve leitura de segredos, acesso a `/data`, chamada externa, push ou deploy.

## Semântica e recuperação do latch de persistência PAPER Falcon — 2026-11-26

No HEAD `11558273449a8d1c5beae67b106f69c6475d9f04`, a revisão de `bots/falcon.py` confirmou que `falcon_paper_persistence_reconciliation_required()` falha fechado se `DATA_DIR`/mount/JSON não puderem ser validados; o latch válido mantém `reconciliation_required=true` e bloqueia novos sinais PAPER em `execute_signal_if_allowed()`. `_falcon_process_entry_signal()` grava o latch quando um sinal já aceito não foi confirmado como sincronizado com Registry e memória Falcon. O payload guarda somente a categoria sanitizada, não identidade suficiente para recuperar por si só o sinal original.

Busca estática em todos os arquivos Python do repositório encontrou leitor e gravador do latch, mas nenhuma operação suportada que faça reconciliação e liberação. O teste `--falcon-lifecycle-projection` passou **32 testes em 22,65 s**; inclui persistência após reinício e mantém bloqueio quando o JSON está corrompido. O teste é local, com diretório temporário e sem rede; não verifica o latch ou suas fontes em produção.

Conclusão operacional: não apagar/criar manualmente o latch. Mesmo após identificar um procedimento técnico para o latch Falcon, isso não inicializaria o ledger PAPER integrado ausente. Ambos os bloqueios exigem reconciliação factual; os registros legacy sem identidade forte não são autorização para importação. Não houve mudança em código de execução, `/data`, Upstash, BingX, Render, push ou deploy.

Complemento da revisão: quando `falcon_persist_accepted_signal()` encontra uma projeção com `falcon_persistence_failure_components`, retorna `FALCON_ACCEPTED_SIGNAL_RECONCILIATION_REQUIRED` sem tentar novamente o writer do Registry nem o save da memória. O teste `test_in_memory_pending_persistence_marker_cannot_be_treated_as_synchronized` confirma esse fail-closed. Portanto, remover somente o latch não é um procedimento de recuperação; é necessário um fluxo explícito de reconciliação por identidade forte, ainda inexistente. Não implementei um bypass nem alterei o comportamento de produção.

## Reexecução integral da suíte de ciclo — 2026-11-26

Corrijo a pendência ambiental registrada acima: o Python base 3.14 não tem
`ccxt`, mas há um ambiente offline preexistente no workspace. Usando
`ccxt-offline-20261108-01/venv/Scripts/python.exe` (Python 3.14.5,
CCXT 4.5.88 e pytest 9.1.1), no HEAD
`11558273449a8d1c5beae67b106f69c6475d9f04`, rodei novamente:

```text
tests/run_falcon_pilot_minimal_offline.py --personal-lifecycle-completeness
892 passed, 1 skipped in 575.57s (0:09:35), exit code 0
```

O runner bloqueia rede, subprocessos e leitura de `.env`, e direciona o estado
para diretório temporário. Nenhuma dependência foi instalada. O skip permanece
sem diagnóstico identificado; os testes exercitam fixtures e não demonstram
ordens, fills, posições ou stops na BingX. Nenhum push ou deploy foi feito.

## Fronteira para futura admissão de capacidade — 2026-11-26

Inspeção AST do `broker.py` confirma um único `ex.create_order(...)` físico, dentro de `_create_order_with_reserved_attempt`. Os cinco chamadores desse helper são `create_disaster_stop_order`, `place_market_order`, `close_position_market`, `_rpm_create_stop_live` e `managed_close_position_market`; a entrada market passa por `place_market_order` com `ROLE_ENTRY`, enquanto stops/fechamentos têm papéis próprios. Em `place_market_order`, `broker_real_pilot_guard_v1_validate` roda antes de `ready_check`, da preparação/readback de margem e alavancagem e da chamada final ao helper, sem segunda verificação de capacidade imediatamente antes do envio.

O guard usa `_broker_rpg_v1_open_positions_count`, que lê posições, não ordens abertas. `fetch_recent_orders()` tenta `fetch_orders`, `fetch_closed_orders` e `fetch_open_orders`, mas retorna `ok=True` mesmo quando registra falhas por método em `errors`; portanto, não serve como fonte fail-closed sem alteração de contrato e validação de cobertura de símbolos. A autoridade atual `account_client_order_id.py` persiste outcomes imutáveis por tentativa/identidade, inclusive `CREATE_ORDER_OUTCOME_UNKNOWN`, mas não oferece reserva agregada de slots por conta. A reprodução AST registrada no relatório C3 mostrou duas identidades concorrentes aprovadas com limite de uma posição, sem chamar exchange.

Consequência de projeto: o ponto de integração está delimitado à entrada em `place_market_order`, mas a proteção correta precisa serializar todos os senders do processo e manter reserva durável por conta através de ACK, ordem pendente, fill, cancelamento/rejeição, timeout e reinício. A leitura do snapshot precisa incluir posições e ordens de entrada abertas, distinguindo ordens reduce-only/protetivas; qualquer consulta incompleta ou resultado desconhecido deve bloquear novas entradas. Reutilizar apenas `threading.RLock`, `fetch_recent_orders()` como está, ou o ledger por client-order-id não satisfaz esses invariantes. Nenhuma mudança foi feita em `broker.py`, no estado de produção ou nos controles LIVE.

## Revalidação do gate HTTP, reconciliação e estado de release — 2026-11-26

Checkout: `codex/prod-wsgi-20261125`, commit local `1be56035a41d7299301339577bea9aaf9a4768e2`. A suíte `--personal-http-auth` passou **243 testes**, `--close-reconciliation` passou **114 testes**, e a suíte completa `--personal-lifecycle-completeness` passou **896 testes, 1 ignorado**, em 616,58 s. As três execuções usaram o venv offline existente e o runner que bloqueia rede/egress, subprocessos e leitura de `.env`; fixtures e persistência foram temporárias. `git diff --check` passou.

Foi corrigido o contrato de `fetch_recent_orders()` para não retornar sucesso quando algum dos leitores configurados falha, não existe ou entrega payload que não seja lista. `fetch_recent_my_trades()` também rejeita payload não-lista; `reconcile_order_from_bingx()` só declara leitura completa quando ambos os lados são completos. Resultados parciais podem conter matches observados, mas `ok=false`/`complete=false` não prova ausência nem autoriza ação. O commit local `1be5603` inclui somente `broker.py` e `tests/test_real_close_reconciliation_v11.py`.

Render MCP somente leitura confirmou workspace Central Quant, serviço `central-robos-bingx`, branch vinculada `codex/prod-wsgi-20261125`, `autoDeploy=no`, HTTP health path `/healthz`, uma instância Standard com disco persistente de 4 GB e SHA Live `455c94a56fe616a963a4ef1ce95a057c784071de`. O probe `/healthz` é uma verificação periódica de saúde/readiness HTTP, não um gatilho de deploy; com auto-deploy Off, novas alterações de branch exigem deploy manual. O checkout local está três commits à frente do `origin` observado, mas não foi enviado. Nenhum deploy, chamada HTTP pública, acesso BingX/Upstash, leitura de secrets ou alteração de `/data` ocorreu.

Um deploy ainda não foi executado: minutos de build são consumidos e a franquia/uso faturável atual não foi verificada, portanto custo zero não está comprovado. Mesmo após release, prontidão de trading permanece incompleta: os ledgers PAPER continuam não reconciliados e a admissão LIVE tem o gap concorrente documentado acima. Não alterar controles LIVE nem executar ordens reais.

## Gates adicionais do candidato local — 2026-11-26

No HEAD `1be56035a41d7299301339577bea9aaf9a4768e2`, reexecutei pelo runner offline os gates que complementam a suíte de ciclo: `--can-open-risk` passou **10 testes** (67 fora do filtro) em 118,59 s; `--registry-writers` passou **73 testes** em 111,87 s; `--c3-dormant-startup` passou **24 testes e 3 subtestes** em 370,53 s. O runner bloqueia rede/egress, subprocessos e leitura de `.env`. Isso sustenta a decisão de manter C3 dormente na topologia pessoal observada e confirma somente comportamento sintético local; não remove o gap de reserva atômica de capacidade para futuras entradas LIVE nem valida produção.

## Validação adicional do fallback de fills malformado — 2026-11-26

No mesmo HEAD local, acrescentei um teste integrado offline para `fetch_order_trades()`: quando o histórico paginado falha e `fetch_my_trades()` devolve um objeto em vez de lista, o fallback é marcado inválido, nenhum trade é exposto e a janela permanece não verificada. A seleção `--close-reconciliation` passou **115 testes em 21,32 s** usando o venv offline existente. Nenhuma chamada de rede/corretora ocorreu. O teste não transforma dados parciais em prova de ausência de fills e não valida estado de produção.

## Health check e deploy Render revalidados — 2026-11-26

Render MCP somente leitura confirmou workspace `Central Quant`, serviço `central-robos-bingx`, `autoDeploy=no`, `healthCheckPath=/healthz` e deploy mais recente `dep-dc3odps9v7es73cpao00` em estado `live`, ainda no SHA `455c94a56fe616a963a4ef1ce95a057c784071de`. Portanto, `/healthz` está configurado como probe periódico e não dispara deploy; com auto-deploy desligado, publicação exige gatilho manual. O HEAD local agora é `9f6c7913c86fc8698137e17a6c40c7cb26e4d8d4`, quatro commits à frente da referência remota localmente observada, sem push. Nenhuma mudança de serviço foi feita. A franquia/custo faturável continua sem confirmação; não publicar até haver decisão financeira específica.

Auditei localmente os quatro commits do candidato: nove arquivos Python/testes, sem alteração de `requirements.txt`; o commit `9f6c791` contém apenas o teste integrado de fallback. Os documentos de readiness e C3 permanecem modificados e fora desses commits, preservados no worktree. Essa inspeção não altera o GitHub nem certifica a franquia de build do Render.

## Revalidação offline da autenticação HTTP pública — 2026-11-26

No HEAD `9f6c7913c86fc8698137e17a6c40c7cb26e4d8d4`, a seleção `--personal-http-auth` passou **243 testes em 75,79 s**. A inspeção confirmou um guard Flask global aplicado antes das rotas, rejeição de mutação por GET e a única exceção pública estreita para `GET /healthz` sem query e sem falha de origem cross-site. Isso valida fixtures offline; não verifica credenciais, comportamento em produção ou se o SHA local foi publicado. Nenhuma credencial foi lida.

Comparação read-only dos paths `main.py`, `personal_http_auth.py`, `central_wsgi.py` e `tests/test_personal_http_auth_gate_v1.py` entre esse HEAD e o SHA Live então observado (`455c94a56fe616a963a4ef1ce95a057c784071de`) não encontrou diferenças. Isso confirma paridade desses quatro arquivos apenas; o restante da release local continua divergente e não enviado.

## Reexecução de gates de entrada e proteção de posição — 2026-11-26

No HEAD `9f6c7913c86fc8698137e17a6c40c7cb26e4d8d4`, as seleções offline passaram: `--initial-stop-containment` **79 testes**; `--initial-stop-cancel` **85**; `--entry-fill-stop` **37**; e `--live-position-risk-gate` **34** em 6m07s. O runner usa fixtures e bloqueia rede/egress e subprocessos. Isso valida cenários sintéticos de contenção quando stop falha, cancelamento/sizing após fill e risco por posição; não prova execução, stop, posição ou cancelamento na BingX e não remove o gap de admissão concorrente descrito anteriormente. Nenhuma ordem real foi enviada.

## Revalidação Render após confirmação do operador — 2026-11-26

Nova leitura somente de metadados pelo Render MCP confirmou `central-robos-bingx` Live no SHA `455c94a56fe616a963a4ef1ce95a057c784071de`, branch `codex/prod-wsgi-20261125`, `autoDeploy=no`, `healthCheckPath=/healthz`, uma instância e disco `/data` de 4 GB. O comando configurado é `GUNICORN_CMD_ARGS='' gunicorn -c gunicorn.conf.py central_wsgi:app`. `/healthz` não inicia deploy. O deploy `11bd1ec855e694e996a59cf90ccc3ca1825906de` está `deactivated`; não há deploy novo pendente nessa leitura. Não houve restart, deploy, push ou chamada à corretora. O operador informou que não há operações abertas, mas isso não foi verificado independentemente na BingX. Custo zero de novo build/deploy continua não comprovado.

Implicação: se for necessário publicar um commit, o gatilho é **Deploys → Manual Deploy**, não acessar `/healthz`; não há necessidade de novo deploy só para executar a probe. A release local continua quatro commits à frente e não publicada. Manter sem push/deploy até custo ser confirmado como zero ou haver decisão financeira específica.

## Reexecução do gate HTTP pessoal — 2026-11-26

Na mesma revisão do HEAD `9f6c7913c86fc8698137e17a6c40c7cb26e4d8d4`, executei `py -3.14 -I tests/run_falcon_pilot_minimal_offline.py --personal-http-auth`: **243 testes passaram em 75,10 s**, código de saída 0. A inspeção do fonte confirma um `app.before_request` global de Basic Auth aplicado antes de qualquer rota, inclusive aliases e caminhos desconhecidos; só `GET /healthz` sem query tem exceção estreita para a probe do Render, e os gates seguintes bloqueiam mutações por GET e runtime não pronto. O runner é offline e não leu credenciais reais. Isso valida os casos sintéticos cobertos, não login válido nem todas as configurações HTTP do Render.

## Consolidação da revalidação offline e do estado Render — 2026-11-26

Revalidação no worktree `cq-gunicorn-candidate-20261125`: branch `codex/prod-wsgi-20261125`, HEAD `9f6c7913c86fc8698137e17a6c40c7cb26e4d8d4`. A referência local `origin/codex/prod-wsgi-20261125` está em `455c94a56fe616a963a4ef1ce95a057c784071de`; o HEAD tem quatro commits a mais e zero atrás. A branch não tem upstream configurado. Preservei as alterações pré-existentes em `PERSONAL_C3_NEED_ASSESSMENT_20261110.md` e neste relatório.

Reexecutei no HEAD atual, com a virtualenv offline existente e o runner `tests/run_falcon_pilot_minimal_offline.py`: `--entry-fill-stop` **37 passou**; `--policy-storage-guard` **34 passaram**; `--close-reconciliation` **115 passaram**; `--personal-http-auth` **243 passaram**; `--paper-integrated-disk-guard` **116 passaram, 13 ignorados e 12 subtestes passaram**; `--paper-registry-source-preview` **47 passaram**; `--paper-registry-source-capture` **22 passaram**. Os testes usam fixtures e não chamam BingX, Upstash, Render ou AWS. Eles não provam a identidade/proveniência dos registros PAPER de produção nem validam operação real de entrada, fill, stop, fechamento ou reconciliação.

Leitura Render MCP somente de metadados, após os testes: workspace `Central Quant`, serviço `central-robos-bingx`, branch `codex/prod-wsgi-20261125`, `autoDeploy=no`, `healthCheckPath=/healthz`, uma instância e disco persistente `/data` de 4 GB. O último deploy continua `live` no SHA `455c94a56fe616a963a4ef1ce95a057c784071de`; não há deploy novo pendente. `/healthz` é uma probe e não inicia publicação. Nenhum push, deploy, restart, GET de produção, leitura de variáveis, acesso a segredo, `/data`, Upstash, AWS ou BingX foi feito nesta revalidação. O custo de publicar não foi comprovado como zero; por isso, os quatro commits locais permanecem sem envio.

Pendências bloqueantes: ledger PAPER integrado ausente e registros legados não elegíveis para importação automática; autenticação válida e integração ponta a ponta ainda não verificadas em produção; testes reais de conta e da sequência de entrada/fill/stop/fechamento/reconciliação não executados; corrida de admissão por identidades distintas permanece aberta para qualquer futura habilitação LIVE. C3 distribuído não tem necessidade demonstrada na topologia observada e fica dormente. Controles LIVE não foram alterados.

## Suíte offline ampla atual — 2026-11-26

No mesmo HEAD `9f6c7913c86fc8698137e17a6c40c7cb26e4d8d4`, executei `tests/run_falcon_pilot_minimal_offline.py --personal-lifecycle-completeness` na virtualenv offline existente: **897 passaram, 1 ignorado, em 599,70 s**. O runner concluiu com código de saída zero; a execução usou fixtures locais, sem chamadas de rede/corretora ou escrita de produção. Esse resultado é uma regressão local ampla, não comprovação da integração ou prontidão em runtime; a corrida de admissão entre identidades distintas não está coberta por esse filtro.

Reproduzi novamente a corrida na função `broker_real_pilot_guard_v1_validate` extraída por AST do HEAD atual. Duas threads com identidades distintas (`DONKEY` e `PREDATOR`), limite sintético de uma posição e snapshots vazios sincronizados retornaram `BROKER_REAL_PILOT_GUARD_ALLOWED` nas duas chamadas (`allowed_count=2`). O harness executou somente a função extraída, com dependências sintéticas; não importou o módulo de produção, não leu ambiente/segredos, não chamou rede/exchange nem `create_order`. Isso prova a lacuna no guard de admissão atual, não um incidente nem uma ordem enviada. Não implementei uma trava parcial; falta projetar/testar a reserva persistente e a reconciliação de ordens pendentes, ACK, timeout e restart.

## Reprodução Falcon-only da admissão concorrente — 2026-11-26

Refinei a reprodução anterior ao caso padrão: `BROKER_REAL_PILOT_ALLOWED_BOTS` tem default `FALCON`. Extraí por AST os corpos atuais de `broker_real_pilot_guard_v1_validate` e `_broker_validate_falcon_ownership_limit`, sem importar `broker.py`; executei duas chamadas concorrentes ambas como FALCON, com client tags sintéticas distintas, limite de uma posição e o mesmo snapshot vazio. Uma barreira sincronizou as leituras de posições. As duas retornaram `BROKER_REAL_PILOT_GUARD_ALLOWED` (`allowed_results=2`). A fixture habilitou flags LIVE apenas no namespace sintético para percorrer o guard; sockets foram substituídos por uma função que falha, e o harness não chamou `_create_order_with_reserved_attempt`/`create_order`, não usou credenciais, rede, exchange ou estado de produção. Isso prova que a validação Falcon por snapshot não reserva capacidade entre duas identidades distintas; não prova uma ordem nem incidente em produção. O gap e o requisito de reserva persistente/reconciliação permanecem; nenhuma correção parcial foi aplicada.

## Reexecução do gate C3 dormente — 2026-11-26

No HEAD `9f6c7913c86fc8698137e17a6c40c7cb26e4d8d4`, rodei novamente `tests/run_falcon_pilot_minimal_offline.py --c3-dormant-startup` com a virtualenv offline existente: **24 testes e 3 subtestes passaram em 366,26 s**, código de saída 0. O runner manteve rede/egress, subprocessos e leitura de `.env` bloqueados. Isso valida apenas os cenários locais de startup C3 dormente; não é evidência de produção nem motivo para ativar C3. Nenhum código de runtime, deploy, controle LIVE ou dado persistente foi alterado.

## Revalidação do bootstrap Gunicorn e do drain — 2026-11-26

No mesmo HEAD, `py -3.14 -I tests/run_gunicorn_bootstrap_offline.py` inicialmente falhou antes da coleta: o runner substitui `subprocess.Popen` por função que nega subprocessos, e o plugin interno `debugging` do pytest tenta herdar dessa função. Reexecutei o mesmo runner com `PYTEST_ADDOPTS='-p no:debugging'`; **24 testes passaram em 1,12 s**, exit code 0. Os bloqueios de rede/subprocessos do harness permaneceram ativos. A configuração testada é um worker `gthread`, 16 threads e `preload_app=False`, com rejeição explícita de workers múltiplos ou preload. Isso sustenta topologia de processo único e confirma que concorrência entre threads ainda existe; não demonstra estado do Render atual nem corrige a admissão concorrente de ordens.

## Recontagem AST do caminho físico de envio — 2026-11-26

AST read-only sobre os arquivos Python fora de testes/venvs, no HEAD `9f6c7913c86fc8698137e17a6c40c7cb26e4d8d4`, encontrou uma chamada física a método `create_order`: `broker.py::_create_order_with_reserved_attempt`. Os dois callsites de `place_market_order` encontrados foram `execution_engine.py::run_execution_engine` e `bots/predator.py::execute_predator_signal_safe`. Isso delimita a superfície estática observada, não cobre dispatch dinâmico/reflection ou writers em processos externos. Não houve import do broker, leitura de ambiente/segredos, chamada a exchange ou alteração de runtime. O ponto único de envio não elimina a corrida antes da reserva de capacidade: os dois callsites podem concorrer nas 16 threads do worker; qualquer correção futura precisa ser compartilhada, persistente, reconciliável após resultado desconhecido/restart e coberta sem habilitar LIVE.

## Correção do runner offline de Gunicorn — 2026-11-26

O runner `tests/run_gunicorn_bootstrap_offline.py` foi ajustado para instalar os bloqueios antes de importar pytest, verificar que `socket.create_connection`, resolução de nomes, `socket.connect`/`connect_ex` e `subprocess.Popen` são negados, e desabilitar explicitamente o plugin interno `debugging`, que tentava herdar do `Popen` substituído. O comando padrão `py -3.14 -I tests/run_gunicorn_bootstrap_offline.py` passa **24 testes em 1,22 s**, sem variável de contorno. Nenhum socket real ou processo-filho foi aberto. Alteração apenas no harness de teste; nenhum código de runtime ou controle LIVE mudou.

## Revalidação fail-closed do estado PAPER — 2026-11-26

No HEAD `9f6c7913c86fc8698137e17a6c40c7cb26e4d8d4`, com o runner offline existente, `--paper-integrated-disk-guard` passou **116 testes, 13 skips e 12 subtests** em 210,36 s; `--falcon-lifecycle-projection` passou **32 testes** em 33,79 s. O runner bloqueou rede/egress, subprocessos e leitura de `.env`, e direcionou estado para diretório temporário. Os testes confirmam separadamente que arquivos PAPER ausentes não são reportados como zero nem inicializados pelo executor e que o latch Falcon de reconciliação persiste após restart e bloqueia novos sinais PAPER. Isso reforça que criar apenas arquivos vazios não resolveria o latch e não pode substituir a reconciliação de identidade/proveniência. Nenhum arquivo de produção foi lido ou escrito.

## Latch PAPER sem resolução operacional — 2026-11-26

Inspeção estática dos únicos helpers `falcon_paper_persistence_latch_path`, `falcon_paper_persistence_reconciliation_required` e `falcon_persist_paper_persistence_latch` em `bots/falcon.py`, além de busca nas rotas de `main.py` e `central_wsgi.py`, não encontrou procedimento suportado para resolver ou liberar o latch. Os testes cobrem persistência, corrupção fail-closed e bloqueio de novos sinais, não uma reconciliação autenticada com recibo de resolução. Portanto não apagar/editar o arquivo do latch nem criar ledgers manualmente; isso contornaria o bloqueio sem provar origem/identidade. Uma resolução segura exige fluxo futuro explícito, auditável e testado que vincule evidências verificadas e preserve os registros ambíguos.

Render MCP read-only em 2026-11-26 confirmou `/healthz`, `autoDeploy=no` e Live em `455c94a56fe616a963a4ef1ce95a057c784071de`; acessar `/healthz` é probe, não gatilho de publicação. Não houve deploy, restart, alteração de configuração, acesso a `/data`, credenciais, Upstash ou BingX nesta etapa.

## SHA candidato ainda não publicado — 2026-11-26

GitHub MCP read-only não encontrou o SHA local `9f6c7913c86fc8698137e17a6c40c7cb26e4d8d4` (`No commit found for SHA`, HTTP 422), enquanto a busca confirmou que a branch remota `codex/prod-wsgi-20261125` existe. Logo, o commit validado ainda não está disponível para seleção no Manual Deploy. Auto-Deploy permanece off; um push não deve publicar automaticamente, mas CI/build e eventual implantação manual podem consumir recursos. Não fiz push porque custo zero não foi comprovado; qualquer avanço externo exige decisão financeira específica, sincronização fast-forward confirmada e novo preflight.

## Revalidação da referência remota — 2026-11-26

Consulta read-only `git ls-remote` confirmou que a branch remota permanece em `455c94a56fe616a963a4ef1ce95a057c784071de`, o mesmo SHA Live do Render. A comparação local `git rev-list --left-right --count origin/codex/prod-wsgi-20261125...HEAD` retornou `0 4`, e `merge-base` foi o SHA `455c94a`; portanto o HEAD local `9f6c791` é fast-forward de quatro commits, sem divergência conhecida na branch consultada. `git ls-tree` não encontrou workflows em `.github/workflows` no HEAD. Isso remove a incerteza de divergência, mas não comprova custo zero do pipeline/build nem autoriza envio/publicação; nenhum push ou deploy foi feito.

## Reexecução de testes do ciclo de ordem — 2026-11-26

No HEAD `9f6c7913c86fc8698137e17a6c40c7cb26e4d8d4`, executei o runner isolado com a virtualenv existente `cq-ccxt-4.5.88`: `--close-reconciliation` passou **115 testes** (25,82 s) e `--entry-fill-stop` passou **37 testes** (2,32 s). São cenários offline e sintéticos; não consultam conta, enviam ordens, validam a resposta real da BingX nem substituem preflight/runtime de produção. Nenhuma dependência foi instalada e nenhum controle LIVE foi alterado.

## Reexecução de posição e proteções de stop — 2026-11-26

Na mesma virtualenv e HEAD, executei offline `--live-position-risk-gate` (**34 testes**, 465,57 s), `--initial-stop-containment` (**79**, 77,12 s), `--stop-readback` (**12**, 36,46 s) e `--initial-stop-cancel` (**85**, 76,79 s); todos passaram. A coleta longa de risco de posição foi acompanhada no mesmo processo até o exit code 0. Esses resultados cobrem fixtures e verificações locais, não dados/ordens da conta nem um ciclo de produção completo. Nenhum segredo foi lido, nenhuma dependência instalada, e nenhum controle LIVE ou dado persistente foi alterado.

## Verificação da probe e da expectativa de deploy — 2026-11-26

Nova leitura read-only do Render confirmou workspace `Central Quant`, serviço `central-robos-bingx`, `autoDeploy=no`, `healthCheckPath=/healthz` e deploy `live` `dep-dc3odps9v7es73cpao00` no SHA `455c94a56fe616a963a4ef1ce95a057c784071de`. Portanto, uma requisição GET a `/healthz` só executa a verificação de saúde; não inicia publicação. As docs atuais do Render descrevem Auto-Deploy `Off` como deploy exclusivamente manual e documentam o trigger em Deploys → Manual Deploy. O candidato local continua quatro commits à frente da branch/Live e não está publicado; “Deploy latest commit” ainda selecionaria `455c94`, não `9f6c791`.

O código Live `455c94` contém a mesma rota mínima `/healthz` do HEAD local: GET sem query retorna somente `HTTP_LIVE` (ou `HTTP_DRAINING`/`CENTRAL_RUNTIME_NOT_READY`), sem estado de trading. No HEAD `9f6c7913c86fc8698137e17a6c40c7cb26e4d8d4`, rodei `tests/test_personal_http_auth_gate_v1.py -k 'render_healthz_is_minimal_public_liveness_only or runtime_routes_fail_closed_until_boot_completes'` na virtualenv existente: **2 passaram** em 19,68 s; a fixture bloqueia resolução DNS e conexões de rede. Em seguida, `tests/run_falcon_pilot_minimal_offline.py --personal-http-auth` passou **243 testes** em 96,32 s com bloqueios offline do runner. `git diff --check` passou. Nenhuma alteração de serviço, push ou deploy foi feita; os três arquivos locais modificados antes desta checagem continuam preservados.

## Concorrência do executor PAPER — 2026-11-26

Inspeção de código confirma que `paper_executor_integrated`, `paper_lifecycle` e `outcome_evaluator` compartilham o mesmo `PAPER_STATE_LOCK` (`threading.RLock`) durante suas operações read-modify-write; o executor mantém o lock ao verificar idempotência e gravar a nova posição. O serviço Render observado tem uma única instância e um único worker Gunicorn, sem outro serviço no workspace; portanto o desenho atual cobre concorrência entre threads dentro do processo, mas não reivindica coordenação entre processos/instâncias. Reexecutei `tests/run_falcon_pilot_minimal_offline.py --paper-integrated-disk-guard`: **116 passaram, 13 skips e 12 subtests** em 230,33 s. O runner bloqueia rede/egress e subprocessos, e os testes usam diretórios temporários. Isso sustenta a alternativa local simples para o ledger PAPER na topologia observada; não substitui reconciliação/proveniência nem justifica ativar C3 distribuído. C3 permanece dormente; escalar workers/instâncias ou adicionar writers externos exigiria nova prova e desenho de coordenação.

Limite de admissão observado: `bots/falcon.py::execute_signal_if_allowed` retorna `allowed=True` diretamente no modo PAPER, sem chamar `can_open_trade_decision`; o `scanner_loop` normal aplica `MAX_OPEN_POSITIONS` (default 10) antes de cada símbolo/setup usando `get_positions()` da fonte Falcon legada. A checagem do fluxo confirma que o mesmo dicionário `positions` é reutilizado durante a varredura e que `falcon_persist_accepted_signal` o atualiza (`positions[pid] = sig`) antes da gravação; em falha de sincronização, `_falcon_process_entry_signal` retorna bloqueio e arma o latch que faz chamadas PAPER seguintes serem negadas. `start_threads()` cria um scanner, e `start_central_runtime_once()` possui trava/flag de startup único no processo. Isso sustenta que o scanner normal atualiza sua contagem no mesmo ciclo; a suíte `--falcon-lifecycle-projection` passou 32 testes offline, inclusive projeção/falhas de persistência, mas não simula diretamente o limite em uma varredura completa. Já `paper_executor_integrated.execute_paper_from_engine` valida plano e idempotência, mas não impõe limite agregado. Uma reprodução sintética isolada, com ledgers em diretório temporário, rede bloqueada e 11 chaves distintas, persistiu 11 posições PAPER abertas e zero IDs de ordens reais. Isso prova que uma chamada direta ao executor pode contornar o limite a montante; não prova que o scanner normal exceda 10. O teto normal ainda depende da precisão/atualização de `get_positions()` e da ausência de outro scanner/processo/caller. Não alterei o limite nem dupliquei políticas.

Na revalidação local de 2026-11-26, `tests/run_falcon_pilot_minimal_offline.py --close-reconciliation` passou 115 testes e `--falcon-lifecycle-projection` passou 32; ambos executados no Python offline isolado, com rede/egress bloqueada e fixtures sintéticas. Eles não validam integração real com a BingX. A corrida concorrente já reproduzida no guard final LIVE para duas identidades distintas permanece um bloqueio separado para qualquer futura habilitação LIVE; não justifica C3 distribuído na topologia conhecida de uma instância/um worker, nem foi corrigida/ativada nesta etapa.

## Publicação validada de `9f6c791` — 2026-11-26

O operador enviou `9f6c7913c86fc8698137e17a6c40c7cb26e4d8d4` por fast-forward à branch `codex/prod-wsgi-20261125`; o Render MCP confirmou o deploy manual `dep-dc42dolg1s2s73d4b8v0` como `live`, no mesmo SHA, iniciado em `2026-11-26T12:32:34Z` e concluído em `12:33:55Z`. A configuração atual confirma `autoDeploy=no`, `healthCheckPath=/healthz`, comando `GUNICORN_CMD_ARGS='' gunicorn -c gunicorn.conf.py central_wsgi:app`, uma instância Standard e disco persistente `/data` de 4 GB. O Render registrou duas chamadas à rota `/healthz` entre `12:30Z` e `12:35Z`; a busca de logs de aplicação de nível error desde `12:32Z` retornou zero registros. Isso prova release e atividade da probe, não validação de login autenticado, prontidão do ledger PAPER nem prontidão de trading. O health check é uma sonda e não gatilho de deploy; com Auto-Deploy desligado, o deploy foi iniciado manualmente.

No HEAD implantado, `tests/run_gunicorn_bootstrap_offline.py` passou 24 testes em 1,47 s e `py -3.14 -I tests/run_falcon_pilot_minimal_offline.py --personal-http-auth` passou 243 em 103,09 s. `git diff --check` não apontou erros; restam avisos de conversão LF/CRLF. A tentativa intermediária com outro interpretador não coletou a suíte HTTP por falta de Flask e não conta como teste de produto. Permanecem modificados, sem stage/commit, `docs/PERSONAL_C3_NEED_ASSESSMENT_20261110.md`, este relatório e `tests/run_gunicorn_bootstrap_offline.py`; foram preservados.

Não foram alterados `/data`, variáveis, controles LIVE/PAPER, Upstash, AWS ou conta BingX, nem enviados ordens. O operador informou ausência de operações abertas; não houve conferência independente da conta nesta etapa. O executor integrado segue bloqueado por ledger PAPER ausente, e os registros legados continuam sem elegibilidade para importação automática. C3 permanece dormente; testes offline não demonstram execução real de entrada, fill, stop, posição, encerramento ou reconciliação. O release não significa prontidão de trading.

## Auditoria de I/O PAPER e C3 após `9f6c791` — 2026-11-26

Repeti no HEAD Live a suíte `py -3.14 -I tests/run_falcon_pilot_minimal_offline.py --paper-integrated-disk-guard`: **116 passaram, 13 ignorados e 12 subtestes passaram** em 234,47 s. Ela usa diretórios temporários e bloqueia rede/egress; não acessa o `/data` de produção. O inventário estático por nomes dos quatro arquivos PAPER centrais não encontrou outro leitor/escritor de aplicação fora de `paper_executor_integrated.py`, `paper_lifecycle.py`, `outcome_evaluator.py`, `execution_pipeline_status.py` (somente agrega health) e `executive_policy_learning.py` (descoberta de fontes e leitura via `paper_data_mount_verified`/`open_paper_binary`/`open_paper_text`). As rotas HTTP em `main.py` delegam a essas funções. Esse rastreio é exaustivo para referências aos nomes pesquisados no código Python, não para processos externos ou scripts que montem caminhos dinamicamente.

Revalidei a topologia para a decisão C3: a listagem read-only do workspace Render confirmado retornou apenas `central-robos-bingx`; o serviço segue com uma instância. `gunicorn.conf.py` fixa um worker, 16 threads e `preload_app=False`; executor, lifecycle e outcome compartilham `PAPER_STATE_LOCK` (`threading.RLock`), e o runtime tem inicialização única no processo. `py -3.14 -I tests/run_falcon_pilot_minimal_offline.py --c3-dormant-startup` passou **24 testes e 3 subtestes** em 398,24 s. Não há evidência concreta de que C3 distribuído seja necessário no caminho crítico pessoal atual; permanece dormente. Escritores externos/Shell concorrentes não foram enumerados, portanto uma mudança de topologia ou writer externo exige reauditoria.

Nenhuma alteração em código de execução ou produção foi feita nesta auditoria. As pendências de readiness permanecem: o operador ainda não forneceu a saída pós-deploy do health PAPER/modos; a leitura em produção de `/data` e a conta BingX não foi feita; o ledger PAPER falta e a captura antiga não oferece identidade forte para importação; a corrida de admissão LIVE e o ciclo real de entrada/fill/stop/fechamento/reconciliação não foram validados. LIVE continua fora do escopo de ativação e C3 não foi ativado.

Complemento C3: a inspeção textual no HEAD `9f6c791` contou **8** chamadas ao guard em `trade_registry.py` e **11** em `main.py` (19 no total). A suíte offline `py -3.14 -I tests/run_falcon_pilot_minimal_offline.py --registry-writers` passou **73 testes** em 144,06 s. A contagem confirma as superfícies lógicas declaradas no código; não representa 19 processos ou escritores simultâneos, e não altera a decisão de manter C3 dormente na topologia observada.

## Defesa adicional de admissão PAPER — 2026-11-26 (local, não publicada)

O rastreio da rota autenticada `/execution/engine/run` mostrou que ela aplica a política executiva e chama o Engine, mas não chama o `can_open_trade_decision` que contém o limitador global. O executor integrado validava identidade e duplicidade, mas não tinha teto agregado; `requested_qty` ausente/zero era apenas aviso. A chamada direta ao executor já havia sido reproduzida com 11 posições sintéticas, contornando o teto de 10 do scanner Falcon legado.

No worktree, acrescentei defesa em profundidade ao executor PAPER: teto agregado aplicado dentro do `PAPER_STATE_LOCK`, com `CENTRAL_PAPER_MAX_OPEN_POSITIONS` como override; fallback para `FALCON_MAX_OPEN_POSITIONS` e, na ausência, 10 (o teto normal Falcon observado). Valor zero bloqueia toda nova entrada; valor negativo/malformado falha fechado. Quantidade solicitada agora precisa ser numérica e estritamente positiva. O ledger ausente continua bloqueando e nenhum arquivo foi criado/importado.

Validação reproduzível: `py -3.14 -I tests/run_falcon_pilot_minimal_offline.py --paper-integrated-disk-guard` passou **119 testes, 13 skips e 15 subtests** em 283,69 s; os casos usam diretório temporário e o runner bloqueia rede/egress. `git diff --check` passou, com avisos apenas de conversão LF/CRLF em arquivos preexistentes modificados. Ainda não rodei a suíte completa de todo o repositório.

O SHA Live segue `9f6c791`; estas mudanças em `paper_executor_integrated.py` e `tests/test_paper_executor_integrated_idempotency_v1.py` são somente locais e não foram commitadas, enviadas ou implantadas. A alteração limita contagem de posições, não define limite monetário agregado nem demonstra entrada/fill/stop/fechamento real. Permanece necessário validar a política monetária e reconciliar a origem do ledger antes de qualquer inicialização; não ativar LIVE.

## Latch Falcon aplicado ao executor PAPER integrado — 2026-11-26 (local)

Auditoria adicional encontrou que o latch de sinais Falcon aceitos sem sincronização era consultado pelo scanner legado, mas não pela chamada direta `execute_paper_from_engine`. Agora o executor, somente quando `bot=FALCON`, lê o latch pelo storage guardado e bloqueia se o arquivo exigir reconciliação, estiver inválido ou não puder ser lido. Também consulta o indicador `HEALTH` do módulo Falcon já carregado para cobrir falha de persistência do próprio latch. A leitura ocorre sob `PAPER_STATE_LOCK`; `falcon_persist_paper_persistence_latch` agora usa o mesmo lock para serializar publicação do latch e admissão. Outros bots PAPER não são bloqueados por este latch Falcon.

Testes offline finais: `py -3.14 -I tests/run_falcon_pilot_minimal_offline.py --paper-integrated-disk-guard` passou **123 testes, 13 skips e 15 subtests** em 325,02 s; `--falcon-lifecycle-projection` passou **32 testes** em 28,04 s. Os testes usam storage temporário e bloqueio de rede/egress. Incluem latch persistido, corrompido, ausente e em memória; bloqueio sem mutação do ledger; e assertiva de que o leitor executa sob o lock compartilhado. Ainda não rodei a suíte completa do repositório nem um teste de integração dentro do processo Render.

As alterações permanecem locais, sem commit, push ou deploy. Não toquei no arquivo latch, nos ledgers, nas variáveis ou em qualquer controle LIVE. A proteção não resolve a proveniência dos registros, não autoriza criar ledger vazio e não comprova o comportamento operacional da instância; o runtime pós-deploy e a reconciliação continuam pendentes.

## Readiness visível no health PAPER — 2026-11-26 (local)

Para que o endpoint não sinalize aparente prontidão apenas porque os ledgers são válidos, `paper_integrated_health()` agora expõe `admission_ready`, `admission_status`, teto efetivo agregado e estado sanitizado do latch Falcon. Com PAPER habilitado, `ok` permanece falso se faltar/invalidar o ledger, se o teto estiver inválido ou se o latch bloquear. O novo teste cobre ledger sintético válido + latch pendente + limite efetivo configurado, sem revelar motivo/IDs do latch.

Após essa alteração, a suíte offline `py -3.14 -I tests/run_falcon_pilot_minimal_offline.py --paper-integrated-disk-guard` passou **124 testes, 13 skips e 15 subtests** em 305,85 s. Isso valida o comportamento em fixtures temporárias com rede bloqueada; não é leitura do health pós-deploy. Nenhuma publicação foi feita; HEAD continua `9f6c791` e as mudanças seguem locais. A proveniência do ledger e a autorização financeira para qualquer publicação continuam pendentes.

## Verificação operacional posterior — 2026-11-26 13:43 UTC

Render MCP confirmou somente metadados do serviço Central: deploy `dep-dc42dolg1s2s73d4b8v0` concluído como `live` no SHA `9f6c7913c86fc8698137e17a6c40c7cb26e4d8d4`, branch `codex/prod-wsgi-20261125`, Auto-Deploy desligado, uma instância Standard, disco `/data` de 4 GB, `healthCheckPath=/healthz` e start command Gunicorn com `GUNICORN_CMD_ARGS=''`. Portanto, visitar `/healthz` não dispara deploy; o deploy foi manual. A lista do Render também confirmou `0.0.0.0/0` na allowlist pública, então a exposição pública permanece e depende da autenticação da aplicação.

Nos logs desde a conclusão do deploy até 13:43 UTC, 14 probes GET de `/healthz` retornaram HTTP 200 e houve zero logs de aplicação no nível `error`. Não havia chamadas registradas para `/livestatus`. Esses fatos provam somente que a probe HTTP responde; não validam login, todas as rotas, ledger PAPER ou negociação.

Validação offline no worktree `codex/prod-wsgi-20261125`, HEAD `9f6c7913c86fc8698137e17a6c40c7cb26e4d8d4`: autenticação HTTP pessoal **243 passed**; bootstrap Gunicorn **24 passed**; `--paper-integrated-disk-guard` **124 passed, 13 skipped, 15 subtests passed**; `--registry-writers` **73 passed**; `--c3-dormant-startup` **24 passed, 3 subtests passed**; `--registry-lock-audit` **1 passed, 72 deselected**. `git diff --check` passou, com apenas avisos de conversão LF/CRLF. As suites usam isolamento e fixtures locais, bloqueiam rede/subprocessos e não leem `.env` quando indicado pelo runner.

As sete alterações locais continuam sem commit e não estão no SHA Live; seus testes não são evidência do comportamento publicado. O estado PAPER da instância não foi reconsultado depois desse deploy: a última saída fornecida pelo operador indicava ledger ausente, contagens `None` e latch de reconciliação do Falcon presente. Nenhuma leitura de arquivo de produção, Upstash ou BingX foi feita nesta verificação. Não importar, descartar ou inicializar ledgers; manter `ENABLE_REAL_TRADING=false`, `BROKER_DRY_RUN=true` e `FALCON_MODE=PAPER`. Próxima evidência manual necessária: executar no Render Shell uma leitura sanitizada do `paper_integrated_health()` e conferir que nenhuma informação bruta ou segredo seja impressa. Não houve commit, push, deploy, restart nem alteração de configuração nesta rodada.

## Suítes de ciclo e segurança de execução — 2026-11-26 14:22 UTC

Revalidei no worktree atual (`codex/prod-wsgi-20261125`, HEAD `9f6c7913c86fc8698137e17a6c40c7cb26e4d8d4`) usando o `site-packages` compatível já presente no ambiente local (`ccxt 4.5.88`, `pytest 9.1.1`, Flask 3.1.3). Nenhum pacote foi instalado. A primeira tentativa com o Python base isolado parou na coleta de três módulos por falta de `ccxt`; não foi falha de teste. Repeti com `PYTHONPATH` para o cache local; o runner nega sockets/HTTP, subprocessos e leitura de `.env` antes da coleta.

- `--personal-lifecycle-completeness`: **897 passed, 1 skipped** em 566,41 s.
- `--personal-execution-safety`: **413 passed** em 619,74 s.

Essas suítes cobrem cenários sintéticos de lifecycle, preflight, entrada/fill, stops protetores, posição, fechamento e reconciliação; não enviam ordens, não leem dados de produção e não provam integração ou execução real na BingX. Os resultados são do worktree sujo e não do deploy Live: os sete arquivos modificados permanecem sem commit/push/deploy. Não houve alteração em `/data`, Upstash, configuração, controles de trading ou serviço Render; health PAPER pós-deploy continua dependente de uma leitura sanitizada manual no Shell.

## Preservação local do hardening PAPER — 2026-11-26

Depois das verificações registradas acima, as sete alterações validadas foram preservadas no commit local `5546bc7a4936ac558b30a0e85b56b23abca639ac` na branch `codex/prod-wsgi-20261125`. A branch remota e o Render continuavam em `9f6c7913c86fc8698137e17a6c40c7cb26e4d8d4` na leitura de 2026-11-26; portanto este hardening segue **não publicado**. O commit pode ser revertido sem reescrever histórico (`git revert 5546bc7a4936ac558b30a0e85b56b23abca639ac`). Não houve push, deploy, restart, alteração de `/data`, de credenciais ou de controles LIVE/PAPER nesta etapa. Custo de build/deploy não foi confirmado como zero.

## Revalidação atual da admissão concorrente LIVE — 2026-11-26

No HEAD local `b3851ee2990be8b7c31ae435b80078013a4fae20`, `broker.py` permanece idêntico ao SHA Live `9f6c7913c86fc8698137e17a6c40c7cb26e4d8d4`. O caminho do Falcon pelo Execution Engine e o caminho direto do Predator convergem em `broker.place_market_order`; a guarda final `broker_real_pilot_guard_v1_validate` conta apenas o snapshot de `get_positions()`, sem reservar atomicamente capacidade para identidades distintas e sem consultar ordens de entrada abertas. O ledger `account_client_order_id` garante unicidade por ID de ordem, não reserva uma vaga agregada da conta.

Reextraí a função atual por AST e executei uma reprodução com dois threads, dois bots/identidades sintéticos, snapshot vazio e limite de uma posição: **2/2 guardas permitiram**. A reprodução não chamou o broker, não acessou rede nem dados de produção; prova a corrida da decisão por snapshot, não uma ordem real. A configuração Render lida em 2026-11-26 mostrava uma instância e o `gunicorn.conf.py` um worker; portanto a coordenação distribuída C3 continua sem necessidade demonstrada. Um mutex local reduziria a corrida simultânea no processo, mas sozinho não cobre resultado desconhecido nem recuperação após restart. Antes de qualquer LIVE, ainda falta uma reserva de capacidade persistente e reconciliável que inclua posições e ordens pendentes; nenhuma foi implementada ou ativada. Controles LIVE permanecem inalterados.
