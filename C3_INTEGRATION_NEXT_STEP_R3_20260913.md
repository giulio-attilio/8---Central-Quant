# C3 — sequência de integração após r3

## Decisão objetiva

Não ativar Live e não executar bootstrap isolado. Preparar primeiro, somente
offline, o pacote do vínculo único de coordenador que já existe na worktree.
Não criar outro contrato de readiness. Não iniciar migração ou contratar serviços.

Esta é a resposta ao pedido “siga” após o preflight de 13/09. Define trabalho
local seguro dentro da autorização offline existente; não autoriza execução
operacional. O preflight não foi repetido nesta análise.

## O que falta, em ordem

| Etapa | Reutilização e mudança necessária | Critério de saída |
| --- | --- | --- |
| 1. Unificar o vínculo dormente | Isolar do trabalho local a construção única do coordenador e sua passagem explícita à recuperação e aos interlocks, sobre a base publicada db3a560 | Pacote local delimitado, testes sobre os bytes exatos, default-off e zero I/O na construção; sem publicação |
| 2. Fechar dependências operacionais | Autoridade autenticada, revogação, consumo durável independente de restauração, fonte temporal e consultas de recovery; reutilizar especificações existentes | Providers concretos e plano de qualificação definidos, sem confundir hashes/pins locais com autenticação ou mocks com serviços reais |
| 3. Compor inicialização e recuperação | Todos os writers sob o mesmo domínio físico de lock; inspecionar WAL/pendências antes da admissão e manter obrigações não resolvidas bloqueantes | Evidência de exclusão, reinício, timeout, perda de resposta e recuperação; nenhuma prontidão inferida de ausência de erro |
| 4. Homologar no alvo, sem trading | Implantação controlada somente após autorização específica, com tratamento de falha e rollback que não reabra cópia antiga para escrita | Vetor completo C3 verificado e Registry pronto; novo preflight autorizado, sem reparo automático ou alteração de flags |
| 5. Decidir piloto Live | Plano operacional de risco e rearmamento, separado da autoridade de manutenção | Autorizações próprias e critérios de proteção/ownership atendidos; preflight verde sozinho não envia ordens |

Etapas 2 e 3 ainda têm decisões de engenharia abertas. Não há plano executável
completo de produção nem prazo de Live demonstrado. Os números são marcos, não
parcelas iguais de esforço. Dois checks bloqueados não significam 11% restante.

## Primeiro pacote: escopo concreto

Base imutável: `db3a560dc555158997004bbe7d08738d318dd528`. A fonte publicada
constrói o coordenador dentro de `_install_c3_closed_repair_writer_coordination_v1`
e cria os adapters sem passá-lo. A worktree tem a correção já testada em contexto
mais amplo: `C3_DORMANT_STARTUP_INTEGRATION_RESULT_20260911.md` (267 aprovações
históricas, não validação de um futuro pacote isolado sobre r3).

Pontos existentes a transportar, depois de fechar suas dependências:

- `main.py`: construção única `C3_CLOSED_REPAIR_WRITER_COORDINATOR_DORMANT_V1`,
  injeção na factory e no instalador, guarda de identidade antes de instalar.
- `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2.py`:
  factory dormente e `dormant_coordinator_bound_v2`, com o fechamento de
  dependências necessário, sem habilitar portas físicas ou inferir paths/raízes.
- `trade_registry_closed_identity_conflict_repair_runtime_static_preflight_v1.py`:
  checagem semântica da mesma instância, ordem e guarda, não só nomes de builders.
- `tests/test_c3_dormant_startup_same_coordinator_v2.py` e regressões existentes
  de adapters, startup, preflight estático e bindings realmente afetados.
- Atualizar apenas pins/spans transitivos comprovadamente afetados pelo novo
  payload, com testes negativos de drift. Não enfraquecer o gate para acomodá-lo.

O diff observado do módulo de adapters contém também proteção de locks e lifetime
anterior. Não copiar as 192 linhas de delta ou o coordenador inteiro sem revisar
dependências; tampouco suprimir proteções para obter um pacote menor. Se a fronteira
não puder ser fechada sem alteração operacional nova, registrar a dependência e
parar nela. Reaproveitar as implementações e testes, sem nova camada de contratos.

Excluir deste pacote: binder `C3_MAINTENANCE_STARTUP_BINDING_V1` e sua barreira de
runtime, autorização pública V3, mudanças ativas de `recover_multistore_v2` que
não sejam dependências indispensáveis, ativação de coordinator/providers,
configuração real, dados, ferramentas de laboratório e outras mudanças alheias.
Uma dependência indispensável deve ser justificada no manifesto, nunca incluída
por cópia integral da worktree dirty nem omitida para reduzir a contagem.

Preparação em diretório local próprio, sem mudar HEAD/index/branches, r3 selado ou
main.py original. Manifesto deve distinguir arquivos de payload e de validação.
Reutilizar o laboratório Linux sem rede existente; ler integralmente seus helpers
antes de executar e ajustar seleção/base apenas na ferramenta de preparação.
O helper histórico fixa 557 arquivos da base antiga: não executá-lo como se
atestasse automaticamente db3a560. Não instalar runtimes ou importar main.

Aceite mínimo: identidade compartilhada; recusa de cópia/troca de instância,
configuração habilitada, pin divergente e guarda removida; nenhuma chamada a
provider/I/O na montagem; estado disabled preservado; preflight real não chamado.
Testes novos só se uma lacuna real da composição isolada exigir. Não repetir a
suíte r3 idêntica por rotina, nem somar rodadas sobrepostas como progresso Live.

## Por que as outras etapas não são só uma conexão de funções

Cinco fontes de startup da base publicada continuam explicitamente DORMANT e
lançam erro: estado, seam, conclusão de manutenção, verificador e callback de
startup. A factory de autoridade também é desativada e sem dependências físicas.
Publicar somente a etapa 1 conservaria isso e não eliminaria os dois bloqueios.

A proposta existente (`C3_PROPOSTA_DECISAO_20260912.md`, seções 8.4, 12 e 13)
documenta que a evidência pública V3 não é um permit de execução e não se encaixa
no autorizador V1 por conversão de campos. Há regras propostas de propagação de
validade e recuperação, mas faltam providers reais qualificados. Não transformar
retorno booleano em prova de validade temporal ou de primeiro consumo.

Não reabrir a pesquisa de infraestrutura ou consulta ao Render: o estudo da
seção 15 já rejeitou mover só a manutenção. Uma eventual migração completa é
outro escopo, com custo e risco próprios, não consequência deste “siga”.

## Evidência e segurança desta entrega

Leitura de relatórios, fontes e diff local relativo ao commit r3; teste existente
de vínculo lido integralmente. Não houve mudança funcional nem teste executado.
Criado este plano e atualizado o topo da continuidade. O automatismo existente
será direcionado à preparação finita da etapa 1, sem exigir outro OK e sem
autorizar commit/push/deploy. As etapas operacionais continuam condicionadas.

Nenhum secret ou dado real acessado; nenhuma chamada à Central, Render, BingX,
Redis ou Telegram; nenhuma configuração de trading alterada; nenhum commit,
push ou deploy. Consulta externa somente à documentação OpenAI Docs para manter
o automatismo: https://learn.chatgpt.com/docs/automations?surface=app.

Modelo recomendado: GPT-6 Astra — Alto. Percentual restante Live: indeterminado.
