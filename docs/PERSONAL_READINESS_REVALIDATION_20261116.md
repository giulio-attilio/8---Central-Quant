# Revalidação de prontidão pessoal — Central Quant/Falcon (2026-11-16)

## Conclusão

**Ainda não pronto para PAPER contínuo autônomo.** A leitura agregada recente do
Upstash ajuda a separar registros de bots, mas não reconcilia sua identidade com
o Registry nem comprova estado da conta BingX. O executor PAPER integrado deve
continuar fail-closed; não inicializar ledgers vazios e não importar/descartar
registros históricos por contagem ou status isolados.

## Evidência de origem fornecida pelo operador

O operador executou uma única consulta `MGET` das sete chaves `*:positions` e
gerou localmente somente contagens e nomes de campos. Nenhum valor de posição,
símbolo ou identificador foi compartilhado. Resultado reportado:

| Fonte | Registros | Status | Modo de execução | Marcador de fechamento | IDs explicitamente preenchidos (registros) |
|---|---:|---|---|---:|---|
| COBRA | 35 | 35 `ENCERRADO` | 35 ausente | 35 | lógico: 21; lifecycle/ordem/fill: 0 |
| DONKEY | 43 | 33 `ENCERRADO`; 10 `PARCIAL 50% + EMA20` | 43 ausente | 33 | lógico/lifecycle/ordem/fill: 0 |
| FALCON | 3 | 3 `OPEN` | 3 `PAPER` | 0 | lógico: 3; `signal_id`: 3; lifecycle/ordem/fill: 0 |
| MEME | 35 | 35 `ENCERRADO` | 35 ausente | 35 | lógico: 22; lifecycle/ordem/fill: 0 |
| SMARTPREDATOR | 43 | 43 `ENCERRADO` | 43 `PAPER` | 43 | lógico: 43; lifecycle/ordem/fill: 0 |
| TRENDPRO | 43 | 43 `ENCERRADO` | 26 `PAPER`, 1 `VERIFY`, 16 ausente | 43 | lógico: 27; lifecycle/ordem/fill: 0 |
| TURTLE | 5 | 5 `OPEN` | 5 ausente | 0 | lifecycle: 5; chave de idempotência: 5; ordem/fill: 0 |

Ao todo, 207 registros foram encontrados; 189 tinham algum marcador de
fechamento e 18 não. Os 18 são **registros possivelmente ativos no estado local
dos bots**, não posições/ordens confirmadas na corretora. A contagem agregada
posterior confirmou que os 10 DONKEY parciais não têm IDs consultados; os 5
TURTLE têm IDs de lifecycle, mas não modo explícito. O fato de uma
chave se chamar `positions` ou de um registro conter `execution_mode` não prova
fill, ownership, abertura atual na BingX ou identidade compartilhada com o
Registry.

A inspeção sanitizada do schema também mostrou que as sete respostas são
objetos indexados, com registros como valores, e não listas. Entre os campos
observados estão `live_order_id` e `bingx_order_id` no SMARTPREDATOR,
`registry_trade_id` no TRENDPRO, e os campos de ciclo/registro no TURTLE.
Presença do nome de um campo no schema não confirma que ele esteja preenchido
em cada registro. O preview reconhece os aliases de ordem existentes e agora
também reconhece `registry_trade_id` como ID lógico de revisão; nenhuma dessas
correspondências habilita importação.

Uma segunda agregação sanitizada contou registros com valores não vazios nos
campos de identidade. Nos 43 SMARTPREDATOR, apesar de o schema conter
`live_order_id` e `bingx_order_id`, nenhum registro tem IDs preenchidos nos
grupos de ordem/fill consultados. Os 3 FALCON têm apenas IDs lógicos e
`signal_id`; os 5 TURTLE têm lifecycle IDs e chaves de registro/replay. Essa
contagem não revela os valores nem comprova correspondência exata com o
Registry.

O produtor DONKEY registra o ID lógico como `DONKEY:setup:símbolo:lado`, mas
não persiste esse campo em todos os snapshots. O preview agora deriva esse ID
somente quando setup, símbolo e lado estão presentes e sem ambiguidade. A
derivação serve apenas para procurar correspondências lógicas únicas e
colisões no histórico aberto/fechado; não é prova de lifecycle e não torna
nenhuma linha importável. O preview/capturador agora calcula contagens de
matches fortes, matches review-only, colisões e órfãos no processo local; essa
comparação ainda não foi executada contra os dados reais atuais.

O contrato local do adapter V2 mostra que `registry_v2_register_idempotency_key`
é o identificador de uma operação idempotente de registro/replay, materializado
no estado do bot; não é suficiente como identidade do ciclo de vida entre
stores. Por isso o preview apenas conta sua presença, não a usa para produzir
correspondência.

Inspecionei também o produtor SMARTPREDATOR no código do deploy informado:
`trade_registry_open_result` armazena o retorno de `register_open_trade`, não
uma resposta da corretora nem confirmação de fill. O campo paralelo
`trade_registry_id` é gerado como chave lógica
`bot:setup:símbolo:lado` (`make_trade_id`); pode ser reutilizada em entradas
sucessivas do mesmo setup/símbolo/lado, portanto não prova lifecycle único. O
objeto `bots/predator.py` no commit Render `9436167...` tem o mesmo blob que o
HEAD local. Isso confirma a semântica do código dessa versão, mas não o conteúdo
dos valores armazenados no Upstash.

