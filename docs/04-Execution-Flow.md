# Fluxo de Execução

Status: APPROVED
Versão: 1.0
Última revisão: 11/07/2026
Responsável: CTO
Implementação: Codex
Aprovado: Sim

---

## 1. Propósito

Definir o fluxo operacional oficial de um trade na arquitetura-alvo da Central Quant, desde a detecção do signal até o outcome e a elegibilidade para Learning.

O fluxo é normativo, orientado por lifecycle e confirmação. A implementação atual serve apenas para identificar compatibilidades, lacunas e migrações; não redefine este contrato.

---

## 2. Relação com o `00-Vision.md`

Este documento concretiza a verdade por trade, a proteção do capital, a autonomia com evidência e a segurança por padrão. Em qualquer incerteza, a Central preserva proteção, impede ações conflitantes e reconcilia antes de continuar.

---

## 3. Relação com o `01-Architecture.md`

As autoridades permanecem separadas: Bot formula hipótese; Decision determina elegibilidade; Executive Policy condiciona; Risk determina risco e size; Execution coordena; Broker traduz; exchange executa e custodia; Registry preserva lifecycle; Management gere; Analytics mede; Learning aprende.

---

## 4. Relação com o `03-System-Components.md`

Cada etapa deste fluxo é atribuída aos componentes oficiais catalogados. Um módulo atual pode participar de várias etapas, mas não adquire por isso autoridade adicional. Execution é a única autoridade de coordenação da execução real.

---

## 5. Princípios do fluxo operacional

1. A Central é a fonte de verdade operacional e estatística; a BingX é executora e custodiante.
2. Cada trade possui identidade e lifecycle independentes.
3. Símbolo, lado e preço médio agregado não comprovam ownership.
4. Solicitação, aceite, fill, proteção, gestão e encerramento são fatos distintos.
5. Estado local só avança com confirmação suficiente e evento persistido.
6. Timeout e ausência de resposta não comprovam falha nem ausência de execução.
7. Retry exige a mesma identidade persistente e reconciliação quando houver ambiguidade.
8. Toda posição real exige disaster stop físico confirmado.
9. TP50, runner, break-even, trailing e close pertencem ao lifecycle.
10. Posição manual permanece externa; Learning só consome outcome confiável.
11. Testes nunca podem acessar produção ou serviço externo.

---

## 6. Visão macro do fluxo

```text
Market Data → Bot → SIGNAL_DETECTED → Decision → Executive Policy
                                      ↓
                                  Risk + Capital
                                      ↓
                         Execution Plan + Identity
                                      ↓
                         ENTRY_INTENT_RECORDED
                                      ↓
                           Execution → Broker → Exchange
                                      ↓
                      Order/Fill Confirmation + Registry
                                      ↓
                    Disaster Stop Creation + Confirmation
                                      ↓
                  Management: TP50 → Runner → BE → Trailing
                                      ↓
                         Close Confirmation → Outcome
                                      ↓
                             Analytics → Learning
```

Nenhuma seta autoriza salto de camada. Evidência externa retorna por Broker e Execution antes de alterar Registry e Lifecycle.

---

## 7. Fluxo de geração de signal

O Bot observa Market Data e contexto, identifica um setup e produz signal estruturado com `signal_id`, bot, setup, símbolo, lado, validade, entrada teórica, stop técnico, alvo, score e justificativa. Isso gera `SIGNAL_DETECTED`, não ordem nem posição.

O Bot não acessa credenciais, Broker ou exchange na arquitetura-alvo.

---

## 8. Fluxo de decisão

Decision recebe o signal em `DECISION_PENDING`, valida elegibilidade e produz `DECISION_ALLOWED` ou `DECISION_DENIED`, podendo condicionar size, exigir espera/verificação ou manter observação. Decision não cria ordem, fill ou proteção.

Uma nova avaliação do mesmo signal preserva `signal_id` e identidade decisória; não cria uma segunda intenção de trade sem evento explícito.

---

## 9. Fluxo de Executive Policy

Executive Policy fornece restrições, prioridades e condições para Decision e Risk. Pode reduzir, bloquear ou exigir observação; nunca envia ordem, altera posição ou substitui fato confirmado do lifecycle.

Toda política aplicada deve ter identidade, versão, motivo, vigência e trilha auditável.

---

## 10. Fluxo de Risk e Capital Allocation

Após `DECISION_ALLOWED`, o lifecycle entra em `RISK_PENDING`. Risk avalia capital livre, orçamento por trade e bot, exposição global, posições externas, concentração, correlação, alavancagem, constraints e políticas.

O resultado é `RISK_APPROVED`, com size e limites explícitos, ou `RISK_DENIED`. Risk não envia ordem nem altera o setup original silenciosamente. Size deve respeitar precision, contract size, `minQty`, `minNotional` e a gestão parcial planejada.

---

## 11. Construção do plano de execução

Execution Orchestrator recebe decisão e risco aprovados e constrói plano imutável contendo modo, `trade_id`, `lifecycle_id`, `signal_id`, `decision_id`, bot, setup, símbolo, lado, tipo, size, stop, constraints e política de confirmação.

No LIVE, o plano exige gates positivos, configuração explícita e Broker READY. Nenhum default permissivo autoriza capital real.

---

## 12. Registro de intenção

