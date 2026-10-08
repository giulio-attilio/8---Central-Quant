# C3 — candidato isolado de coordenador único, concluído offline

## Resultado

Preparado o candidato r2 em `.offline_releases/same_coordinator_candidate_20260913/r2`,
sobre a base publicada `db3a560dc555158997004bbe7d08738d318dd528`.
São dez arquivos de payload alterados; o contexto sintático possui 559 arquivos,
incluindo um helper exclusivo de validação. Nenhuma publicação ou ativação.

A construção passa uma única instância dormente do coordenador aos adapters e
aos interlocks. Troca de instância, pin divergente ou configuração habilitada
é rejeitada antes da instalação. A montagem não chama providers nem faz I/O.
O preflight estático exige o grafo e a guarda, não somente nomes de builders.

O primeiro ensaio revelou uma dependência adicional real: a fixture do harness
de projeção ainda modelava o grafo antigo. O validador fortalecido recusou-a,
causando duas falhas e 48 erros de preparação nos testes dependentes. Corrigido
somente o gerador de strings sintéticas e seus controles negativos; o gate não
foi flexibilizado. A primeira revisão e sua evidência permanecem preservadas.

## Testes e limites da evidência

- Primeira revisão: 123 casos, 73 aprovados, duas falhas e 48 erros de fixture.
- R2: 62 aprovados, zero falhas/erros/skips e sem timeout externo. Inclui os dois
  módulos de readiness afetados e cinco verificações novas da fixture.
- Todos os 50 casos anteriormente falhos/erro foram aprovados no R2. A união
  dos casos aprovados tem 128 identificadores únicos, descontando sete repetidos.
  Isso NÃO é uma rodada única de 128 sobre r2. As 66 aprovações não repetidas
  pertencem ao núcleo/testes preservados da primeira revisão.
- Mesma instância, troca de instância, default-on, pin inválido, ausência de
  guarda, chamada anterior à guarda, bindings e vetor completo foram cobertos.
- Linux/Python 3.11.9 existente, UID não privilegiado, rede sem rotas, origem
  read-only, scratch ext4 sintético; imports de main/Registry/broker/bots negados.
  Rede e subprocessos bloqueados antes da coleta dos testes. Conftest/plugins
  externos desativados. Não foram instaladas dependências.
- Todos os 559 hashes do candidato conferidos novamente após os testes.
- Não executados: suíte integral do repositório, runtime, preflight real,
  recovery real, reinício de produção ou qualificação de providers reais.

## Diff e arquivos do payload

Todos os caminhos abaixo são relativos ao diretório `r2/src` do candidato,
não alterações nas fontes originais da worktree:

1. `main.py`: uma atribuição global e três nós de montagem/instalação.
2. `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2.py`: referências opcionais inertes, factory e validação da identidade dormente.
3. `trade_registry_closed_identity_conflict_repair_runtime_static_preflight_v1.py`: exigência do grafo explícito e da guarda inicial.
4. `trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_contract_v1.py`: somente hashes/tamanhos afetados.
5. `trade_registry_closed_identity_conflict_repair_runtime_readiness_preflight_patch_plan_contract_v1.py`: somente hash do binding.
6. `trade_registry_closed_identity_conflict_repair_runtime_installation_preflight_projection_harness_v1.py`: projeção sintética compatível e controles negativos ajustados.
7. `tests/test_c3_dormant_startup_same_coordinator_v2.py`: transporte dos 20 testes existentes e cinco novos casos da fixture.
8. `tests/test_trade_registry_closed_identity_conflict_repair_runtime_static_preflight_v1.py`: mock baseado apenas em nomes agora deve falhar.
9. `tests/test_trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_v1.py`: expectativa do novo pin de main.
10. `tests/test_trade_registry_closed_identity_conflict_repair_runtime_readiness_preflight_patch_plan_v1.py`: expectativa do novo pin do binding.

Ferramentas locais criadas: `build.py`, `run.py`, `prepare_r2.py` e `r2/run.py`
na raiz do candidato; manifestos, patches e evidências separados do payload.
`tests/helpers/c3_linux_lab.py` é validation_only, não arquivo de release.
Criado este relatório e atualizado o topo de `C3_OFFLINE_CONTINUITY_20260911.md`.

## Integridade, exclusões e riscos residuais

Manifesto R2 SHA-256: `df70ccd13194ac4c2a3e57e970076059971e7d70ca157fa21a18f0840c621866`.
Inventário R2: `c44bb0bdf9d3aa53408d801eeefee37a773ce8c8e94ebcd894ca1de1b9e56658`.
Main candidato: `3cd7dfe93c9f9e549c4eb490a786b99af8345aaa250958575494d1afe89ec93f`.
JUnit R2: `af755ec11edb64b5463f1d525eaf52156373ed73df518426b2bc2794f4d09145`.

Patch sobre db3a560: `candidate.review.patch` da primeira revisão, seguido de
`r2/fixture.review.patch`. Manifestos explicitam as dez alterações finais.
As fontes de main fora dos três nós escolhidos e da nova atribuição foram
comparadas por AST. Coordenador, seam, Registry e mapas dos 19 writers são
idênticos à base. Os hashes dos seis donors conferem com a captura inicial.
HEAD original d9e12e9, main dirty 6e2f5718 e index 861b693e preservados.

`recover_multistore_v2` continua idêntico à base publicada: este pacote NÃO
transporta o hardening ativo de locks/lifetime existente na worktree. O argumento
opcional `_lock_backend` apenas fica guardado, sem efeito na recuperação da base.
Não há lock físico, raiz autenticada ou readiness de produção inferidos desse
vínculo. Binder separado de manutenção e providers reais ficaram excluídos.

Nenhum secret, arquivo .env ou dado real foi acessado. Nenhuma chamada à Central,
Render, BingX, Redis ou Telegram. Nenhum commit, push, deploy ou alteração de
configuração de trading. Testes inteiramente sem rede. Fora dos testes houve
somente consulta à documentação oficial OpenAI para manter o automatismo:
https://learn.chatgpt.com/docs/automations?surface=app.

## Próximo passo

A etapa 1 do plano C3_INTEGRATION_NEXT_STEP_R3_20260913.md terminou. Não repetir
o pacote ou o preflight concluído. Próxima ação segura: preparar e validar,
em candidato complementar exclusivamente offline, o hardening de locks/lifetime
da recuperação multistore já implementado localmente e excluído deste pacote.
Reutilizar componentes e testes, sem novo contrato ou provider fictício promovido
a produção. Se surgir dependência operacional nova, parar nessa fronteira.

Publicação, providers reais, domínio físico dos 19 writers e recuperação no alvo
ainda não foram homologados. Os dois bloqueios do preflight continuam sem prova
de remoção. Percentual restante para Live: indeterminado.
Modelo recomendado: GPT-6 Astra — Alto. Automatismo ativo; próximo trabalho
offline agendado, sem novo OK. Nenhum processo técnico ficou pendente desta rodada.
