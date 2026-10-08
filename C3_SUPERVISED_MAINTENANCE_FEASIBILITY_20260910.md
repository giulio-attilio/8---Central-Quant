# C3 — viabilidade de manutenção pontual supervisionada

Data: 10/09/2026 BRT; conclusão em 11/09/2026 UTC.
Escopo inicial: análise estática local e proposta. Nenhuma manutenção executada.
Atualização após o aceite do experimento: seção 8, testes somente sintéticos.
Parecer: **VARIANTE COM RESTORE DOS DOIS HISTÓRICOS REPROVADA NO MODELO — NÃO APROVADO PARA LIVE**.

## 1. Decisão para o usuário

Não contratar infraestrutura nem atualizar o workspace Render neste momento.
O usuário confirmou Hobby; Render e Redis existentes ficam preservados.
US$ 30 adicionais/mês é limite de planejamento, não autorização de compra.

A manutenção supervisionada poderia substituir disponibilidade permanente por
disponibilidade apenas durante a manutenção. Não elimina autenticação, histórico
de consumo independente, recuperação ou coordenação de todos os writers.
Não foi encontrada implementação pronta que entregue essas garantias sem novos
componentes. Não há base para afirmar custo zero, encaixe no orçamento ou prazo
de retorno ao Live. Também não há base para exigir AWS/PostgreSQL como únicos
provedores possíveis: são escolhas da proposta anterior, não nomes exigidos
pelo gate de Live.

A alternativa estritamente local, com todos os estados restauráveis juntos e
somente confirmação humana/desafio novo, é **insuficiente para a ameaça de replay
após restauração**. A alternativa com autoridade supervisionada independente é
uma hipótese tecnicamente investigável, não uma solução validada.

## 2. Evidência e mapa mínimo de dependências

As referências abaixo são fontes da worktree
`.worktrees/c3_final_release_promote_20260910`, não leituras de produção.
HEAD local identificado na auditoria precedente: `d9e12e9daa8f606c3649370bbbf1551650979eb6`.
Há alterações anteriores não commitadas; linhas referem-se à worktree.
O gate completo e a instalação dormente também foram encontrados no `main.py`
de HEAD por leitura de objeto Git, sem consulta remota. Isso não confirma qual
processo está rodando agora no Render.

| Etapa necessária | Evidência local | Lacuna ou limite |
| --- | --- | --- |
| Autorização autenticada e vinculada ao pedido | `trade_registry_c3_maintenance_authorization_v1.py:38`, `:150`, `:185` | Consumidor independente é injetado; não há autoridade operacional pronta. Hash de origem não autentica sozinho o emissor |
| Exclusão dos writers e mesma permissão | `trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1.py:404`; `trade_registry_c3_maintenance_activation_offline_v1.py:170` | Registrar 19 nomes não comprova que todos os processos/writers reais usam a mesma trava; a instalação global continua pendente |
| Bootstrap, recovery e postflight de manutenção | `trade_registry_c3_maintenance_activation_offline_v1.py:137` | Valida `synthetic_only=True` e `registry_write=False`; não é executor real de reparo CLOSED |
| Startup impedido durante a composição offline | `main.py:33465`, `:33482` | Binder aceita tipo legado, bloqueia início do runtime quando vinculado e não oferece promoção para Live |
| Recuperação autoritativa antes de readiness | `trade_registry_closed_identity_conflict_repair_runtime_seam_v1.py:592` | Exige inspeção WAL/log, transações PREPARED/RESOLVED, zero pendências finais, mesma época/namespace e autoridade real |
| Adaptadores de recuperação no aplicativo | `main.py:68674`, `:68705`; `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2.py:502` | Construídos dormentes, sem dependências operacionais; estado limpo não pode ser presumido |
| Reparo com preview exato e revalidação sob locks | `trade_registry_closed_identity_conflict_repair_runtime_operation_v1.py:607`, `:647` | Apply default-off; exige recibo autorizado, controles seguros, vetor completo de coordenação, lease e comparação origem/candidato/conflitos/preservação |
| Rearmamento depois da recuperação | `main.py:56908` | Gate obrigatório exige vetor completo; sucesso de uma manutenção não atende sozinho aos demais checks do preflight |

Dependência essencial, sem nomes de provedor:

1. Preparação e autorização de escopo exato, com autoridade externa ao domínio
   restaurável da Central e política atual verificável.
2. Bloqueio comprovado dos participantes e recuperação sob a mesma lease.
3. Qualquer reparo: preview autorizado próprio e revalidação do estado sob lock.
4. Resultado durável e reconciliação de toda operação incompleta.
5. Startup coordenado e preflight completo, ainda sem autorizar trading sozinho.

