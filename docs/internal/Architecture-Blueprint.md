# Central Quant — Architecture Blueprint

**Status:** APPROVED BLUEPRINT  
**Versão:** 1.0  
**Responsável:** CTO  
**Escopo:** Arquitetura-alvo da Central Quant  
**Relação hierárquica:** subordinado a `docs/00-Vision.md`  
**Uso:** base para `01-Architecture.md`, `03-System-Components.md`, `04-Execution-Flow.md`, `05-Broker-Integration.md`, `07-Risk-Management.md`, `08-Lifecycle.md` e ADRs

---

## 1. Propósito

Este Blueprint define a arquitetura oficial que a Central Quant deve preservar e perseguir.

Ele não descreve apenas o código atual. Ele estabelece:

- as camadas do sistema;
- a autoridade de cada camada;
- os contratos entre componentes;
- as dependências permitidas e proibidas;
- a separação entre decisão, risco, execução, custódia e aprendizado;
- a unidade fundamental de ownership;
- o fluxo de lifecycle de cada trade;
- a relação entre a Central, os robôs e a BingX;
- os critérios para evolução arquitetural.

Quando a implementação atual divergir deste Blueprint, a divergência deve ser tratada como dívida técnica, limitação transitória ou requisito de migração. A implementação não redefine a arquitetura por acidente.

---

## 2. Relação com o `00-Vision.md`

O `00-Vision.md` define por que a Central Quant existe.

Este Blueprint define como o sistema deve ser organizado para cumprir essa visão.

A hierarquia é:

```text
00-Vision.md
    ↓
Architecture Blueprint
    ↓
01-Architecture.md
    ↓
Documentos especializados
    ↓
ADRs
    ↓
Código
    ↓
Estado operacional
```

Nenhum componente, documento ou implementação pode contradizer o `00-Vision.md`.

---

## 3. Princípios arquiteturais fundamentais

### 3.1 Separação entre pensar e executar

A Central Quant separa claramente:

- geração de sinais;
- decisão;
- risco;
- execução;
- custódia;
- gestão;
- outcome;
- aprendizado.

Nenhum componente deve acumular autoridade além da necessária para sua função.

### 3.2 Autoridade explícita

Toda ação relevante deve ter uma camada responsável.

Nenhum componente pode assumir autoridade por conveniência, ausência de resposta ou compartilhamento de estado.

### 3.3 Ownership nunca é implícito

Símbolo, lado e preço médio não constituem ownership.

Ownership deve ser sustentado, em ordem de força, por:

1. `trade_id` ou `trade_uuid`;
2. `lifecycle_id`;
3. `signal_id`;
4. `decision_id`;
5. `client_order_id`;
6. `exchange_order_id`;
7. fills;
8. quantidade reconciliada;
9. contexto de execução.

Matching por símbolo e lado pode ser usado para awareness, nunca como prova definitiva.

### 3.4 Lifecycle explícito

Cada trade possui lifecycle próprio, independente de:

- outros robôs;
- outras estratégias;
- posições manuais;
- posição agregada da corretora;
- preço médio global da exchange.

### 3.5 A BingX não é fonte de verdade estatística

A BingX:

- executa ordens;
- mantém custódia;
- reporta posições;
- fornece fills e estado de ordens.

A Central:

- preserva identidade;
- mantém lifecycle;
- calcula estatística por robô;
- decide risco;
- gerencia intenção;
- atribui outcome.

### 3.6 Segurança por confirmação

Estado local só avança mediante confirmação suficiente.

Solicitar não significa executar.

Retornar sem erro não significa confirmar.

Timeout não significa falha.

Ausência de resposta não significa ausência de execução.

### 3.7 Evolução incremental

Grandes refatorações só devem ocorrer após:

- documentação da arquitetura;
- cobertura adequada de testes;
- capacidade de rollback;
- análise de impacto;
- preservação de compatibilidade operacional.