Antes de qualquer submissão, Execution persiste `ENTRY_INTENT_RECORDED`, a identidade estável, `client_order_id`, payload normalizado, timestamp, modo e hash/idempotency key. A persistência deve ocorrer antes do contato externo.

Falha ao persistir impede submissão.

---

## 13. Idempotência

A mesma intenção usa a mesma identidade em retry, reinício e recovery. O ledger deve rejeitar segunda submissão quando execução anterior estiver confirmada ou incerta.

Retry de decisão não cria nova identidade. Retry de execução preserva `trade_id`, `lifecycle_id` e `client_order_id`; nunca depende apenas de símbolo e lado e nunca pode alcançar posição manual.

---

## 14. Submissão da entrada

Execution transita para `ENTRY_SUBMITTING`, grava o evento e entrega ao Broker um comando autorizado. Broker valida formato e constraints, traduz para a exchange e devolve resultado estruturado.

Broker não decide se o trade é bom e não inicia retry. O ato de chamar a exchange não confirma ordem ou fill.

---

## 15. Confirmação de ordem

Uma ordem somente é reconhecida quando há evidência correlacionável: `client_order_id`, `exchange_order_id`, status, símbolo, lado, timestamp e quantidade. Retorno sem erro é indício, não confirmação final.

Status aberto pode confirmar aceite da ordem, mas não confirma fill completo.

---

## 16. Confirmação de fill

Fill exige registro da exchange correlacionado à identidade, com order ID, fill ID quando disponível, preço, quantidade e timestamp. A entrada operacional e estatística usa fills confirmados daquele lifecycle, nunca preço médio agregado.

Somente quantidade cumulativa suficiente permite `ENTRY_CONFIRMED`.

---

## 17. Tratamento de fill parcial

Fill inferior à quantidade planejada produz `ENTRY_PARTIALLY_FILLED`. Execution registra quantidade executada e restante, reavalia constraints e impede presumir a quantidade total.

A política explícita pode aguardar, cancelar o restante ou aceitar a posição parcial. Qualquer posição real já executada deve receber proteção física compatível com a quantidade confirmada.

---

## 18. Tratamento de rejeição confirmada

`ENTRY_REJECTED_CONFIRMED` exige status inequívoco de rejeição/cancelamento sem fill e evidência persistida. Somente então a intenção pode ser encerrada ou, após nova decisão e risco, reenviada com a mesma identidade e tentativa auditada.

Rejeição com fill parcial não é rejeição pura; permanece posição real a proteger e reconciliar.

---

## 19. Tratamento de timeout ou resposta ambígua

```text
ENTRY_SUBMITTING
      │ timeout / conexão perdida / resposta ambígua
      ▼
ENTRY_SUBMISSION_UNKNOWN
      ▼
RECONCILIATION_REQUIRED
      ├── ordem/fill encontrado ──▶ ENTRY_PARTIALLY_FILLED ou ENTRY_CONFIRMED
      ├── rejeição comprovada ────▶ ENTRY_REJECTED_CONFIRMED
      └── evidência insuficiente ─▶ permanece bloqueado
```

Timeout não prova falha. Ausência de resposta não prova ausência de execução. `ENTRY_SUBMISSION_UNKNOWN` proíbe nova entrada até reconciliação conclusiva.

---

## 20. Reconciliação antes de retry

Reconciliation consulta, nesta ordem aplicável, `client_order_id`, `exchange_order_id`, status da ordem, fills, quantidade e posição reconciliada. O resultado e suas fontes são persistidos.

Retry só é permitido quando existe prova suficiente de não execução ou rejeição confirmada. Persistindo dúvida, o lifecycle continua em `RECONCILIATION_REQUIRED`.

---

## 21. Registro no Trade Registry

Registry recebe eventos desde o signal, mas só registra entrada, quantidade, proteção e close como confirmados com evidência correspondente. Mantém IDs, modo, tentativas, fills, quantidades, stop, gestão e reconciliação por lifecycle.

Logs, Redis, arquivos e estado da exchange apoiam auditoria; não substituem o Registry como fonte primária do lifecycle.

---

## 22. Criação e confirmação do disaster stop

```text
ENTRY_CONFIRMED / ENTRY_PARTIALLY_FILLED
              ▼
Execution solicita proteção ao Broker
              ▼
Broker cria/consulta stop físico na exchange
        ┌─────┴───────────┐
        ▼                 ▼
stop aberto, lado e   ausente/rejeitado/
qty confirmados       resposta ambígua
        ▼                 ▼
ENTRY_PROTECTED       ENTRY_CONFIRMED_STOP_MISSING
```

Confirmação exige ID, status aberto/ativo, lado correto, trigger válido, quantidade protegida e timestamp. A resposta de criação isolada não basta.

---

## 23. Estado `ENTRY_CONFIRMED_STOP_MISSING`

É estado crítico: há fill/posição real confirmada, mas proteção física suficiente não foi confirmada. Bloqueia novas entradas conflitantes e gestão não essencial, ativa alerta, auditoria, `RECOVERY_REQUIRED` e watchdog.

Esse estado nunca pode ser convertido em `ENTRY_PROTECTED` por suposição ou proteção virtual.

---

## 24. Recovery de posição sem proteção

