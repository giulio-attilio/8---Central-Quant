# C3 — coordenador compartilhado na composição de manutenção offline

11/09/2026. Concluída a unidade de injeção explícita, sem integração operacional.

## Atualização — cadeia conjunta concluída

Retomada de 11/09 às 14:58 UTC: autorização pública, manutenção e boundary de
recuperação foram compostos no mesmo teste com o mesmo coordenador. Somente
testes e seleção do laboratório mudaram nesta retomada; nenhum módulo funcional,
startup ou configuração de produção foi editado.

- `tests/test_trade_registry_c3_maintenance_activation_offline_v1.py`: extrai a
  preparação existente para `recovery_composition_options`, reaproveitada pelos
  quatro casos anteriores e pela matriz conjunta; nenhum novo harness operacional.
- `tests/test_c3_public_authority_offline_v2.py`: 10 novos casos conjuntos:
  sucesso, assinatura inválida, revogação pública, raiz revogada, raiz expirada,
  lease perdido, deadline, cópia do coordenador, recibo do primeiro store
  adulterado e relatório de escrita no Registry. Negação da autorização impede
  todos os callbacks; falha no primeiro store impede o segundo. Recriar os
  chamadores não reutiliza o claim consumido, mesmo com novo prazo assinado.
- `tests/helpers/c3_dependency_assembly_lab.py`: perfil público inclui essa
  matriz e os quatro casos que reutilizam a preparação refatorada.
- Este relatório, continuidade e proposta atualizados com o resultado final.

Resultado: **21 aprovados, zero falhas/erros/skips, 2,19 s**; 10 novos e 11 de
regressão afetada. Evidência:
`.offline_validation/c3_dependency_assembly_20260911/cq-c3-lab-assembly-jr9ye6k8/`.
JUnit SHA-256:
`e38ad3e7383517776e2d7398fd565f5f4e8137d04785e0f0bbace3d2f2a67f2e`.
Todos os overlays atuais conferem com esse resultado; as execuções anteriores
abaixo permanecem históricas e não devem ser somadas como testes exclusivos.

O orçamento usa o relógio sintético 100.0 compartilhado entre coordenador e
manutenção; a raiz usa época sintética 1500. O teste de expiração da raiz não
altera o relógio de orçamento. O teste de deadline avança o orçamento sem voltar
o relógio no retry. Isso demonstra separação de domínios, não sincronização de
relógios ou deadlines de transporte de produção. Os atestados originais mantêm
flags e hash intactos; relatório de escrita continua recusado.

A próxima unidade indicada no histórico abaixo está concluída. Não repetir a
composição ou criar mais camadas apenas para atividade. Permanecem as lacunas
operacionais da proposta: conta/identidade e custódia da raiz, implementação dos
providers persistentes e homologação no destino, fora da autorização offline.
A conta AWS própria ainda não foi identificada; a região AWS da Upstash não é
essa conta. Pedir essa informação uma vez, sem pedir OK genérico, contratar ou
acessar contas. Não há outra mudança offline necessária identificada antes da
definição do destino/custódia e do escopo operacional específico.

Automatismo permanece ACTIVE; continuidade bloqueada pela definição operacional,
não pela conclusão dos testes. Ficar silencioso em retomadas sem informação nova.
Nenhum secret, dado real, chamada externa, instalação, commit/push/deploy, ordem
ou alteração de trading. Não foram executados aplicação, PG real, preflight ou
homologação de produção. GPT-6 Astra — Alto; percentual restante de Live indeterminado.

## Resultado e alterações

- `trade_registry_c3_maintenance_activation_offline_v1.py`: aceita opcionalmente
  `maintenance_coordinator`, sem reconstruí-lo ou alterar sua configuração. Antes
  do consumo, exige tipo exato, maintenance-only, backend/store e relógio/nonce
  idênticos, raiz vinculada, namespace canônico, 19 writers e zero operações.
  Revalida configuração/identidade após autorização e nas fronteiras das etapas.
  O timeout do lock precisa caber no orçamento configurado e no tempo restante.
  A permissão física atual é conferida antes/depois de cada callback, também no
  caminho legado. Default-off continua sem inspecionar a dependência opcional.
- `tests/test_trade_registry_c3_maintenance_activation_offline_v1.py`: 27 novos
  casos; 95 casos no arquivo. Incluem troca de instância/configuração/portas,
  orçamento, reentrada, perda de lease e composição com o boundary de recuperação
  existente. A cópia do coordenador não alcança os dois stores. O cenário sem
  pendências usa um input PREPARED sintético sem escrita; o cenário com relatório
  de escrita continua rejeitado, sem substituir flags da evidência recebida.
