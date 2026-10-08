# Candidato isolado dos nove writers — 13/09/2026

## Estado

Candidato local montado em
`.offline_releases/nine_writers_candidate_20260913/r2/src`.
**352 testes aprovados, zero falhas/erros/skips, em 218,59 segundos.**
Hashes conferidos após os testes, tanto no candidato quanto no laboratório;
manifesto final em `r2/final_evidence_manifest.json`. A aprovação é exclusivamente
offline, não uma homologação operacional ou autorização de publicação.

Nada foi publicado, instalado em produção ou ativado. A preparação local usa
somente código e testes; não contém Registry real, histórico operacional,
credenciais, laboratório Linux ou distribuição Python.

## Origem e escopo

Base Git disponível LOCALMENTE:
`17e767c14b7c90c97a01bc5173f4fd94985672cc`. Não foi feito fetch nem confirmação do
estado atual do GitHub/Render. Esta base já contém o preflight com
`read_only=True`. Não foi usada a branch main local antiga.

Antes da geração, os corpos originais das duas correções anteriores foram
comparados com a base, usando o RED congelado; os sete restantes também conferem.
O transporte veio do GREEN congelado, verificado pelo manifesto da rodada de 264
testes, não da cópia integral do worktree modificado.

Em `main.py`, somente estes nove corpos foram transportados:

- `_trs_v1_manual_register_open_trade`;
- `_rtlm_v1_update_open_trade_snapshot`;
- `registry_persistence_v12_recover_closed_trade_from_params`;
- `trade_close_outcome_v1_commit`;
- `registry_mode_segregation_v1_analyze`;
- `mark_registry_missing_trades`;
- `predator_paper_registry_sync_fix_v1_status`;
- `predator_registry_orphan_open_fix_v1_status`;
- `predator_auto_closed_sync_v1_status`.

Os corpos coincidem com os já testados. Assinaturas, decoradores e todos os
demais nós de topo foram conferidos por AST contra a base. O lock existente
envolve a leitura–modificação–gravação; ausência de lock impede o commit. Não foi
introduzido coordenador, wrapper, monkey patch ou comportamento operacional novo.

Startup, flags, gates, `trade_registry.py` e `runtime_seam_v1.py` permanecem da
base. As mudanças locais de manutenção/startup foram explicitamente excluídas.
Fontes originais e manifestos históricos não foram alterados.

## Arquivos diferentes da base

Além de `main.py`, somente as cópias destes arquivos diferem no candidato:

- `tests/test_registry_two_writers_atomic_rmw_v1.py` e
  `tests/test_registry_remaining_writers_atomic_rmw_v1.py`: testes novos já
  existentes no GREEN, agora transportados ao candidato.
- `tests/test_trade_close_outcome_semantic_recurrence_v1.py` e
  `tests/test_trade_registry_closed_identity_residual_guards_v1.py`: dependência
  sintética do lock nas fixtures.
- `tests/test_main_traderegistry_sync_v2_ownership.py`,
  `tests/test_predator_orphan_open_fix.py`,
  `tests/test_predator_auto_closed_registry_sync.py` e
  `tests/test_predator_daily_summary_registry_sync.py`: fixtures já validadas,
  incluindo lock/admissão sintéticos e delimitação correta da seção auto-sync.
- `trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_contract_v1.py`
  e seu `tests/test_trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_v1.py`:
  apenas SHA-256 e tamanho do novo main.
- `trade_registry_closed_identity_conflict_repair_runtime_readiness_preflight_patch_plan_contract_v1.py`
  e seu `tests/test_trade_registry_closed_identity_conflict_repair_runtime_readiness_preflight_patch_plan_v1.py`:
  apenas o novo SHA-256 do binding acima.
- `trade_registry_closed_identity_conflict_repair_writer_seam_binding_contract_v1.py`:
  dez coordenadas de linha reatestadas entre os 19 writers; assinaturas,
  estratégias, marcadores, decisões e restrições inalterados.
- `tests/helpers/c3_nine_writer_candidate_lab.py`: ferramenta de validação,
  explicitamente separada do payload operacional. Seu modo de coleta inicial foi
  substituído, para esta validação, pelo launcher externo `run_full.py`.

São 14 arquivos de payload/teste e um auxiliar de validação diferentes da base.
O inventário completo contém 560 arquivos selecionados de fonte/configuração.
Os 56 itens excluídos foram classificados por metadados, sem ler seu conteúdo.

Ferramentas criadas fora de `src`, na pasta do candidato:
`build.py`, `build_r2.py`, `run.py`, `run_full.py` e `seal.py`. São ferramentas
locais de geração/verificação; não instalar em runtime. Também foram gerados
`candidate.review.patch`, `source_manifest.json` e diretórios de evidências, nas
revisões inicial e r2. Este relatório e `C3_OFFLINE_CONTINUITY_20260911.md`
registram a continuidade.