Recovery primeiro reconcilia quantidade e stops existentes. Se não houver proteção suficiente, solicita criação/reparo idempotente. Se a proteção não puder ser confirmada, aplica a política fail-safe aprovada, que pode incluir fechamento controlado da quantidade pertencente ao lifecycle.

Recovery nunca fecha ou protege posição manual e registra cada tentativa.

---

## 25. Gestão da posição

Somente `ENTRY_PROTECTED` com ownership e quantidade reconciliados avança para `POSITION_MANAGED`. Management observa gatilhos do lifecycle e solicita ações por Execution.

Solicitar TP50, stop, break-even, trailing ou close não atualiza o estado local antes da confirmação.

---

## 26. TP50

```text
POSITION_MANAGED
      ▼ gatilho válido
TP50_PENDING
      ▼ ordem de redução via Execution/Broker
fill parcial confirmado + quantidade reconciliada
      ▼
TP50_CONFIRMED
      ▼
redimensionar e confirmar proteção
      ▼
RUNNER_PROTECTED
```

TP50 usa quantidade compatível com constraints e pertence somente ao lifecycle. Confirmação parcial mantém `TP50_PENDING` com quantidade executada explícita até resolução.

---

## 27. Runner

Runner é a quantidade remanescente confirmada após redução parcial. Só entra em `RUNNER_PROTECTED` quando sua quantidade e proteção física forem reconciliadas.

Runner sem proteção é crítico, exige `RECOVERY_REQUIRED` e bloqueia trailing ou nova redução não essencial.

---

## 28. Break-even

Gatilho válido produz `BREAK_EVEN_PENDING`. Execution solicita substituição/ajuste de stop; `BREAK_EVEN_ACTIVE` exige proteção aberta confirmada no preço e quantidade corretos.

Falha ou timeout mantém o estado pendente e exige reconciliação; nunca se declara break-even apenas porque a solicitação retornou.

---

## 29. Trailing

`TRAILING_PENDING` registra trigger, stop anterior e novo stop proposto. `TRAILING_ACTIVE` exige confirmação do stop novo e preservação de risco não maior que o permitido.

Cada atualização é idempotente, monotônica segundo a estratégia e restrita ao lifecycle.

---

## 30. Redimensionamento do disaster stop

Após qualquer redução confirmada, a proteção deve corresponder à quantidade remanescente. Cancel/replace minimiza a janela sem proteção e deve preferir edição atômica quando suportada.

Ao cancelar e recriar, a confirmação do cancelamento não autoriza declarar o novo stop ativo. Falha exige rollback para a proteção anterior quando possível ou failsafe explícito.

---

## 31. Fechamento parcial

Execution calcula no máximo a quantidade pertencente ao lifecycle, valida constraints e registra `CLOSE_PENDING`. Fill parcial de saída produz `CLOSE_PARTIALLY_CONFIRMED`, atualiza quantidade remanescente confirmada e exige proteção redimensionada.

---

## 32. Fechamento total

```text
POSITION_MANAGED / RUNNER_PROTECTED
              ▼
         CLOSE_PENDING
        ┌─────┴──────────┐
        ▼                ▼
fill parcial         qty total confirmada
        ▼                ▼
CLOSE_PARTIALLY_     CLOSE_CONFIRMED
CONFIRMED                ▼
        └── retry após reconciliação
```

Fechamento total usa a quantidade remanescente reconciliada do lifecycle, não a posição agregada da exchange.

---

## 33. Confirmação de close

Close exige fills de saída, quantidade acumulada e posição reconciliada compatíveis com zero remanescente do trade. Cancelamento de stops residuais também deve ser confirmado e auditado.

Uma posição agregada ainda aberta pode pertencer a outro bot ou ser manual; isso não invalida o close do lifecycle confirmado.

---

## 34. Outcome

`CLOSE_CONFIRMED` produz `OUTCOME_PENDING`. Outcome Evaluator usa fills de entrada/saída, custos, quantidade, MFE, MAE, modo e contexto. Após validação e persistência, avança para `OUTCOME_RECORDED`.

Outcome não é criado para posição aberta, close incerto ou ownership insuficiente.

---

## 35. Analytics

Analytics consome outcomes e lifecycles reconciliados para calcular PnL, R, expectancy, win rate, drawdown, MAE/MFE e qualidade de execução por bot/setup. Posições manuais e preço médio agregado não contaminam essas métricas.

```text
CLOSE_CONFIRMED → OUTCOME_PENDING → OUTCOME_RECORDED
                                           ▼
                                       Analytics
                                           ▼
                                  evidência estatística
```

---

## 36. Learning

Somente `OUTCOME_RECORDED` validado pode se tornar `LEARNING_ELIGIBLE`. Learning pode recomendar pesos, confiança ou política, mas nunca executa, altera posição ou ultrapassa Decision/Risk/Execution.

Outcome PAPER deve permanecer segregado de LIVE.

---

## 37. PAPER

PAPER simula execução, lifecycle e resultado sem chamar exchange. Preserva IDs e estados equivalentes, mas marca toda evidência como PAPER e usa fills simulados explicitamente.

```text
Signal → Decision → Risk → Execution Plan
                         ├── PAPER ──▶ lifecycle simulado ──▶ outcome PAPER
                         ├── DRY RUN ▶ validação/payload ───▶ sem fill
                         └── LIVE ───▶ Broker/Exchange ─────▶ evidência real
```

PAPER pode alimentar Analytics segregado; nunca deve aparentar fill ou posição LIVE.