O preview agora classifica também cada registro fechado do Registry contra os
snapshots dos bots e informa contagens agregadas de status/modo para
`closed_trades`. Isso evita chamar de “não reconciliado” um snapshot que só
encontre correspondência no histórico fechado; colisões entre registros
abertos/fechados continuam ambíguas, e a saída continua não migrável.

Os dados recebidos contêm apenas contagens de presença de campos, não os valores
necessários a um cruzamento exato com o Registry. Nenhuma reconciliação foi
executada ou inferida a partir dessas contagens.

Para reduzir essa lacuna sem compartilhar posições ou IDs, foi criado o utilitário
local `paper_registry_source_capture.py`. Ele lê o arquivo Registry ativo e,
somente quando executado com `--read-upstash`, faz uma chamada SDK `MGET` para
as sete chaves; mantém os dados em memória, não grava arquivos e imprime apenas
contagens/estados agregados. Usa exclusivamente
`UPSTASH_REDIS_REST_READONLY_TOKEN` temporário; nunca faz fallback para o token
normal do serviço. Sem a flag, nenhuma consulta é iniciada. Se o
Registry estiver ausente/inválido, a execução para antes de consultar Upstash;
o caminho padrão só é aceito dentro do data dir configurado e, usando `/data`,
exige confirmação de mountpoint. Falha ou ausência de qualquer chave marca o
snapshot incompleto e impede correspondências confiáveis. O relatório declara
que o cruzamento Registry/Upstash não é transacional; todas as linhas seguem
inelegíveis para importação.
O utilitário ainda não foi executado contra dados reais nem está no deploy. Uma
execução real consome uso do Upstash e requer decisão financeira atual; não
reutilizei a autorização anterior, que era para outra leitura.

O relatório sanitizado inclui `source_reconciliation_counts`, com matches
fortes e review-only separados entre Registry aberto/fechado, candidatos
ambíguos/conflitantes, órfãos e snapshots incompletos. Correspondência
review-only não prova lifecycle, e nenhuma classe se torna importável. A captura
e o preview não expõem os identificadores usados no cruzamento.

Na revisão dos módulos PAPER, identifiquei que executor, lifecycle e outcome
verificavam arquivos/espaço, mas não confirmavam que `/data` continuava montado.
O import também tentava criar a pasta antes do guard. Localmente, a verificação
foi centralizada em `paper_state_storage`: leituras do ledger, writes atômicos e
criação da pasta recusam `/data` sem mount verificado; healths reportam o estado
como inválido, lifecycle/outcome não atualizam posição/estatísticas e logs não
criam arquivos nesse caso. Isso não altera nem inicializa dados de produção e
precisa ser validado no Render após uma release aprovada.

O guard compara caminho lexical/resolvido, rejeita `/data` como symlink e
componentes intermediários symlinked. Nas operações POSIX sob `/data`, abre a
raiz e percorre pais com descritores `dir_fd`, `O_NOFOLLOW` e `O_DIRECTORY`,
validando `st_dev` e IDs de mount dos descritores. A abertura do arquivo e o
`os.replace` usam esses descritores; o temporário JSON é criado no mesmo
diretório validado e recebe `fsync` antes da substituição. Isso bloqueia a troca
de um caminho pai por symlink após a abertura do descritor. Os testes Linux/WSL
cobrem symlink na raiz de teste, subdiretório, symlink relativo/final, troca do
diretório após abertura do descritor e substituição atômica de alvo symlink.

Limites: o guard comprova que `/data` é um mount separado da raiz e mantém as
operações no mount ID aberto, mas **não autentica que esse mount ID é o volume
persistente específico configurado pelo Render**. Não simula mount namespace
adversarial nem troca privilegiada de mount; falha de `/proc/self/fdinfo`
bloqueia o acesso. No Windows há fallback para paths de teste, sem a mesma
garantia POSIX; isso não é evidência para produção Linux.

A inspeção dos módulos PAPER confirma bloqueio de entrada quando falta o ledger
de posições; se falta o cache de idempotência, uma chave nova também é
bloqueada. Uma chave já presente no ledger de posições é tratada como replay e
pode reconstruir o cache; esse caminho está coberto por teste. Lifecycle e
Outcome recusam atualizar posições quando o ledger está ausente. A ausência do
arquivo `seen` bloqueia uma chave nova; uma chave já registrada no ledger de
posições continua sendo reconhecida como replay e pode reconstruir o cache, sem
abrir uma segunda posição. Executor, lifecycle, outcome, adaptive weights,
pipeline status, policy learning, history memory e mapper usam os helpers
guardados nos acessos examinados aos arquivos PAPER/relacionados. Isso não é uma
prova AST exaustiva de cada destino dinâmico de I/O no repositório.
`get_outcome_stats` separa estatística presente de ausente/inválida.
`adaptive_weights.py` e
`execution_pipeline_status.py` também tinham `DATA_DIR.mkdir()` no import; isso
foi substituído por inicialização guardada. Pesos agora recusam leitura/escrita
quando o mount não está verificado, escrevem JSON atomicamente e propagam falha
de persistência; o pipeline reporta contagens `None` e status explícito para
mount ausente, estatística ausente ou inválida, em vez de exibir zeros como se
fossem observados.