Não usar o experimento de manutenção para chamar a rota de apply contornando
seu gate. A transição entre manutenção e startup normal não está implementada.
O instalador controlado rejeita coordenador `maintenance_only`
(`trade_registry_closed_identity_conflict_repair_runtime_seam_v1.py:372`).
A manutenção não deve converter esse coordenador em habilitação de runtime.

## 3. Alternativa concreta avaliada — autoridade do operador sob demanda

Desenho proposto, não instrução de operação nem recurso já disponível:

- Um ambiente do operador separado do backup/restauração da Central guarda a
  identidade de assinatura e o histórico durável de consumo. Fica disponível
  durante a preparação/manutenção/reconciliação, não necessariamente 24 horas.
  Não é a sessão do Codex e não usa o histórico da conversa como autoridade.
- O processo de manutenção da Central guarda somente a confiança pública
  matriculada e usa portas limitadas. Não recebe poder de emitir suas próprias
  autorizações nem de apagar/restaurar o histórico externo.
- O operador se autentica nesse ambiente e examina uma descrição legível da
  ação. O protocolo deve assinar também sua representação canônica: operação,
  alvo/instância, revisão do código/plano, hashes de origem e candidato quando
  houver reparo, preservação exigida, namespace, época, prazo e identificador
  lógico da ação. Não assinar digest arbitrário apresentado por um processo.
- A autorização seria preparada e entregue por troca explícita de mensagens
  assinadas. O transporte não pode ler/expor chaves; seu mecanismo e limites
  ainda precisam de desenho. Nenhuma nova porta HTTP ou comando de shell é
  recomendado por este relatório.
- Antes de qualquer ação, o ambiente do operador registra atomicamente o consumo
  vinculado à ação, e somente então emite resposta para um desafio fresco.
  Repetir pedido, recriar processo ou trocar nonce não pode repetir a mesma
  tentativa lógica sem uma reconciliação e decisão separadas.
- O resultado local associa permissão, transação, estado anterior/posterior e
  obrigações. O registro externo distingue autorização consumida de operação
  concluída. Ausência de resposta mantém a ação pendente; não libera outra.
- Ao terminar ou falhar, volta-se a um estado de admissão bloqueada. Retomada
  exige recuperação verificada. Desligar a autoridade impede novas manutenções;
  não deve desativar stops ou a proteção de posições existentes.

O desenho conserva as responsabilidades de emissão, revogação e consumo;
concentrá-las fisicamente num dispositivo não comprova separação de permissões.
Custódia, identidade do operador, sincronização do estado, recuperação do próprio
dispositivo e comportamento sob clonagem/restore permanecem sem solução pronta.
Não foi inspecionado nem qualificado equipamento do usuário para essa função.

### Diferenças concretas em relação ao código atual

1. `AuthorizationBindingV1` (`trade_registry_c3_maintenance_activation_offline_v1.py:51`)
   e seu digest (`trade_registry_c3_maintenance_authorization_v1.py:38`) vinculam
   escopo, raiz, nonce, deadline, writers, modo e época. Não contêm plano exato,
   origem/candidato ou identidade lógica do reparo. Isso não é autorização
   operacional incompleta em uso: é um contrato offline que não deve ser
   reaproveitado como aprovação de qualquer modificação real.
2. `PublicMaintenanceAuthorizationOfflineV2` (`trade_registry_c3_public_authority_offline_v2.py:293`)
   aceita tipos concretos do experimento PostgreSQL e referência externa.
   Trocar por um arquivo do operador não é substituição transparente.
3. O mesmo componente reduz sua janela interna a `min(binding.deadline, now + 5.0)`.
   Não inserir espera humana nessa janela, aumentar prazo silenciosamente ou
   enfraquecer revogação. Preparação humana e consumo final precisam de fases
   distintas, com revalidação após a preparação; a composição atual não as fornece.
4. `OfflineMaintenanceActivationV1` produz `production_ready=False` e
   `live_allowed=False` mesmo com sucesso (`:98`). Suas etapas são sintéticas;
   não há execução real preparada pelo simples fornecimento de uma assinatura.
5. A recuperação da seam exige `network_accessed=False` (`runtime_seam_v1.py:650`).
   Uma autoridade sob demanda não pode introduzir chamadas remotas escondidas
   nesse callback e manter o atestado falso. A eventual separação entre
   admissão autenticada e recovery local precisa de composição explicitamente
   validada; nenhuma alteração dessa fronteira é feita aqui.

