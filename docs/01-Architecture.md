# Arquitetura da Central Quant

Status: APPROVED
Versão: 0.1
Última revisão:
Responsável: CTO
Implementação: Codex
Aprovado: Sim

---

## 1. Propósito

Este documento define a arquitetura-alvo oficial da Central Quant: suas camadas, autoridades, contratos, dependências, limites operacionais e critérios de evolução.

A Central Quant é um sistema de trading autônomo para uso pessoal do proprietário. Sua arquitetura deve ser suficiente para operar com confiabilidade, segurança, rastreabilidade e evolução incremental, sem introduzir complexidade comercial ou abstrações para múltiplos clientes.

Este documento é normativo. Quando a implementação atual divergir dele, a divergência representa compatibilidade transitória, dívida técnica ou trabalho de migração; não redefine a arquitetura desejada.

---

## 2. Relação com o `00-Vision.md`

O `00-Vision.md` estabelece por que a Central Quant existe e quais princípios são invioláveis. Este documento estabelece como o sistema deve ser organizado para preservar esses princípios.

A hierarquia documental é:

```text
00-Vision.md
    ↓
Architecture-Blueprint.md
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

Nenhuma decisão arquitetural pode contrariar a visão. Em particular, a arquitetura deve preservar capital, idempotência, ownership, lifecycle por trade, consistência Central × exchange, estatística independente e observabilidade.

---

# Filosofia da Arquitetura

A arquitetura da Central Quant existe, antes de tudo, para proteger o capital e preservar a previsibilidade operacional. A separação de responsabilidades reduz o risco operacional ao tornar explícito onde cada decisão pode ser tomada e quais limites não podem ser ultrapassados.

A organização do código é consequência desses compromissos, não o objetivo principal da arquitetura. Como a Central Quant é um sistema de uso pessoal, a simplicidade adequada ao problema deve prevalecer sobre abstrações desnecessárias, desde que sejam preservadas segurança, clareza de autoridade, rastreabilidade e capacidade de evolução.

---

## 3. Arquitetura-alvo

A arquitetura-alvo separa explicitamente as autoridades de observar, gerar intenção, decidir, limitar risco, executar, custodiar, gerenciar, medir e aprender.

Seus fundamentos são:

- bots geram hipóteses de trade, não ordens finais;
- Decision Layer decide elegibilidade, não executa;
- Risk Layer define risco e tamanho, não cria sinais ou ordens;
- Execution Layer possui a autoridade exclusiva para coordenar uma execução real;
- Broker Adapter traduz comandos autorizados, sem autoridade estratégica;
- exchange executa e mantém custódia, sem definir ownership ou estatística;
- Registry é a fonte primária do lifecycle de cada trade;
- Management atua por lifecycle e somente após confirmação;
- Analytics e Learning consomem dados confiáveis e nunca executam ordens;
- Executive Layer governa políticas e prioridades, mas não opera diretamente a exchange;
- supervisão humana define objetivos, capital, tolerâncias e aprovações excepcionais.

A unidade arquitetural fundamental é o trade identificado, não a posição agregada da corretora.

---

## 4. Visão macro do sistema

```text
                         ┌──────────────────────────┐
                         │ SUPERVISÃO HUMANA        │
                         │ objetivos e limites      │
                         └────────────┬─────────────┘
                                      ▼
                         ┌──────────────────────────┐
                         │ EXECUTIVE LAYER          │
                         │ políticas e prioridades  │
                         └────────────┬─────────────┘
                                      │
              ┌───────────────────────┴───────────────────────┐
              ▼                                               ▼
 ┌──────────────────────────┐                   ┌──────────────────────────┐
 │ ANALYTICS / LEARNING     │                   │ PORTFOLIO / CAPITAL      │
 │ outcomes e evidências    │                   │ exposição e alocação     │
 └────────────┬─────────────┘                   └────────────┬─────────────┘
              └───────────────────────┬───────────────────────┘
                                      ▼
                         ┌──────────────────────────┐
                         │ BOT / STRATEGY LAYER     │
                         │ sinais e contexto        │
                         └────────────┬─────────────┘
                                      ▼
                         ┌──────────────────────────┐
                         │ DECISION LAYER           │
                         │ elegibilidade            │
                         └────────────┬─────────────┘
                                      ▼
                         ┌──────────────────────────┐
                         │ RISK LAYER               │
                         │ risco, size e limites    │
                         └────────────┬─────────────┘
                                      ▼
                         ┌──────────────────────────┐
                         │ EXECUTION LAYER          │
                         │ identidade e coordenação │
                         └────────────┬─────────────┘
                                      ▼
                         ┌──────────────────────────┐
                         │ BROKER ADAPTER           │
                         │ tradução e confirmação   │
                         └────────────┬─────────────┘
                                      ▼
                         ┌──────────────────────────┐
                         │ BINGX / EXCHANGE         │
                         │ execução e custódia      │
                         └──────────────────────────┘

       Registry, Lifecycle, Management e Observabilidade atravessam o fluxo
       preservando identidade, estado confirmado e trilha auditável por trade.
