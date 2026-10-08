# C3 — correção das referências offline, candidato r3

## Estado

Correção concluída exclusivamente na cópia isolada r3: 378 testes aprovados,
zero falhas, erros ou skips. Os hashes de todos os 560 arquivos do candidato e
do laboratório foram conferidos após os testes. Evidência selada em
r3/final_evidence_manifest.json. R2 e todas as tentativas foram preservados.
Não há processo de validação pendente. Isto não autoriza publicação ou Live.

## Causa e alterações

As nove correções de leitura–modificação–gravação alteraram o tamanho e a
estrutura das funções. Dois mapas offline continuavam apontando para o código
anterior. O harness recusava os intervalos, corretamente, com
FUNCTION_LINE_SHIFT_DENIED. Isso não representa onze novos defeitos de trading.

Base da revisão: r2 em
.offline_releases/nine_writers_candidate_20260913/r2. A r3 altera somente:

- trade_registry_closed_identity_conflict_repair_runtime_writer_source_anchor_contract_v1.py:
  onze intervalos MAIN, quatro marcadores de leitura e inventário de locks;
  agora são 18 marcadores (sete de módulo, oito locais e três condicionais).
- trade_registry_closed_identity_conflict_repair_runtime_writer_transaction_placement_contract_v1.py:
  coordenadas reais dos onze caminhos MAIN, incluindo as oito posições de lock
  antes ausentes. Classificações, protocolo e requisitos de segurança preservados.
- trade_registry_closed_identity_conflict_repair_runtime_writer_source_anchor_harness_v1.py:
  reconhecimento do leitor raw e de duas formas condicionais exatas de lock.
  Formas arbitrárias continuam rejeitadas.
- tests/test_trade_registry_closed_identity_conflict_repair_runtime_writer_source_anchor_v1.py:
  expectativas atualizadas, conferência AST independente e controles negativos.

Todos os caminhos acima são relativos a
.offline_releases/nine_writers_candidate_20260913/r3/src.
Os outros 556 arquivos, incluindo main, Registry, startup, seam e gates, são
idênticos ao r2. Inventário total: 560 arquivos. São 19 arquivos diferentes da
base Git local17e767c, incluindo o auxiliar de validação já presente no r2.

## Testes e escopo da prova

- RED no r2: 1 falha, 1 aprovação e 18 erros de preparação, em 19,94 s.
  Preservado em r2/evidence-red-anchor.
- Primeira tentativa r3: 25 aprovações e 1 falha no teste AST novo, em 45,04 s.
  Todos os vinte casos antigos passaram. A expectativa nova exigia leitura e
  gravação diretamente no corpo do mesmo with para todos os onze caminhos.
- Restauração e bootstrap, que não foram modificados pelas nove correções,
  usam retorno recursivo sob lock com _lock_held=True. Logo, essa expectativa de
  formato não se aplica a eles. O teste agora exige chamadas e coordenadas reais
  nos onze casos e contenção direta estrita nos nove corrigidos. Não comprova
  segurança de todos os callers do parâmetro privado ou integração operacional.
- A primeira tentativa permanece em r3/evidence-green-anchor; manifesto e patch
  correspondentes foram movidos, sem exclusão, para source_manifest.anchor-first.json
  e candidate.review.anchor-first.patch. O laboratório conserva as fontes exatas.
- Regressão final inclui os 352 casos anteriores e os 26 casos de source-anchor.
  Não representa a suíte global do repositório.
- A primeira regressão ampliada atingiu o orçamento externo de 420 segundos.
  Não há aprovação nem contagem final dessa execução. Última amostra: processo
  de testes ativo, 99,8% de CPU. Laboratório preservado em
  /var/tmp/cq-c3-lab-nine-full-v_cr3n2f; resumo em
  r3/evidence-green-full-timeout/summary.json. O launcher original não exportou
  a saída parcial no timeout; essa limitação está registrada, sem inventar log.
- A repetição usa run_anchors_retry.py, orçamento externo de 900 segundos e
  log contínuo. Não altera deadline interno, fonte candidata ou teste. O aviso
  de sessão systemd foi observado; o processo Python de preparação foi confirmado.
- Repetição concluída, exit0: 378 casos únicos aprovados. Fontes somente leitura
  e ausência de rotas confirmadas. Evidências em r3/evidence-green-full-retry;
  laboratório /var/tmp/cq-c3-lab-nine-full-8nnpijju.
- Duração bruta reportada pelo JUnit: 30033,865 s, anômala em relação ao orçamento
  externo de 900 s, que não expirou. A causa temporal não foi diagnosticada.
  Não usar essa duração como benchmark, prova de deadline ou homologação de
  relógio/lease. A conclusão é funcional e vinculada às fontes, não temporal.

Laboratório Linux Python3.11.9 existente, sem instalações, usuário não
privilegiado, namespace sem rotas de rede, fontes somente leitura e armazenamento
temporário ext4 sintético. Hooks anteriores à coleta bloqueiam sockets,
subprocessos, secrets e imports operacionais. main é somente dado para AST.

## Integridade e ferramentas

Main candidato preservado:
2c04c752b0fed634bc2344d8a2cba13132ffe4652e1dea01e6575d316b41a52e.

Inventário final r3:
2629e2ad6edc0c0302c5d640f8c73feb24cbd7741da59c9b926bcbf3f5321da1.

Manifesto de fontes:
e21d24306f83f36f22603a6e848c456fab8933fb451ad6dc56ce7ed9657e3791.

JUnit final:
5a95dfae766cf9f50defa5e844186cce0c712e720b12cedf937639300ac1858c.

Patch cumulativo de revisão:
a1937ce470e13549e3035c8aa0fdea54d38d7a0907248f8cb4cd6a1baa2c1e50.

Main original do worktree preservado:
6e2f5718282f553ae089a301faa6d1488a0b8ef883455aebc6dca426dd2efdf2.

Ferramentas locais criadas nesta etapa, fora de src:
run_anchors.py, run_anchors_retry.py, prepare_r3.py e seal_r3.py. Também gerados manifesto, patch de
revisão e evidências da r3. Não transportar ferramentas, laboratórios ou
evidências para runtime. Este relatório e C3_OFFLINE_CONTINUITY_20260911.md
registram a conclusão e continuidade.

## Limites

Os mapas descrevem requisitos declarativos de uma coordenação futura.
Atualizar coordenadas não instala coordenador interprocessos, não prova
WAL/recovery, relógio/lease, persistência de produção ou readiness de Live.
Os campos de coleta externa/sidecar fora do coordenador são requisitos, não
evidência de que o runtime publicado os cumpre. Nenhum novo wrapper ou protocolo
foi criado. A revisão não homologa toda a composição C3.

Nenhum secret, .env, token, Registry real ou histórico foi acessado. Nenhuma
chamada operacional externa, ordem, alteração de flags, commit, push, merge ou
deploy foi executada. Consulta pública OpenAI Docs apenas para manutenção do
automatismo, fora dos testes. Produção e trading real não foram alterados.

Modelo recomendado: GPT-6 Astra — Alto. Percentual restante para Live:
indeterminado, sem base objetiva para estimativa.

Próximo passo finito: revisão somente leitura do patch cumulativo r3 e de sua
elegibilidade de publicação, usando a evidência pronta. Entregar lista curta de
pendências e separar aprovação offline de autorização operacional. Não repetir
testes sem novo achado, regenerar pacotes ou criar contratos. Automatismo ativo
para essa revisão; não é autorização de commit/push/deploy ou reparo real.