O inventário por nomes de arquivos PAPER não encontrou leitores do ledger
integrado em `main.py`: as rotas delegam aos módulos guardados. Isso não prova
cobertura de todo I/O persistente do repositório: `history_manager.py` e várias
rotinas independentes em `main.py` ainda têm I/O direto para outros históricos,
auditorias e estados. Um inventário AST global com classificação de destinos
dinâmicos continua pendente. O uso de descritores reduz TOCTOU para as operações
protegidas, mas não prova identidade do disco Render nem cobre automaticamente
esses outros arquivos/sistemas.

O preview mantém `eligible_for_import=False` para todas as linhas e marca
explicitamente `cross_store_atomic_snapshot=False`. A captura lê o Registry e
depois solicita `MGET`; as contagens são evidência de presença/ausência nas
duas amostras, não uma reconciliação transacional nem prova do estado da
BingX. O cruzamento exato sobre dados reais não foi executado.

## Estado Render observado novamente (somente leitura)

Em 2026-11-16 UTC, nova consulta somente leitura ao MCP confirmou
`central-robos-bingx` no workspace `Central Quant`
(`tea-d8gnnuojo6nc73ep3lg0`), Live no SHA
`9436167fe1944da0017252630cb5ac2cbd3eb9aa` (deploy
`dep-dbt2mcoae00c739g7po0`). O serviço está ligado à branch
`codex/personal-readiness-20261103`, com auto-deploy desligado, uma instância
Standard, disco persistente de 4 GB em `/data` e `healthCheckPath` vazio. O HEAD
local `035d79a71ddc79694d51d0771992c30ad2297de0` está em outra branch de trabalho
e não corresponde à branch configurada nem ao SHA Live.

Em 2026-11-17 UTC, nova leitura MCP somente de metadados confirmou o mesmo SHA
Live, uma instância e nenhum outro serviço listado nesse workspace. A branch
configurada continua `codex/personal-readiness-20261103`, auto-deploy desligado,
disco de 4 GB em `/data` e health check vazio. Isso não inspeciona os arquivos
do mount nem confirma os flags atuais do processo.