```

O fluxo principal é direcional, mas não puramente linear. Analytics, Learning, Portfolio e Executive Layer influenciam políticas, pesos e limites futuros; nenhum deles pode contornar Decision, Risk e Execution para enviar ordens.

---

## 5. Camadas de autoridade

Autoridade é a permissão arquitetural para tomar uma classe específica de decisão. Ela deve ser explícita, mínima e não transferível por conveniência.

| Camada | Autoridade principal | Saída autorizada |
|---|---|---|
| Mercado e Dados | Expor evidência observável | Dados e estado externo |
| Bot / Strategy | Formular hipótese de trade | Signal estruturado |
| Decision | Determinar elegibilidade | ALLOW, DENY, REDUCE_SIZE, WAIT, VERIFY ou OBSERVE |
| Risk | Determinar risco admissível | Aprovação de risco, size e limites |
| Execution | Coordenar execução autorizada | Plano, identidade e estado de execução |
| Broker Adapter | Traduzir comando autorizado | Resultado estruturado e evidência da exchange |
| Exchange | Executar e custodiar | Fills, ordens, saldos e posição agregada |
| Registry / Lifecycle | Preservar verdade por trade | Estado persistente e reconciliável |
| Management | Gerir o lifecycle próprio | Solicitações de redução, proteção e fechamento |
| Analytics / Performance | Medir comportamento | Métricas e avaliações |
| Learning | Aprender com outcomes elegíveis | Recomendações, pesos e avaliações |
| Executive | Governar políticas e prioridades | Restrições, diretrizes e alertas |
| Supervisão humana | Definir direção estratégica | Objetivos, tolerâncias e aprovações |

Nenhuma camada adquire autoridade de outra por compartilhar processo, memória, arquivo, posição ou resposta externa.

---

## 6. Responsabilidades e limites de cada camada

## Princípio da Responsabilidade Dominante

Cada camada possui uma responsabilidade dominante. Ela pode executar tarefas auxiliares necessárias ao cumprimento dessa responsabilidade, mas nunca deve assumir a responsabilidade principal de outra camada.

Esse princípio reduz acoplamento, facilita testes e evita o crescimento descontrolado das responsabilidades.

### 6.1 Mercado e Dados

**Faz:** fornece candles, preços, volume, saldos, ordens, fills, posições e estado operacional.

**Pode:** expor evidência e contexto para análise e reconciliação.

**Nunca pode:** decidir estratégia, atribuir ownership, autorizar execução, calcular estatística por robô ou alterar lifecycle.

### 6.2 Bot / Strategy Layer

**Faz:** observa mercado e transforma condições de estratégia em signal estruturado, com direção, setup, score, referências teóricas, contexto e validade.

**Pode:** detectar setups, calcular indicadores, registrar sinais e sugerir parâmetros de trade.

**Nunca pode:** decidir exposição final, acessar credenciais, falar diretamente com a exchange na arquitetura-alvo, gerenciar posição sem ownership ou possuir autoridade final de execução real.

### 6.3 Decision Layer

**Faz:** converte signal, contexto e políticas em decisão canônica.

**Pode:** aprovar, negar, reduzir, condicionar, aguardar ou exigir verificação.

**Nunca pode:** enviar ordens, acessar a corretora, concluir fills, alterar proteção física ou ocultar divergências.

### 6.4 Risk Layer

**Faz:** determina quanto risco pode ser assumido considerando capital, exposição, concentração, correlação, alavancagem, políticas e estado do pipeline.

**Pode:** calcular size, reduzir risco, limitar exposição e bloquear entrada.

**Nunca pode:** gerar signal, alterar setup, criar ordem, atribuir ownership ou modificar outcome.

### 6.5 Execution Layer

**Faz:** transforma decisão e risco aprovados em plano executável, idempotente, auditável e reconciliável.

**Pode:** validar o comando, criar identidade estável, reservar intenção, impedir duplicidade, persistir estados de submissão, solicitar execução ao Broker e reconciliar resultado.

**Nunca pode:** redefinir estratégia, ignorar Risk, alterar score, presumir falha após timeout ou repetir ordem sem reconciliação.

Seus subcomponentes conceituais são Execution Engine, Execution Orchestrator, Idempotency Ledger, Confirmation Guard, Reconciliation Guard e Execution Audit.

### 6.6 Broker Adapter

**Faz:** traduz comandos completos e autorizados para a interface da exchange, aplica constraints operacionais e retorna evidências estruturadas.

**Pode:** consultar mercados, saldo, ordens, fills e posições; criar ou cancelar ordens; substituir stop; fechar quantidade; confirmar proteção.

**Nunca pode:** decidir qualidade de setup, aumentar risco, atribuir ownership, calcular performance, definir política ou fazer retry cego.

O Broker executa; não pensa estrategicamente.

### 6.7 Exchange

**Faz:** executa, custodia e reporta seu estado operacional.

**Pode ser fonte de evidência para:** fills, IDs e status de ordens, quantidade executada, saldo, ordens abertas e posição agregada.

**Nunca pode ser autoridade suficiente para:** ownership, lifecycle, PnL por robô, entrada estatística individual, atribuição de posição manual ou decisão estratégica.

### 6.8 Registry e Lifecycle

**Faz:** preserva identidade e estado de cada trade durante todo o lifecycle.

**Pode:** receber eventos confirmados, persistir estados explícitos e expor a verdade operacional por trade.

**Nunca pode:** inferir ownership por símbolo/lado, sobrescrever incerteza, concluir ação sem evidência ou misturar lifecycles.

### 6.9 Management Layer

**Faz:** gerencia posição por lifecycle, incluindo TP50, runner, break-even, trailing, stop, fechamento e recovery.

**Pode:** solicitar redução ou proteção e atualizar estado depois da confirmação correspondente.

**Nunca pode:** gerir posição manual, atingir quantidade de outro trade, usar posição agregada sem reconciliação ou avançar estado local antes da confirmação.

### 6.10 Analytics e Performance

**Faz:** mede PnL, R, expectancy, win rate, MAE, MFE, drawdown, qualidade de execução e desempenho por bot/setup.

**Pode:** comparar, classificar e produzir evidência analítica.

**Nunca pode:** abrir ordens, alterar risco diretamente, atribuir outcome sem lifecycle confiável ou misturar estatísticas de bots.

### 6.11 Learning Layer

**Faz:** aprende apenas com outcomes confiáveis e dados com ownership suficiente.

**Pode:** sugerir pesos, ajustar confiança, avaliar políticas, detectar degradação e recomendar pausa ou redução.

**Nunca pode:** executar ordens, ultrapassar Decision/Risk, aprender com trade sem ownership ou alterar comportamento LIVE sem trilha auditável.

### 6.12 Executive Layer

**Faz:** governa políticas, confiança, alertas, prioridades e direção de portfólio.

**Pode:** restringir operação, reduzir expansão, priorizar capital, exigir observação e liberar política quando sua condição for satisfeita.

**Nunca pode:** enviar ordem diretamente, alterar posição manual, mascarar falha operacional ou substituir estado confirmado do lifecycle.

### 6.13 Supervisão humana

**Faz:** define objetivos, capital, tolerância de risco, limites operacionais, direção estratégica, aprovação de deploy e resolução excepcional.

**Pode:** aprovar ou interromper mudanças e alterar políticas por decisão explícita.

**Nunca deve depender:** de operação manual rotineira para compensar ausência de segurança arquitetural.

---

## 7. Contratos arquiteturais

| Contrato | Entrada | Saída | Proibição central |
|---|---|---|---|
| Bot | Dados de mercado e contexto | Signal estruturado | Executar diretamente |
| Decision | Signal, contexto e políticas | Decisão estruturada | Criar ordem |
| Risk | Decisão elegível, capital e exposição | Aprovação e size | Executar |
| Execution | Decisão e risco aprovados | Plano, identidade e estado | Retry cego |
| Broker | Comando autorizado e idempotente | Evidência estruturada | Decidir estratégia |
| Registry | Eventos confirmados e estados explícitos | Lifecycle persistente | Inferir conclusão |
| Management | Lifecycle com ownership e gatilho válido | Ação solicitada e estado confirmado | Gerir posição externa |
| Analytics | Dados reconciliados | Métricas | Executar ou alterar risco diretamente |
| Learning | Outcomes elegíveis | Recomendações e pesos | Operar capital |

Todo contrato deve possuir payload estruturado, IDs persistentes, estados canônicos, erros explícitos e comportamento fail-closed.

---

## 8. Fluxo macro entre as camadas

```text
Dados de Mercado
      │
      ▼