- `tests/test_c3_public_authority_offline_v2.py`: 7 novos casos de autorização
  pública com o coordenador injetado. Verificam assinatura, revogação, vínculos,
  recibo perdido, consumo único após reconstrução e default-off. Consumo do banco
  simulado em memória; lease físico e ledger local apenas temporários.
- `tests/helpers/c3_dependency_assembly_lab.py`: perfis seletivos para as suítes
  afetadas, reutilizando Python 3.11.9 e criptografia já instalados. Exporta somente
  fontes explícitas sobre o inventário histórico de 557 arquivos. Inclui a recusa
  maintenance-only já existente no seam; esse arquivo não foi editado nesta rodada.
- Este relatório, `C3_OFFLINE_CONTINUITY_20260911.md` e a atualização de estado
  de `C3_AUTHORITY_INFRASTRUCTURE_PROPOSAL_20260910.md` completam os arquivos alterados.

## Evidência executada

| Execução | Resultado | Evidência local |
| --- | --- | --- |
| Manutenção, autorização legada/startup isolado, lifetime e adapters | 164 aprovados; zero falhas/erros/skips; 10,220 s | `.offline_validation/c3_dependency_assembly_20260911/cq-c3-lab-assembly-9dcddp2o/` |
| Novos casos da autoridade pública + coordenador | 7 aprovados; zero falhas/erros/skips; 1,35 s | `.offline_validation/c3_dependency_assembly_20260911/cq-c3-lab-assembly-5b4wbfi8/` |

São 171 aprovações nestas duas execuções, incluindo 34 novos casos. Não somar
esses números aos 267 históricos como se fossem testes distintos de readiness.
A primeira execução divide-se em 95 manutenção, 36 autorização/startup, 28 lifetime
e 5 adapters. Os hashes dos overlays atuais conferem com a evidência final; o
módulo e sua suíte também conferem com a execução dos 164 testes.

JUnit da execução de 164:
`8306bcc54a4df05d1ed1317927e9df0ac3d4baf464b94adc36245ca1f0d97764`.
JUnit da execução pública:
`11d01df4ef6d602bc15f19d8abaa27b644b41705dbce6aa8cc092452128319e2`.
Cada pasta contém `result.json` com hashes das fontes e `results.xml`.

Tentativas iniciais preservadas: `cq-c3-lab-assembly-y2ged9eu` (160 aprovados,
2 falhas) e `cq-c3-lab-assembly-rkjakxal` (161 aprovados, 1 falha). Causas:
exportação de seam histórico sem a recusa maintenance-only já existente, e
fixture de composição fora de `tempfile.gettempdir()`. Corrigidos somente export
e cenário de teste; nenhum guard foi relaxado. A chamada WSL dentro do sandbox
Windows não enxergou a distribuição; o launcher autorizado fora dele reutilizou
o laboratório existente. Não houve instalação ou download.

## Limites e continuidade

O laboratório confirmou UID 999, zero rotas, fontes read-only, scratch ext4,
sem mounts Windows/home e sem privilégios. Rede, subprocessos e imports de
main/Registry/broker/bots foram bloqueados antes dos testes. Apenas prefixos AST
sem processos operacionais foram usados para a regressão do bloqueio de startup.

Não executados: aplicação completa, PostgreSQL real nesta rodada, chamadas cloud,
preflight real ou homologação de reinício em produção. O teste público substitui
somente o armazenamento de consumo por fake, não comprova persistência externa.
Deadlines continuam cooperativos; callbacks devem limitar seu próprio I/O.
As verificações de instância são invariantes de composição com portas confiáveis,
não uma barreira contra execução Python maliciosa no mesmo processo.

A composição com recuperação e a composição com autorização pública foram
exercitadas separadamente. Próxima unidade offline delimitada: juntar ambas num
único cenário sintético de ponta a ponta, reaproveitando fixtures e distinguindo
os relógios de orçamento e da raiz; testar autorização negada antes da recuperação,
perda de lease e falha de recuperação sem reutilizar a autorização consumida.
Não criar módulo, contrato ou provider operacional para isso.

Ainda faltam providers de produção autenticados/persistentes e sua homologação;
o protocolo público de manutenção não autentica automaticamente a raiz HMAC da
recuperação. O binder e as fontes de startup continuam intocados/default-off.
Percentual restante para Live: indeterminado.

Nenhum secret ou dado real acessado; nenhuma chamada externa, instalação,
commit, push, deploy, ordem ou alteração de configuração de trading realizada.