---

## 38. DRY RUN

DRY RUN valida plano, gates, payload, constraints e preview sem enviar ordem e sem simular fill como LIVE. Deve produzir evidência positiva de que Broker mutável, exchange, rede e serviços externos não foram chamados.

Não cria `ENTRY_SUBMITTING`, posição ou disaster stop real.

---

## 39. LIVE

LIVE exige configuração explícita, gates positivos, Broker READY, decisão e risco aprovados, identidade persistida, idempotência, confirmação, disaster stop físico e reconciliação.

Qualquer gate ausente encerra de forma conservadora. LIVE nunca é ativado por import, teste, diagnóstico ou ausência de bloqueio.

---

## 40. Posições manuais e externas

```text
Snapshot da exchange + Registry da Central
                  ▼
      evidência forte de ownership?
        ┌─────────┴─────────┐
       sim                 não
        ▼                   ▼
Central Position     MANUAL_POSITION_DETECTED
                            ▼
                    EXTERNAL_EXPOSURE_ONLY
                    (observar; não gerir)
```

Posição manual nunca pertence ao Falcon ou a outro bot. Pode influenciar exposição global, mas não pode ser gerida, fechada, protegida ou usada em estatística de bot. Símbolo/lado apenas ajudam awareness.

---

## 41. Múltiplos bots no mesmo ativo

```text
Bot A ─▶ lifecycle A ─▶ fills A ─▶ gestão/stop/outcome A
             │
             ├──────── Exchange pode agregar símbolo/lado
             │
Bot B ─▶ lifecycle B ─▶ fills B ─▶ gestão/stop/outcome B

Central preserva: IDs, quantidades, TP50, BE, trailing e PnL separados.
```

Restrição operacional por limitação da exchange pode bloquear nova ação, mas nunca transfere ownership. A posição agregada não substitui fills por lifecycle.

---

## 42. Reinício da Central

O bootstrap carrega Registry, ledger e eventos antes de habilitar novas ações. Lifecycles não terminais são classificados por estado persistido, e nenhuma submissão é repetida automaticamente.

Reinício durante `ENTRY_SUBMITTING` produz ou preserva `ENTRY_SUBMISSION_UNKNOWN` e `RECONCILIATION_REQUIRED` até prova externa.

---

## 43. Recovery após reinício

Recovery reconcilia ordens, fills, posições, stops, quantidades e closes usando IDs persistidos. `ENTRY_CONFIRMED_STOP_MISSING` recebe prioridade de proteção sobre novas oportunidades.

Estado não recuperável permanece explícito, bloqueado e alertado; não é substituído por inferência conveniente.

---

## 44. Pontos obrigatórios de auditoria

Devem gerar evento persistido: signal; decisão; política aplicada; risk result; plano; intenção; submissão; resposta; ordem; fill; divergência; reconciliação; criação/consulta/cancelamento/substituição de stop; TP50; runner; BE; trailing; close; outcome; retry; recovery; posição manual; mudança de modo e reinício.

Cada evento contém IDs do trade/lifecycle, modo, timestamp, ator/componente, tentativa, estado anterior/novo, evidência e motivo.

---

## 45. Estados que bloqueiam novas ações

Bloqueiam nova entrada ou ação conflitante: `DECISION_DENIED`, `RISK_DENIED`, `ENTRY_SUBMITTING` concorrente, `ENTRY_SUBMISSION_UNKNOWN`, `RECONCILIATION_REQUIRED`, `ENTRY_CONFIRMED_STOP_MISSING`, `RECOVERY_REQUIRED`, runner sem proteção, `CLOSE_PENDING` ambíguo e ownership incerto.

`MANUAL_POSITION_DETECTED` não bloqueia globalmente um bot por simples existência; somente uma restrição explícita de risco/agregação pode limitar ação, sem transferir ownership.

---

## 46. Fluxos específicos e de falha

### A. Fluxo nominal LIVE

Signal → Decision → Risk → intenção persistida → submissão → ordem/fill confirmados → stop confirmado → gestão → close confirmado → outcome → Learning elegível.

### B. Fluxo PAPER

Segue identidade e lifecycle equivalentes com fills simulados marcados PAPER; não chama Broker/Exchange.

### C. Fluxo DRY RUN

Valida plano, gates e payload; termina com evidência de zero chamadas externas e sem fill.

### D. Ordem rejeitada

Somente rejeição inequívoca sem fill produz `ENTRY_REJECTED_CONFIRMED`; qualquer fill muda o fluxo para posição real.

### E. Timeout antes da confirmação

Vai para `ENTRY_SUBMISSION_UNKNOWN`; não presume ausência de envio e exige reconciliação.

### F. Timeout após possível aceite

Busca ordem/fills por IDs; retry fica proibido até prova de não execução.

### G. Fill parcial

Registra `ENTRY_PARTIALLY_FILLED`, protege a quantidade executada e resolve/cancela o restante por política explícita.

### H. Entrada confirmada sem disaster stop

Entra em `ENTRY_CONFIRMED_STOP_MISSING` e `RECOVERY_REQUIRED`, alerta e bloqueia novas ações conflitantes.

### I. Falha de cancelamento/recriação de stop

Preserva stop anterior quando possível; tenta rollback ou failsafe e nunca declara proteção nova sem consulta.

