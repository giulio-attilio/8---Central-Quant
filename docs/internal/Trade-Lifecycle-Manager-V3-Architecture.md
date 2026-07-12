# Trade Lifecycle Manager V3 — Arquitetura Oficial

Status: DRAFT
Versão: 0.1
Última revisão: 11/07/2026
Responsável: CTO
Implementação: Pendente
Aprovado: Não

---

## 1. Propósito

O Trade Lifecycle Manager V3 será o componente responsável por coordenar, validar e persistir o ciclo de vida completo de cada trade da Central Quant.

Ele existirá para garantir que cada trade possua:

- identidade própria;
- estado explícito;
- transições válidas;
- ownership comprovável;
- quantidade individual;
- proteção individual;
- gestão individual;
- outcome individual;
- histórico auditável.

O componente não executará ordens, não decidirá estratégia e não substituirá o Broker, o Execution Engine ou o Trade Registry.

---

## 2. Posição arquitetural

```text
Bot / Strategy
      ↓
Decision
      ↓
Risk
      ↓
Execution Orchestrator
      ↓
Trade Lifecycle Manager V3
      ↓
Execution Engine
      ↓
Broker
      ↓
Exchange

Eventos confirmados retornam por:

Exchange
   ↓
Broker
   ↓
Execution / Reconciliation
   ↓
Trade Lifecycle Manager V3
   ↓
Trade Registry / History / Analytics
```

O Trade Lifecycle Manager V3 ficará entre a intenção operacional e a persistência do estado do trade.

---

## 3. Responsabilidade dominante

A responsabilidade dominante será:

> Aplicar e preservar a máquina de estados oficial de cada trade, com identidade, evidência, ownership e quantidade por lifecycle.

---

## 4. Autoridade permitida

O componente poderá:

- criar um lifecycle;
- validar transições;
- aceitar ou rejeitar eventos;
- manter estado atual;
- manter histórico de transições;
- associar IDs;
- registrar fills;
- registrar quantidades;
- registrar proteção;
- registrar TP50;
- registrar break-even;
- registrar trailing;
- registrar close;
- registrar outcome;
- marcar reconciliação necessária;
- marcar recovery necessário;
- bloquear transição inválida;
- expor snapshots;
- gerar eventos auditáveis.

---

## 5. Autoridade proibida

O componente nunca poderá:

- gerar signal;
- aprovar strategy;
- calcular score;
- decidir risco;
- enviar ordem;
- chamar BingX diretamente;
- alterar alavancagem;
- calcular size;
- cancelar ordem;
- fechar posição;
- proteger posição manual;
- atribuir ownership apenas por símbolo e lado;
- inferir fill sem evidência;
- declarar stop ativo sem confirmação;
- declarar close sem fills e quantidade reconciliada.

---

## 6. Identidade canônica

Cada lifecycle deverá possuir:

```text
signal_id
decision_id
trade_id
lifecycle_id
client_order_id
exchange_order_id
fill_ids[]
outcome_id
```

### Regras

- `trade_id` identifica o trade lógico.
- `lifecycle_id` identifica a instância operacional daquele trade.
- `signal_id` identifica a origem estratégica.
- `decision_id` identifica a autorização.
- `client_order_id` identifica a intenção enviada.
- `exchange_order_id` identifica a ordem na exchange.
- `fill_ids` identificam execuções reais.
- `outcome_id` identifica o resultado final.

Símbolo e lado são atributos, não identidade.

---

## 7. Modelo de estado

Estados mínimos:

```text
SIGNAL_DETECTED
DECISION_PENDING
DECISION_ALLOWED
DECISION_DENIED
RISK_PENDING
RISK_APPROVED
RISK_DENIED
ENTRY_INTENT_RECORDED
ENTRY_SUBMITTING
ENTRY_SUBMISSION_UNKNOWN
ENTRY_REJECTED_CONFIRMED
ENTRY_PARTIALLY_FILLED
ENTRY_CONFIRMED
ENTRY_CONFIRMED_STOP_MISSING
ENTRY_PROTECTED
POSITION_MANAGED
TP50_PENDING
TP50_CONFIRMED
RUNNER_PROTECTED
BREAK_EVEN_PENDING
BREAK_EVEN_ACTIVE
TRAILING_PENDING
TRAILING_ACTIVE
CLOSE_PENDING
CLOSE_PARTIALLY_CONFIRMED
CLOSE_CONFIRMED
OUTCOME_PENDING
OUTCOME_RECORDED
LEARNING_ELIGIBLE
RECONCILIATION_REQUIRED
RECOVERY_REQUIRED
MANUAL_POSITION_DETECTED
EXTERNAL_EXPOSURE_ONLY
```

---

## 8. Regras de transição

Cada transição deverá conter:

- estado anterior;
- estado novo;
- evento causador;
- componente emissor;
- timestamp;
- tentativa;
- evidência;
- motivo;
- IDs associados;
- quantidade antes;
- quantidade depois;
- proteção antes;
- proteção depois.

Uma transição só será aceita quando:

1. o estado anterior permitir a transição;
2. a evidência mínima existir;
3. o evento pertencer ao mesmo lifecycle;
4. não houver conflito de ownership;
5. a quantidade for reconciliável;
6. o evento não tiver sido aplicado anteriormente.

---

## 9. Eventos canônicos

Eventos mínimos:

```text
SIGNAL_CREATED
DECISION_RECORDED
RISK_RECORDED
ENTRY_INTENT_CREATED
ENTRY_SUBMITTED
ENTRY_REJECTED
ENTRY_FILL_RECORDED
ENTRY_PARTIAL_RECORDED
ENTRY_CONFIRMED
DISASTER_STOP_REQUESTED
DISASTER_STOP_CONFIRMED
DISASTER_STOP_FAILED
TP50_REQUESTED
TP50_FILL_RECORDED
TP50_CONFIRMED
RUNNER_PROTECTION_CONFIRMED
BREAK_EVEN_REQUESTED
BREAK_EVEN_CONFIRMED
TRAILING_REQUESTED
TRAILING_CONFIRMED
CLOSE_REQUESTED
CLOSE_FILL_RECORDED
CLOSE_CONFIRMED
OUTCOME_CREATED
OUTCOME_CONFIRMED
RECONCILIATION_REQUESTED
RECONCILIATION_COMPLETED
RECOVERY_REQUESTED
RECOVERY_COMPLETED
EXTERNAL_POSITION_DETECTED
```

---

## 10. Estado persistido por lifecycle

Estrutura mínima:

```json
{
  "trade_id": "",
  "lifecycle_id": "",
  "signal_id": "",
  "decision_id": "",
  "bot": "",
  "setup": "",
  "symbol": "",
  "side": "",
  "mode": "PAPER|VERIFY|LIVE",
  "state": "",
  "quantity_planned": 0,
  "quantity_filled": 0,
  "quantity_open": 0,
  "quantity_closed": 0,
  "entry_price_theoretical": 0,
  "entry_price_confirmed": 0,
  "client_order_id": "",
  "exchange_order_id": "",
  "fill_ids": [],
  "disaster_stop": {},
  "tp50": {},
  "break_even": {},
  "trailing": {},
  "close": {},
  "reconciliation": {},
  "outcome": {},
  "created_at": "",
  "updated_at": "",
  "version": 1
}
```

---

## 11. Relação com o Trade Registry

### Trade Lifecycle Manager V3

Responsável por:

- validar estado;
- aplicar transição;
- manter regras;
- produzir eventos;
- rejeitar inconsistência.

### Trade Registry

Responsável por:

- persistir;
- recuperar;
- consultar;
- versionar;
- fornecer snapshot;
- preservar histórico.

### Regra

O Lifecycle Manager decide se a transição é válida.

O Registry persiste o resultado.

O Registry não deverá aplicar regras de transição por conta própria.

---

## 12. Relação com o Execution Orchestrator

O Orchestrator:

- cria o plano;
- gera identidade;
- registra intenção;
- verifica idempotência;
- encaminha para execução.

O Lifecycle Manager:

- cria o lifecycle;
- registra `ENTRY_INTENT_RECORDED`;
- valida `ENTRY_SUBMITTING`;
- recebe eventos posteriores;
- preserva a máquina de estados.

---

## 13. Relação com o Execution Engine

O Execution Engine:

- aplica gates;
- coordena modo;
- chama PAPER ou Broker;
- produz resultado operacional.

O Lifecycle Manager:

- não chama o Engine;
- recebe eventos do Engine;
- valida avanço de estado;
- bloqueia avanço sem confirmação.

---

## 14. Relação com o Broker

O Broker:

- envia;
- consulta;
- cancela;
- fecha;
- protege;
- devolve evidências.

O Lifecycle Manager:

- nunca chama a exchange diretamente;
- recebe evidências normalizadas;
- associa IDs;
- confirma ou recusa a transição.

---

## 15. Relação com o Falcon e outros bots

Bots:

- geram signal;
- mantêm lógica estratégica;
- solicitam gestão por intenção.

Lifecycle Manager:

- mantém estado;
- impede que um bot gerencie trade alheio;
- impede associação de posição manual;
- mantém TP50, BE, trailing e PnL por lifecycle.

---

## 16. Posições manuais

Posições manuais:

- não recebem `trade_id` da Central;
- não recebem `lifecycle_id` da Central;
- não podem ser convertidas automaticamente em trade da Central;
- podem ser registradas como `EXTERNAL_EXPOSURE_ONLY`;
- podem influenciar risco global;
- nunca alimentam estatística de bot;
- nunca são geridas pelo Lifecycle Manager.

---

## 17. Múltiplos bots no mesmo ativo

O Lifecycle Manager deve permitir:

```text
FALCON BTCUSDT LONG lifecycle A
DONKEY BTCUSDT LONG lifecycle B
posição manual BTCUSDT LONG externa
```

Mesmo que a exchange agregue as três exposições.

Cada lifecycle deve manter:

- fills próprios;
- quantidade própria;
- stop próprio;
- TP50 próprio;
- BE próprio;
- trailing próprio;
- outcome próprio.

---

## 18. Idempotência

Toda aplicação de evento deve ser idempotente.

Chave recomendada:

```text
lifecycle_id + event_type + event_id
```

Quando `event_id` não existir:

```text
lifecycle_id + event_type + source_id + timestamp_bucket
```

Eventos duplicados:

- não alteram estado;
- não duplicam fill;
- não duplicam close;
- não duplicam TP50;
- geram auditoria de duplicidade.

---

## 19. Reconciliação

O Lifecycle Manager deverá aceitar resultados de reconciliação com:

- ordens;
- fills;
- posição agregada;
- quantidade atribuível;
- stops;
- closes;
- timestamps;
- nível de confiança.

Resultado possível:

```text
RECONCILED
PARTIALLY_RECONCILED
RECONCILIATION_REQUIRED
OWNERSHIP_UNCERTAIN
EXTERNAL_EXPOSURE_ONLY
```

Posição agregada nunca substitui fills por lifecycle.

---

## 20. Recovery

Recovery terá prioridade quando existir:

- posição sem disaster stop;
- runner sem proteção;
- close ambíguo;
- entry unknown;
- divergência de quantidade;
- divergência de stop;
- Registry incompleto;
- reinício durante execução.

Recovery pode restaurar consistência.

Não pode criar ownership novo.

---

## 21. Interface pública proposta

```python
create_lifecycle(payload) -> result

apply_event(lifecycle_id, event) -> result

get_lifecycle(lifecycle_id) -> snapshot

get_trade_lifecycles(trade_id) -> list

get_open_lifecycles(filters=None) -> list

validate_transition(current_state, event_type) -> result

reconcile_lifecycle(lifecycle_id, evidence) -> result

mark_recovery_required(lifecycle_id, reason, evidence=None) -> result

record_outcome(lifecycle_id, outcome) -> result

get_lifecycle_history(lifecycle_id) -> list

health() -> result
```