┌─────────────┐   signal    ┌─────────────┐  decisão   ┌─────────────┐
│ BOT         │────────────▶│ DECISION    │───────────▶│ RISK        │
│ hipótese    │             │ elegibilidade│           │ size/limite │
└─────────────┘             └─────────────┘            └──────┬──────┘
                                                               │ aprovação
                                                               ▼
                                                     ┌──────────────────┐
                                                     │ EXECUTION        │
                                                     │ identidade/gates │
                                                     └────────┬─────────┘
                                                              │ comando autorizado
                                                              ▼
                                                     ┌──────────────────┐
                                                     │ BROKER ADAPTER   │
                                                     │ tradução/evidência│
                                                     └────────┬─────────┘
                                                              │ ordem/consulta
                                                              ▼
                                                     ┌──────────────────┐
                                                     │ BINGX / EXCHANGE │
                                                     │ execução/custódia│
                                                     └────────┬─────────┘
                                                              │ fills/status
                                                              ▼
                                               Registry + Lifecycle + Management
```

O retorno da exchange percorre Broker e Execution antes de atualizar Registry e Lifecycle. Nenhuma confirmação deve ser inferida de uma simples solicitação.

---

## 9. Registry e lifecycle

O Registry é a fonte primária do lifecycle. Logs, history e estado da exchange fornecem evidência e auditoria, mas não substituem o estado estruturado do trade.

Cada trade deve preservar, quando aplicável:

- bot e setup;
- símbolo e lado;
- signal ID, decision ID, trade ID e lifecycle ID;
- client order ID e exchange order ID;
- fills e entrada confirmada;
- quantidades planejada, executada, remanescente e protegida;
- stop, TP50, break-even e trailing;
- MFE, MAE e outcome;
- estados de submissão, proteção, gestão e reconciliação.

Incerteza é um estado válido e não deve ser apagada. O lifecycle só avança quando existe evidência suficiente para a transição.

---

## 10. Ownership

Ownership é a relação comprovada entre um trade, seu lifecycle, o bot responsável e as evidências de execução correspondentes.

A força de evidência segue esta ordem:

1. trade ID ou trade UUID;
2. lifecycle ID;
3. signal ID;
4. decision ID;
5. client order ID;
6. exchange order ID;
7. fills;
8. quantidade reconciliada;
9. contexto de execução.

Símbolo, lado e preço médio agregado podem apoiar awareness ou reconciliação inicial, mas nunca comprovam ownership.

---

## 11. Múltiplos robôs no mesmo ativo

A arquitetura permite que robôs diferentes operem o mesmo símbolo e lado, mantendo entradas, stops, quantidades, gestões, outcomes e estatísticas independentes.

A exchange pode agregar fisicamente a exposição. A Central deve preservar a separação lógica por lifecycle, fills e quantidade de cada trade.

Quando a exchange impedir isolamento físico seguro, a Central pode impor bloqueio operacional conservador. Esse bloqueio deve ser explícito e auditável e nunca transfere ownership entre trades.

---

## 12. Posições manuais e externas

Posições abertas fora da Central:

- permanecem externas;
- devem ser detectadas e exibidas como exposição externa;
- podem influenciar Risk e exposição global;
- não pertencem a bot algum;
- não podem ser geridas automaticamente;
- não entram nas estatísticas dos bots;
- não devem ser reconciliadas à força com um lifecycle;
- não bloqueiam globalmente o Falcon por sua simples existência.

Uma restrição motivada por agregação da exchange deve preservar essa classificação.

---

## 13. Arquitetura de proteção

A proteção possui duas dimensões complementares:

### Proteção virtual

Controla a lógica de gestão por lifecycle: TP50, break-even, trailing e regras de saída.

### Proteção física

Mantém um disaster stop confirmado na exchange como última defesa da posição real.

Regras obrigatórias:

- toda posição real deve possuir disaster stop físico confirmado;
- proteção virtual não substitui disaster stop;
- disaster stop não substitui gestão por lifecycle;
- falha de criação ou confirmação gera estado crítico, alerta e recovery;
- depois de TP50, a proteção deve ser redimensionada e confirmada para o runner;
- cancelamento e recriação de stop exigem rollback ou failsafe;
- estado local de proteção só avança após confirmação.

---

## 14. Idempotência e reconciliação

Toda intenção de execução deve possuir identidade estável antes do envio. A identidade conceitual combina bot, setup, signal ID, símbolo, lado e lifecycle ID.

Antes de enviar, a Execution Layer deve:

- registrar a intenção;
- persistir client order ID;
- consultar Idempotency Ledger e Registry;
- reconciliar tentativa anterior relacionada.

Após timeout ou resposta ambígua, deve consultar client order ID, exchange order ID, fills e posição reconciliada. Se a evidência continuar insuficiente, o estado permanece desconhecido e bloqueia retry cego.

Reconciliation compara a verdade interna com evidências externas sem entregar à exchange autoridade sobre lifecycle ou ownership.

---

## 15. Comunicação entre módulos

A comunicação preferida utiliza:

```text
payloads estruturados
+ contratos explícitos
+ estados canônicos
+ IDs persistentes
+ evidência de confirmação
```

Devem ser evitados:

- variáveis globais como contrato entre camadas;
- efeitos colaterais durante import;
- monkey patches em cascata;
- strings ambíguas como único estado;
- estado implícito;
- chamadas diretas que contornem autoridade;
- leitura de estado externo sem adaptação;
- logs textuais como única fonte operacional.

Comunicação assíncrona ou síncrona não altera a autoridade de cada camada.

---

## 16. Dependências permitidas

- Bots → dados de mercado, indicadores, contexto, contratos de signal e configuração não sensível.
- Decision → signals, contexto, políticas e analytics confiáveis.
- Risk → decisão elegível, exposição, capital, políticas, correlação e regime.
- Execution → decisão aprovada, risk approval, Registry, Idempotency Ledger e Broker Adapter.
- Broker → Exchange Manager, constraints, autenticação, logging e configuração operacional.
- Registry → eventos confirmados e identidades persistentes.
- Management → lifecycle com ownership e Broker por meio da autoridade de Execution.
- Analytics → Registry, History e outcomes reconciliados.
- Learning → outcomes, analytics, histórico e políticas.
- Executive → analytics, learning, portfolio, alertas e políticas.

---

## 17. Dependências proibidas

- Broker → Strategy.
- Broker → Learning.
- Exchange → Ownership.
- Bot → credenciais.
- Bot → exchange direta na arquitetura-alvo.
- Bot → autoridade final de Execution.
- Learning → Broker.
- Analytics → Execution.
- Registry → decisão estratégica.
- posição agregada → estatística individual de bot.
- import de módulo → início automático de runtime.
- teste → rede ou serviço externo.
- timeout → retry automático.
- log textual → única fonte de estado.

---

## 18. Runtime e inicialização

O runtime deve possuir entrypoint explícito, liderança definida e proteção contra múltiplas inicializações.

Importar um módulo não deve iniciar:

- threads ou loops;
- servidor;
- Telegram;
- exchange;
- Redis externo;
- execução LIVE.

O runtime deve registrar processos, threads e loops ativos, permitir shutdown controlado, isolar bots quando necessário e separar composição, inicialização e execução. A simplicidade de um sistema pessoal não autoriza bootstrap implícito ou duplicado.

---

## 19. Testabilidade e isolamento de produção

Testes devem ser seguros por padrão e incapazes de acessar produção.

A infraestrutura de teste deve incluir Network Kill Switch, Fake Exchange, Fake Redis, Fake Registry, Fake Clock e Fake Notifier, além de testes de Broker, Falcon, disaster stop, idempotência, ownership, reconciliação, TP50, runner e import safety.

Nenhum teste pode acessar BingX, Telegram, Render, Redis externo, rede pública, credenciais ou contas reais. Modo de teste não pode depender apenas de configuração operacional de produção.

---

## 20. Ciclo de outcome, analytics, learning e governança

```text
┌──────────────────┐
│ LIFECYCLE        │
│ close confirmado │
└────────┬─────────┘
         ▼