### J. TP50 parcialmente confirmado

Mantém `TP50_PENDING`, registra fill parcial, reconcilia remanescente e redimensiona proteção apenas pela quantidade confirmada.

### K. Runner sem proteção

É crítico; bloqueia gestão não essencial, ativa recovery e pode aplicar failsafe aprovado.

### L. Fechamento parcial

Produz `CLOSE_PARTIALLY_CONFIRMED`, mantém lifecycle aberto e confirma proteção da quantidade restante.

### M. Fechamento total

Somente fills e zero remanescente reconciliado produzem `CLOSE_CONFIRMED`.

### N. Reinício durante `ENTRY_SUBMITTING`

Recupera identidade e marca submissão desconhecida até reconciliar ordem/fills; não reenvia automaticamente.

### O. Reinício durante `ENTRY_CONFIRMED_STOP_MISSING`

Prioriza reconciliação e proteção/failsafe antes de habilitar novas entradas.

### P. Posição manual no mesmo símbolo/lado

Registra exposição externa, não atribui ao trade e não a fecha/protege; símbolo/lado não provam ownership.

### Q. Dois bots no mesmo símbolo/lado

Mantém IDs, fills, quantidades, stops, gestão e outcomes separados, ainda que a exchange agregue fisicamente.

### R. Divergência Central × BingX

Interrompe ações conflitantes, preserva proteção, cria `RECONCILIATION_REQUIRED`, registra evidências e só avança após explicação suficiente.

---

## 47. Matriz de transições e catálogo de estados

