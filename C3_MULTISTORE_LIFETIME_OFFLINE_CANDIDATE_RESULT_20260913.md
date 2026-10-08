# C3 — candidato complementar de recuperação multistore

## Entrega concluída

Preparado e testado exclusivamente offline em
`.offline_releases/multistore_lifetime_candidate_20260913`.
Origem: candidato same-coordinator/r2 selado, sobre db3a560. São nove diferenças
incrementais, 18 diferenças acumuladas do payload e 563 arquivos de contexto.
Main, mapas dos writers e backend físico de armazenamento foram preservados.
Nenhuma nova implementação operacional, publicação ou ativação foi realizada.

A implementação já existente na worktree foi transportada com suas dependências:
posse dos dois locks durante ambas as chamadas, validação de cada recibo antes
do próximo store, cópias independentes dos argumentos, soltura na ordem inversa
e recusa de sucesso quando a soltura não é confirmada. A prova do permit consulta
o frame proprietário atual, thread/processo, mesma instância e lease persistido.
Uma permissão de manutenção encerrada não pode ser reutilizada.

## Dependências e arquivos alterados no candidato

Todos os nomes abaixo são relativos a `src` do candidato. Fontes originais da
worktree permanecem intocadas.

1. `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2.py`: transporte do hardening de locks, vínculos e posse atual.
2. `trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1.py`: frame de manutenção, validação do permit vigente, revogação local antes do cleanup e suporte maintenance-only. Dependência indispensável: o adapter chama `maintenance_permit_is_current_v1`, inexistente na base anterior.
3. `trade_registry_closed_identity_conflict_repair_runtime_seam_v1.py`: exclusivamente quatro linhas existentes que recusam promover coordenador maintenance-only. Essa proteção acompanha o modo; não há chamada de instalação/runtime.
4. `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_harness_v2.py`: mesmo backend/lease e namespaces sintéticos explícitos; permit obtido durante lease real, apenas em diretório temporário do laboratório.
5. `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2.py`: regressão existente usa lease sintético vigente.
6. `tests/test_c3_multistore_lock_proof_v2.py`: 31 casos existentes de locks, contenção, deadline de aquisição, falhas e limpeza.
7. `tests/test_c3_multistore_maintenance_lifetime_v2.py`: 28 casos existentes de validade de ownership e regressão de mutações/reentrada.
8. `tests/test_c3_multistore_cross_binding_order_v2.py`: dez casos existentes de vínculos e ordem dos stores.
9. `tests/test_c3_multistore_candidate_dormant_seam.py`: dois casos novos, somente fragmento AST da recusa no seam e factory default-off.

Também criados na raiz do candidato: PLAN.md, build.py, run.py,
test_dormant_seam.py (origem do teste novo), manifesto, patch e evidências.
Helper Linux permanece validation_only. Criado este relatório e atualizado o
topo da continuidade. Nada foi gravado nas fontes originais ou no index Git.

## Validação

Uma rodada no candidato exato: **101 aprovados, zero falhas, erros ou skips**.
Distribuição: 31 locks + 28 lifetime + 10 vínculos + 5 adapters + 2 seam/factory
+ 25 montagem dormente herdada. Não somar com os resultados anteriores como
se fossem testes exclusivos ou progresso percentual para Live.

Linux, Python 3.11.9 existente, UID999, zero rotas, fontes read-only, scratch
ext4 sintético e sem acesso a mounts Windows/home. Imports de main, Registry,
broker/bots e execução de subprocessos foram bloqueados antes dos testes.
Os testes não acessaram rede. Todos os 563 hashes conferem após execução e
coincidem com o inventário exportado. Oito donors, main dirty, HEAD e index
originais permanecem iguais aos valores anteriores.

A primeira tentativa do preparador tentou analisar agents.md como Python e
parou antes de criar `src`; corrigido o filtro para somente `.py`. Não foi falha
de aplicação nem do ensaio. A rodada de testes completou sem timeout externo.

Manifesto SHA-256: `d8aa8bdc2c76a83bdc59e2f297c768c459133b27e4efe7606b5b37828ef2e2a4`.
Inventário: `a4971a7631ef7e63ce4405da8d80fd7cbb39fce789947745693238a4b895ad9a`.
Patch incremental: `f249a4bca3b75e95dc541ddcb11ee611142315b4b5064fbd5ea47e13e7afd978`.
JUnit: `a70adff7ec6acfcd5c15561c3ef7babb1382a901d394cbd695cf5d7d2cbc3027`.
Evidências: `evidence/results.xml`, `tests.txt`, `location.json` e inventário de exportação.

## Limites e próxima fronteira

Não foram executados suíte integral do repositório, recovery de WAL real,
reinício/concorrência de processos em produção, preflight ou homologação no Render.
O teste de contenção usa handles físicos distintos no laboratório; não prova
coordenação de todos os 19 writers no alvo. Ports de store e autoridade continuam
sintéticos; hashes de objetos/arquivos não substituem autenticação de produção.
O deadline limita aquisição dos locks, não interrompe callbacks bloqueados.

Concluídas as duas preparações offline delimitadas. Não criar outra rodada de
contratos/testes idênticos apenas para atividade. A próxima fronteira continua
ser implementação e homologação das dependências reais de autoridade/revogação,
consumo durável independente de restauração, relógio e recuperação, com escopo
operacional específico. Os estudos existentes não autorizam comprar infraestrutura,
criar chaves, migrar, publicar ou ativar esse candidato. Esta entrega não comprova
remoção dos dois bloqueios do último preflight. Percentual restante Live: indeterminado.

Nenhum secret, .env ou dado real acessado; nenhuma chamada à Central/Render/BingX/
Redis/Telegram; nenhum commit, push, deploy, ordem ou flag de trading alterada.
Consulta externa fora dos testes somente à documentação OpenAI para atualizar
o automatismo: https://learn.chatgpt.com/docs/automations?surface=app.

Automatismo permanece ativo, sem processo técnico pendente e sem repetição agendada
desta etapa. Não é preciso OK para o trabalho offline já concluído; a passagem
à operação real depende de uma decisão específica de escopo, não de OK genérico.
Modelo recomendado: GPT-6 Astra — Alto.