### 3.8 Testes isolados de produção

Nenhum teste pode acessar:

- BingX;
- Telegram;
- Render;
- Redis externo;
- rede pública;
- credenciais reais;
- contas de produção.

---

## 4. Modelo macro da Central Quant

```text
                        ┌─────────────────────────┐
                        │ SUPERVISÃO ESTRATÉGICA  │
                        │ CEO / OPERADOR HUMANO   │
                        └────────────┬────────────┘
                                     │
                                     ▼
                        ┌─────────────────────────┐
                        │ EXECUTIVE LAYER         │
                        │ políticas, confiança,   │
                        │ prioridades, alertas    │
                        └────────────┬────────────┘
                                     │
             ┌───────────────────────┴───────────────────────┐
             ▼                                               ▼
┌─────────────────────────┐                    ┌─────────────────────────┐
│ ANALYTICS / LEARNING    │                    │ PORTFOLIO / CAPITAL     │
│ outcomes, estatística,  │                    │ exposição, alocação,    │
│ pesos, performance      │                    │ concentração, orçamento │
└────────────┬────────────┘                    └────────────┬────────────┘
             │                                               │
             └───────────────────────┬───────────────────────┘
                                     ▼
                        ┌─────────────────────────┐
                        │ BOT / STRATEGY LAYER    │
                        │ sinais e contexto       │
                        └────────────┬────────────┘
                                     ▼
                        ┌─────────────────────────┐
                        │ DECISION LAYER          │
                        │ ALLOW / DENY / REDUCE   │
                        └────────────┬────────────┘
                                     ▼
                        ┌─────────────────────────┐
                        │ RISK LAYER              │
                        │ sizing, exposição,      │
                        │ limites e políticas     │
                        └────────────┬────────────┘
                                     ▼
                        ┌─────────────────────────┐
                        │ EXECUTION LAYER         │
                        │ plano, idempotência,    │
                        │ gates e reconciliação   │
                        └────────────┬────────────┘
                                     ▼
                        ┌─────────────────────────┐
                        │ BROKER ADAPTER          │
                        │ execução e proteção     │
                        └────────────┬────────────┘
                                     ▼
                        ┌─────────────────────────┐
                        │ BINGX / EXCHANGE        │
                        │ execução e custódia     │
                        └─────────────────────────┘
```

O fluxo não é estritamente linear. Analytics, Learning, Portfolio e Executive Layer influenciam políticas, pesos e limites, mas não devem executar ordens diretamente.

---

## 5. Camadas de autoridade

## 5.1 Mercado e dados

### Responsabilidade

Fornecer dados brutos e contexto observável:

- candles;
- preço;
- volume;
- ordem e fills;
- posição;
- saldo;
- status operacional.

### Pode

- fornecer evidência;
- expor estado;
- servir como entrada para análise.

### Não pode

- decidir estratégia;
- atribuir ownership;
- autorizar execução;
- calcular estatística por robô;
- alterar lifecycle.

---

## 5.2 Bots e estratégias

### Responsabilidade

Transformar dados de mercado em hipóteses de trade.

Cada bot pode produzir:

- sinal;
- direção;
- setup;
- score;
- entry teórica;
- stop técnico;
- alvo;
- contexto;
- justificativa;
- validade temporal.

### Pode

- observar mercado;
- detectar setups;
- calcular indicadores;
- registrar sinais;
- sugerir parâmetros de trade.

### Não pode

- alterar saldo ou capital global;
- decidir exposição final;
- acessar credenciais;
- falar diretamente com a BingX na arquitetura-alvo;
- gerenciar posição que não pertença ao próprio lifecycle;
- atribuir posição manual a si mesmo;
- usar posição agregada como estatística própria.

### Regra

Bots geram intenção. Não possuem autoridade final para execução real.

---

## 5.3 Decision Layer

### Responsabilidade

Converter sinal em decisão.

Resultados canônicos:

- `ALLOW`;
- `DENY`;
- `REDUCE_SIZE`;
- `WAIT`;
- `VERIFY`;
- `OBSERVE`.

### Considera

- qualidade do sinal;
- score;
- contexto;
- política executiva;
- amostra;
- conflitos conhecidos;
- elegibilidade do setup.

### Pode

- aprovar;
- negar;
- condicionar;
- reduzir;
- exigir verificação.

### Não pode

- enviar ordem;
- acessar corretora;
- alterar stop físico;
- concluir fill;
- mascarar divergência.

---

## 5.4 Risk Layer

### Responsabilidade

Determinar quanto risco pode ser assumido.

### Considera

- capital livre;
- risco por trade;
- risco por bot;
- exposição global;
- concentração direcional;
- correlação;
- alavancagem;
- limites operacionais;
- políticas ativas;
- estado do pipeline.

### Pode

- calcular tamanho;
- reduzir size;
- bloquear entrada;
- limitar novas exposições;
- impor multiplicador de risco;
- classificar risco.

### Não pode

- gerar sinal;
- alterar setup;
- criar ordem;
- atribuir ownership;
- alterar outcome.

---

## 5.5 Execution Layer

### Responsabilidade

Transformar uma decisão autorizada em um plano executável, idempotente e reconciliável.

### Subcomponentes conceituais

- Execution Engine;
- Execution Orchestrator;
- Idempotency Ledger;
- Confirmation Guard;
- Reconciliation Guard;
- Execution Audit.

### Pode

- validar payload;
- gerar plano;
- gerar identidade estável;
- reservar intenção;
- impedir duplicidade;
- solicitar execução ao Broker;
- persistir estados de submissão;
- reconciliar resultado.

### Não pode

- redefinir estratégia;
- calcular indicadores;
- alterar score;
- ignorar risco;
- presumir falha após timeout;
- repetir ordem sem reconciliação.

### Regra

Toda execução real deve passar por identidade persistente e estado explícito.

---

## 5.6 Broker Adapter

### Responsabilidade

Traduzir intenção autorizada em chamadas à exchange.

### Pode

- consultar mercados;
- consultar saldo;
- consultar ordens;
- consultar fills;
- consultar posições;
- criar ordem;
- cancelar ordem;
- substituir stop;
- fechar quantidade;
- confirmar proteção;
- normalizar constraints;
- retornar estado estruturado.

### Não pode

- decidir se o setup é bom;
- alterar risco por iniciativa própria;
- atribuir ownership estatístico;
- calcular performance do bot;
- decidir política;
- reutilizar posição agregada como lifecycle;
- transformar timeout em retry automático cego.

### Regra

O Broker executa. Não pensa.

---

## 5.7 Exchange

### Responsabilidade

Execução, custódia e reporte de estado operacional.

### É fonte válida para

- fills;
- IDs de ordens;
- status de ordens;
- quantidade executada;
- saldo;
- posição agregada;
- ordens abertas.

### Não é fonte suficiente para

- ownership;
- lifecycle;
- PnL por robô;
- entrada estatística individual;
- atribuição de posição manual;
- decisão estratégica.

---

## 5.8 Registry e Lifecycle

### Responsabilidade

Preservar a identidade e o estado de cada trade.

### Deve registrar

- bot;
- setup;
- símbolo;
- lado;
- signal ID;
- decision ID;
- trade ID;
- lifecycle ID;
- client order ID;
- exchange order ID;
- fills;
- entry teórica;
- entry confirmada;
- quantidade planejada;
- quantidade executada;
- quantidade protegida;
- stop;
- TP50;
- break-even;
- trailing;
- MFE;
- MAE;
- outcome;
- estado de reconciliação.

### Não pode

- inferir ownership apenas por símbolo/lado;
- sobrescrever incerteza;
- marcar ação como concluída sem evidência;
- misturar lifecycles.

---

## 5.9 Management Layer

