# Central Quant/Falcon — revalidação pessoal (2026-11-25)

## Escopo e segurança

Revalidação local do checkout isolado `codex/prod-wsgi-20261125`, baseado no
SHA Live `3502638ea3d364a21078b4d687f1353ec69bdd5e`. O worktree principal não
foi alterado. Sem credenciais, secrets, payloads brutos, chamadas à corretora,
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