| Estado | Significado | Evento de entrada | Confirmação necessária | Ações permitidas | Ações proibidas | Próximos estados possíveis | Condição de bloqueio | Evidência mínima |
|---|---|---|---|---|---|---|---|---|
| `SIGNAL_DETECTED` | Setup detectado | Signal emitido | Payload e `signal_id` persistidos | Avaliar Decision | Executar | `DECISION_PENDING` | Signal inválido/expirado | Signal, bot, setup, timestamp |
| `DECISION_PENDING` | Elegibilidade em avaliação | Signal aceito para análise | Registro da avaliação | Aplicar políticas | Enviar ordem | `DECISION_ALLOWED`, `DECISION_DENIED` | Contexto insuficiente | Signal/decision IDs, política |
| `DECISION_ALLOWED` | Trade elegível | Decisão ALLOW | Decisão persistida | Solicitar Risk | Executar | `RISK_PENDING` | Condição não satisfeita | Decision ID, motivo, versão |
| `DECISION_DENIED` | Trade inelegível | Decisão DENY | Decisão persistida | Encerrar/observar | Criar intenção | Terminal ou nova avaliação | Sempre bloqueia execução | Decision ID, motivo |
| `RISK_PENDING` | Risco e size em cálculo | Decision permitida | Snapshot de capital/exposição | Calcular limites | Executar | `RISK_APPROVED`, `RISK_DENIED` | Dados/limites ausentes | Decision ID, capital, exposição |
| `RISK_APPROVED` | Size autorizado | Risk aprovado | Resultado persistido | Construir plano | Aumentar size | `ENTRY_INTENT_RECORDED` | Aprovação expirada | Size, limites, risk ID |
| `RISK_DENIED` | Risco recusado | Risk negado | Motivo persistido | Encerrar/observar | Executar | Terminal ou nova avaliação | Sempre bloqueia execução | Risk ID, motivo |
| `ENTRY_INTENT_RECORDED` | Intenção idempotente persistida | Plano válido | IDs e ledger gravados | Submeter uma vez | Nova identidade/retry cego | `ENTRY_SUBMITTING` | Falha de persistência | Trade/lifecycle/client IDs, payload |
| `ENTRY_SUBMITTING` | Comando em trânsito | Chamada autorizada ao Broker | Evento pré-envio persistido | Aguardar/consultar | Submeter em paralelo | `ENTRY_CONFIRMED`, `ENTRY_PARTIALLY_FILLED`, `ENTRY_REJECTED_CONFIRMED`, `ENTRY_SUBMISSION_UNKNOWN` | Resultado pendente | Tentativa, timestamp, client ID |
| `ENTRY_SUBMISSION_UNKNOWN` | Resultado ambíguo | Timeout/perda de resposta | Ambiguidade persistida | Reconciliar | Retry/assumir falha | `RECONCILIATION_REQUIRED` | Até reconciliação | Client ID, erro, timestamp |
| `ENTRY_REJECTED_CONFIRMED` | Rejeição sem fill | Status inequívoco | Status e ausência de fills | Encerrar/reavaliar | Marcar posição | Terminal ou `ENTRY_SUBMITTING` após gates | Fill ou dúvida | IDs, status, consulta de fills |
| `ENTRY_PARTIALLY_FILLED` | Parte da entrada executada | Fill parcial | Fills e qty cumulativa | Proteger/reconciliar restante | Presumir total/retry integral | `ENTRY_CONFIRMED`, `ENTRY_PROTECTED`, `RECONCILIATION_REQUIRED` | Quantidade/proteção incertas | Fill IDs, qty, posição |
| `ENTRY_CONFIRMED` | Entrada executada | Fill suficiente | Fills correlacionados | Criar/confirmar stop | Reenviar entrada | `ENTRY_PROTECTED`, `ENTRY_CONFIRMED_STOP_MISSING` | Stop ainda não confirmado | Order/fill IDs, preço, qty |
| `ENTRY_CONFIRMED_STOP_MISSING` | Posição real sem proteção confirmada | Stop ausente/rejeitado/ambíguo | Fill e falta de stop | Recovery/failsafe | Nova entrada/gestão não essencial | `RECOVERY_REQUIRED`, `ENTRY_PROTECTED`, `CLOSE_PENDING` | Enquanto desprotegida | Qty, consulta de stops, alerta |
| `ENTRY_PROTECTED` | Posição e stop confirmados | Stop físico validado | Status, lado e qty do stop | Iniciar gestão | Declarar qty diferente | `POSITION_MANAGED` | Divergência de proteção | Stop ID/status/qty/timestamp |
| `POSITION_MANAGED` | Gestão ativa do lifecycle | Ownership e proteção válidos | Registry reconciliado | TP50/BE/trailing/close | Gerir posição externa | `TP50_PENDING`, `BREAK_EVEN_PENDING`, `TRAILING_PENDING`, `CLOSE_PENDING` | Ownership/proteção incertos | Lifecycle, qty, stop |
| `TP50_PENDING` | Redução TP50 solicitada | Gatilho e comando registrados | Ainda aguardando fills | Consultar/reconciliar | Marcar TP50/duplicar close | `TP50_CONFIRMED`, `RECONCILIATION_REQUIRED` | Resultado ambíguo | Client/order IDs, qty alvo |
| `TP50_CONFIRMED` | Redução TP50 confirmada | Fill parcial de saída | Fill e remanescente | Redimensionar stop | Presumir runner protegido | `RUNNER_PROTECTED`, `RECOVERY_REQUIRED` | Stop do runner pendente | Fill, qty fechada/restante |
| `RUNNER_PROTECTED` | Remanescente protegido | Stop redimensionado confirmado | Stop e qty reconciliados | BE/trailing/close | Gerir qty alheia | `BREAK_EVEN_PENDING`, `TRAILING_PENDING`, `CLOSE_PENDING` | Stop divergente | Runner qty, stop ID/status |
| `BREAK_EVEN_PENDING` | Ajuste BE solicitado | Gatilho registrado | Stop novo pendente | Consultar/reconciliar | Declarar BE ativo | `BREAK_EVEN_ACTIVE`, `RECOVERY_REQUIRED` | Substituição incerta | Stop antigo/novo, tentativa |
| `BREAK_EVEN_ACTIVE` | Proteção BE confirmada | Stop BE validado | Status/preço/qty | Trailing/close | Aumentar risco | `TRAILING_PENDING`, `CLOSE_PENDING` | Proteção perdida | Stop ID, preço, qty |
| `TRAILING_PENDING` | Atualização trailing solicitada | Novo nível registrado | Stop novo pendente | Consultar/rollback | Declarar trailing ativo | `TRAILING_ACTIVE`, `RECOVERY_REQUIRED` | Replace incerto | Stop antigo/novo, trigger |
| `TRAILING_ACTIVE` | Trailing confirmado | Stop novo validado | Status/preço/qty | Nova atualização/close | Afrouxar risco indevido | `TRAILING_PENDING`, `CLOSE_PENDING` | Proteção divergente | Stop ID, preço, qty |
| `CLOSE_PENDING` | Fechamento solicitado | Comando de saída persistido | Aguardando fills | Consultar/reconciliar | Declarar close/repetir cegamente | `CLOSE_PARTIALLY_CONFIRMED`, `CLOSE_CONFIRMED`, `RECONCILIATION_REQUIRED` | Resultado ambíguo | Client/order IDs, qty |
| `CLOSE_PARTIALLY_CONFIRMED` | Parte fechada | Fill parcial de saída | Fill e remanescente | Proteger restante/reconciliar | Outcome/close total presumido | `CLOSE_PENDING`, `CLOSE_CONFIRMED`, `RUNNER_PROTECTED` | Remanescente incerto | Fills, qty restante |
| `CLOSE_CONFIRMED` | Lifecycle sem quantidade aberta | Fills de saída completos | Zero remanescente reconciliado | Avaliar outcome | Nova gestão | `OUTCOME_PENDING` | Stops/resíduos incertos | Fills, qty zero, timestamp |
| `OUTCOME_PENDING` | Resultado em validação | Close confirmado | Dados completos | Calcular/validar | Learning | `OUTCOME_RECORDED` | Dados/ownership insuficientes | Lifecycle, fills, custos |
| `OUTCOME_RECORDED` | Resultado confiável persistido | Outcome validado | Registro durável | Analytics | Reescrever sem evento | `LEARNING_ELIGIBLE` | Qualidade insuficiente | Outcome ID, métricas, modo |
| `LEARNING_ELIGIBLE` | Outcome apto ao aprendizado | Gate de qualidade aprovado | Ownership/mode/outcome | Learning/Analytics | Executar | Terminal analítico | PAPER/LIVE misturados | Outcome e elegibilidade |
| `RECONCILIATION_REQUIRED` | Verdades interna/externa incertas | Timeout/divergência/reinício | Consultas correlacionadas | Reconciliar/alertar | Retry/gestão conflitante | Estado factual correspondente, `RECOVERY_REQUIRED` | Até evidência suficiente | IDs, ordens, fills, posição |
| `RECOVERY_REQUIRED` | Segurança/consistência deve ser restaurada | Stop/registry/close crítico | Plano e evidências de recovery | Proteger/rollback/failsafe | Nova exposição conflitante | `ENTRY_PROTECTED`, `RUNNER_PROTECTED`, `CLOSE_CONFIRMED`, `RECONCILIATION_REQUIRED` | Enquanto risco persiste | Alerta, tentativas, estado externo |
| `MANUAL_POSITION_DETECTED` | Posição sem ownership Central | Snapshot externo não casado por evidência forte | Ausência de IDs/fills Central | Exibir/medir exposição | Gerir/atribuir a bot | `EXTERNAL_EXPOSURE_ONLY` | Sempre bloqueia gestão automática | Snapshot, comparação Registry |
| `EXTERNAL_EXPOSURE_ONLY` | Exposição externa segregada | Classificação manual/externa | Registro de awareness | Informar Risk/Observabilidade | Estatística/stop/close Central | Permanece externa ou sai por evento externo | Sem ownership comprovado | Snapshot e classificação |