### Responsabilidade

Gerenciar posições por lifecycle.

### Inclui

- TP50;
- break-even;
- trailing;
- stop update;
- fechamento parcial;
- fechamento total;
- disaster stop;
- runner;
- recovery.

### Pode

- solicitar redução;
- solicitar ajuste de stop;
- atualizar estado após confirmação;
- reagir a gatilhos do próprio lifecycle.

### Não pode

- gerenciar posição manual;
- atingir quantidade de outro bot;
- usar posição agregada sem reconciliação;
- avançar estado local antes da confirmação.

---

## 5.10 Analytics e Performance

### Responsabilidade

Medir comportamento e resultado.

### Pode

- calcular PnL;
- calcular R;
- calcular expectancy;
- calcular win rate;
- calcular MAE/MFE;
- comparar setups;
- gerar ranking;
- medir drawdown;
- medir qualidade de execução.

### Não pode

- abrir ordem;
- alterar risco diretamente;
- atribuir outcome sem lifecycle confiável;
- misturar estatísticas de bots.

---

## 5.11 Learning Layer

### Responsabilidade

Aprender com outcomes confiáveis.

### Pode

- sugerir pesos;
- ajustar confiança;
- recomendar pausa;
- recomendar redução;
- avaliar políticas;
- detectar degradação.

### Não pode

- executar ordem;
- ultrapassar policy/risk gates;
- aprender com trade sem ownership;
- transformar correlação em causalidade;
- alterar comportamento LIVE sem trilha auditável.

---

## 5.12 Executive Layer

### Responsabilidade

Governança estratégica da Central.

### Inclui

- Executive Policies;
- CEO Confidence;
- Strategic Advisor;
- Alert Manager;
- Policy Learning;
- Auto Release;
- prioridades de portfólio.

### Pode

- definir política;
- restringir operação;
- reduzir expansão;
- priorizar capital;
- exigir observação;
- recomendar pausa;
- liberar política quando condição for satisfeita.

### Não pode

- enviar ordem diretamente;
- alterar posição manual;
- mascarar falha operacional;
- substituir decisão de lifecycle confirmada.

---

## 5.13 Supervisão humana

### Responsabilidade

Definir:

- objetivos;
- tolerância de risco;
- capital;
- direção estratégica;
- limites operacionais;
- aprovação de deploy;
- resolução excepcional.

### Papel

Supervisor estratégico, não operador rotineiro.

A Central deve funcionar de forma autônoma dentro dos limites aprovados.

---

## 6. Contratos arquiteturais

## 6.1 Contrato do Bot

**Entrada:** dados de mercado e contexto.  
**Saída:** sinal estruturado.  
**Proibido:** falar diretamente com exchange na arquitetura-alvo.

## 6.2 Contrato do Decision Engine

**Entrada:** sinal, contexto e políticas.  
**Saída:** decisão estruturada.  
**Proibido:** criar ordem.

## 6.3 Contrato do Risk Engine

**Entrada:** decisão elegível, capital e exposição.  
**Saída:** autorização de risco e size.  
**Proibido:** executar.

## 6.4 Contrato do Execution Engine

**Entrada:** decisão aprovada e size.  
**Saída:** plano, identidade e estado de execução.  
**Proibido:** retry cego.

## 6.5 Contrato do Broker

**Entrada:** comando autorizado, completo e idempotente.  
**Saída:** resultado estruturado com evidência.  
**Proibido:** decidir estratégia.

## 6.6 Contrato do Registry

**Entrada:** eventos confirmados e estados explícitos.  
**Saída:** lifecycle persistente.  
**Proibido:** inferir conclusão sem evidência.

## 6.7 Contrato do Learning

**Entrada:** outcomes confiáveis.  
**Saída:** recomendações, pesos e avaliações.  
**Proibido:** operar capital diretamente.

---

## 7. Modelo oficial de lifecycle

Estados conceituais mínimos:

```text
SIGNAL_DETECTED
    ↓
DECISION_PENDING
    ↓
DECISION_ALLOWED / DECISION_DENIED
    ↓
RISK_APPROVED
    ↓
ENTRY_INTENT_RECORDED
    ↓
ENTRY_SUBMITTING
    ↓
ENTRY_SUBMISSION_UNKNOWN
    ou
ENTRY_REJECTED_CONFIRMED
    ou
ENTRY_CONFIRMED
    ↓
ENTRY_CONFIRMED_STOP_MISSING
    ou
ENTRY_PROTECTED
    ↓
POSITION_MANAGED
    ↓
TP50_PENDING / TP50_CONFIRMED
    ↓
RUNNER_PROTECTED
    ↓
BREAK_EVEN_ACTIVE
    ↓
TRAILING_ACTIVE
    ↓
CLOSE_PENDING
    ↓
CLOSE_CONFIRMED
    ↓
OUTCOME_RECORDED
    ↓
LEARNING_ELIGIBLE
```

### Regras

- estados incertos bloqueiam retry cego;
- `ENTRY_CONFIRMED_STOP_MISSING` é crítico;
- proteção é subestado separado da entrada;
- gestão só ocorre após ownership suficiente;
- outcome só existe após encerramento confirmado;
- aprendizado só ocorre após outcome confiável.

---

## 8. Modelo de ownership

A Central deve distinguir:

### Posição de trade

Quantidade pertencente a um lifecycle específico.

### Posição agregada da exchange

Soma operacional exibida pela corretora para símbolo/lado.

### Posição manual ou externa

Quantidade cuja origem não pertence à Central.

### Exposição global

Soma de todas as quantidades, independentemente de ownership.

### Regra

A exposição global pode incluir posições manuais.

As estatísticas de um bot nunca podem incluí-las.

---

## 9. Múltiplos robôs no mesmo ativo

A arquitetura permite:

- mesmo símbolo;
- mesmo lado;
- estratégias diferentes;
- entradas diferentes;
- stops diferentes;
- gestões diferentes;
- outcomes diferentes.

A BingX pode agregar a posição operacionalmente.

A Central deve preservar separação lógica.

### Requisitos

- identidade por lifecycle;
- fills registrados;
- quantidade por trade;
- gestão por trade;
- disaster stop compatível com exposição;
- reconciliação após qualquer ação externa.

### Limitação transitória

Quando a exchange impedir isolamento físico seguro, a Central pode impor bloqueio operacional conservador. Esse bloqueio não altera ownership.

---

## 10. Posições manuais

Posições manuais:

- devem ser detectadas;
- devem aparecer como exposição externa;
- podem influenciar risco global;
- não pertencem a nenhum bot;
- não devem ser geridas automaticamente;
- não devem bloquear globalmente o Falcon por simples existência;
- não devem ser incorporadas à estatística;
- não devem ser reconciliadas à força com um lifecycle.

---

## 11. Arquitetura de proteção

### Proteção virtual

Usada para lógica de gestão:

- TP50;
- break-even;
- trailing;
- regras de saída;
- gestão por lifecycle.

### Proteção física

Usada como última defesa:

- disaster stop na exchange.

### Regras

- toda posição real deve ter disaster stop físico confirmado;
- o disaster stop não substitui a gestão virtual;
- gestão virtual não substitui o disaster stop;
- falha de proteção gera estado crítico;
- após TP50, proteção deve ser redimensionada para o runner;
- cancel/replace deve possuir rollback ou failsafe.

---

## 12. Arquitetura de idempotência

Toda intenção deve possuir identidade estável.

### Chave conceitual

```text
bot + setup + signal_id + symbol + side + lifecycle_id
```

### Antes de enviar

- registrar intenção;
- persistir client order ID;
- verificar ledger;
- verificar registry;
- reconciliar estado anterior.

### Após timeout

