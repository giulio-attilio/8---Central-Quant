# C3 — auditoria somente leitura dos 19 writers (2026-10-04)

## Atualização posterior — prevalece sobre a fotografia abaixo

A fotografia original deste arquivo foi feita **antes** da revisão local dos
limites de transação e dos contratos de âncoras. Suas afirmações de que os 11
writers de `main.py` usam um decorador C3 sobre a função inteira e de que o
preflight local ainda tem 10 âncoras divergentes **não descrevem mais a fonte
atual**. Ela fica abaixo apenas como histórico da lacuna que foi investigada;
não deve ser usada para decidir release ou LIVE.

Na fonte atual, os 8 writers de `trade_registry.py` usam contextos C3 locais.
Os 11 writers de `main.py` também usam blocos `with` delimitados, com C3 antes
do lock local; os caminhos de restore e bootstrap mantêm o contexto externo
durante a chamada recursiva com `_lock_held=True`. A revisão de AST verifica
início/fim desses blocos, leitura fresca e gravação nas linhas contratadas,
mas não é ensaio físico de exclusão entre processos nem prova de que todo
writer fora do inventário respeita a mesma trava.

Em laboratório WSL isolado, três suítes de âncoras e preflight terminaram com
**53 testes aprovados em 113,73 s**. O launcher comprovou zero rotas de rede,
ausência de montagens Windows e fontes somente leitura. O preflight estático
local passou e seus testes confirmaram os 19 writers; `production_ready` e
`live_allowed` permaneceram falsos. Nenhum módulo `main.py` foi iniciado como
aplicação.

**Bloqueio que permanece:** a montagem em `main.py` ainda cria o coordenador e
a fronteira de recuperação em modo dormente/default-off. A verificação física
agregada é opcional e não está ligada nessa montagem. Portanto os testes
estáticos e os recibos locais não comprovam, no alvo de produção, que os 19
writers, Registry, WAL e ledger RESOLVED usem um único domínio físico de lock e
maintenance lease. Não habilitar o coordenador nem promover recibos sintéticos
para `production_ready`; a próxima etapa exige composição e ensaio físico
separados, com autorização específica antes de qualquer alteração operacional.

Nenhum código foi alterado nesta atualização; nenhum secret foi acessado,
nenhuma chamada externa, commit, push, deploy ou alteração de configuração de
trading real foi feita.

## Escopo e método

Revisão estática de `trade_registry.py`, `main.py`, do contrato de posições `trade_registry_closed_identity_conflict_repair_runtime_writer_transaction_placement_contract_v1.py`, do contrato de âncoras `trade_registry_closed_identity_conflict_repair_runtime_writer_source_anchor_contract_v1.py` e da semântica do contexto C3 em `trade_registry_closed_identity_conflict_repair_runtime_seam_v1.py` / `trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1.py`. As fontes foram lidas como texto/AST; não foram importadas nem executadas como aplicação. Nenhum Registry, secret, broker ou serviço externo foi acessado.

Este relatório **não** aprova atualização de âncoras, instalação/ativação do coordenador, release, deploy ou LIVE. O gate estático continua falhando fechado em `WRITER_SOURCE_ANCHORS_MATCH_AUDITED_CONTRACT` (10 divergências de âncora).

## Matriz de fontes

Os oito writers de `trade_registry.py` têm início e fim da função iguais aos do contrato de âncoras e o arquivo não difere de `HEAD`. Cada função mantém `_c3_closed_repair_writer_mutation_v1(...)` em um bloco `with` sobre a escrita:

| Writer | Função (linhas atuais = contratadas) | Gravação atual |
| --- | --- | ---: |
| `TRADE_REGISTRY_LOAD_INITIALIZE_OR_MIGRATE` | `load_registry` 263–287 | 274, 280 |
| `TRADE_REGISTRY_REGISTER_OPEN_TRADE` | `register_open_trade` 366–440 | 433 |
| `TRADE_REGISTRY_UPDATE_OPEN_TRADE` | `update_trade` 443–466 | 459 |
| `TRADE_REGISTRY_UPDATE_CLOSED_TRADE` | `update_closed_trade` 603–745 | 731 |
| `TRADE_REGISTRY_HISTORICAL_STRONG_IDENTITY_BACKFILL` | `backfill_historical_strong_identity` 2714–2814 | 2800 |
| `TRADE_REGISTRY_RECORD_MANUAL_CLOSE_OUTCOME` | `record_manual_close_outcome` 2853–3017 | 3001 |
| `TRADE_REGISTRY_CLOSE_TRADE` | `close_trade` 3098–3252 | 3244 |
| `TRADE_REGISTRY_RESET` | `reset_trade_registry` 3302–3309 | 3306 |

Nos 11 writers de `main.py`, a coluna “gravação contratada” é o alvo do contrato de colocação, não uma recomendação de substituição. “Atual” indica a chamada encontrada na fonte. O bootstrap tem quatro alvos de escrita de naturezas diferentes.