## 4. Avaliação adversarial

| Evento/ataque | Resposta obrigatória | Situação da alternativa |
| --- | --- | --- |
| Operador não autenticado ou chave pública trocada no pedido | Recusar antes de consumir; confiança matriculada fora do pedido | Matrícula e autenticação operacional não implementadas |
| Operador aprova texto A, processo apresenta digest de B | Vincular apresentação legível ao manifesto canônico; recusar divergência | Falta representação de ação exata no binding atual |
| Dois operadores/processos simultâneos | Uma reserva atômica por ação e uma lease física compartilhada; demais recusados | Trava local não substitui consumo externo nem prova instalação em todos os writers |
| Recibo antigo reapresentado | Verificar desafio, escopo, instância, época e consumo; recusar | Caso já existe no experimento sintético, não nesta alternativa |
| Nonce novo para a mesma ação após dúvida/timeout | Reconciliar identidade lógica e estado antes de nova autorização | Histórico só por nonce não impede o operador de autorizar repetição lógica |
| Queda antes de consumir | Nenhuma execução; reavaliar antes de retomar | Precisa ensaio em todas as fronteiras |
| Consumo confirmado e resposta perdida | Manter consumido/pendente; sem nova permissão automática | Exige consulta autenticada para reconciliação, distinta de reemissão de grant |
| Reparo efetivado e confirmação perdida | Comparar evidência transacional e estado durável; não reaplicar | Recibo de consumo não é prova de fechamento da transação |
| Restart ou troca de chave | Preservar histórico, reinspecionar transações/lease, usar política atual | Renovação de chave não zera tentativas anteriores |
| Restore apenas da Central | Autoridade externa retida recusa consumo antigo e exige reconciliação | Depende de retenção realmente independente |
| Restore da Central E do ambiente do operador | Quarentena, sem emissão; exigir prova independente de continuidade | Não demonstrado; desafio fresco sozinho não resolve |
| Chave revogada, política atrasada ou autoridade ausente | Negar novas admissões; não usar cache antigo para liberar | Fonte atual e política de recuperação ainda não qualificadas |
| Deadline excedido ou relógio regressivo | Recusar; manter pendência após qualquer consumo/efeito | Timeout de transporte real e fronteiras temporais faltam |
| Lease liberada após erro no callback | Não inferir sucesso da transação nem readiness | Coordenador libera em `finally`; erro deve persistir como obrigação separada |
| Operador encerra a manutenção/fecha o computador | Novas manutenções ficam bloqueadas; proteção das posições permanece | Não autoriza parar o runtime/proteções para obter exclusão |

### Por que um desafio novo não basta

Considere: ação autorizada e consumida; ambos os históricos são restaurados
para antes dela; um novo processo gera desafio novo; o operador aprova novamente
com base no histórico restaurado. A assinatura pode ser válida e fresca, mas
não comprova que a ação nunca ocorreu. Essa é uma inferência do modelo de
ameaça, não um novo teste executado. Uma fonte independente retida ou prova
confiável de restauração/quarentena precisa quebrar essa ambiguidade. Identidade
de arquivo/caminho, hash encadeado guardado no mesmo backup, novo nonce e
lembrança humana isolada não estabelecem continuidade.

O teste existente `tests/test_c3_public_authority_offline_v2.py:261` restaura
os estados locais e limpa deliberadamente os claims externos: a autorização
volta a ser aceita. É controle negativo que expõe a premissa, não aprovação de
anti-rollback. O teste `:251` retém a referência externa e recusa; `:224` recusa
recibo capturado diante de desafio fresco. Esses casos foram lidos, não rodados.
O relatório `C3_PUBLIC_AUTHORITY_OFFLINE_VALIDATION_20260910.md` registra 251
aprovações históricas, exclusivamente sintéticas, não aprovação desta proposta.

## 5. Custos e operabilidade

O relatório de infraestrutura anterior registra base B de US$ 43,50/mês com
upgrade Hobby→Pro, antes dos extras. Esse valor é contexto da cotação anterior,
não nova consulta ou conta real. A alternativa supervisionada visa evitar
serviço permanente adicional e PostgreSQL adicional, mas não há equivalência
validada com o experimento que usa PostgreSQL.

Custos não quantificados: equipamento/custódia independente, recuperação e
backup externo, emissão/revogação, transporte autenticado, retenção de auditoria,
desenvolvimento e tempo humano por manutenção. Nenhuma dessas rubricas foi
presumida gratuita. Disponibilidade intermitente aumenta a necessidade de
intervenção humana em falhas; essa troca importa para um usuário que deseja
autonomia. Ela não obriga interação a cada trade, mas pode obrigá-la durante
manutenção e recuperação. Sem essas definições, não há total defensável.

