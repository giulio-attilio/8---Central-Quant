# C3 — Caminho de ativação e recuperação: auditoria somente leitura

Data: 2026-09-11. Retomada automática após o preflight das 07:53.
Não houve nova chamada ao preflight ou acesso a produção nesta etapa.

## Conclusão

**O bloqueio C3 é uma lacuna deliberada de composição runtime, não um timeout
nem uma configuração que possa ser resolvida apenas trocando uma flag.**
O código publicado instala componentes dormentes e não conecta o instalador
controlado ao startup. O bootstrap isolado do Registry não satisfaz o gate C3.

As quatro fontes centrais abaixo foram comparadas por identidade de blob Git
com o commit publicado 17e767c14b7c90c97a01bc5173f4fd94985672cc. Coincidem:

| Fonte | Blob |
|---|---|
| main.py | 656a98aeda336f1bd20031d4e579c0723cc22df6 |
| trade_registry_closed_identity_conflict_repair_runtime_seam_v1.py | 8917e0323fb47dd5135911e98162434e178a3f91 |
| trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1.py | c3ee4b7a46892a212bc1815f9334782f7bcd77fe |
| trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2.py | 6af5829fce4f1b87d227b5b056efeaac206be077 |

A primeira comparação falhou por limite de comprimento de caminho no Git
Windows, não por drift; a repetição com core.longpaths=true concluiu as quatro.
As fontes examinadas estão em .offline_releases/preflight_ro_full_20260911/src.
Não foi executado/importado nenhum módulo da aplicação.

## Evidências do fluxo atual

1. main.py:68473, _install_c3_closed_repair_writer_coordination_v1, chama o
   builder de produção sem config, lock_backend, lease_store, clock ou nonce.
   No builder, linhas 805–819, config ausente seleciona enabled=false e retorna
   um coordenador desabilitado. O startup chama o instalador dormente.
2. main.py:68653–68684 constrói bridge/autoridade/adaptadores explicitamente
   dormentes. O builder de adaptadores, linha 502, instancia quatro dependências
   desabilitadas, sem paths, chaves ou I/O. Isso não é autoridade provisionada.
3. main.py:68563, _recover_c3_closed_repair_registry_v1, devolve
   C3_DORMANT_STARTUP_RECOVERY_DEFERRED_DEFAULT_OFF quando enabled não é true:
   clean=false, startup_recovery_verified=false e readiness_allowed=false.
   Não inspeciona WAL nem afirma recuperação concluída nesse ramo.
4. main.py:68697–68714 define cinco providers que lançam erros DORMANT:
   startup state, seam binding, maintenance completion, evidence verifier e
   startup callback. A montagem seguinte usa authority_root_sha256=None,
   enabled=false e dormant_only=true. Seu status declara activation_possible=false.
5. runtime_seam_v1.py:320 contém o instalador controlado, mas sua chamada não
   está ligada ao main. As buscas literais localizaram chamada em harness offline.
   As sentinelas de autoridade/interlock são None nas linhas 56–57 e o instalador
   rejeita ausência ou identidade diferente. As atribuições encontradas fora da
   definição são de testes/harnesses offline, não composição de produção.
6. main.py:68549–68550 já injeta coordination_status e maintenance_lease da
   mesma instância de binding na operação de reparo. Portanto, não é correto
   repetir o antigo diagnóstico de dependências ausentes nesse construtor.
7. O binding (seam:548–700) recusa coordenador trocado, adquire maintenance lease,
   exige inspeção de WAL e transações PREPARED/RESOLVED, reconciliação concluída,
   zero pendências e atestado vinculado ao mesmo epoch/namespace antes de readiness.

As buscas textuais não constituem prova contra toda chamada dinâmica concebível.
Os ramos explícitos da composição publicada e o preflight observado sustentam
a conclusão delimitada: a instalação padrão atual permanece dormente.

## O que já existe e deve ser reutilizado

Há builders de coordenador físico, lock/lease, autoridade persistente, composição
de startup, interlock de ativação e harnesses de recuperação. Também existem testes
de identidade de binding e recuperação. Não há justificativa nesta auditoria para
inventar mais um contrato genérico ou duplicar um harness com a mesma finalidade.
Não foram reexecutados nem auditados integralmente todos esses harnesses; a
presença de arquivos não atesta cobertura ou prontidão de produção.

## Próxima mudança funcional: limites concretos

Uma implementação deve conectar os componentes existentes por uma composição
explícita de dependências, mantendo o default-off, sem instalar automaticamente
autoridade, gravar dados ou ativar a coordenação no startup atual. Antes de habilitar:

- Definir o vínculo físico e autenticado da autoridade persistente e suas portas
  de verificação/revogação/recuperação. Hashes ou bools fornecidos pelo chamador
  não substituem autenticação de produção. Não preencher sentinelas com object()
  como fazem fakes de teste.
- Vincular lock e lease ao mesmo armazenamento/namespace, registrar os 19 writers,
  validar os hashes do release e a ausência de mutações concorrentes.
- Comprovar o interlock do Registry e os pré-requisitos do recibo/janela de
  ativação, rollback e kill switch. O bootstrap continua separado e potencialmente
  mutante; não deve ser executado como efeito colateral de preflight.
- Preservar o mesmo coordenador no status, lease, operação e recuperação.
  Readiness só pode vir após recuperação/reconciliação válida. Não fazer bypass
  do gate para obter um preflight verde.
- Exercitar a composição usando testes existentes e fixtures sintéticas isoladas:
  default-off sem I/O, identidade divergente, autoridade ausente/revogada,
  falha de lock/lease, writers incompletos, restart com PREPARED/RESOLVED,
  reconciliação pendente, kill switch e rollback. Reutilizar a infraestrutura de
  testes com rede/startup operacional bloqueados.

Esse é um escopo de implementação adicional, não executado pela auditoria.
O armazenamento/autoridade efetivos e os providers de produção não foram
inspecionados nem provisionados. Não há base para prometer que uma única linha,
um bootstrap ou mais um deploy fechará a integração inteira.

## Segurança e encerramento

Único arquivo criado: este relatório. Nenhum código, teste ou evidência anterior
alterado; nenhuma chamada externa, secret ou dado real acessado; nenhum teste
executado, processo operacional iniciado, commit, push, deploy, bootstrap,
reparo, flag, ordem ou stop. O resultado operacional continua sendo o único
preflight das 07:53, documentado em C3_PREFLIGHT_PRODUCTION_RESULT_20260911.md.

Auditoria concluída; não repetir sem nova evidência. A implementação funcional
precisa de escopo específico; ativação ou alteração de produção continua fora
desta auditoria. Automatismo permanece ativo, sem repetir etapas concluídas.
Modelo recomendado: GPT-6 Astra — Alto. Restante para Live: indeterminado.