---

## 48. Matriz de confirmação

| Etapa | Solicitação não basta porque | Evidência mínima para conclusão |
|---|---|---|
| Ordem de entrada | Chamada pode falhar após aceite | Client ID, exchange order ID, status e timestamp |
| Fill | Ordem aceita pode não executar | Fills, preço, quantidade, order ID e timestamp |
| Disaster stop | Criação pode ser rejeitada/expirar | Proteção aberta, ID, status, lado, trigger e qty |
| TP50 | Close pode ser parcial/ambíguo | Fill de saída, qty fechada e posição reconciliada |
| Break-even | Replace pode não se efetivar | Stop aberto confirmado, preço e qty |
| Trailing | Atualização pode falhar após cancel | Stop novo aberto, preço, qty e stop anterior tratado |
| Cancelamento de stop | Pedido pode não cancelar | Status cancelado/fechado e consulta de ordens abertas |
| Substituição de stop | Cancel não confirma novo stop | ID/status do novo stop, preço e qty |
| Fechamento parcial | Ordem pode preencher parcialmente | Fills e quantidade remanescente reconciliada |
| Fechamento total | Resposta não prova posição zerada | Fills totais, qty zero do lifecycle e evento persistido |

Toda confirmação inclui timestamp e evento persistido no Registry/History. Posição reconciliada complementa, mas não substitui IDs e fills por lifecycle.

---

## 49. Matriz de retries permitidos e proibidos

| Situação | Retry | Condição obrigatória |
|---|---|---|
| Reavaliação de Decision | Permitido | Mesma identidade; evento e política versionados |
| Rejeição confirmada sem fill | Condicional | Nova aprovação, mesma identidade e tentativa auditada |
| `ENTRY_SUBMISSION_UNKNOWN` | Proibido | Só após reconciliação provar não execução |
| Fill parcial de entrada | Proibido como entrada integral | Resolver restante e proteger qty executada |
| Fill confirmado | Proibido | Nunca reenviar entrada confirmada |
| Disaster stop ausente | Permitido | Mesma proteção lógica; consultar stops; preservar proteção existente |
| Cancel/replace de stop | Condicional | Rollback/failsafe e confirmação de cada etapa |
| TP50 ambíguo | Proibido | Reconciliar fills e quantidade restante |
| Close parcial | Condicional | Consultar qty remanescente e usar somente essa quantidade |
| Close ambíguo | Proibido | Reconciliar ordem, fills e posição por lifecycle |
| Após reinício | Condicional | Recuperar ledger/Registry e reconciliar antes |
| Matching apenas por símbolo/lado | Proibido | Exigir identidade, orders, fills e qty reconciliada |
| Posição manual | Proibido | Nunca executar retry, proteção ou close da Central |

Todo retry preserva identidade persistente, registra número da tentativa, motivo, evidência anterior e resultado.

---

## 50. Compatibilidades transitórias da implementação atual

| Condição atual | Classificação | Tratamento arquitetural | Dívida relacionada |
|---|---|---|---|
| Falcon → Broker direto | Compatibilidade transitória / risco em tratamento | Convergir para autoridade de Execution sem retirar proteções | TD-007, TD-009 |
| Wrappers sucessivos do Execution Engine | Dívida técnica aceita | Caracterizar e migrar para pipeline único testado | TD-002 |
| Monkey patches operacionais | Dívida técnica | Não tratar como contrato; remover só após testes | TD-001, TD-003 |
| Runtime iniciado no import | Migração planejada / risco operacional | Bootstrap explícito e import safety | TD-004, TD-005 |
| Lifecycle distribuído | Migração planejada | Máquina de estados oficial por lifecycle | TD-009 |
| Matching parcial por símbolo/lado | Risco operacional em tratamento | Usar somente para awareness; ownership por IDs/fills | TD-008 |
| Persistência distribuída | Migração planejada | Registry como fonte primária e adapters explícitos | TD-001, TD-009 |
| Gestão entre bot, Broker e `main.py` | Compatibilidade transitória | Management por lifecycle através de Execution | TD-001, TD-003, TD-009 |
| Stop considerado pela resposta inicial | Risco operacional em tratamento | Consulta posterior obrigatória | TD-010 |