## 6. Parecer e menor próximo escopo

**Não demonstrado** para a autoridade supervisionada com histórico independente.
**Insuficiente** para a variante com todos os estados restauráveis juntos e
somente aprovação humana. Não promover, contratar ou integrar qualquer delas.

Próximo escopo de implementação proposto, NÃO executado nem autorizado por esta
automação: um único experimento de viabilidade em testes sintéticos, no arquivo
`tests/test_c3_supervised_maintenance_feasibility_v1.py`, reutilizando fixtures
existentes quando compatíveis. Não criar nova família de contratos, alterar
`main.py`, diminuir gates ou fingir que um modelo de teste é adaptador pronto.
Modelar o pedido de ação exata, histórico independente do operador e transições
de consumo/pendência/conclusão, antes de escolher um backend de produção.

Critérios desse experimento, todos sem rede, dados reais ou runtime:

1. Assinatura sintética vincula alvo, ação e revisão exatos; alteração de um
   campo recusa antes de qualquer efeito. A apresentação revisada coincide com
   o conteúdo assinado; nonce novo não é nova autorização da mesma ação pendente.
2. Disputa por mesma ação permite no máximo um consumo. Separar esse teste de
   qualquer alegação de exclusão entre processos reais, que exigirá ensaio próprio.
3. Injetar interrupções antes/depois de reserva, gravação local e resposta.
   Nenhum retry gera segundo efeito; estados ambíguos ficam pendentes e bloqueados.
4. Restore da Central com registro externo retido recusa repetição e exige
   reconciliação. Restore também do registro externo deve ficar bloqueado por
   evidência de recuperação realmente independente; se essa evidência não
   existir no desenho, registrar CONTRAEXEMPLO e encerrar como inviável nesse
   modelo. Não usar um booleano confiável fictício para declarar a lacuna resolvida.
5. Revogação, política atrasada, relógio regressivo, timeout e perda da autoridade
   negam admissão. Preparação humana não congela validade ou contorna deadlines.
6. Nenhum resultado de teste concede `production_ready`, `runtime_activation_allowed`
   ou `live_allowed`. Não executar callbacks reais de bootstrap, reparo ou trading.

Parada objetiva: se o desenho só funcionar presumindo o histórico nunca
restaurado ou o operador sempre lembrando o que ocorreu, a hipótese não passou.
Mesmo um experimento bem-sucedido não conclui a integração: persistência física,
identidade real, múltiplos processos, startup e recuperação operacional seriam
validações posteriores explícitas. Não listar essas etapas como concluídas.

## 7. Encerramento, verificações e segurança

Os três entregáveis desta análise estão concluídos: mapa, avaliação adversarial
e parecer com um próximo experimento delimitado. A automação foi pausada
após salvar e conferir este relatório; o aplicativo confirmou PAUSED e a
configuração foi relida para verificar. Não continuar gerando contratos ou
presumir autorização para o experimento. Nenhuma pergunta de inventário é
necessária para emitir o parecer não demonstrado desta rodada.

Único arquivo criado: este Markdown. Revisão de conteúdo, referências e
formatação; nenhum teste executado e nenhuma aprovação histórica recontada.
Nenhum módulo do aplicativo importado, servidor ou processo operacional iniciado.
Nenhum `.env`, secret, chave real, token, Registry ou dado operacional acessado.
Nenhuma chamada a serviços operacionais; nenhuma ordem, contratação, instalação,
commit, push, merge, pull, deploy, alteração de Render/Redis ou flag de trading.
O controle do agendamento usa a ferramenta do aplicativo; eventual consulta
à documentação pública OpenAI para pausá-lo não constitui teste operacional.
Alterações preexistentes preservadas. Não houve redução dos requisitos de segurança.

Modelo/esforço recomendado para o próximo experimento: GPT-6 Astra — Alto.
Percentual restante para Live: **indeterminado**, sem inventar uma porcentagem.

## 8. Experimento autorizado posteriormente — resultado e parada

Após o usuário aceitar o próximo experimento, foi criado somente
`tests/test_c3_supervised_maintenance_feasibility_v1.py` (445 linhas), além desta
atualização documental. Nenhum módulo operacional ou helper existente foi alterado.

**45 testes aprovados em 0,48 s; zero falhas, erros ou ignorados.** O JUnit
registra 0,485 s. Isso comprova que as asserções do experimento passaram, NÃO
que a hipótese de segurança foi aprovada. O controle negativo produziu:

```text
security_verdict = COUNTEREXAMPLE_RESTORE_ALL_DUPLICATE
synthetic_effect_count = 2
```

O modelo confirma que um novo nonce/desafio e uma nova aprovação assinada não
impedem repetição lógica quando o estado local e o histórico da autoridade são
restaurados. O teste deliberadamente exige observar esse contraexemplo, sem
xfail, skip ou booleano fictício de recuperação. A variante investigada é
reprovada para essa ameaça; encerrar este experimento, sem promovê-lo a runtime
nem acrescentar novas camadas para ocultar o resultado.

Com o histórico externo retido, o modelo recusa repetição após restore local,
mudança de nonce/revisão/época e resposta perdida após consumo. Antes da reserva,
uma interrupção sem efeito permite uma nova tentativa; depois dela, preserva
RESERVED ou COMPLETED e não reaplica. O ensaio concorrente usa oito threads com
estados locais separados e uma autoridade compartilhada: exatamente uma ação
é admitida. Foram cobertos assinatura de todos os campos do plano e metadados,
texto revisado divergente, chave errada, recibo adulterado/antigo, revogação,
política atrasada, expiração, relógio regressivo e indisponibilidade, incluindo
mudanças após preparar a transação. Todos os resultados mantêm flags de
produção/runtime/Live falsas.

### Isolamento e limites da evidência

- Executado com o launcher `tests/helpers/c3_linux_lab.py` existente, selecionando
  apenas o novo teste e seu entrypoint, sem modificar as listas do helper no disco.
  Laboratório novo: `/var/tmp/cq-c3-lab-supervised-2diqg2kk`.
- Isolamento confirmado antes da coleta: UID 999, zero rotas externas, nenhum
  mount Windows/diretório pessoal visível, fontes somente leitura, scratch ext4,
  capabilities removidas e ambiente limpo. Rede/DNS/subprocessos também negados
  por fixture antes dos imports dos componentes usados pelo teste.
- 68 fontes Python exportadas pelo helper; `main.py` é apenas arquivo copiado,
  nunca importado ou iniciado. PostgreSQL não foi iniciado. Nenhum dado real ou
  credencial exportado. Nenhum serviço novo, instalação ou download.
- Todos os estados de ação/autoridade são objetos em memória. O efeito é uma
  atribuição simbólica, não um reparo financeiro, trade ou escrita de Registry.
  Um log do próprio teste conta os efeitos e NÃO é consultado pelo modelo para
  admitir operações; portanto não serve como solução externa anti-rollback.
- Reutilizado o verificador Ed25519 do módulo público offline com sementes
  publicamente reproduzíveis. O fixture `public_env` não foi usado porque cria
  SQLite. Não há autenticação real de operador, custódia, persistência física,
  teste multiprocesso, queda de energia, rede distribuída, startup completo,
  coordenação real dos 19 writers, recuperação real ou preflight de produção.
  O lock em memória que serializa política/efeito não prova atomicidade entre
  máquinas. Esses limites impedem interpretar o modelo como adaptador entregue.

JUnit: `/var/tmp/cq-c3-lab-supervised-2diqg2kk/scratch/supervised-results.xml`.
SHA-256 do novo teste:
`026b9803febee603637414e0c5738098142e606a9c2750a40798d748ed86a02b`.
`main.py` permanece com SHA-256
`62b985fc9f7ef49d94ebc2d16945d3301e4603bf4c661ebd10461083bd529b03`;
o verificador legado permanece com
`1e2fa06fe820159a51268e0f48c708d2533d294ca38ff779ae00b4401663e264`,
iguais às evidências anteriores. Novo teste sem whitespace final; diff check
dos dois arquivos preservados sem erros (aviso preexistente LF/CRLF).

Próximo passo recomendado: definir e qualificar a fonte independente de
continuidade/consumo e seu procedimento de recuperação antes de outra
implementação. Não inferir que ela precise ser o pacote AWS/Render anteriormente
cotado, mas também não afirmar que confirmação humana o substitui. Essa decisão
de arquitetura/persistência continua pendente; não há liberação para contratação.

A automação anterior permanece pausada; não foi reativada neste turno.
Nenhum secret, `.env`, token ou dado real acessado; nenhuma chamada externa,
ordem, commit, push, deploy ou alteração de configuração de trading/Render/Redis.
Só o teste e este relatório foram alterados; artefatos sintéticos do laboratório
foram preservados. Não houve regressão operacional introduzida, pois o código
operacional foi preservado; isso não substitui testes integrais não executados.