┌──────────────────┐     ┌──────────────────┐
│ OUTCOME          │────▶│ ANALYTICS        │
│ resultado válido │     │ métricas/evidência│
└──────────────────┘     └────────┬─────────┘
                                  ▼
                         ┌──────────────────┐
                         │ LEARNING         │
                         │ avaliação/pesos  │
                         └────────┬─────────┘
                                  ▼
                         ┌──────────────────┐
                         │ EXECUTIVE LAYER  │
                         │ política/limites │
                         └────────┬─────────┘
                                  │
                                  └──▶ influencia decisões futuras

Nenhuma seta deste ciclo alcança Broker ou Exchange diretamente.
```

Learning só consome outcomes elegíveis. Analytics mede; Learning recomenda; Executive governa. Nenhuma dessas camadas executa ordens.

---

## 21. Lifecycle conceitual de um trade

```text
SIGNAL_DETECTED
      │
      ▼
DECISION_PENDING ───────────────▶ DECISION_DENIED
      │ ALLOW
      ▼
RISK_APPROVED
      ▼
ENTRY_INTENT_RECORDED
      ▼
ENTRY_SUBMITTING
      ├────────▶ ENTRY_REJECTED_CONFIRMED
      ├────────▶ ENTRY_SUBMISSION_UNKNOWN ──▶ RECONCILIATION
      └────────▶ ENTRY_CONFIRMED
                          │
                          ├────▶ ENTRY_CONFIRMED_STOP_MISSING ──▶ RECOVERY
                          └────▶ ENTRY_PROTECTED
                                          ▼
                                  POSITION_MANAGED
                                          ▼
                             TP50_PENDING / TP50_CONFIRMED
                                          ▼
                                  RUNNER_PROTECTED
                                          ▼
                                  BREAK_EVEN_ACTIVE
                                          ▼
                                   TRAILING_ACTIVE
                                          ▼
                                    CLOSE_PENDING
                                          ▼
                                   CLOSE_CONFIRMED
                                          ▼
                                   OUTCOME_RECORDED
                                          ▼
                                   LEARNING_ELIGIBLE