Nenhuma dessas condições é o fluxo oficial. Migração deve ser incremental, coberta por testes sem rede, plano, impacto e rollback; não se recomenda refatoração ampla imediata.

---

## 51. Critérios para alteração futura do fluxo

Uma alteração exige problema documentado, autoridade responsável, estados/transições afetados, confirmação mínima, impacto em ownership/idempotência/proteção, comportamento de falha, reconciliação, testes sem rede, migração, rollback e ADR quando mudar lifecycle, ownership, execução, proteção ou fonte de verdade.

Nenhuma implementação isolada altera automaticamente este fluxo.

---

## 52. Relação com os demais documentos

- `00-Vision.md`: princípios superiores;
- `01-Architecture.md`: autoridades e dependências;
- `03-System-Components.md`: owners e contratos dos componentes;
- `05-Broker-Integration.md`: tradução e confirmação com a exchange;
- `06-Bot-Architecture.md`: geração de signals e independência dos bots;
- `07-Risk-Management.md`: sizing, exposição e limites;
- `08-Lifecycle.md`: especificação aprofundada dos estados;
- `09-Learning-System.md`: outcome, Analytics e Learning;
- `Glossary.md`: vocabulário canônico;
- `KNOWN_DEBT.md`: divergências confirmadas;
- ADRs: decisões arquiteturais aplicáveis.

---

# Event Timeline

A sequência oficial de eventos da Central Quant é:

`SIGNAL → DECISION → RISK → ENTRY_INTENT → ENTRY_SUBMITTING → ENTRY_CONFIRMED → ENTRY_PROTECTED → POSITION_MANAGED → TP50 → RUNNER → BREAK_EVEN → TRAILING → CLOSE → OUTCOME → ANALYTICS → LEARNING`

- `SIGNAL`: sinal bruto recebido ou produzido por uma estratégia.
- `DECISION`: decisão estruturada sobre aceitar, negar, bloquear ou revisar o sinal.
- `RISK`: validação de risco, exposição, capital, limites e políticas executivas.
- `ENTRY_INTENT`: intenção formal e persistível de abrir um trade.
- `ENTRY_SUBMITTING`: estado transitório durante a tentativa de envio da ordem.
- `ENTRY_CONFIRMED`: entrada confirmada por evidência válida de ordem ou fill.
- `ENTRY_PROTECTED`: posição confirmada como protegida por stop operacional ou disaster stop físico.
- `POSITION_MANAGED`: posição sob gestão ativa do lifecycle.
- `TP50`: realização parcial de 50% ou evento equivalente definido pela estratégia.
- `RUNNER`: parcela remanescente mantida após a realização parcial.
- `BREAK_EVEN`: proteção movida para o preço de entrada ou nível equivalente.
- `TRAILING`: proteção dinâmica que acompanha a evolução favorável do trade.
- `CLOSE`: fechamento total confirmado.
- `OUTCOME`: resultado final consolidado e atribuído ao trade correto.
- `ANALYTICS`: processamento estatístico, métricas e avaliação de desempenho.
- `LEARNING`: uso dos resultados para aprendizado, adaptação e evolução das políticas.

Nem todo trade percorre todos os estados intermediários. `TP50`, `RUNNER`, `BREAK_EVEN` e `TRAILING` dependem da estratégia e das condições do trade; quando aplicáveis, a ordem dos eventos deve ser preservada. Toda confirmação depende de evidência suficiente, não apenas de intenção ou estado local. A Central Quant mantém autoridade sobre lifecycle e estatísticas, enquanto a exchange atua como executora, custodiante e fonte de evidências operacionais.

---

# Identity Chain

A sequência oficial de identificadores é:

`Signal ID → Decision ID → Trade ID → Lifecycle ID → Client Order ID → Exchange Order ID → Fill ID → Outcome ID`

- `Signal ID`: identifica de forma única o sinal original.
- `Decision ID`: identifica a decisão produzida a partir do sinal.
- `Trade ID`: identidade lógica e permanente do trade dentro da Central Quant.
- `Lifecycle ID`: identidade da instância de lifecycle e de sua máquina de estados.
- `Client Order ID`: identificador criado pela Central para rastrear a ordem enviada.
- `Exchange Order ID`: identificador atribuído pela exchange à ordem.
- `Fill ID`: identificador de cada execução ou preenchimento confirmado.
- `Outcome ID`: identificador do resultado final consolidado do trade.

Esses IDs formam uma cadeia de rastreabilidade na qual cada identificador possui responsabilidade distinta e não deve ser reutilizado entre trades independentes. O `Trade ID` permanece estável durante toda a vida do trade, enquanto o `Lifecycle ID` identifica seu acompanhamento pela máquina de estados. O `Client Order ID` deve existir antes do envio; `Exchange Order ID` e `Fill ID` somente existem após confirmação da exchange.

Um mesmo `Exchange Order ID` pode possuir múltiplos fills, e um mesmo `Trade ID` ou `Lifecycle ID` pode estar associado a múltiplas ordens. O `Outcome ID` deve referenciar os `Trade ID` e `Lifecycle ID` correspondentes. A cadeia completa deve permitir auditoria do sinal original até Analytics e Learning.

---

## 53. Status final

Este documento define o fluxo operacional oficial aprovado da arquitetura-alvo da Central Quant.

Ele não autoriza execução real, mudança de configuração, migração ou alteração de código.

---