| Writer `MAIN_*` | Span contratado → atual | Gravação contratada → atual |
| --- | --- | --- |
| `SYNC_MANUAL_REGISTER_OPEN` | 4489–4536 → 4489–4540 | 4528 → 4532 |
| `LIFECYCLE_UPDATE_OPEN_SNAPSHOT` | 7250–7295 → 7254–7305 | 7290 → 7300 |
| `PERSISTENCE_RESTORE_LATEST_SNAPSHOT` | 9860–10008 → 9870–10018 | 9991 → 10001 |
| `PERSISTENCE_RECOVER_CLOSED_TRADE` | 10187–10368 → 10197–10407 | 10328 → 10344 |
| `TRADE_CLOSE_OUTCOME_COMMIT` | 11146–11277 → 11185–11333 | 11263 → 11308 |
| `REGISTRY_MODE_SEGREGATION_COMMIT` | 11716–11815 → 11772–11877 | 11761 → 11823 |
| `MARK_REGISTRY_MISSING_TRADES` | 14791–14839 → 14853–14905 | 14831 → 14897 |
| `PREDATOR_PAPER_REGISTRY_SYNC` | 49455–49714 → 49529–49805 | 49593 → 49679 |
| `PREDATOR_ORPHAN_OPEN_FIX` | 49891–50090 → 49982–50197 | 50016 → 50123 |
| `PREDATOR_AUTO_CLOSED_SYNC` | 67750–67957 → 67867–68074 | 67851 → 67967 |
| `TRADE_REGISTRY_STORAGE_BOOTSTRAP` | 50667–51058 → 50774–51165 | 50966/50974/51036/51045 → backup 51073, Registry ativo 51081, status 51143, evento ~51148 |

O writer manual é o controle negativo relevante: sua linha inicial continua 4489, mas o contrato aponta 4528, que hoje fecha a montagem de um dicionário; `save_registry` ocorre em 4532. Logo, conferir apenas início de função não prova colocação da gravação. Nos outros dez, a linha inicial também mudou. Há mudanças de corpo, não só deslocamento uniforme de linhas.

## Divergência de escopo da transação

Todos os 11 writers de `main.py` usam `@c3_runtime_seam_v1._c3_closed_repair_writer_mutation_v1(...)` sobre a função inteira. Esse objeto é um `ContextDecorator`: seu `__enter__` chama `coordinator.mutation(writer_id)` e o `__exit__` só o libera ao retornar da função. Com o coordenador habilitado, `mutation` adquire o lock compartilhado até o fim do contexto. Assim, os blocos efetivos são **mais amplos** do que as seções curtas `acquire_before_line`/`release_after_line` do contrato de colocação.

Exemplos concretos:

- `predator_paper_registry_sync_fix_v1_status`: coleta/auditoria começa em ~49541, antes do lock local em 49583; o decorador C3 já estaria ativo durante essa coleta, embora o contrato exija `external_collection_outside_coordinator=True`.
- `registry_persistence_v12_recover_closed_trade_from_params`: a gravação do Registry é em 10344, mas snapshot/evento auxiliares são gravados após isso em ~10371–10373, ainda dentro do decorador; o contrato requer `sidecar_io_outside_coordinator=True`. O lock local termina antes do sidecar, mas isso não encerra o contexto C3 externo.
- `trade_close_outcome_v1_commit`: `save_registry` em 11308, sidecar/evento em 11314–11315, ambos dentro do contexto C3 da função; o contrato também requer sidecar fora do coordenador.
- `registry_mode_segregation_v1_analyze`: a gravação do Registry ocorre em 11823 e o sidecar em ~11870–11871, ainda sob o decorador.
- Restore e bootstrap adquirem o lock local e se chamam recursivamente com `_lock_held=True`; a análise estática superficial da segunda chamada isolada não equivale a provar ausência de lock. Essa reentrada, o token C3 e os caminhos de exceção precisam de teste específico antes de aceitação.

Os oito writers de `trade_registry.py` usam o contexto C3 em torno do trecho de mutação, não como decorador da função inteira. Em `record_manual_close_outcome` e `close_trade`, a observação shadow vem depois do bloco de gravação.

## Conclusão e próxima decisão

**Não atualizar apenas os números de linha.** Isso poderia remover o bloqueio estático sem demonstrar que coleta externa, sidecars e reentradas respeitam a topologia prometida. Primeiro é necessário decidir e implementar, com autorização explícita separada, os limites reais de coordenação dos 11 writers de `main.py` e revalidar cada leitura fresca, gravação, retorno, exceção e token reentrante. Depois, e somente depois, revisar como conjunto as 19 âncoras, spans, marcadores de colocação, hashes/precondições, recibos dependentes e controles negativos. A validação deve continuar em laboratório local sem rede; nenhuma promoção a produção decorre de um preflight verde por si só.

Nenhum código foi alterado nesta auditoria. Os testes de runtime não foram repetidos porque a revisão só leu fontes; a rodada isolada imediatamente anterior terminou com 499 testes e 28 subtestes aprovados e três falhas estáticas já conhecidas.