```

Estados desconhecidos bloqueiam retry cego. Entrada e proteção são dimensões separadas. Management exige ownership suficiente. Outcome exige fechamento confirmado. Learning exige outcome confiável.

---

## 22. Observabilidade

Estados críticos devem ser visíveis por health, audit, alert, Registry, History, watchdog e report.

No mínimo, devem ser observáveis:

- posição sem stop;
- submissão de entrada desconhecida;
- divergência Central × exchange;
- ownership incerto;
- runner sem proteção;
- retry bloqueado;
- posição manual agregada;
- quantidade incompatível;
- stop não confirmado.

Observabilidade não substitui estado estruturado. Logs apoiam reconstrução e auditoria, enquanto Registry preserva lifecycle.

---

## 23. Governança arquitetural

Toda mudança relevante segue o fluxo:

```text
Problema → Especificação → Análise de impacto → Implementação
        → Autoauditoria Codex → Auditoria CTO → Testes
        → Commit → Deploy aprovado → Observação pós-deploy
```

Exigem ADR as mudanças de ownership, lifecycle, autoridade de camada, fonte de verdade, proteção, execução, idempotência, integração de exchange ou persistência estrutural.

ADRs subordinam-se à Visão e a esta arquitetura. Dívida técnica não cria precedente arquitetural.

---

## 24. Arquitetura atual versus arquitetura-alvo

A implementação atual contém caminhos diretos de bot para Broker, wrappers sucessivos, monkey patches, redefinições, runtime iniciado durante import, matching parcial por símbolo/lado e estado distribuído.

Essas condições são transitórias. Na arquitetura-alvo:

| Condição atual | Arquitetura-alvo |
|---|---|
| Bot pode alcançar Broker por caminho direto | Bot produz signal; Execution possui autoridade exclusiva |
| Controles adicionados por wrappers | Pipeline explícito e testável |
| Runtime pode iniciar em import | Bootstrap explícito e isolado |
| Matching parcial por símbolo/lado | Ownership por lifecycle, ordens e fills |
| Estado distribuído sem contrato único | Registry como fonte primária do lifecycle |
| Definições sucessivas | Responsabilidade única e contrato explícito |

Migração não deve ocorrer por estética. Cada mudança exige teste, plano, impacto conhecido, rollback e preservação de compatibilidade operacional.

---

## 25. Critérios para novos componentes

Um novo componente só pode ser proposto quando estiverem definidos:

1. camada responsável;
2. autoridade concedida;
3. autoridade explicitamente negada;
4. entradas e saídas;
5. estado persistido;
6. comportamento de falha segura;
7. estratégia de reconciliação;
8. teste sem rede;
9. impacto no lifecycle e ownership;
10. documentação ou ADR a atualizar.

Se essas respostas não forem claras, o componente não está pronto para implementação. Para o uso pessoal da Central, novos componentes devem resolver uma responsabilidade real sem criar generalização comercial desnecessária.

---

## 26. Critérios para aprovação de mudanças

Uma mudança arquitetural só pode ser aprovada quando:

- respeita `00-Vision.md` e o Blueprint;
- possui owner de camada;
- não mistura lifecycles;
- não atribui ownership por atalho;
- não aumenta risco sem controle;
- não cria caminho paralelo de execução;
- não concede autoridade estratégica ao Broker;
- não concede execução final aos bots;
- preserva disaster stop físico;
- preserva idempotência e reconciliação;
- mantém posições manuais externas;
- produz estado auditável;
- possui teste seguro e isolado;
- atualiza documentação e ADRs aplicáveis;
- não depende de comportamento implícito.

---

## 27. Prioridades de migração

A ordem oficial de migração é:

1. testes sem rede;
2. Fake Exchange;
3. segurança de importação;
4. estado explícito de entrada e proteção;
5. idempotência persistente;
6. fill confirmado como base operacional;
7. ownership por lifecycle, ordens e fills;
8. reconciliação antes de retry;
9. consolidação dos caminhos de execução;
10. redução gradual de wrappers e redefinições;
11. separação progressiva de responsabilidades concentradas;
12. evolução posterior de Learning e estratégias.

Essa ordem prioriza capital, duplicidade, ownership e consistência antes de expansão funcional.

---

## 28. Relação com os demais documentos de `docs`

- `00-Vision.md`: princípios superiores e identidade.
- `02-Trading-Philosophy.md`: disciplina de interpretação e resposta ao mercado.
- `03-System-Components.md`: catálogo oficial dos componentes.
- `04-Execution-Flow.md`: detalhamento do fluxo de execução.
- `05-Broker-Integration.md`: contrato com Broker e exchange.
- `06-Bot-Architecture.md`: contrato e independência dos bots.
- `07-Risk-Management.md`: autoridade e limites de Risk.
- `08-Lifecycle.md`: estados e transições por trade.
- `09-Learning-System.md`: ciclo de outcomes, analytics e aprendizado.
- `10-Roadmap.md`: sequência de evolução.
- `Glossary.md`: vocabulário canônico.
- `KNOWN_DEBT.md`: divergências confirmadas entre estado atual e alvo.
- `adr/`: decisões arquiteturais específicas subordinadas a este documento.
- `diagrams/`: representações visuais oficiais quando aprovadas.

Documentos especializados podem detalhar esta arquitetura, mas não alterar suas autoridades ou princípios sem revisão arquitetural e ADR aplicável.

---

## 29. Decisões arquiteturais consolidadas

1. A Central é a fonte de verdade operacional e estatística.
2. A BingX é executora e custodiante.
3. Cada trade possui lifecycle independente.
4. Posições manuais permanecem externas.
5. Bots não executam diretamente na arquitetura-alvo.
6. Toda execução real é idempotente e reconciliável.
7. Toda posição real possui disaster stop físico confirmado.
8. Estado local só avança após confirmação suficiente.
9. Analytics e Learning nunca executam ordens.
10. A arquitetura não é redefinida por dívida técnica.

---

## 30. Relação com outros documentos

- `00-Vision.md`
- `02-Trading-Philosophy.md`
- `03-System-Components.md`
- `04-Execution-Flow.md`
- `05-Broker-Integration.md`
- `06-Bot-Architecture.md`
- `07-Risk-Management.md`
- `08-Lifecycle.md`
- `09-Learning-System.md`
- `10-Roadmap.md`
- `Glossary.md`
- `KNOWN_DEBT.md`
- `adr/ADR-001-BingX-Is-Executor.md`
- `adr/ADR-002-Independent-Bots.md`
- `adr/ADR-003-Manual-Positions.md`
- `adr/ADR-004-Disaster-Stop.md`
- `adr/ADR-005-Virtual-Management.md`
- `adr/ADR-006-Statistics.md`
- `adr/ADR-007-Execution-Orchestrator.md`

---

# Arquitetura Viva

Este documento representa a arquitetura oficial da Central Quant. O código pode divergir temporariamente do que está definido aqui, mas essas divergências representam dívida técnica ou trabalho de migração.

Nenhuma implementação altera automaticamente a arquitetura. Alterações arquiteturais exigem especificação, auditoria e ADR quando aplicável.