---

## 22. Resultados canônicos

Toda operação deverá retornar:

```json
{
  "ok": true,
  "status": "",
  "lifecycle_id": "",
  "trade_id": "",
  "previous_state": "",
  "current_state": "",
  "event_applied": false,
  "duplicate": false,
  "blocked": false,
  "reasons": [],
  "warnings": [],
  "snapshot": {}
}
```

---

## 23. Persistência

Requisitos:

- escrita atômica;
- lock;
- schema versionado;
- backup;
- recovery após corrupção;
- histórico append-only;
- snapshot atual separado do event log;
- nenhuma chamada externa;
- testes com filesystem temporário.

---

## 24. Estrutura de arquivos proposta

```text
trade_lifecycle_manager.py
trade_lifecycle_models.py
trade_lifecycle_transitions.py
trade_lifecycle_repository.py
trade_lifecycle_events.py
```

### Fase inicial recomendada

Começar apenas com:

```text
trade_lifecycle_manager.py
```

Sem quebrar o sistema em vários módulos antes de o contrato estabilizar.

---

## 25. Migração incremental

### Fase 1 — Shadow Mode

- criar lifecycle paralelo;
- consumir eventos;
- não controlar execução;
- comparar com Registry atual;
- gerar divergências.

### Fase 2 — Validation Mode

- validar transições;
- ainda não bloquear produção;
- emitir alertas.

### Fase 3 — Guard Mode

- bloquear transições inválidas;
- bloquear duplicidade;
- bloquear ownership incerto.

### Fase 4 — Authority Mode

- tornar-se autoridade oficial de lifecycle;
- Registry vira repositório;
- bots deixam de alterar estado diretamente.

### Fase 5 — Consolidation

- remover regras duplicadas;
- reduzir monkey patches;
- consolidar gestão por lifecycle.

---

## 26. Testes obrigatórios

- criação de lifecycle;
- IDs obrigatórios;
- transição válida;
- transição inválida;
- evento duplicado;
- fill parcial;
- fill completo;
- entry unknown;
- stop missing;
- stop confirmado;
- TP50 parcial;
- TP50 confirmado;
- runner sem proteção;
- BE;
- trailing;
- close parcial;
- close total;
- outcome;
- reinício;
- recovery;
- posição manual;
- dois bots no mesmo ativo;
- corrupção de arquivo;
- concorrência;
- rollback;
- nenhuma rede.

---

## 27. Critérios de aprovação

O V3 só poderá controlar LIVE quando:

- operar em Shadow Mode sem divergência crítica;
- possuir testes sem rede;
- possuir Fake Exchange;
- possuir replay de eventos;
- preservar trades atuais;
- manter rollback;
- não alterar comportamento do Falcon;
- não atingir posição manual;
- produzir auditoria completa;
- suportar reinício.

---

## 28. Decisões arquiteturais

### TLMV3-A01

Lifecycle Manager não executa ordens.

### TLMV3-A02

Registry persiste; Lifecycle Manager valida.

### TLMV3-A03

Ownership depende de IDs, orders e fills.

### TLMV3-A04

Posições manuais permanecem externas.

### TLMV3-A05

Cada trade possui lifecycle independente.

### TLMV3-A06

Eventos duplicados são idempotentes.

### TLMV3-A07

Estado só avança com evidência suficiente.

### TLMV3-A08

Migração será incremental e reversível.

---

## 29. Próxima implementação

A primeira implementação deverá ser:

```text
Trade Lifecycle Manager V3.0 — Shadow Mode
```

Ela deverá:

- não alterar código operacional;
- não bloquear execução;
- consumir eventos existentes;
- construir lifecycle paralelo;
- comparar com Registry atual;
- registrar divergências;
- funcionar sem rede;
- possuir testes unitários;
- não fazer deploy automático.

---

## 30. Status

Arquitetura proposta para auditoria do CTO.

Nenhum código deve ser alterado antes da aprovação desta especificação.