## Verificações e ocorrências

1. Sintaxe das fontes Python selecionadas verificada sem importar a aplicação.
2. Primeira coleta: bloqueada antes de executar testes, pois o launcher proibia
   também a seam dormente importada pelo Registry. Evidência preservada em
   `evidence/`; não foi falha de um writer.
3. Validação com árvore completa e a mesma barreira de imports do laboratório
   anterior: 299 aprovações, cinco falhas e 48 erros de preparação entre 352
   casos. Causa comum: dez números de linha antigos; o preflight estático bloqueou
   corretamente e o bloqueio propagou para os harnesses dependentes.
4. R2 preserva o candidato inicial e altera somente esses números, depois de
   comprovar identidade, assinatura e decoradores das 19 funções. A inversão
   desses números reproduz byte a byte o contrato anterior.
5. A rodada final usa a árvore inteira de fontes selecionadas, mas somente a
   suíte dirigida de 352 casos. Isso não é a suíte completa do repositório.
   Todos passaram na r2, incluindo concorrência, identidade, locks, falhas de
   save, preflight/readiness, os 19 writers, controles negativos e rejeição de
   adulteração da fonte. Evidências em `r2/evidence-full/`.

Um cache de bytecode do helper, gerado na primeira preparação pelo Python do
host, foi movido para `evidence/host-helper-cache.cpython-314.pyc`, fora das fontes.
É recuperável; nenhum arquivo do usuário foi apagado. As execuções seguintes
usam `-B`. Python dos testes: 3.11.9, já instalado; nenhum download ou instalação.

Laboratório sem rotas de rede, uid não privilegiado, fontes somente leitura,
scratch ext4 sintético, ambiente limpo, sem mounts Windows/home ou dados reais.
Hooks anteriores à coleta bloqueiam rede, subprocessos, leitura de secrets e
imports de main/bots/broker/execução. O Registry e a seam dormente são usados
somente nesse ambiente sintético; a aplicação não é inicializada.

## Identificação do candidato

- Main SHA-256: `2c04c752b0fed634bc2344d8a2cba13132ffe4652e1dea01e6575d316b41a52e`.
- Inventário r2 SHA-256: `6aaddd91e34c0f39724a0788fa3ef8ea1b75e7a6fe0fb24c51094f25fa00f31b`.
- Manifesto de fontes r2 SHA-256: `0ad18a9bfd86e90d920ec36a2cc3046ad2e16ed2da3e4f48af5a1ccbc0f50ecd`.
- JUnit final SHA-256: `1880ea547e178bb08682cbe018a2aa932d54784f2a79b514476789aef388d559`.
- Patch de revisão r2 SHA-256: `063f3e001aedf313c8bb58441552300543bed82ecede7739c71b19a6a979ce93`.

Trocar referências de integridade após verificar o delta não concede readiness
nem permissão para ativação.

## Limites e segurança

As correções continuam locais ao processo. Não comprovam exclusão entre
processos/hosts, WAL/recovery, relógio/lease, persistência de produção ou segurança
de Live. Não houve benchmark; manter o lock durante planejamento pode aumentar
contenção. Callers sem lock falham fechado.

Os demais contratos históricos/offline da base, incluindo os mapas detalhados
de source-anchor/transaction-placement, não foram migrados nem homologados por
esta suíte. Não confundir o preflight estático do candidato com homologação de
toda composição C3 ou autorização de release.

Não executados: suíte global, servidor, bots, preflight operacional, broker,
reinício real, bootstrap ou reparo real. Nenhum secret ou dado real foi acessado.
Nenhuma chamada operacional externa, commit, push, merge, pull, fetch ou deploy;
nenhuma configuração de trading real ou ordem foi alterada/executada. A consulta
de rede limitou-se à documentação pública OpenAI sobre automatismo.

OpenAI Docs foi usado apenas para conferir/manter o automatismo, não para mudar
a lógica da Central. Referência: [tarefas agendadas](https://learn.chatgpt.com/docs/automations?surface=app).

Modelo recomendado: GPT-6 Astra — Alto; nenhuma troca de modelo executada.
Percentual restante para Live: indeterminado; falta uma validação operacional
atual e não há denominador verificável para um percentual.

## Próximo passo finito

Revisão SOMENTE LEITURA da elegibilidade de publicação deste candidato: distinguir
metadados históricos não consumidos pelo runtime de dependências efetivamente
necessárias, e produzir uma lista curta de pendências/limites para publicação.
Partir do candidato r2 e das evidências acima; não regenerar o pacote ou repetir
os mesmos testes sem mudança ou achado novo. Não iniciar nova família de wrappers,
contratos ou estudos de infraestrutura. Não executar commit/push/deploy nem
alterar produção. Automatismo existente mantido ativo para essa revisão local;
nenhum OK genérico é necessário.