As referências oficiais atuais do Render confirmam que deploys com disco
persistente não têm garantia de zero downtime e que a opção do Dashboard para
deploy de SHA específico desliga auto-deploy. Sem `healthCheckPath`, o Render
usa probe TCP, que não valida os ledgers nem a prontidão lógica do executor.
Fontes: [deploys](https://render.com/docs/deploys.md) e
[health checks](https://render.com/docs/health-checks.md), consultadas em
2026-11-16. Auto-deploy já estava desligado; não alterei esse controle.

As métricas recentes mostraram uma instância durante toda a janela consultada,
uso de memória aproximadamente entre 851 MB e 1,06 GB, e CPU entre 0,13 e 0,65
na unidade bruta retornada pela API. A série filtrada para `/healthz` teve
latência p95 de 4 a 530 ms, com aproximadamente uma requisição por bucket de
cinco minutos. A série de latência p95 do host inteiro incluiu alguns buckets
entre 5,5 e 8,5 s para respostas HTTP 200; sem discriminação por rota, isso não
identifica a causa nem demonstra que o endpoint de health falhou. Não fiz
requisição ao endpoint. A consulta de logs filtrada por nível `error` retornou
12 registros; as mensagens não foram inspecionadas, então não atribuo causa nem
severidade operacional a eles.

O SHA Live continua diferente do HEAD local `035d79a71ddc79694d51d0771992c30ad2297de0`; há alterações locais não commitadas/não rastreadas. Nenhum push ou deploy
foi executado. Essa leitura é atual para o instante da consulta, não uma prova
de que todos os arquivos PAPER no `/data` estejam íntegros ou reconciliados.

## Validação local desta retomada

Worktree preservado: branch `codex/falcon-paper-persist-guard-20261115`, HEAD
`035d79a71ddc79694d51d0771992c30ad2297de0`. Alterações preexistentes não foram
descartadas: `tests/run_falcon_pilot_minimal_offline.py` continua modificado e
os módulos/testes de preview e captura continuam não rastreados. O helper e seu teste foram ampliados localmente para
reportarem contagens agregadas por bot de status, modo, marcadores de fechamento
e presença de campos de identidade, sem imprimir valores. `eligible_for_import`
continua sempre falso.

O novo capturador foi testado apenas com um Redis falso. A saída de Shell inclui
contagens estruturais de identidade/fechamento, mas omite valores arbitrários
de `status` e `execution_mode` vindos dos snapshots. Seus testes verificam
uma única chamada MGET, sanitização, chave ausente, JSON inválido, erro do
cliente, Registry ausente/inválido, quantidade incorreta de respostas, mount
não verificado/data dir divergente e que a flag explícita é necessária para
iniciar a leitura. Outro teste garante que o token normal não é usado quando
falta o token temporário read-only. Nenhum secret ou serviço externo foi acessado.

Testes executados no Python temporário `cq-readiness-tests`:

- `tests/run_falcon_pilot_minimal_offline.py --personal-lifecycle-completeness`:
  893 passaram, sem skips, em 824,27 s após centralizar o guard de mount PAPER.
  Foi usado o ambiente
  temporário existente com `ccxt 4.5.88`/`pytest 9.1.1`; nenhuma dependência foi
  instalada pela rede. Uma tentativa inicial no Python global falhou na coleta
  porque `ccxt` não estava instalado e não conta como validação.
- `tests/test_paper_registry_source_preview.py`: 35 passaram em 0,27 s (reexecutado nesta retomada).
- `tests/run_falcon_pilot_minimal_offline.py --paper-registry-source-preview`:
  35 passaram em 0,19 s (reexecutado nesta retomada).
- `tests/run_falcon_pilot_minimal_offline.py --paper-registry-source-capture`:
  12 passaram em 0,24 s, com rede bloqueada e Redis falso.
- `--registry-writers`: reexecutado nesta retomada; 60 passaram em 67,50 s.
- `--c3-dormant-startup`: reexecutado nesta retomada; 24 passaram e 3 subtestes
  passaram em 553,36 s.
- `--personal-http-auth`: reexecutado nesta retomada; 243 passaram em 95,70 s.
- `--paper-integrated-disk-guard`: antes do guard compartilhado, 53 passaram e
  12 subtestes passaram em 1,41 s.
- Após a centralização do guard de mount, `tests/test_paper_executor_data_dir_resolution_v1.py`,
  `tests/test_paper_executor_integrated_idempotency_v1.py` e
  `tests/test_outcome_evaluator_closed_identity_v1.py`: 59 passaram e 12
  subtestes passaram em 1,40 s; `--paper-integrated-disk-guard`: 61 passaram e
  12 subtestes passaram em 1,40 s após o guard compartilhado.
- Após a checagem de symlink, os três arquivos acima reexecutados: 60 passaram,
  12 subtestes passaram, sem skips, em 1,38 s. A suíte completa de 893 testes
  passou após o guard compartilhado, antes deste refinamento de symlink.
- Após a revisão crítica e os guards de Adaptive Weights/Execution Pipeline,
  sete módulos PAPER/captura/preview passaram: 113 testes, 12 subtestes, sem
  skips, em 2,88 s. Após os guards finais dos leitores de log/estatísticas,
  esses módulos passaram novamente: 114 testes, 12 subtestes, sem skips, em
  3,65 s.
- Após a revisão de caminho por arquivo, o runner offline
  `--paper-integrated-disk-guard` passou: 69 testes e 12 subtestes, sem skips,
  em 2,33 s. Inclui regressão para bloquear leitura/append quando o guard do
  caminho exato do JSONL falha e para bloquear nova entrada se o caminho do
  ledger não for validado. Nenhuma instalação de dependência foi feita; o
  executável do venv temporário havia sido removido, então reutilizei o Python
  local com o `site-packages` já existente.
- Após essas alterações, a seleção offline ampla
  `--personal-lifecycle-completeness` terminou com 892 testes passados e 1
  ignorado, em 868,13 s. O único skip foi
  `test_upstash_httpx_redis_get_timeout_with_mock_transport`, condicionado a
  `httpx` e `upstash_redis`, ausentes no ambiente temporário. Não instalei
  dependências pela rede; esse contrato SDK/HTTP permanece sem validação nesta
  execução. Depois da suíte ampla, acrescentei o mesmo guard ao helper genérico
  `_read_json` do executor e reexecutei `--paper-integrated-disk-guard` com 69
  testes e 12 subtestes aprovados. O runner manteve bloqueio de rede e diretório
  temporário isolado.
- **Validação completa reexecutada após o guard de mount, symlinks e guard de
  import/status:**
  `tests/run_falcon_pilot_minimal_offline.py --personal-lifecycle-completeness`
  no ambiente temporário existente com `ccxt 4.5.88`: 893 passaram, sem skips,
  em 1.859,01 s. O runner bloqueia sockets, DNS, `urllib`, subprocessos e leitura
  de `.env`, e usa diretório de dados temporário isolado. Nenhuma dependência foi
  instalada pela rede. Essa execução antecedeu apenas os últimos guards de
  leitura de logs/estatísticas; estes foram cobertos pela execução focada acima.
  A primeira tentativa no Python global falhou por falta de `ccxt`; ela não
  conta como validação.
- `git diff --check`: sem erros.

Validação adicional em 2026-11-17 após os últimos ajustes de leitura de
histórico/mapper: `--history-memory-state-io` passou com 52 testes; o teste de
importação isolada foi repetido separadamente com funções de rede bloqueadas.
`--paper-integrated-disk-guard` passou com 75 testes, 6 skips POSIX no Windows
e 12 subtestes; os testes POSIX de symlink/mount passaram em Linux/WSL (8),
outcome em Linux/WSL (15), mapper em Linux/WSL (10), captura (14) e preview
(38). A reexecução completa `--personal-lifecycle-completeness`, usando o
`site-packages` local existente com `ccxt 4.5.88`, passou com 892 testes e 1
skip em 1.087,87 s. Sem baixar dependências nem permitir rede. A execução
`--personal-lifecycle-no-ccxt` também passou com 766 e 1 skip, mas não substitui
a seleção completa. Dois testes de fsync são POSIX-only e passaram no teste
Linux/WSL de outcome; o runner Windows os marca como skip.

Revalidação adicional em 2026-11-17, no Python atualmente selecionado neste
checkout: `--personal-lifecycle-completeness` falhou na coleta de
`test_broker_entry_fill_stop_sizing_v1.py`,
`test_broker_managed_entry_cancel_v1.py` e
`test_real_close_reconciliation_v11.py` por `ModuleNotFoundError: ccxt`. Não
instalei dependências nem usei rede; o pip não listou wheel local de `ccxt` e o
Python do WSL também não tem o pacote. A seleção documentada
`--personal-lifecycle-no-ccxt` passou com 766 testes e 1 ignorado em 954,03 s,
mas exclui esses três módulos e não substitui a suíte completa. Os resultados
anteriores com `ccxt 4.5.88` permanecem evidência histórica de outro ambiente,
não da instalação Python selecionada agora.

Essas são validações locais do código/fixtures; não provam integração de
produção, execução de ordens, fills, gestão de posições ou comportamento atual
do serviço hospedado.

## C3

Manter C3 preservado e dormente. A avaliação local de necessidade datada de
2026-11-10 descreve uma topologia de uma instância/processo com `/data`, lock
local e `RLock`; os 19 writers são callsites, não 19 writers concorrentes
comprovados. Nesta retomada, as seleções de writers e startup dormente passaram
novamente. O operador forneceu leitura atual do Shell Render, mas ela não inclui
uma nova auditoria de concorrência/locks; não houve ativação de signer/lease ou
acesso a AWS. As condições de backup/restauração externa, âncora/assinatura e
recuperação de produção seguem não demonstradas; portanto os gates para ativar
C3 não estão satisfeitos nem são necessários com a evidência disponível.

Em 2026-11-17, a listagem MCP confirmou uma instância e nenhum serviço
concorrente no workspace; os 19 writers seguem sendo pontos de código, não uma
medição de concorrência real. Não há evidência concreta de necessidade de C3
distribuído no serviço pessoal atual. Preservar o código, manter a integração
default-off e depender de locks locais no processo normal; job/processo
independente futuro que escreva Registry exigiria nova análise.

Revalidação local em 2026-11-17: `c3_closed_repair_writer_coordination_status_v1`
retornou `C3_WRITER_COORDINATION_DORMANT_DEFAULT_OFF`, `enabled=false`, zero
writers registrados e `runtime_activation_allowed=false`; o inventário canônico
contém 19 pontos de escrita declarados e o lock do Registry é um `RLock` do
processo. A auditoria AST de saves diretos passou (1 teste), e a suíte de
read-modify-write dos writers passou (60 testes), exercitando contenção entre
threads. Isso reforça a decisão de manter C3 dormente para a topologia de uma
instância/processo observada, mas não prova exclusão mútua entre processos
independentes: um novo serviço ou job externo que escreva o mesmo Registry
exigiria revisão e coordenação explícita. Nenhum teste C3 foi ativado e não houve
acesso a dados de produção.

## Pendências que impedem conclusão

1. Fazer cruzamento sanitizado, um-para-um, entre os 18 registros sem marcador
   de fechamento e as coleções abertas/fechadas do Registry, incluindo colisões
   e aliases. A contagem atual mostra zero IDs explícitos de lifecycle/ordem/fill
   em DONKEY (há agora uma derivação lógica revisada localmente, ainda sem match
   sobre os dados reais); Falcon tem somente IDs lógicos/`signal_id`; Turtle tem
   lifecycle IDs sem modo explícito. Os valores não foram compartilhados, então
   ainda não houve match exato. Não substituir identidade por símbolo/lado.
2. O operador informou BingX Real sem posições/ordens abertas às 20:40 de
   16/11/2026. Essa leitura pode suportar a janela operacional naquele horário,
   mas deve ser refeita imediatamente antes de qualquer interrupção posterior;
   ela não atribui ownership aos registros PAPER.
3. **Leitura atual do Render Shell recebida em 16/11/2026, 23:39:** flags de
   trading real seguras, `/data` montado e 4 GB, mas os dois arquivos de estado
   PAPER e o log integrado estão ausentes; `paper_integrated_health` retorna
   `ok=false`/`PAPER_STATE_FILES_MISSING`. Sem inicializar arquivos vazios nem
   importar histórico sem reconciliação.
4. Confirmar que a versão validada localmente é exatamente a versão implantada,
   com custo e janela operacional revistos. A consulta somente leitura ao
   histórico do Render confirmou o deploy Live `9436167fe1944da0017252630cb5ac2cbd3eb9aa`, criado em 2026-11-15T16:17:17Z e concluído em 2026-11-15T22:00:28Z. Ele não corresponde ao HEAD local `035d79a71ddc79694d51d0771992c30ad2297de0`. Nenhum push/deploy foi feito nesta etapa.
5. Depois de reconciliar a proveniência, completar prova PAPER integrada de
   entrada, fill, posição, disaster stop, fechamento, restart/reconciliação e
   persistência sem emitir ordens LIVE.

Não acessei secrets nem fiz chamadas a BingX ou Upstash. O operador forneceu
leituras manuais do Render Shell e da BingX, com os respectivos horários
descritos acima; as consultas externas do assistente limitaram-se a metadados
somente leitura do serviço e deploys no Render. Não alterei
`ENABLE_REAL_TRADING`, `BROKER_DRY_RUN` ou `FALCON_MODE`; não enviei ordens e
não fiz commit, push, merge ou deploy.

## Adendo de verificação em 2026-11-17

O runner offline completo foi reexecutado no checkout `035d79a71ddc79694d51d0771992c30ad2297de0`, usando o `site-packages` temporário existente com `ccxt 4.5.88` via `PYTHONPATH`; resultado: 892 passaram e 1 foi ignorado em 1.957,05 s. Nenhuma dependência foi instalada e o runner manteve seus bloqueios de rede e dados temporários isolados.

A seleção `--registry-writers` passou com 60 testes em 123,48 s. A cobertura inclui auditoria AST dos `save_registry` diretos e contenção entre threads para sete writers read-modify-write de `main.py`; ela não prova coordenação entre processos independentes. A seleção C3 dormente mais âncoras estáticas teve 24 testes e 3 subtestes aprovados, mas 3 testes de âncora falharam: os spans absolutos de funções não acompanham o `main.py` atual, e a expectativa de erro por scope drift é mascarada primeiro pelo erro de span. Isso não habilita nem testa ativação C3; registrar como dívida dos testes de source-anchor, mantendo C3 dormente.

Nova leitura de metadados MCP confirmou o serviço Render `central-robos-bingx` em uma instância Standard, disco persistente de 4 GB em `/data`, auto-deploy desligado e Live no SHA `9436167fe1944da0017252630cb5ac2cbd3eb9aa`. O HEAD local e as alterações não commitadas/não rastreadas permanecem fora dessa release. O Shell manual confirmou os interlocks (`ENABLE_REAL_TRADING=false`, `BROKER_DRY_RUN=true`, `FALCON_MODE=paper`, paper habilitado e os dois flags real falsos). A verificação sanitizada também mostrou Registry presente e URL do Upstash configurada, mas `paper_registry_source_capture` e `paper_registry_source_preview` ausentes no Live, assim como `UPSTASH_REDIS_REST_READONLY_TOKEN`. Nenhum novo MGET foi feito; a leitura cruzada continua pendente e nenhum arquivo PAPER foi criado.

**Estado operacional inalterado:** não inicializar ou importar o ledger, não ativar C3 e não inferir prontidão do status Live. Próxima etapa da reconciliação depende de uma forma validada de executar o cruzamento no ambiente que contém `/data`, de credencial Read-Only temporária e de autorização financeira específica para uma nova leitura Upstash; a autorização anterior cobriu uma única consulta já consumida. A nova captura/preview foi validada apenas localmente e permanece fora da release Live.

Atualização de evidência recebida do Render Shell após esse adendo: `capture_module=False`, `preview_module=False`, `rest_url_set=True`, `readonly_token_set=False` e `registry_file_present=True`. Isso confirma que os módulos locais de captura/preview não podem ser importados no runtime Live e que não há credencial Upstash Read-Only temporária disponível no ambiente; não usar o token normal da aplicação como substituto. Nenhuma leitura MGET adicional foi executada.

Revalidação local, sem alteração de arquivos além deste relatório, dos testes de captura e preview: `python -m pytest -q tests/test_paper_registry_source_capture.py tests/test_paper_registry_source_preview.py` passou com 54 testes em 0,78 s. A chamada direta ao launcher `pytest` falhou na coleta porque não incluiu o checkout no caminho de importação; repetir por `python -m pytest` resolveu sem contornar os testes. Isso valida o comportamento local, não disponibilidade no Render nem reconciliação com os dados atuais.

Nova consulta MCP somente leitura nesta continuação confirmou que o deploy Live continua em `9436167fe1944da0017252630cb5ac2cbd3eb9aa`, branch `codex/personal-readiness-20261103`, uma instância Standard, disco de 4 GB montado em `/data`, auto-deploy desligado e `healthCheckPath` vazio. O coletor local permanece fora dessa release; não houve leitura de Shell/logs nesta consulta, MGET, alteração de configuração ou deploy.

Verificação read-only do repositório nesta continuação: `git log --all -- paper_registry_source_capture.py paper_registry_source_preview.py` não encontrou versão commitada desses módulos em refs locais; a branch remota examinada também não contém o coletor. Portanto, não há cópia publicada pronta para invocar no Render Shell sem nova mudança de código. Nenhum push ou deploy foi feito.

Revalidação POSIX local em WSL dos testes de resolução e armazenamento: os mesmos dois módulos passaram com `37 passed` em 8,32 s, agora sem skips. A repetição desabilitou o autoload de plugins do pytest e substituiu chamadas de socket por uma função que falha, bloqueando rede; assim foram exercitados os casos Linux de `dir_fd`/`O_NOFOLLOW`, symlinks e armazenamento atômico, além dos casos portáveis. É evidência local do guard, não teste no disco montado do Render. A primeira tentativa Windows dos mesmos módulos também passou nos casos portáveis (29 passados, 8 ignorados por exigirem POSIX). `git diff --check` continuou sem erros; apenas reportou aviso de normalização LF/CRLF já existente.

Inventário estático direcionado dos quatro nomes dos ledgers integrados PAPER: os callsites em `paper_executor_integrated.py`, `paper_lifecycle.py`, `outcome_evaluator.py`, `execution_pipeline_status.py`, `executive_policy_learning.py` e `registry_v2_wal.py` usam as APIs de `paper_state_storage` para leituras/escritas; as rotas HTTP observadas em `main.py` delegam aos módulos de lifecycle/executor. Não encontrei `open()`/`Path.read_text()` direto ligado a esses caminhos na busca. Isto é uma verificação por referências/callsites direcionados, não uma prova formal de ausência de todos os possíveis acessos dinâmicos/reflexivos; e o código validado continua não implantado.

Nova execução offline dos testes de âncora C3, com sockets bloqueados: os 3 testes falharam como gate fechado. Comparação AST sintetizada encontrou spans fixos divergentes em 8 writers de `trade_registry.py` e nos 11 writers de `main.py`; os placement lines ficam fora do span canônico em 7 e 11 casos, respectivamente, e o verificador de escopo C3 dos 11 casos `main.py` fica falso. A expectativa de teste de scope-drift é mascarada primeiro por `FUNCTION_LINE_SHIFT_DENIED`. Não atualizei os spans nem relaxei o harness: isso exige reancoragem explícita da fonte, revisão das placements e dos hashes/recibos do contrato. Como a evidência de uma instância e locks locais não demonstra necessidade do coordenador distribuído, C3 permanece preservado e dormente; esses testes não autorizam ativação.

Auditoria AST independente por nome de função, sem usar os spans fixos obsoletos e sem importar/executar os módulos: 19/19 writers declarados têm exatamente uma definição e um `with` lexical que recebe o identificador daquele writer no guard C3 primeiro e o lock local (`_lock` no `trade_registry.py`, `registry_lock` no `main.py`) em segundo. Isso confirma a estrutura textual atual dos 19 scopes; não prova alcançabilidade em runtime, ativação do C3, concorrência entre processos, nem necessidade do coordenador. A falha do contrato de spans permanece registrada e C3 segue dormente.

Revisão adversarial offline do coletor: `paper_registry_source_capture.py` lê somente `UPSTASH_REDIS_REST_READONLY_TOKEN` e não cai para `UPSTASH_REDIS_REST_TOKEN`; o CLI exige `--read-upstash`; faz uma chamada `mget` com as sete chaves; os relatórios de captura omitem IDs e valores arbitrários e deixam todos os registros inelegíveis. Limite importante: uma variável de ambiente dedicada não prova criptograficamente que o valor inserido tem privilégio Read-Only; essa confirmação depende do operador copiá-lo da opção Read-Only do Upstash, sem expô-lo nem compartilhar a resposta bruta. Além disso, essa versão permanece local/não implantada, e nenhuma leitura Upstash de produção foi feita.

Melhoria da execução manual em 2026-11-17: o CLI local ganhou `--prompt-readonly-token`, que usa entrada oculta e falha fechado se o terminal não suportar entrada sem eco. A opção só solicita o token quando `--read-upstash` também foi explicitamente passado; não persiste o valor em variável de ambiente. Testes WSL/pytest com sockets bloqueados para captura e preview: `56 passed` em 8,02 s; as verificações usam cliente falso e não executam MGET nem leem segredos. `git diff --check` sem erros (permanece o aviso pré-existente de normalização LF/CRLF em um teste). A saída sanitizada continua afirmando `all_rows_ineligible_for_import=true` e `writes_performed=false`, mesmo para matches diagnósticos.

Nova confirmação manual do operador no Render Shell em 2026-11-17: `capture_module=False`, `preview_module=False`, `rest_url_set=True`, `readonly_token_set=False`, `registry_file_present=True`. Isso não autoriza nem permite rodar o coletor no processo Live: os módulos não existem na release e a credencial dedicada Read-Only não está configurada ali. Não configurar o token de aplicação como substituto, não criar ledgers vazios e não transferir ou colar dados brutos no chat. A etapa de reconciliação permanece pendente; nenhuma chamada Upstash real, exportação do Registry, importação ou deploy foi executado.

Revalidação adicional em WSL em 2026-11-17, com sockets bloqueados, dos módulos de persistência e consumo PAPER: armazenamento Render, executor/idempotência, outcome, status do pipeline e projeção de lifecycle Falcon passaram com `84 passed, 12 subtests passed` em 25,91 s. Isso exercita somente fixtures e armazenamento temporário; não cria os arquivos `/data` reais, não demonstra comportamento da release Live e não valida entrada/fill/fechamento com corretora.

Revalidação MCP Render somente leitura em 2026-11-17: o serviço permanece `central-robos-bingx`, uma instância Standard, disco `/data` de 4 GB, auto-deploy desligado e `healthCheckPath` vazio. O deploy Live continua no SHA `9436167fe1944da0017252630cb5ac2cbd3eb9aa`; nenhuma implantação ocorreu nesta continuação. O inventário de ferramentas Render disponível permite metadados/deploys/logs, mas não expõe Shell nem leitura de arquivos do disco, portanto não substitui o operador para executar o coletor. Isso mantém a divergência entre a release Live e os módulos locais; sem nova autorização/custo confirmado, não fiz push/deploy nem MGET.

Revisão da barreira HTTP pessoal em 2026-11-17: `main.py` registra um `before_request` global de Basic Auth antes das rotas; a única exceção deliberada é GET `/healthz` sem query, que retorna só liveness e continua submetido às barreiras de origem e prontidão. A suíte `tests/test_personal_http_auth_gate_v1.py` passou com `161 passed` em 33,67 s no Python 3.14 local, com chamadas de socket/conexão bloqueadas. A primeira tentativa no WSL não coletou porque Flask não está instalado nesse interpretador; nada foi instalado. Paridade de fonte verificada: o SHA Live `9436167fe1944da0017252630cb5ac2cbd3eb9aa` é ancestral do HEAD local; o blob de `personal_http_auth.py` no SHA Live, no HEAD e no arquivo de trabalho tem o mesmo hash; os diffs do SHA Live até o HEAD e as alterações locais em `main.py` não modificam o gancho global nem a função de decisão de autenticação. Isso dá evidência de que a barreira testada localmente existe na fonte implantada, mas não comprova comportamento efetivo do processo/ambiente Live; nenhum GET público foi feito nesta continuação.

Seleção adicional de regressão em Windows em 2026-11-17, com conexões de socket bloqueadas: sete módulos alterados ligados a resolução de diretório, fail-closed do executor/orchestrator, auditoria de armazenamento, relatórios PAPER, adapter e WAL do Registry passaram com `239 passed` em 39,01 s. Esses casos cobrem o comportamento portátil; não substituem os testes POSIX de `dir_fd`/symlink no WSL nem comprovam I/O no disco real `/data` do Render. Nenhuma dependência foi instalada.

Seleção de startup/readiness em Windows em 2026-11-17, conexões bloqueadas: `test_falcon_real_pilot_preflight_fail_closed_v1.py`, `test_trade_registry_live_entry_storage_readiness_v1.py`, `test_startup_disk_forensics.py` e `test_c3_dormant_startup_same_coordinator_v2.py` concluíram com `136 passed, 1 skipped` em 681,53 s. O único skip é o caso de symlink em `test_startup_disk_forensics.py`, que explicitamente pula quando symlink não está disponível na plataforma Windows; os testes POSIX de `/data` guard/symlink já passaram separadamente em WSL. Isso continua sendo teste local com fixtures, não preflight de produção nem validação de estado atual da corretora/Render.

Auditoria de release local em 2026-11-17: o checkout permanece em `035d79a71ddc79694d51d0771992c30ad2297de0`, três commits após o Live `9436167fe1944da0017252630cb5ac2cbd3eb9aa`. Os commits incluem `0130a01 fix(paper): harden local registry audit and risk snapshots`; o delta rastreado desde o Live abrange 9 arquivos, inclusive `main.py` (+82/-22), `registry_v2_migration_audit.py` (+44/-11) e os testes correlatos. Além disso, há 23 arquivos rastreados modificados no worktree e 10 arquivos não rastreados, incluindo os guardas PAPER e o comparador; isso ainda não é uma release reprodutível/limpa. O branch local coincide com seu `origin` local, mas o serviço Render está ligado a outro branch e com auto-deploy desligado. O catálogo de ferramentas MCP não expõe billing/uso; portanto não há confirmação de custo zero. Nenhum push/deploy foi iniciado. Antes de publicar seria necessário concluir e congelar o candidato, validar todo o estado de trabalho preservando as alterações do usuário, revisar o diff final e obter evidência financeira/autorização específica.

Revalidação adicional do ciclo pessoal em 2026-11-17 no checkout atual `035d79a71ddc79694d51d0771992c30ad2297de0`: `tests/run_falcon_pilot_minimal_offline.py --personal-lifecycle-completeness` passou com `893 passed` em 849,38 s. O runner nega sockets/rede, subprocessos e acesso a arquivos `.env` e usa diretório de dados temporário. Para satisfazer a dependência broker já cacheada, o `PYTHONPATH` apontou para um `site-packages` temporário preexistente com `ccxt 4.5.88`; nada foi instalado nem escrito nessa pasta. O resultado cobre fixtures e contratos de entrada/fill/cancelamento/stops/fechamento, não prova uma ordem ou fill real, integração com a conta BingX, persistência no Render ou prontidão LIVE.