- consultar por client order ID;
- consultar exchange order ID;
- consultar fills;
- consultar posição reconciliada;
- marcar estado `UNKNOWN` quando necessário;
- nunca reenviar automaticamente sem prova de não execução.

---

## 13. Arquitetura de dados

### Estado operacional

Deve ser estruturado, persistente e recuperável.

### Eventos

Devem registrar transições relevantes.

### Logs

Devem apoiar auditoria, mas não substituir estado.

### Registry

É a fonte primária de lifecycle.

### History

Preserva eventos e outcomes.

### Analytics

Consome dados confiáveis.

### Learning

Consome analytics e outcomes elegíveis.

---

## 14. Comunicação entre camadas

Preferência arquitetural:

```text
payloads estruturados
+ contratos explícitos
+ estados canônicos
+ IDs persistentes
```

Evitar:

- dependência em variáveis globais;
- side effects no import;
- monkey patches em cascata;
- strings ambíguas;
- estado implícito;
- chamadas diretas entre camadas não autorizadas;
- leitura de estado externo sem adaptação.

---

## 15. Dependências permitidas

### Bots podem depender de

- dados de mercado;
- indicadores;
- contratos de sinal;
- contexto;
- configuração não sensível.

### Decision pode depender de

- sinais;
- contexto;
- políticas;
- analytics confiáveis.

### Risk pode depender de

- decisão;
- exposição;
- capital;
- políticas;
- correlação;
- regime.

### Execution pode depender de

- decisão aprovada;
- risk approval;
- registry;
- idempotency ledger;
- broker adapter.

### Broker pode depender de

- exchange manager;
- constraints;
- autenticação;
- logging;
- configuração operacional.

### Learning pode depender de

- outcomes;
- analytics;
- histórico;
- políticas.

---

## 16. Dependências proibidas

- Broker → Strategy
- Broker → Learning
- Exchange → Ownership
- Bot → Credenciais
- Bot → Exchange direta na arquitetura-alvo
- Learning → Broker
- Analytics → Execução
- Registry → Decisão estratégica
- Posição agregada → estatística de robô
- Import de módulo → início automático de runtime
- Teste → rede externa
- Timeout → retry automático
- Log textual → única fonte de estado

---

## 17. Arquitetura atual versus arquitetura-alvo

A implementação atual contém compatibilidades históricas, incluindo:

- caminhos diretos de bot para broker;
- wrappers sucessivos;
- monkey patches;
- funções redefinidas;
- runtime iniciado em import;
- matching parcial por símbolo/lado;
- estado distribuído entre Redis, arquivos e memória.

Esses pontos não redefinem a arquitetura oficial.

Eles devem ser classificados em:

- compatibilidade transitória;
- dívida técnica aceita;
- migração planejada;
- risco operacional em tratamento.

### Regra

Não refatorar por estética.

Refatorar apenas com:

- teste;
- plano;
- migração;
- rollback;
- impacto conhecido.

---

## 18. Arquitetura de runtime

O runtime ideal deve:

- iniciar explicitamente;
- possuir entrypoint claro;
- impedir múltiplas inicializações;
- separar import de execução;
- possuir liderança definida;
- registrar threads e loops;
- permitir testes sem side effects;
- isolar bots quando necessário;
- suportar shutdown controlado.

Importar um módulo não deve iniciar:

- threads;
- servidor;
- Telegram;
- exchange;
- Redis externo;
- execução LIVE.

---

## 19. Arquitetura de testes

A suíte deve incluir:

- Network Kill Switch;
- Fake Exchange;
- Fake Redis;
- Fake Registry;
- Fake Clock;
- Fake Notifier;
- testes de Broker;
- testes de Falcon;
- testes de disaster stop;
- testes de idempotência;
- testes de ownership;
- testes de reconciliação;
- testes de TP50 e runner;
- testes de import safety.

---

## 20. Arquitetura de observabilidade

Estados críticos devem ser visíveis por:

- health;
- audit;
- alert;
- registry;
- history;
- watchdog;
- report.

Exemplos críticos:

- posição sem stop;
- entry unknown;
- divergência Central × BingX;
- ownership incerto;
- runner sem proteção;
- retry bloqueado;
- posição manual agregada;
- quantidade incompatível;
- stop não confirmado.

---

## 21. Arquitetura de governança

Toda mudança relevante deve passar por:

```text
Problema
    ↓
Especificação
    ↓
Análise de impacto
    ↓
Implementação
    ↓
Auto-auditoria Codex
    ↓
Auditoria CTO
    ↓
Testes
    ↓
Commit
    ↓
Deploy aprovado
    ↓
Observação pós-deploy
```

### Mudanças que exigem ADR

- alteração de ownership;
- mudança de lifecycle;
- nova autoridade de camada;
- nova fonte de verdade;
- mudança de proteção;
- mudança de execução;
- mudança de idempotência;
- integração de nova exchange;
- mudança de persistência estrutural.

---

## 22. Critérios para novos componentes

Antes de criar um módulo, responder:

1. Qual camada é responsável?
2. Qual autoridade ele possui?
3. Que autoridade ele não possui?
4. Quais entradas recebe?
5. Quais saídas produz?
6. Qual estado persiste?
7. Como é testado sem rede?
8. Como falha de forma segura?
9. Como se reconcilia?
10. Qual documento precisa ser atualizado?

Se essas respostas não estiverem claras, o módulo não está pronto para implementação.

---

## 23. Critérios para aprovação arquitetural

Uma mudança só é aprovada quando:

- respeita o `00-Vision.md`;
- possui owner de camada;
- não mistura lifecycle;
- não atribui ownership por atalho;
- não aumenta risco sem controle;
- não cria novo caminho paralelo de execução;
- preserva disaster stop;
- preserva idempotência;
- produz estado auditável;
- possui teste seguro;
- atualiza documentação;
- não depende de comportamento implícito.

---

## 24. Prioridade de migração arquitetural

Ordem recomendada:

1. testes sem rede;
2. Fake Exchange;
3. import safety;
4. estado explícito de entrada e proteção;
5. idempotência persistente;
6. fill confirmado como base operacional;
7. ownership por lifecycle/order/fill;
8. reconciliação antes de retry;
9. consolidação de caminhos de execução;
10. redução gradual de wrappers e redefinições;
11. separação progressiva do `main.py`;
12. evolução do learning e novas estratégias.

---

## 25. Decisões centrais consolidadas

### CQ-A01

A Central é a fonte de verdade operacional e estatística.

### CQ-A02

A BingX é executora e custodiante.

### CQ-A03

Cada trade possui lifecycle independente.

### CQ-A04

Posições manuais permanecem externas.

### CQ-A05

Bots não devem executar diretamente na arquitetura-alvo.

### CQ-A06

Toda execução real deve ser idempotente.

### CQ-A07

Toda posição real deve possuir disaster stop físico confirmado.

### CQ-A08

Estado local só avança após confirmação.

### CQ-A09

Learning nunca executa.

### CQ-A10

Arquitetura não é redefinida por dívida técnica.

---

## 26. Artefatos derivados deste Blueprint

Este documento deve originar:

- `docs/01-Architecture.md`;
- `docs/03-System-Components.md`;
- `docs/04-Execution-Flow.md`;
- `docs/05-Broker-Integration.md`;
- `docs/07-Risk-Management.md`;
- `docs/08-Lifecycle.md`;
- `docs/09-Learning-System.md`;
- diagramas oficiais;
- ADRs;
- checklist arquitetural;
- backlog de migração.

---

## 27. Status

**Architecture Blueprint v1.0: aprovado como base da arquitetura oficial da Central Quant.**

Este documento não autoriza alteração de código.

Ele define a direção arquitetural que os próximos documentos e implementações devem seguir.
