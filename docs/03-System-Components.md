# Componentes do Sistema

Status: APPROVED
Versão: 1.0
Última revisão: 11/07/2026
Responsável: CTO
Implementação: Codex
Aprovado: Sim

---

## 1. Propósito

Este documento é o catálogo oficial dos componentes da arquitetura-alvo da Central Quant e o mapa entre esses componentes e os módulos que hoje os implementam total ou parcialmente.

O catálogo define responsabilidade dominante, autoridade, contratos, estado e criticidade sem transformar a organização atual do código em arquitetura oficial. Divergências são registradas como compatibilidade transitória, dívida técnica ou migração necessária.

---

## Princípios do Catálogo de Componentes

Um componente existe por sua responsabilidade arquitetural, não pela simples existência de um arquivo.

Uma responsabilidade pode ser dividida entre componentes quando seus contratos e autoridades exigirem separação clara. Componentes também podem ser fundidos quando compartilham uma única responsabilidade dominante e a união não compromete segurança, testabilidade ou rastreabilidade.

A arquitetura prevalece sobre a organização física do código. Arquivos, classes, funções, wrappers ou processos são formas de implementação e podem mudar sem redefinir automaticamente o catálogo oficial.

---

## 2. Relação com o `00-Vision.md`

Este catálogo é subordinado ao `00-Vision.md`. Portanto, todos os componentes devem preservar capital, verdade por trade, ownership comprovável, lifecycle independente, segurança por confirmação, isolamento de posições externas, observabilidade e aprendizado baseado em dados confiáveis.

A Central permanece a fonte de verdade operacional e estatística. A BingX executa e mantém custódia, mas não define ownership, lifecycle ou estatística de robô.

---

## 3. Relação com o `01-Architecture.md`

O `01-Architecture.md` define as camadas, autoridades e dependências normativas. Este documento detalha os componentes que realizam essas responsabilidades e registra a distância entre a arquitetura-alvo e a implementação atual.

Em caso de divergência, prevalece o `01-Architecture.md`. Um arquivo existente não cria autoridade arquitetural, e a ausência de módulo isolado não elimina um componente oficial.

---

## 4. Como interpretar componente versus módulo

Um **componente arquitetural** é uma responsabilidade oficial com autoridade, entradas, saídas e limites definidos. Um **módulo atual** é um arquivo ou conjunto de trechos que implementa parte dessa responsabilidade no estado presente do projeto.

As relações não são necessariamente individuais: um componente pode estar distribuído por vários módulos, e um módulo pode acumular responsabilidades de vários componentes. Wrappers, monkey patches, redefinições e aliases são características da implementação atual, não componentes desejados.

Os estados deste catálogo significam:

- **ALINHADO:** responsabilidade e limites atuais correspondem substancialmente ao contrato-alvo;
- **PARCIALMENTE ALINHADO:** existe implementação útil, mas há distribuição, lacunas ou limites incompletos;
- **LEGADO:** implementação atual depende predominantemente de contrato ou composição que não representa o alvo;
- **MIGRAÇÃO PLANEJADA:** existe capacidade atual, mas sua forma arquitetural oficial requer migração confirmada;
- **AUSENTE:** não existe implementação suficiente do componente-alvo.

---

## 5. Catálogo dos componentes

### 5.1 Market Data Layer

- **Camada arquitetural:** Mercado e Dados.
- **Responsabilidade dominante:** Fornecer dados brutos e contexto observável de mercado e exchange.
- **Owner:** Infrastructure.
- **Maturidade:** ESTÁVEL.
- **Falhas típicas:** Dados atrasados ou incompletos, cache inconsistente e indisponibilidade da fonte.
- **Autoridade permitida:** Consultar e normalizar candles, preços, volume, saldo, ordens, fills e posições.
- **Autoridade proibida:** Decidir estratégia, autorizar execução, atribuir ownership ou alterar lifecycle.
- **Entradas:** Fontes de mercado, estado da exchange e configuração não sensível.
- **Saídas:** Dados normalizados e evidências operacionais.
- **Estado mantido ou persistido:** Cache de markets, candles e contexto; nunca ownership.
- **Dependências permitidas:** Exchange Manager, provedores de dados, Context Manager e relógio.
- **Dependências proibidas:** Decision como efeito colateral, Broker mutável, Registry como alvo de escrita e execução.
- **Módulos atuais relacionados:** `exchange_manager.py`, `context_manager.py`, `main.py` e módulos em `bots/`.
- **Efeitos colaterais conhecidos:** Instanciação de exchange nos bots, cache global e criação de diretório por `context_manager.py`.
- **Criticidade:** ALTA.
- **Testes mínimos necessários:** Normalização, indisponibilidade, dados incompletos, cache e import sem rede.
- **Estado arquitetural:** PARCIALMENTE ALINHADO.
- **Dívidas técnicas relacionadas:** TD-001, TD-004.

### 5.2 Bot / Strategy Layer

- **Camada arquitetural:** Bot / Strategy.
- **Responsabilidade dominante:** Transformar dados e contexto em hipóteses de trade identificadas.
- **Owner:** Trading.
- **Maturidade:** ESTÁVEL.
- **Falhas típicas:** Signal duplicado, estado de estratégia inconsistente e tentativa de ultrapassar seus limites de autoridade.
- **Autoridade permitida:** Detectar setups, calcular indicadores e emitir signals estruturados.
- **Autoridade proibida:** Executar ordens, decidir exposição final, acessar credenciais ou gerir lifecycle alheio.
- **Entradas:** Market Data, contexto e parâmetros da estratégia.
- **Saídas:** Signal, setup, score, direção, referências teóricas e validade.
- **Estado mantido ou persistido:** Estado específico da estratégia, watchlist, sinais e métricas próprias.
- **Dependências permitidas:** Market Data, indicadores, contratos de signal e configuração não sensível.
- **Dependências proibidas:** Exchange direta, credenciais, Broker direto e ownership por posição agregada.
- **Módulos atuais relacionados:** `bots/*.py`, `cq_bot_framework.py` e partes de `main.py`.
- **Efeitos colaterais conhecidos:** Todos os sete bots iniciam threads no import e instanciam Redis e/ou exchange globalmente.
- **Criticidade:** ALTA.
- **Testes mínimos necessários:** Signal determinístico, isolamento entre bots, ausência de execução e import safety.
- **Estado arquitetural:** MIGRAÇÃO PLANEJADA.
- **Dívidas técnicas relacionadas:** TD-003, TD-004, TD-007.

### 5.3 Decision Engine

- **Camada arquitetural:** Decision.
- **Responsabilidade dominante:** Converter signal e contexto em decisão canônica de elegibilidade.
- **Owner:** Trading.
- **Maturidade:** ESTÁVEL.
- **Falhas típicas:** Decisão ambígua, política ignorada e aprovação com contexto insuficiente.
- **Autoridade permitida:** Produzir `ALLOW`, `DENY`, `REDUCE_SIZE`, `WAIT`, `VERIFY` ou `OBSERVE`.
- **Autoridade proibida:** Criar ordem, acessar exchange, concluir fill ou alterar proteção.
- **Entradas:** Signal, contexto, políticas e analytics confiáveis.
- **Saídas:** Decisão estruturada, justificativa e condições.
- **Estado mantido ou persistido:** Registro de decisões e evidências; não posição.
- **Dependências permitidas:** Bots, Context, Executive Policy e Analytics.
- **Dependências proibidas:** Broker, Exchange Manager e Management.
- **Módulos atuais relacionados:** `decision_engine.py`, `decision_pack.py` e `main.py`.
- **Efeitos colaterais conhecidos:** Decisões e logs podem ser persistidos por fluxos concentrados em `main.py`.
- **Criticidade:** ALTA.
- **Testes mínimos necessários:** Todos os estados canônicos, políticas conflitantes e prova de que não executa.
- **Estado arquitetural:** PARCIALMENTE ALINHADO.
- **Dívidas técnicas relacionadas:** TD-001.

### 5.4 Executive Decision Layer

- **Camada arquitetural:** Executive / Decision.
- **Responsabilidade dominante:** Consolidar confiança, estratégia e políticas em orientação executiva para decisão.
- **Owner:** Executive.
- **Maturidade:** EXPERIMENTAL.
- **Falhas típicas:** Conflito de políticas, recomendação sem evidência suficiente e precedência incorreta.
- **Autoridade permitida:** Restringir, priorizar, recomendar observação e condicionar decisões futuras.
- **Autoridade proibida:** Enviar ordem, contornar Risk/Execution ou substituir estado confirmado.
- **Entradas:** Confidence, políticas, estratégia, Analytics e contexto.
- **Saídas:** Decisão executiva estruturada e justificativa.
- **Estado mantido ou persistido:** Evidência decisória e snapshots quando registrados.
- **Dependências permitidas:** CEO Confidence, Strategic Advisor, Executive Policy e Analytics.
- **Dependências proibidas:** Broker, Exchange Manager e controle direto de Position.
- **Módulos atuais relacionados:** `executive_decision_engine.py`, `decision_pack.py` e `main.py`.
- **Efeitos colaterais conhecidos:** Integração e exposição HTTP concentradas em `main.py`.
- **Criticidade:** ALTA.
- **Testes mínimos necessários:** Precedência de restrições, conflitos de política e ausência de execução direta.
- **Estado arquitetural:** PARCIALMENTE ALINHADO.
- **Dívidas técnicas relacionadas:** TD-001.

### 5.5 Risk Engine

- **Camada arquitetural:** Risk.
- **Responsabilidade dominante:** Determinar risco admissível antes e durante o trade.
- **Owner:** Trading.
- **Maturidade:** CRÍTICO.
- **Falhas típicas:** Size incorreto, limite não aplicado e exposição subestimada.
- **Autoridade permitida:** Calcular size, reduzir risco, limitar exposição e bloquear entrada.
- **Autoridade proibida:** Gerar signal, criar ordem, atribuir ownership ou alterar outcome.
- **Entradas:** Decisão elegível, capital, exposição, correlação, regime e políticas.
- **Saídas:** Aprovação de risco, size, limites ou bloqueio.
- **Estado mantido ou persistido:** Orçamentos, limites e auditoria de risco quando aplicável.
- **Dependências permitidas:** Capital Allocator, Portfolio, Exposure, Context e Executive Policy.
- **Dependências proibidas:** Broker, execução direta e alteração de setup.
- **Módulos atuais relacionados:** `policy_engine.py`, `capital_allocator.py`, `bot_exposure_manager.py`, `portfolio_manager.py` e `main.py`.
- **Efeitos colaterais conhecidos:** Estado e logs de política; grande parte da autoridade efetiva permanece em `main.py`.
- **Criticidade:** CRÍTICA.
- **Testes mínimos necessários:** Limites, sizing, concentração, correlação, fail-closed e precisão.
- **Estado arquitetural:** PARCIALMENTE ALINHADO.
- **Dívidas técnicas relacionadas:** TD-001.

### 5.6 Capital Allocator

- **Camada arquitetural:** Portfolio / Capital.
- **Responsabilidade dominante:** Distribuir orçamento de capital dentro dos limites aprovados.
- **Owner:** Executive.
- **Maturidade:** ESTÁVEL.
- **Falhas típicas:** Sobrealocação, orçamento inconsistente e capital indisponível considerado livre.
- **Autoridade permitida:** Propor ou limitar capital disponível por bot, estratégia ou trade.
- **Autoridade proibida:** Criar signal, enviar ordem ou elevar limites de risco por iniciativa própria.
- **Entradas:** Capital disponível, políticas, performance e exposição.
- **Saídas:** Alocação e limites de capital.
- **Estado mantido ou persistido:** Alocações e referências de orçamento quando adotadas.
- **Dependências permitidas:** Risk, Portfolio, Analytics e Executive Policy.
- **Dependências proibidas:** Broker e Exchange como executores.
- **Módulos atuais relacionados:** `capital_allocator.py` e `main.py`.
- **Efeitos colaterais conhecidos:** Nenhum efeito no import foi identificado no módulo dedicado.
- **Criticidade:** ALTA.
- **Testes mínimos necessários:** Limites, soma de alocações, capital insuficiente e determinismo.
- **Estado arquitetural:** PARCIALMENTE ALINHADO.
- **Dívidas técnicas relacionadas:** TD-001.

### 5.7 Portfolio Manager

- **Camada arquitetural:** Portfolio / Capital.
- **Responsabilidade dominante:** Manter visão consolidada de portfólio, pesos e concentração.
- **Owner:** Executive.
- **Maturidade:** ESTÁVEL.
- **Falhas típicas:** Concentração não detectada, agregação incorreta e mistura de estatísticas entre bots.
- **Autoridade permitida:** Produzir limites, prioridades e recomendações de alocação.
- **Autoridade proibida:** Executar, atribuir ownership ou fundir estatística de bots.
- **Entradas:** Trades, exposição, correlação, performance e políticas.
- **Saídas:** Visão de portfólio, pesos e restrições propostas.
- **Estado mantido ou persistido:** Pesos e snapshots quando aplicável.
- **Dependências permitidas:** Registry, Exposure, Analytics, Capital e Executive.
- **Dependências proibidas:** Broker e gestão direta de Position.
- **Módulos atuais relacionados:** `portfolio_manager.py`, `analytics_engine.py` e `main.py`.
- **Efeitos colaterais conhecidos:** Nenhum efeito de import relevante confirmado no módulo dedicado.
- **Criticidade:** ALTA.
- **Testes mínimos necessários:** Agregação sem misturar ownership, concentração e múltiplos bots no mesmo ativo.
- **Estado arquitetural:** PARCIALMENTE ALINHADO.
- **Dívidas técnicas relacionadas:** TD-001, TD-008.

### 5.8 Exposure Manager

- **Camada arquitetural:** Risk / Portfolio.
- **Responsabilidade dominante:** Calcular exposição por trade, bot, símbolo, direção e portfólio.
- **Owner:** Trading.
- **Maturidade:** CRÍTICO.
- **Falhas típicas:** Exposição omitida, posição externa atribuída à Central e dupla contagem.
- **Autoridade permitida:** Expor métricas e acionar limites de risco.
- **Autoridade proibida:** Atribuir ownership por símbolo/lado ou gerenciar posição externa.
- **Entradas:** Registry, posições Central e posições externas classificadas.
- **Saídas:** Exposição segmentada e global.
- **Estado mantido ou persistido:** Snapshots e limites de exposição quando configurados.
- **Dependências permitidas:** Trade Registry, Manual Position Awareness e Portfolio.
- **Dependências proibidas:** Exchange agregada como verdade de trade e Broker mutável.
- **Módulos atuais relacionados:** `bot_exposure_manager.py`, `portfolio_manager.py` e `main.py`.
- **Efeitos colaterais conhecidos:** Parte do estado e das rotas está concentrada em `main.py`.
- **Criticidade:** CRÍTICA.
- **Testes mínimos necessários:** Posição manual, múltiplos lifecycles, exposição agregada e ownership incerto.
- **Estado arquitetural:** PARCIALMENTE ALINHADO.
- **Dívidas técnicas relacionadas:** TD-001, TD-008.

### 5.9 Execution Engine

- **Camada arquitetural:** Execution.
- **Responsabilidade dominante:** Transformar decisão e risco aprovados em execução controlada e reconciliável.
- **Owner:** Execution.
- **Maturidade:** CRÍTICO.
- **Falhas típicas:** Ordem duplicada, timeout ambíguo e retry sem reconciliação.
- **Autoridade permitida:** Aplicar gates, coordenar PAPER/LIVE e solicitar ação ao Broker.
- **Autoridade proibida:** Redefinir estratégia, ignorar Risk, presumir falha ou fazer retry cego.
- **Entradas:** Plano validado, decisão, aprovação de risco e identidade persistente.
- **Saídas:** Estado de execução e evidências para Registry.
- **Estado mantido ou persistido:** Logs, auditoria, tentativas e estados de submissão.
- **Dependências permitidas:** Orchestrator, Guards, Registry, PAPER e Broker Adapter.
- **Dependências proibidas:** Indicadores de estratégia e bypass de risco.
- **Módulos atuais relacionados:** `execution_engine.py` e oito definições de `run_execution_engine` em `main.py`.
- **Efeitos colaterais conhecidos:** Criação de diretório no import, escrita de logs e cadeia de wrappers/redefinições.
- **Criticidade:** CRÍTICA.
- **Testes mínimos necessários:** OBS/PAPER/LIVE, gates, timeout, retry bloqueado, idempotência e falhas do Broker.
- **Estado arquitetural:** MIGRAÇÃO PLANEJADA.
- **Dívidas técnicas relacionadas:** TD-001, TD-002, TD-003, TD-004, TD-007.

### 5.10 Execution Orchestrator

- **Camada arquitetural:** Execution.
- **Responsabilidade dominante:** Construir plano, identidade e pré-condições antes da execução.
- **Owner:** Execution.
- **Maturidade:** CRÍTICO.
- **Falhas típicas:** Plano incompleto, identidade instável e encaminhamento sem pré-condição satisfeita.
- **Autoridade permitida:** Validar payload, gerar chave idempotente, registrar intenção e encaminhar ao Engine.
- **Autoridade proibida:** Enviar ordem diretamente ou substituir Risk/Broker.
- **Entradas:** Signal aprovado, decisão, size, modo e contexto.
- **Saídas:** Plano estruturado e idempotency key.
- **Estado mantido ou persistido:** Log de planos e registro de chaves vistas.
- **Dependências permitidas:** Decision, Risk, Registry e Idempotency Ledger.
- **Dependências proibidas:** Exchange direta e decisão estratégica própria.
- **Módulos atuais relacionados:** `execution_orchestrator.py`, `execution_engine.py` e `main.py`.
- **Efeitos colaterais conhecidos:** Cria diretório e persiste log/seen.
- **Criticidade:** CRÍTICA.
- **Testes mínimos necessários:** Plano válido/inválido, identidade estável, duplicidade e reinício.
- **Estado arquitetural:** PARCIALMENTE ALINHADO.
- **Dívidas técnicas relacionadas:** TD-002, TD-004, TD-007.

### 5.11 Idempotency e Confirmation Guards

- **Camada arquitetural:** Execution.
- **Responsabilidade dominante:** Impedir duplicidade e exigir confirmação suficiente antes de avançar estado.
- **Owner:** Execution.
- **Maturidade:** CRÍTICO.
- **Falhas típicas:** Chave colidida, tentativa não reservada e confirmação presumida.
- **Autoridade permitida:** Reservar intenção, bloquear retry, classificar estado desconhecido e exigir reconciliação.
- **Autoridade proibida:** Reenviar automaticamente, inferir não execução por timeout ou decidir estratégia.
- **Entradas:** IDs persistentes, ledger, Registry, ordens e fills.
- **Saídas:** Autorização, bloqueio ou estado de confirmação/reconciliação.
- **Estado mantido ou persistido:** Chaves idempotentes, tentativas e estados conhecidos/desconhecidos.
- **Dependências permitidas:** Registry, Reconciliation, Execution Audit e Broker consultivo.
- **Dependências proibidas:** Símbolo/lado como identidade única e timeout → retry.
- **Módulos atuais relacionados:** `execution_orchestrator.py`, `execution_engine.py`, `main.py` e estado de auditoria.
- **Efeitos colaterais conhecidos:** Persistência distribuída e comportamento composto por wrappers.
- **Criticidade:** CRÍTICA.
- **Testes mínimos necessários:** Timeout após aceite, reinício, repetição idêntica, rejeição confirmada e concorrência.
- **Estado arquitetural:** MIGRAÇÃO PLANEJADA.
- **Dívidas técnicas relacionadas:** TD-002, TD-007, TD-009.

### 5.12 Broker Adapter

- **Camada arquitetural:** Broker Adapter.
- **Responsabilidade dominante:** Traduzir comando autorizado em operação da exchange e devolver evidência estruturada.
- **Owner:** Execution.
- **Maturidade:** CRÍTICO.
- **Falhas típicas:** Timeout, ordem parcial, rejeição e resposta normalizada incorretamente.
- **Autoridade permitida:** Consultar, criar, cancelar, fechar quantidade, substituir stop e normalizar constraints.
- **Autoridade proibida:** Decidir estratégia, aumentar risco, atribuir ownership ou executar retry cego.
- **Entradas:** Comando completo, autorizado e idempotente.
- **Saídas:** Resultado, IDs, status, fills e evidências de proteção.
- **Estado mantido ou persistido:** Logs e auditoria de execução; não lifecycle estatístico.
- **Dependências permitidas:** Exchange Manager, autenticação, constraints, Configuration e logging.
- **Dependências proibidas:** Strategy, Learning e decisão de ownership.
- **Módulos atuais relacionados:** `broker.py`, `exchange_manager.py` e patches em `main.py`.
- **Efeitos colaterais conhecidos:** Escrita de logs; chamadas externas quando funções LIVE são acionadas; funções redefinidas e monkey patches.
- **Criticidade:** CRÍTICA.
- **Testes mínimos necessários:** Preview, constraints, market, timeout, fill, stop, close, hedge/one-way e nenhuma rede.
- **Estado arquitetural:** MIGRAÇÃO PLANEJADA.
- **Dívidas técnicas relacionadas:** TD-003, TD-006, TD-007, TD-010, TD-011.

### 5.13 Exchange Manager

- **Camada arquitetural:** Integração com Exchange.
- **Responsabilidade dominante:** Encapsular cliente BingX/CCXT e cache de mercados.
- **Owner:** Infrastructure.
- **Maturidade:** CRÍTICO.
- **Falhas típicas:** Cliente indisponível, cache de markets obsoleto e erro de autenticação ou transporte.
- **Autoridade permitida:** Criar cliente sob bootstrap explícito e executar consultas solicitadas pelo Broker.
- **Autoridade proibida:** Definir ownership, lifecycle, estratégia ou estatística.
- **Entradas:** Configuração operacional e comandos do Broker.
- **Saídas:** Cliente adaptado, markets e respostas da exchange.
- **Estado mantido ou persistido:** Singleton e cache em memória.
- **Dependências permitidas:** CCXT, autenticação e Configuration.
- **Dependências proibidas:** Bots, Learning e Registry como autoridade.
- **Módulos atuais relacionados:** `exchange_manager.py`, `broker.py` e instâncias diretas nos bots.
- **Efeitos colaterais conhecidos:** Instancia `ccxt.bingx`; `load_markets_once()` acessa rede quando chamado; bots podem instanciar no import.
- **Criticidade:** CRÍTICA.
- **Testes mínimos necessários:** Singleton, cache, falhas, fake CCXT e import sem cliente/rede.
- **Estado arquitetural:** MIGRAÇÃO PLANEJADA.
- **Dívidas técnicas relacionadas:** TD-004, TD-006, TD-011.

### 5.14 Trade Registry

- **Camada arquitetural:** Registry / Lifecycle.
- **Responsabilidade dominante:** Preservar identidade e verdade operacional estruturada de cada trade.
- **Owner:** Execution.
- **Maturidade:** CRÍTICO.
- **Falhas típicas:** Perda de sincronização, schema inválido e gravação concorrente inconsistente.
- **Autoridade permitida:** Registrar eventos confirmados, estados explícitos, IDs, fills e quantidades por lifecycle.
- **Autoridade proibida:** Inferir ownership por símbolo/lado, concluir sem evidência ou decidir estratégia.
- **Entradas:** Eventos de Decision, Execution, Broker, Management e Reconciliation.
- **Saídas:** Estado persistente e consultável por trade/lifecycle.
- **Estado mantido ou persistido:** Registry, IDs, quantidades, proteção, gestão, outcome e reconciliação.
- **Dependências permitidas:** Trade Record, Persistence, History e contratos de evento.
- **Dependências proibidas:** Posição agregada como substituto de trade e política executiva.
- **Módulos atuais relacionados:** `trade_registry.py`, `trade_record.py`, `main.py` e integração Falcon/Predator.
- **Efeitos colaterais conhecidos:** Cria diretório, grava registry e recebe monkey patches de persistência.
- **Criticidade:** CRÍTICA.
- **Testes mínimos necessários:** Concorrência, schema, recovery, lifecycle independente, IDs e falha de persistência.
- **Estado arquitetural:** PARCIALMENTE ALINHADO.
- **Dívidas técnicas relacionadas:** TD-001, TD-008, TD-009.

### 5.15 Trade Record

- **Camada arquitetural:** Registry / Dados de domínio.
- **Responsabilidade dominante:** Representar o registro canônico de um trade e sua identidade.
- **Owner:** Execution.
- **Maturidade:** ESTÁVEL.
- **Falhas típicas:** Campo obrigatório ausente, versão incompatível e identidade malformada.
- **Autoridade permitida:** Validar e transportar campos do trade sem executar ações externas.
- **Autoridade proibida:** Consultar exchange, decidir, executar ou inferir ownership.
- **Entradas:** IDs, bot, setup, parâmetros, fills e estados confirmados.
- **Saídas:** Registro estruturado para Registry e consumidores autorizados.
- **Estado mantido ou persistido:** Estrutura do trade; persistência delegada ao Registry.
- **Dependências permitidas:** Tipos e contratos de domínio.
- **Dependências proibidas:** Broker, Exchange, Runtime e Learning mutável.
- **Módulos atuais relacionados:** `trade_record.py` e estruturas paralelas em `trade_registry.py`, bots e `main.py`.
- **Efeitos colaterais conhecidos:** Nenhum efeito de import identificado no módulo dedicado.
- **Criticidade:** ALTA.
- **Testes mínimos necessários:** Validação de schema, serialização, IDs obrigatórios e compatibilidade de versão.
- **Estado arquitetural:** PARCIALMENTE ALINHADO.
- **Dívidas técnicas relacionadas:** TD-009.

### 5.16 Lifecycle Manager

- **Camada arquitetural:** Registry / Lifecycle.
- **Responsabilidade dominante:** Aplicar estados e transições oficiais por trade.
- **Owner:** Execution.
- **Maturidade:** CRÍTICO.
- **Falhas típicas:** Transição inválida, estado avançado sem confirmação e mistura de lifecycles.
- **Autoridade permitida:** Avançar lifecycle somente com evento e confirmação suficientes.
- **Autoridade proibida:** Misturar trades, apagar incerteza ou avançar estado por solicitação sem confirmação.
- **Entradas:** Signal, decisão, risco, submissão, fill, proteção, gestão e close confirmados.
- **Saídas:** Estado canônico e eventos de transição.
- **Estado mantido ou persistido:** Lifecycle completo e estados desconhecidos/recovery.
- **Dependências permitidas:** Registry, Reconciliation, Management, History e Outcome.
- **Dependências proibidas:** Exchange agregada como máquina de estados e decisão estratégica.
- **Módulos atuais relacionados:** `trade_registry.py`, `paper_lifecycle.py`, bots, Broker, History e blocos de `main.py`.
- **Efeitos colaterais conhecidos:** Estado distribuído entre arquivos, Redis e memória; criação/escrita de diretórios e dados.
- **Criticidade:** CRÍTICA.
- **Testes mínimos necessários:** Todas as transições oficiais, estados desconhecidos, confirmação, recovery e isolamento.
- **Estado arquitetural:** MIGRAÇÃO PLANEJADA.
- **Dívidas técnicas relacionadas:** TD-001, TD-003, TD-009.

### 5.17 Position Management

- **Camada arquitetural:** Management.
- **Responsabilidade dominante:** Gerir quantidade pertencente a um lifecycle confirmado.
- **Owner:** Execution.
- **Maturidade:** CRÍTICO.
- **Falhas típicas:** Quantidade incorreta, TP50 duplicado e gestão aplicada ao trade errado.
- **Autoridade permitida:** Solicitar TP50, break-even, trailing, redução e fechamento do próprio trade.
- **Autoridade proibida:** Gerir posição manual, quantidade alheia ou avançar estado antes da confirmação.
- **Entradas:** Lifecycle, ownership, preço, gatilhos e quantidade reconciliada.
- **Saídas:** Solicitações via Execution e estados confirmados de gestão.
- **Estado mantido ou persistido:** TP50, runner, stop, BE, trailing, quantidades e close.
- **Dependências permitidas:** Lifecycle, Risk, Execution, Registry e Reconciliation.
- **Dependências proibidas:** Broker direto na arquitetura-alvo e posição agregada sem reconciliação.
- **Módulos atuais relacionados:** `bots/falcon.py`, `paper_lifecycle.py`, outros bots, `broker.py` e `main.py`.
- **Efeitos colaterais conhecidos:** Loops automáticos no import dos bots e redefinições no Falcon.
- **Criticidade:** CRÍTICA.
- **Testes mínimos necessários:** TP50, runner, BE, trailing, confirmação, falhas e isolamento de posição manual.
- **Estado arquitetural:** MIGRAÇÃO PLANEJADA.
- **Dívidas técnicas relacionadas:** TD-003, TD-004, TD-007, TD-009.

### 5.18 Disaster Stop Management

- **Camada arquitetural:** Management / Proteção.
- **Responsabilidade dominante:** Garantir disaster stop físico confirmado para toda posição real.
- **Owner:** Execution.
- **Maturidade:** CRÍTICO.
- **Falhas típicas:** Stop ausente, stop não confirmado e quantidade protegida divergente.
- **Autoridade permitida:** Criar, consultar, validar, redimensionar, substituir, recuperar e alertar.
- **Autoridade proibida:** Declarar proteção apenas pela resposta de criação ou remover stop sem failsafe.
- **Entradas:** Fill, lado, quantidade, stop, modo da conta e estado atual.
- **Saídas:** Proteção confirmada, pendência crítica ou recovery.
- **Estado mantido ou persistido:** ID, status, preço, quantidade protegida e estado de confirmação.
- **Dependências permitidas:** Execution, Broker, Registry, Reconciliation, Watchdog e Alert Manager.
- **Dependências proibidas:** Gestão virtual como substituta e estado local antecipado.
- **Módulos atuais relacionados:** `broker.py`, `bots/falcon.py` e fallbacks/auditorias/watchdogs em `main.py`.
- **Efeitos colaterais conhecidos:** Operações LIVE quando acionado; comportamento dividido entre criação, fallback, patches e recovery.
- **Criticidade:** CRÍTICA.
- **Testes mínimos necessários:** Criação, consulta posterior, quantidade, rejeição, timeout, rollback, failsafe e recovery.
- **Estado arquitetural:** MIGRAÇÃO PLANEJADA.
- **Dívidas técnicas relacionadas:** TD-002, TD-003, TD-007, TD-009, TD-010.

### 5.19 Reconciliation

- **Camada arquitetural:** Execution / Registry.
- **Responsabilidade dominante:** Comparar estado interno e evidência externa sem transferir autoridade à exchange.
- **Owner:** Execution.
- **Maturidade:** CRÍTICO.
- **Falhas típicas:** Divergência não detectada, matching falso e incerteza sobrescrita.
- **Autoridade permitida:** Classificar divergência, confirmar por IDs/fills, bloquear conflito e propor recovery.
- **Autoridade proibida:** Forçar matching, apagar incerteza ou atribuir ownership por símbolo/lado.
- **Entradas:** Registry, client/exchange order IDs, fills, ordens, posições e proteções.
- **Saídas:** Estado reconciliado, divergência explícita ou estado desconhecido.
- **Estado mantido ou persistido:** Evidências, divergências e decisões de reconciliação.
- **Dependências permitidas:** Registry, Broker consultivo, History, Idempotency e Management.
- **Dependências proibidas:** Retry automático e posição agregada como prova individual.
- **Módulos atuais relacionados:** `broker.py`, `trade_registry.py`, Falcon e múltiplos fluxos em `main.py`.
- **Efeitos colaterais conhecidos:** Pode escrever snapshots/recovery quando acionado; implementação distribuída.
- **Criticidade:** CRÍTICA.
- **Testes mínimos necessários:** Timeout, fill parcial, stop divergente, posição externa e múltiplos lifecycles.
- **Estado arquitetural:** MIGRAÇÃO PLANEJADA.
- **Dívidas técnicas relacionadas:** TD-001, TD-007, TD-008, TD-009.

### 5.20 Manual Position Awareness

- **Camada arquitetural:** Observabilidade / Risk.
- **Responsabilidade dominante:** Detectar e classificar exposição sem ownership da Central.
- **Owner:** Execution.
- **Maturidade:** CRÍTICO.
- **Falhas típicas:** Posição manual atribuída a bot, exposição externa omitida e matching por símbolo/lado tratado como prova.
- **Autoridade permitida:** Exibir, alertar e incluir posição externa na exposição global de risco.
- **Autoridade proibida:** Atribuir a bot, gerenciar, fechar, proteger ou incorporar à estatística.
- **Entradas:** Posições da exchange e trades/lifecycles registrados.
- **Saídas:** Exposição externa e classificação com grau de evidência.
- **Estado mantido ou persistido:** Snapshots e divergências; nunca ownership presumido.
- **Dependências permitidas:** Broker consultivo, Registry, Exposure e Observabilidade.
- **Dependências proibidas:** Management, matching definitivo por símbolo/lado e estatística de bot.
- **Módulos atuais relacionados:** Fluxos e relatórios de manual position awareness em `main.py`.
- **Efeitos colaterais conhecidos:** Chaves atuais por símbolo/lado podem classificar correspondência sem prova suficiente.
- **Criticidade:** CRÍTICA.
- **Testes mínimos necessários:** Manual no mesmo símbolo/lado, quantidade agregada, múltiplos bots e nenhum gerenciamento.
- **Estado arquitetural:** MIGRAÇÃO PLANEJADA.
- **Dívidas técnicas relacionadas:** TD-001, TD-008.

### 5.21 History Manager

- **Camada arquitetural:** Persistência / Observabilidade.
- **Responsabilidade dominante:** Preservar eventos e outcomes históricos auditáveis.
- **Owner:** Infrastructure.
- **Maturidade:** ESTÁVEL.
- **Falhas típicas:** Evento duplicado, perda de ordenação e histórico incompleto.
- **Autoridade permitida:** Registrar, deduplicar, consultar e agregar eventos confirmados.
- **Autoridade proibida:** Substituir Registry, decidir ou executar.
- **Entradas:** Eventos de domínio e lifecycle.
- **Saídas:** Histórico consultável, filtros e agregações.
- **Estado mantido ou persistido:** JSON/JSONL de eventos, seen e histórico diário.
- **Dependências permitidas:** Event Bus, Registry e Persistence.
- **Dependências proibidas:** Broker e mutação de lifecycle por inferência.
- **Módulos atuais relacionados:** `history_manager.py`, `history_statistics.py` e `main.py`.
- **Efeitos colaterais conhecidos:** Cria diretório, grava eventos e aplica wrappers/monkey patches.
- **Criticidade:** ALTA.
- **Testes mínimos necessários:** Dedupe, ordenação, concorrência, corrupção e reconstrução.
- **Estado arquitetural:** PARCIALMENTE ALINHADO.
- **Dívidas técnicas relacionadas:** TD-003, TD-004.

### 5.22 Event Bus

- **Camada arquitetural:** Comunicação / Persistência.
- **Responsabilidade dominante:** Transportar e persistir eventos estruturados entre produtores e consumidores.
- **Owner:** Infrastructure.
- **Maturidade:** CONSOLIDADO.
- **Falhas típicas:** Evento perdido, duplicidade e consumidor processando schema incompatível.
- **Autoridade permitida:** Publicar, deduplicar e expor eventos.
- **Autoridade proibida:** Decidir transições por conta própria ou executar ações externas.
- **Entradas:** Eventos canônicos com IDs e timestamps.
- **Saídas:** Eventos persistidos para consumidores autorizados.
- **Estado mantido ou persistido:** Event log e conjunto de eventos vistos.
- **Dependências permitidas:** History Manager, contratos de evento e Persistence.
- **Dependências proibidas:** Broker, Exchange e efeitos estratégicos implícitos.
- **Módulos atuais relacionados:** `event_bus.py`, `history_manager.py` e rotas em `main.py`.
- **Efeitos colaterais conhecidos:** Cria diretório e grava event bus/seen.
- **Criticidade:** ALTA.
- **Testes mínimos necessários:** Emissão, dedupe, replay, falha de disco e consumidor isolado.
- **Estado arquitetural:** ALINHADO.
- **Dívidas técnicas relacionadas:** TD-004.

### 5.23 Journal Manager

- **Camada arquitetural:** Observabilidade / Persistência.
- **Responsabilidade dominante:** Organizar journal operacional e consultas por dimensões do trade.
- **Owner:** Infrastructure.
- **Maturidade:** CONSOLIDADO.
- **Falhas típicas:** Registro ausente, filtro inconsistente e exportação incompleta.
- **Autoridade permitida:** Registrar, filtrar e exportar evidências.
- **Autoridade proibida:** Alterar lifecycle, ownership, risco ou execução.
- **Entradas:** Eventos, trades e metadados reconciliados.
- **Saídas:** Journal, filtros e exports.
- **Estado mantido ou persistido:** Arquivos de journal e exportação.
- **Dependências permitidas:** History, Registry e Persistence.
- **Dependências proibidas:** Broker e execução.
- **Módulos atuais relacionados:** `journal_manager.py` e rotas em `main.py`.
- **Efeitos colaterais conhecidos:** Cria diretório e grava journal/export.
- **Criticidade:** MÉDIA.
- **Testes mínimos necessários:** Filtros, export, consistência de IDs e falha de persistência.
- **Estado arquitetural:** ALINHADO.
- **Dívidas técnicas relacionadas:** TD-004.

### 5.24 Analytics Engine

- **Camada arquitetural:** Analytics / Performance.
- **Responsabilidade dominante:** Produzir análise e métricas a partir de dados confiáveis.
- **Owner:** Learning.
- **Maturidade:** ESTÁVEL.
- **Falhas típicas:** Métrica contaminada, amostra insuficiente e agregação entre lifecycles distintos.
- **Autoridade permitida:** Calcular rankings, scores, comparações e evidência analítica.
- **Autoridade proibida:** Executar, alterar risco diretamente ou misturar estatísticas de bots.
- **Entradas:** History, Registry, outcomes e contexto reconciliados.
- **Saídas:** Métricas, rankings e avaliações.
- **Estado mantido ou persistido:** Resultados analíticos quando materializados; não estado operacional.
- **Dependências permitidas:** History, Performance, Outcome e Registry.
- **Dependências proibidas:** Broker, Exchange e Execution.
- **Módulos atuais relacionados:** `analytics_engine.py`, `history_statistics.py` e `main.py`.
- **Efeitos colaterais conhecidos:** Predominantemente leitura; exposição e composição concentradas em `main.py`.
- **Criticidade:** MÉDIA.
- **Testes mínimos necessários:** Métricas por bot/lifecycle, dados incompletos e exclusão de posição manual.
- **Estado arquitetural:** PARCIALMENTE ALINHADO.
- **Dívidas técnicas relacionadas:** TD-001, TD-008, TD-009.

### 5.25 Performance Engine

- **Camada arquitetural:** Analytics / Performance.
- **Responsabilidade dominante:** Calcular desempenho, R, expectancy, win rate e drawdown.
- **Owner:** Learning.
- **Maturidade:** ESTÁVEL.
- **Falhas típicas:** PnL incorreto, fill ausente e preço agregado usado como referência individual.
- **Autoridade permitida:** Medir e comparar performance por bot, setup e lifecycle.
- **Autoridade proibida:** Executar, gerir posição ou usar preço médio agregado como entrada estatística.
- **Entradas:** Outcomes, fills, History e Registry.
- **Saídas:** Métricas de performance.
- **Estado mantido ou persistido:** Agregados quando registrados.
- **Dependências permitidas:** History, Outcome, Rating e Analytics.
- **Dependências proibidas:** Broker e posição agregada como estatística individual.
- **Módulos atuais relacionados:** `performance_engine.py`, `rating_engine.py`, `history_statistics.py` e `real_pnl_r_mapper.py`.
- **Efeitos colaterais conhecidos:** `real_pnl_r_mapper.py` possui redefinições e possíveis leituras/escritas.
- **Criticidade:** MÉDIA.
- **Testes mínimos necessários:** Fills reais, parcial, fees, R, MAE/MFE e isolamento estatístico.
- **Estado arquitetural:** PARCIALMENTE ALINHADO.
- **Dívidas técnicas relacionadas:** TD-003, TD-008, TD-009.

### 5.26 Outcome Evaluator

- **Camada arquitetural:** Analytics / Lifecycle.
- **Responsabilidade dominante:** Consolidar outcome somente após encerramento confirmado.
- **Owner:** Learning.
- **Maturidade:** ESTÁVEL.
- **Falhas típicas:** Outcome prematuro, fechamento não confirmado e resultado duplicado.
- **Autoridade permitida:** Avaliar resultado e determinar elegibilidade para aprendizado.
- **Autoridade proibida:** Fechar trade, executar ordem ou inventar resultado sem lifecycle confiável.
- **Entradas:** Lifecycle fechado, fills, custos, MAE/MFE e contexto.
- **Saídas:** Outcome estruturado e elegibilidade.
- **Estado mantido ou persistido:** Avaliações e logs de outcome.
- **Dependências permitidas:** Registry, History, Performance e Persistence.
- **Dependências proibidas:** Broker mutável e lifecycle não confirmado.
- **Módulos atuais relacionados:** `outcome_evaluator.py`, `paper_lifecycle.py` e `main.py`.
- **Efeitos colaterais conhecidos:** Cria diretório e grava avaliações.
- **Criticidade:** ALTA.
- **Testes mínimos necessários:** Close confirmado, parcial, trade desconhecido, duplicidade e dados insuficientes.
- **Estado arquitetural:** PARCIALMENTE ALINHADO.
- **Dívidas técnicas relacionadas:** TD-004, TD-009.

### 5.27 Learning Engine

- **Camada arquitetural:** Learning.
- **Responsabilidade dominante:** Aprender com outcomes elegíveis e evidência estatística confiável.
- **Owner:** Learning.
- **Maturidade:** EXPERIMENTAL.
- **Falhas típicas:** Aprendizado com dados inválidos, overfitting e recomendação sem amostra suficiente.
- **Autoridade permitida:** Recomendar pesos, confiança, pausa, redução e avaliação de política.
- **Autoridade proibida:** Executar, ultrapassar gates ou alterar LIVE sem trilha auditável.
- **Entradas:** Outcomes, Analytics, History e políticas.
- **Saídas:** Recomendações e estado de aprendizado.
- **Estado mantido ou persistido:** Estado e logs de aprendizado.
- **Dependências permitidas:** Outcome, Analytics, History e Executive Policy.
- **Dependências proibidas:** Broker, Exchange e Execution.
- **Módulos atuais relacionados:** `learning_engine.py`, `adaptive_weights.py`, `executive_policy_learning.py` e `main.py`.
- **Efeitos colaterais conhecidos:** Criação de diretórios e escrita de estado/log; refresh automático pode ser iniciado pelo runtime.
- **Criticidade:** MÉDIA.
- **Testes mínimos necessários:** Elegibilidade, amostra insuficiente, isolamento por bot e prova de ausência de execução.
- **Estado arquitetural:** PARCIALMENTE ALINHADO.
- **Dívidas técnicas relacionadas:** TD-001, TD-003, TD-004, TD-009.

### 5.28 Adaptive Weights

- **Camada arquitetural:** Learning.
- **Responsabilidade dominante:** Manter pesos adaptativos derivados de evidência aprovada.
- **Owner:** Learning.
- **Maturidade:** EXPERIMENTAL.
- **Falhas típicas:** Peso fora do limite, atualização instável e ausência de rollback.
- **Autoridade permitida:** Calcular e sugerir pesos dentro de limites e versões auditáveis.
- **Autoridade proibida:** Executar, ampliar risco unilateralmente ou aprender com ownership incerto.
- **Entradas:** Outcomes, Analytics, performance e políticas.
- **Saídas:** Pesos e justificativas versionadas.
- **Estado mantido ou persistido:** Arquivo de pesos e log de alterações.
- **Dependências permitidas:** Learning, Analytics, Outcome e Persistence.
- **Dependências proibidas:** Broker, Exchange e alteração direta de posição.
- **Módulos atuais relacionados:** `adaptive_weights.py` e integrações em `main.py`.
- **Efeitos colaterais conhecidos:** Cria diretório e grava pesos/log.
- **Criticidade:** MÉDIA.
- **Testes mínimos necessários:** Limites, versionamento, rollback, amostra insuficiente e determinismo.
- **Estado arquitetural:** PARCIALMENTE ALINHADO.
- **Dívidas técnicas relacionadas:** TD-004, TD-009.

### 5.29 Executive Policy Manager

- **Camada arquitetural:** Executive.
- **Responsabilidade dominante:** Manter e aplicar políticas executivas auditáveis.
- **Owner:** Executive.
- **Maturidade:** ESTÁVEL.
- **Falhas típicas:** Política conflitante, prioridade incorreta e expiração não aplicada.
- **Autoridade permitida:** Restringir operação, prioridade, expansão e observação.
- **Autoridade proibida:** Enviar ordem, alterar posição manual ou mascarar falha.
- **Entradas:** Decisões humanas, Analytics, Learning, alertas e contexto.
- **Saídas:** Políticas ativas e efeitos permitidos sobre Decision/Risk.
- **Estado mantido ou persistido:** Políticas, status, prioridade, expiração e timeline.
- **Dependências permitidas:** Human Supervision, Learning, Analytics e Persistence.
- **Dependências proibidas:** Broker e Exchange.
- **Módulos atuais relacionados:** `executive_policy_manager.py`, `executive_policy_priority.py`, `executive_policy_expiration.py`, `executive_policy_auto_release.py`, `executive_policy_timeline.py` e `main.py`.
- **Efeitos colaterais conhecidos:** Leitura/escrita de políticas, timelines e alterações de estado quando acionado.
- **Criticidade:** ALTA.
- **Testes mínimos necessários:** Prioridade, conflito, expiração, release, auditoria e ausência de execução.
- **Estado arquitetural:** PARCIALMENTE ALINHADO.
- **Dívidas técnicas relacionadas:** TD-001.

### 5.30 Executive Policy Learning

- **Camada arquitetural:** Learning / Executive.
- **Responsabilidade dominante:** Avaliar efeitos e outcomes de políticas para recomendar evolução.
- **Owner:** Executive.
- **Maturidade:** CRÍTICO.
- **Falhas típicas:** Rebuild inconsistente, efeito duplicado e versão ativa equivocada.
- **Autoridade permitida:** Produzir avaliação, comparação, insights e recomendação.
- **Autoridade proibida:** Executar, liberar risco sem política ou reescrever outcome.
- **Entradas:** Histórico de políticas, outcomes, Analytics e contexto.
- **Saídas:** Efeitos, comparações e recomendações.
- **Estado mantido ou persistido:** Estado de aprendizado, effects e logs.
- **Dependências permitidas:** Policy Manager, Outcome, Analytics e History.
- **Dependências proibidas:** Broker, Exchange e Execution.
- **Módulos atuais relacionados:** `executive_policy_learning.py` e `main.py`.
- **Efeitos colaterais conhecidos:** Cria/grava estado e possui muitas redefinições sucessivas.
- **Criticidade:** ALTA.
- **Testes mínimos necessários:** Rebuild, dedupe, versões, amostra, consistência e ausência de execução.
- **Estado arquitetural:** LEGADO.
- **Dívidas técnicas relacionadas:** TD-003, TD-004.

### 5.31 Executive Alert Manager

- **Camada arquitetural:** Executive / Observabilidade.
- **Responsabilidade dominante:** Consolidar alertas executivos e seu estado de resolução.
- **Owner:** Executive.
- **Maturidade:** ESTÁVEL.
- **Falhas típicas:** Alerta perdido, duplicidade e resolução marcada sem evidência.
- **Autoridade permitida:** Emitir, priorizar, reconhecer e resolver alertas conforme política.
- **Autoridade proibida:** Executar ordens ou ocultar estado crítico.
- **Entradas:** Health, Watchdogs, Registry, Execution e políticas.
- **Saídas:** Alertas, snapshots e status de resolução.
- **Estado mantido ou persistido:** Snapshot e log de alertas.
- **Dependências permitidas:** Observabilidade, Policy Manager, History e Notifier adaptado.
- **Dependências proibidas:** Broker mutável e fechamento automático implícito.
- **Módulos atuais relacionados:** `executive_alert_manager.py` e `main.py`.
- **Efeitos colaterais conhecidos:** Cria diretório e grava snapshot/log.
- **Criticidade:** ALTA.
- **Testes mínimos necessários:** Severidade, dedupe, ACK, persistência e notifier falso.
- **Estado arquitetural:** PARCIALMENTE ALINHADO.
- **Dívidas técnicas relacionadas:** TD-004.

### 5.32 CEO Confidence

- **Camada arquitetural:** Executive / Analytics.
- **Responsabilidade dominante:** Consolidar confiança executiva a partir de evidências.
- **Owner:** Executive.
- **Maturidade:** CONSOLIDADO.
- **Falhas típicas:** Score desatualizado, dado ausente tratado como confirmação e confiança superestimada.
- **Autoridade permitida:** Produzir score e contexto para políticas e decisões.
- **Autoridade proibida:** Autorizar execução isoladamente ou alterar risco diretamente.
- **Entradas:** Analytics, Outcome, Pipeline, Risk e políticas.
- **Saídas:** Confidence e justificativa.
- **Estado mantido ou persistido:** Snapshot quando exposto ou registrado.
- **Dependências permitidas:** Analytics, Performance, Pipeline e Policy.
- **Dependências proibidas:** Broker, Exchange e Execution direta.
- **Módulos atuais relacionados:** `ceo_confidence.py` e `main.py`.
- **Efeitos colaterais conhecidos:** Nenhum efeito de import relevante confirmado no módulo dedicado.
- **Criticidade:** MÉDIA.
- **Testes mínimos necessários:** Score, dados ausentes, limites e ausência de autoridade executiva final.
- **Estado arquitetural:** ALINHADO.
- **Dívidas técnicas relacionadas:** TD-001.

### 5.33 Strategic Advisor

- **Camada arquitetural:** Executive / Analytics.
- **Responsabilidade dominante:** Produzir recomendações estratégicas explicáveis.
- **Owner:** Executive.
- **Maturidade:** CONSOLIDADO.
- **Falhas típicas:** Recomendação contraditória, contexto incompleto e justificativa insuficiente.
- **Autoridade permitida:** Recomendar prioridade, pausa, observação ou ajuste de política.
- **Autoridade proibida:** Executar, decidir ownership ou operar capital diretamente.
- **Entradas:** Confidence, Analytics, Portfolio, Performance e políticas.
- **Saídas:** Recomendações e justificativas.
- **Estado mantido ou persistido:** Relatórios ou snapshots quando registrados.
- **Dependências permitidas:** CEO Confidence, Analytics, Portfolio e Executive Policy.
- **Dependências proibidas:** Broker, Exchange e Execution.
- **Módulos atuais relacionados:** `strategic_advisor.py` e `main.py`.
- **Efeitos colaterais conhecidos:** Nenhum efeito de import relevante confirmado no módulo dedicado.
- **Criticidade:** MÉDIA.
- **Testes mínimos necessários:** Recomendações determinísticas, dados insuficientes e não execução.
- **Estado arquitetural:** ALINHADO.
- **Dívidas técnicas relacionadas:** TD-001.

### 5.34 Runtime e Bootstrap

- **Camada arquitetural:** Runtime.
- **Responsabilidade dominante:** Compor e iniciar explicitamente um único runtime controlado.
- **Owner:** Infrastructure.
- **Maturidade:** CRÍTICO.
- **Falhas típicas:** Inicialização duplicada, thread órfã e runtime iniciado durante import.
- **Autoridade permitida:** Instanciar dependências, registrar loops, eleger liderança e controlar shutdown.
- **Autoridade proibida:** Iniciar por import, duplicar workers ou ativar LIVE implicitamente.
- **Entradas:** Configuração validada e comando explícito de inicialização.
- **Saídas:** Runtime ativo, inventário de processos/threads e health.
- **Estado mantido ou persistido:** Liderança, locks, flags de startup e estado de shutdown.
- **Dependências permitidas:** Configuration, componentes de runtime e Observabilidade.
- **Dependências proibidas:** Import como gatilho e configuração operacional mutada automaticamente.
- **Módulos atuais relacionados:** `main.py`, todos os módulos em `bots/` e `memory_profiler_v1.py`.
- **Efeitos colaterais conhecidos:** `main.py` e todos os bots iniciam runtime/threads no import; risco de duplicidade.
- **Criticidade:** CRÍTICA.
- **Testes mínimos necessários:** Import safety, single start, múltiplos workers, shutdown e nenhuma rede.
- **Estado arquitetural:** MIGRAÇÃO PLANEJADA.
- **Dívidas técnicas relacionadas:** TD-001, TD-004, TD-005, TD-007.

### 5.35 Watchdogs

- **Camada arquitetural:** Runtime / Observabilidade.
- **Responsabilidade dominante:** Detectar inatividade, falha, divergência e ausência de proteção.
- **Owner:** Infrastructure.
- **Maturidade:** CRÍTICO.
- **Falhas típicas:** Falha não detectada, alerta repetido e recovery acionado com estado incompleto.
- **Autoridade permitida:** Avaliar, alertar, bloquear conflito e acionar recovery autorizado.
- **Autoridade proibida:** Executar estratégia, atribuir ownership ou alterar estado sem evidência.
- **Entradas:** Heartbeats, Registry, Execution, Position, Disaster Stop e runtime.
- **Saídas:** Health, alerta, bloqueio ou solicitação de recovery.
- **Estado mantido ou persistido:** Heartbeats, snapshots e último estado observado.
- **Dependências permitidas:** Observabilidade, Registry, Reconciliation, Alert Manager e Runtime.
- **Dependências proibidas:** Broker direto sem comando autorizado e posição agregada como ownership.
- **Módulos atuais relacionados:** Loops em `main.py`, todos os bots e `memory_profiler_v1.py`.
- **Efeitos colaterais conhecidos:** Threads automáticas, notificações e escrita de snapshots durante runtime.
- **Criticidade:** CRÍTICA.
- **Testes mínimos necessários:** Clock falso, timeout, posição sem stop, divergência, dedupe e shutdown.
- **Estado arquitetural:** PARCIALMENTE ALINHADO.
- **Dívidas técnicas relacionadas:** TD-001, TD-004, TD-007, TD-010.

### 5.36 Observabilidade e Health

- **Camada arquitetural:** Observabilidade.
- **Responsabilidade dominante:** Tornar estados operacionais e críticos visíveis e auditáveis.
- **Owner:** Infrastructure.
- **Maturidade:** ESTÁVEL.
- **Falhas típicas:** Health falso positivo, estado crítico oculto e consulta com efeito mutável.
- **Autoridade permitida:** Consultar, agregar e reportar health, audit, alert, Registry e History.
- **Autoridade proibida:** Substituir estado estruturado, executar ou silenciar divergência.
- **Entradas:** Estados canônicos de todos os componentes.
- **Saídas:** Health, relatórios, auditorias, alertas e dashboards.
- **Estado mantido ou persistido:** Snapshots, logs e relatórios; não lifecycle primário.
- **Dependências permitidas:** Todos os componentes em modo consultivo, especialmente Registry e History.
- **Dependências proibidas:** Mutação operacional implícita por rota de consulta.
- **Módulos atuais relacionados:** `execution_pipeline_status.py`, `executive_alert_manager.py`, `main.py` e health dos bots.
- **Efeitos colaterais conhecidos:** Criação de diretórios, escrita de snapshots e rotas GET que em alguns domínios podem modificar estado.
- **Criticidade:** ALTA.
- **Testes mínimos necessários:** Estados críticos mínimos, degradação, consistência e consultas sem mutação.
- **Estado arquitetural:** PARCIALMENTE ALINHADO.
- **Dívidas técnicas relacionadas:** TD-001, TD-004.

### 5.37 Persistence Layer

- **Camada arquitetural:** Persistência.
- **Responsabilidade dominante:** Persistir estado operacional de forma estruturada, recuperável e auditável.
- **Owner:** Infrastructure.
- **Maturidade:** CRÍTICO.
- **Falhas típicas:** Escrita parcial, corrupção, concorrência e recovery incompleto.
- **Autoridade permitida:** Salvar, carregar, versionar, bloquear e recuperar dados dos componentes.
- **Autoridade proibida:** Decidir estratégia, inferir lifecycle ou ocultar falha de escrita.
- **Entradas:** Registros e eventos estruturados.
- **Saídas:** Estado persistido, confirmação de escrita e erro explícito.
- **Estado mantido ou persistido:** Redis externo, JSON, JSONL, snapshots e arquivos de dados atuais.
- **Dependências permitidas:** Filesystem/Redis por adapters e contratos de schema.
- **Dependências proibidas:** Acesso externo em testes e persistência ad hoc como contrato implícito.
- **Módulos atuais relacionados:** `trade_registry.py`, `history_manager.py`, `event_bus.py`, `journal_manager.py`, módulos learning/policy, bots e `main.py`.
- **Efeitos colaterais conhecidos:** Criação de diretórios no import; estado distribuído entre Redis, arquivos e memória.
- **Criticidade:** CRÍTICA.
- **Testes mínimos necessários:** Falha de I/O, concorrência, atomicidade, schema, recovery e Fake Redis.
- **Estado arquitetural:** MIGRAÇÃO PLANEJADA.
- **Dívidas técnicas relacionadas:** TD-001, TD-004, TD-009.

### 5.38 Configuration Layer

- **Camada arquitetural:** Configuração.
- **Responsabilidade dominante:** Fornecer configuração validada e não sensível aos componentes autorizados.
- **Owner:** Infrastructure.
- **Maturidade:** CRÍTICO.
- **Falhas típicas:** Default inseguro, configuração capturada no import e valor sensível exposto.
- **Autoridade permitida:** Ler, validar e expor valores; separar modos e requisitos operacionais.
- **Autoridade proibida:** Alterar switches LIVE, credenciais ou defaults de risco como efeito colateral.
- **Entradas:** Ambiente e configuração explícita fornecida pelo operador.
- **Saídas:** Configuração tipada/validada sem revelar secrets.
- **Estado mantido ou persistido:** Snapshot não sensível e versão da configuração quando necessário.
- **Dependências permitidas:** Ambiente por adapter e Human Supervision.
- **Dependências proibidas:** Logs de secrets, mutação automática e dependência circular com runtime.
- **Módulos atuais relacionados:** Leituras distribuídas de `os.environ` em `main.py`, bots, Broker e Exchange Manager.
- **Efeitos colaterais conhecidos:** Constantes são capturadas no import e permanecem distribuídas; não há módulo oficial isolado.
- **Criticidade:** CRÍTICA.
- **Testes mínimos necessários:** Defaults seguros, validação, redaction, modos e import sem ativação.
- **Estado arquitetural:** MIGRAÇÃO PLANEJADA.
- **Dívidas técnicas relacionadas:** TD-001, TD-004, TD-011.

### 5.39 Testing Infrastructure

- **Camada arquitetural:** Testabilidade e isolamento.
- **Responsabilidade dominante:** Tornar testes determinísticos e incapazes de alcançar produção.
- **Owner:** Infrastructure.
- **Maturidade:** EXPERIMENTAL.
- **Falhas típicas:** Rede não bloqueada, fake divergente do contrato e import com efeito real.
- **Autoridade permitida:** Bloquear rede, fornecer fakes e controlar relógio, persistência e notificações.
- **Autoridade proibida:** Usar credenciais, rede, BingX, Telegram, Render ou Redis externo.
- **Entradas:** Cenários, fixtures e contratos dos componentes.
- **Saídas:** Evidência automatizada de comportamento seguro.
- **Estado mantido ou persistido:** Somente dados temporários e isolados de teste.
- **Dependências permitidas:** Fake Exchange, Fake Redis, Fake Registry, Fake Clock e Fake Notifier.
- **Dependências proibidas:** Socket/HTTP/CCXT reais e import inseguro antes do kill switch.
- **Módulos atuais relacionados:** `tests/test_history_eventbus_smoke.py`.
- **Efeitos colaterais conhecidos:** O único teste importa `main.py`, que atualmente inicia runtime; não existe kill switch global.
- **Criticidade:** CRÍTICA.
- **Testes mínimos necessários:** Teste do próprio Network Kill Switch e suíte LIVE simulada completa.
- **Estado arquitetural:** AUSENTE.
- **Dívidas técnicas relacionadas:** TD-004, TD-005, TD-006, TD-007.

### 5.40 Human Supervision Layer

- **Camada arquitetural:** Supervisão humana.
- **Responsabilidade dominante:** Definir objetivos, capital, tolerância, limites e aprovações excepcionais.
- **Owner:** Executive.
- **Maturidade:** ESTÁVEL.
- **Falhas típicas:** Aprovação sem trilha, comando ambíguo e intervenção que contorna controles.
- **Autoridade permitida:** Aprovar políticas, mudanças, deploys e intervenções explícitas.
- **Autoridade proibida:** Ser pressuposto como compensação rotineira para falhas de segurança arquitetural.
- **Entradas:** Relatórios, alertas, Analytics, Confidence e recomendações.
- **Saídas:** Direção estratégica, limites e decisões explícitas.
- **Estado mantido ou persistido:** Aprovações, políticas e trilha de governança.
- **Dependências permitidas:** Executive, Observabilidade, Analytics e documentação oficial.
- **Dependências proibidas:** Atalhos informais que contornem Registry, Risk ou Execution.
- **Módulos atuais relacionados:** Rotas e relatórios administrativos em `main.py`, políticas executivas e notificações.
- **Efeitos colaterais conhecidos:** Comandos administrativos estão distribuídos e algumas ações mutáveis usam rotas GET.
- **Criticidade:** ALTA.
- **Testes mínimos necessários:** Autorização, auditoria, idempotência de comandos e separação entre consulta/mutação.
- **Estado arquitetural:** PARCIALMENTE ALINHADO.
- **Dívidas técnicas relacionadas:** TD-001, TD-012.

---

## 6. Catálogo dos bots

Todos os bots pertencem à Bot / Strategy Layer na arquitetura-alvo. Eles podem observar mercado, detectar setups e emitir signals; nenhum possui autoridade final de execução. O caminho atual de qualquer bot até Broker é compatibilidade transitória e deve convergir para Execution.

| Bot | Módulo atual | Responsabilidade estratégica observada | Estado atual relevante | Efeitos colaterais conhecidos | Estado arquitetural | Dívidas |
|---|---|---|---|---|---|---|
| Cobra | `bots/cobra.py` | Scanner Cobra Attack e geração de sinais | Usa connector de risco/execução e Redis | Inicia threads, Redis e/ou exchange no import | MIGRAÇÃO PLANEJADA | TD-004, TD-007 |
| Donkey | `bots/donkey.py` | Scanner próprio e monitor de break-even | Mantém estado em Redis; não há watchlist nominal inventariada | Inicia threads, Redis e/ou exchange no import | MIGRAÇÃO PLANEJADA | TD-004, TD-007 |
| Falcon | `bots/falcon.py` | ORB NY, FALCON15/FALCON30 e gestão de trade | Possui caminho LIVE direto ao Broker, Registry e gestão própria | Inicia threads; envia startup; funções redefinidas | MIGRAÇÃO PLANEJADA | TD-003, TD-004, TD-007, TD-008, TD-009, TD-010 |
| Meme | `bots/meme.py` | Scanner de ativos meme e geração de sinais | Mantém estado em Redis | Inicia três threads no import | MIGRAÇÃO PLANEJADA | TD-004, TD-007 |
| Predator | `bots/predator.py` | Estratégia Predator/PAPER com firewall | Integra Registry e execução PAPER | Inicia threads e Redis/exchange no import | MIGRAÇÃO PLANEJADA | TD-004, TD-007, TD-009 |
| TrendPro | `bots/trendpro.py` | Estratégia de tendência, BE e resumos | Mantém estado em Redis; inclui handler Donkey legado | Inicia três threads no import | MIGRAÇÃO PLANEJADA | TD-004, TD-007 |
| Turtle | `bots/turtle.py` | Turtle20/Turtle55 em PAPER | Mantém lifecycle e estado PAPER/Redis | `startup()` inicia threads e notificação no import | MIGRAÇÃO PLANEJADA | TD-004, TD-007, TD-009 |

Regras comuns:

- cada bot mantém identidade e estatística próprias;
- múltiplos bots podem operar o mesmo ativo e lado com lifecycles independentes;
- fill confirmado, e não preço médio agregado, fundamenta a entrada operacional;
- posição manual nunca pertence a um bot;
- nenhum bot pode alcançar exchange diretamente na arquitetura-alvo.

---

## 7. Matriz componente × módulo atual

| Componente | Módulos atuais principais | Forma atual |
|---|---|---|
| Market Data Layer | `exchange_manager.py`, `context_manager.py`, `bots/*.py`, `main.py` | Distribuída |
| Bot / Strategy Layer | `bots/*.py`, `cq_bot_framework.py` | Distribuída por bot |
| Decision Engine | `decision_engine.py`, `decision_pack.py`, `main.py` | Parcialmente modular |
| Executive Decision Layer | `executive_decision_engine.py`, `decision_pack.py`, `main.py` | Parcialmente modular |
| Risk Engine | `policy_engine.py`, managers de capital/exposição, `main.py` | Predominantemente distribuída |
| Capital Allocator | `capital_allocator.py`, `main.py` | Módulo dedicado + integração |
| Portfolio Manager | `portfolio_manager.py`, `analytics_engine.py`, `main.py` | Parcialmente modular |
| Exposure Manager | `bot_exposure_manager.py`, `portfolio_manager.py`, `main.py` | Distribuída |
| Execution Engine | `execution_engine.py`, `main.py` | Wrappers sucessivos |
| Execution Orchestrator | `execution_orchestrator.py`, `execution_engine.py` | Parcialmente modular |
| Idempotency/Confirmation Guards | Orchestrator, Engine, auditorias em `main.py` | Distribuída |
| Broker Adapter | `broker.py`, patches em `main.py` | Módulo dedicado com patches |
| Exchange Manager | `exchange_manager.py`, instâncias nos bots | Parcialmente centralizada |
| Trade Registry | `trade_registry.py`, `trade_record.py`, `main.py` | Módulo dedicado + patches |
| Trade Record | `trade_record.py`, estruturas paralelas | Parcialmente canônico |
| Lifecycle Manager | Registry, `paper_lifecycle.py`, bots, `main.py` | Distribuída/implícita |
| Position Management | Falcon, outros bots, PAPER, Broker, `main.py` | Distribuída por fluxo |
| Disaster Stop Management | `broker.py`, Falcon, `main.py` | Distribuída |
| Reconciliation | Broker, Registry, Falcon, `main.py` | Distribuída |
| Manual Position Awareness | `main.py` | Concentrada com matching parcial |
| History Manager | `history_manager.py`, `history_statistics.py` | Módulo dedicado com wrappers |
| Event Bus | `event_bus.py`, `history_manager.py` | Módulo dedicado |
| Journal Manager | `journal_manager.py` | Módulo dedicado |
| Analytics Engine | `analytics_engine.py`, `history_statistics.py` | Parcialmente modular |
| Performance Engine | `performance_engine.py`, `rating_engine.py`, `real_pnl_r_mapper.py` | Distribuída |
| Outcome Evaluator | `outcome_evaluator.py`, lifecycle, `main.py` | Parcialmente modular |
| Learning Engine | `learning_engine.py`, adaptive/policy learning | Distribuída |
| Adaptive Weights | `adaptive_weights.py` | Módulo dedicado |
| Executive Policy Manager | `executive_policy_*.py`, `main.py` | Família de módulos |
| Executive Policy Learning | `executive_policy_learning.py` | Módulo com redefinições |
| Executive Alert Manager | `executive_alert_manager.py` | Módulo dedicado |
| CEO Confidence | `ceo_confidence.py` | Módulo dedicado |
| Strategic Advisor | `strategic_advisor.py` | Módulo dedicado |
| Runtime e Bootstrap | `main.py`, `bots/*.py` | Implícito no import |
| Watchdogs | `main.py`, `bots/*.py`, profiler | Distribuídos |
| Observabilidade e Health | pipeline status, alertas, `main.py`, bots | Distribuída |
| Persistence Layer | Registry, History, Event Bus, Journal, bots, policies | Redis/arquivos/memória |
| Configuration Layer | Leituras de ambiente distribuídas | Sem módulo oficial |
| Testing Infrastructure | `tests/test_history_eventbus_smoke.py` | Insuficiente |
| Human Supervision Layer | `main.py`, relatórios, políticas e notificações | Distribuída |

---

## 8. Matriz de autoridade

| Grupo de componentes | Pode | Nunca pode |
|---|---|---|
| Market Data | Fornecer evidência | Decidir, executar ou atribuir ownership |
| Bots | Emitir signal | Executar ou decidir exposição final |
| Decision / Executive Decision | Determinar elegibilidade e condições | Criar ordem |
| Risk / Capital / Portfolio / Exposure | Limitar risco, size e alocação | Executar ou transferir ownership |
| Execution / Orchestrator / Guards | Coordenar execução autorizada e idempotente | Redefinir estratégia ou fazer retry cego |
| Broker / Exchange Manager | Traduzir e realizar operação autorizada | Decidir estratégia, lifecycle ou estatística |
| Registry / Record / Lifecycle | Preservar identidade e estado confirmado | Inferir por símbolo/lado ou apagar incerteza |
| Management / Disaster Stop | Gerir quantidade do lifecycle e proteção física | Atingir posição manual ou trade alheio |
| Reconciliation / Manual Awareness | Comparar evidências e classificar divergência | Forçar ownership ou gestão externa |
| History / Event Bus / Journal | Registrar e expor evidência | Substituir Registry ou executar |
| Analytics / Performance / Outcome | Medir e avaliar resultado confirmado | Executar ou misturar estatísticas |
| Learning / Adaptive / Policy Learning | Recomendar evolução baseada em outcome | Operar capital diretamente |
| Executive Policy / Alerts / Confidence / Advisor | Governar, restringir e recomendar | Enviar ordem ou mascarar falha |
| Runtime / Watchdogs / Observabilidade | Iniciar explicitamente, observar e alertar | Ativar LIVE implicitamente ou inventar estado |
| Persistence / Configuration / Testing | Sustentar estado, configuração e isolamento | Decidir negócio ou alcançar produção em testes |
| Human Supervision | Definir direção, limites e aprovações | Substituir controles arquiteturais rotineiros |

---

## 9. Matriz de dependências permitidas

| Origem | Dependências permitidas |
|---|---|
| Bot | Market Data, indicadores, contexto, signal contract, configuração não sensível |
| Decision | Signals, contexto, políticas e Analytics confiável |
| Risk | Decision, Capital, Exposure, Portfolio, correlação, regime e políticas |
| Execution | Decision aprovada, Risk approval, Registry, Guards e Broker Adapter |
| Broker | Exchange Manager, constraints, autenticação, logging e Configuration |
| Registry/Lifecycle | Trade Record, eventos confirmados, Persistence, History e Reconciliation |
| Management | Lifecycle com ownership, Risk e Execution |
| Analytics/Performance | Registry, History e outcomes reconciliados |
| Learning | Outcome, Analytics, History e políticas |
| Executive | Analytics, Learning, Portfolio, alertas e Human Supervision |
| Runtime | Configuration, composição explícita e Observabilidade |
| Testing | Fakes locais, relógio e persistência isolada |

---

## 10. Matriz de dependências proibidas

| Dependência proibida | Motivo |
|---|---|
| Bot → Broker/Exchange direta | Bot não possui autoridade final de execução |
| Bot → credenciais | Estratégia não administra segredo operacional |
| Broker → Strategy/Learning | Broker executa e não pensa |
| Exchange → Ownership/Lifecycle | Estado agregado não comprova identidade |
| Learning/Analytics → Execution/Broker | Avaliação não opera capital |
| Registry → decisão estratégica | Registry preserva estado, não governa estratégia |
| Management → posição manual | Posições externas permanecem externas |
| Posição agregada → estatística de bot | Estatística pertence a trade/lifecycle |
| Símbolo/lado → ownership definitivo | É apenas indício de exposição |
| Timeout → retry automático | Ausência de resposta não prova ausência de execução |
| Import → runtime/rede/LIVE | Inicialização deve ser explícita |
| Teste → rede externa/produção | Testes devem ser fail-closed |
| Log textual → única fonte de estado | Lifecycle exige estado estruturado |

---

## 11. Componentes críticos para LIVE

São classificados como **CRÍTICA**:

1. Risk Engine;
2. Exposure Manager;
3. Execution Engine;
4. Execution Orchestrator;
5. Idempotency e Confirmation Guards;
6. Broker Adapter;
7. Exchange Manager;
8. Trade Registry;
9. Lifecycle Manager;
10. Position Management;
11. Disaster Stop Management;
12. Reconciliation;
13. Manual Position Awareness;
14. Runtime e Bootstrap;
15. Watchdogs;
16. Persistence Layer;
17. Configuration Layer;
18. Testing Infrastructure.

Esses componentes podem autorizar, coordenar, executar, proteger, identificar, persistir ou validar operações reais. Uma falha neles pode produzir exposição incorreta, duplicidade, posição sem proteção ou estado divergente.

---

## 12. Componentes que mantêm estado

| Tipo de estado | Componentes |
|---|---|
| Identidade e lifecycle | Trade Registry, Trade Record, Lifecycle Manager |
| Intenção e confirmação | Execution Engine, Orchestrator, Guards, Reconciliation |
| Posição e proteção | Position Management, Disaster Stop Management, Manual Awareness |
| Capital e política | Risk, Capital Allocator, Portfolio, Exposure, Executive Policy |
| Evidência histórica | History, Event Bus, Journal, Observabilidade |
| Estatística e aprendizado | Performance, Outcome, Learning, Adaptive Weights, Policy Learning |
| Runtime | Runtime/Bootstrap, Watchdogs, Exchange Manager |
| Infraestrutura | Persistence, Configuration e Testing em armazenamento isolado |

Estado de exchange é evidência operacional externa. Não substitui Registry nem transforma posição agregada em lifecycle.

---

## 13. Componentes com efeitos colaterais no import

Efeitos confirmados na implementação atual:

- **Runtime e Bootstrap / Bot Layer:** `main.py` e todos os sete bots iniciam runtime ou threads no import;
- **Market Data / Exchange Manager:** bots instanciam Redis e/ou exchange em escopo global;
- **Persistence e componentes dependentes:** vários módulos criam diretórios no import, incluindo Registry, History, Event Bus, Journal, Execution, Learning, Policy e PAPER;
- **Execution/Broker:** `main.py` aplica monkey patches e wrappers durante import;
- **Configuration:** variáveis de ambiente são capturadas em constantes no import;
- **Testing Infrastructure:** o teste existente importa `main.py` antes de existir proteção global de rede.

Esses comportamentos são implementação atual e estão cobertos principalmente por TD-004 e TD-005. Não constituem o contrato arquitetural desejado.

---

## 14. Componentes ainda ausentes na arquitetura atual

| Componente | Lacuna confirmada | Estado |
|---|---|---|
| Testing Infrastructure | Não há Network Kill Switch, Fake Exchange, Fake Redis/Registry/Clock/Notifier nem suíte LIVE isolada | AUSENTE |

Configuration Layer, Lifecycle Manager, Guards e Reconciliation possuem capacidades distribuídas, portanto não são classificados como totalmente ausentes; exigem consolidação e contratos oficiais.

---

## 15. Componentes parcialmente implementados

Estão **PARCIALMENTE ALINHADOS**: Market Data Layer, Decision Engine, Executive Decision Layer, Risk Engine, Capital Allocator, Portfolio Manager, Exposure Manager, Execution Orchestrator, Trade Registry, Trade Record, History Manager, Analytics Engine, Performance Engine, Outcome Evaluator, Learning Engine, Adaptive Weights, Executive Policy Manager, Executive Alert Manager, Watchdogs, Observabilidade e Health e Human Supervision Layer.

Estão **ALINHADOS** dentro do escopo inventariado: Event Bus, Journal Manager, CEO Confidence e Strategic Advisor. Essa classificação não elimina efeitos colaterais ou dívidas transversais registrados.

Executive Policy Learning está **LEGADO** devido às redefinições sucessivas confirmadas.

---

## 16. Compatibilidades transitórias

Permanecem registradas como transitórias, sem força de contrato oficial:

- caminho direto Falcon → Broker;
- caminhos diretos de bots para exchange/Redis;
- cadeia de oito definições de `run_execution_engine`;
- wrappers e monkey patches de Execution, Broker, Exchange, Registry e History;
- lifecycle distribuído entre bots, PAPER, Registry, Broker, History e `main.py`;
- matching Central × BingX parcialmente baseado em símbolo/lado;
- runtime e threads iniciados no import;
- estado distribuído entre Redis externo, JSON/JSONL e memória;
- comandos administrativos e aliases HTTP concentrados em `main.py`.

Sua remoção deve ser incremental, coberta por testes e acompanhada de plano, impacto e rollback.

---

## 17. Critérios para criação de novos componentes

Um novo componente só pode ser aceito quando estiverem definidos:

1. problema e responsabilidade dominante;
2. camada e autoridade responsável;
3. autoridades explicitamente proibidas;
4. entradas, saídas e estados canônicos;
5. estado persistido e estratégia de recovery;
6. dependências permitidas e proibidas;
7. comportamento fail-closed;
8. teste completo sem rede;
9. impacto sobre capital, ownership, lifecycle e reconciliação;
10. documentação e ADR aplicáveis.

Um arquivo novo não é justificativa suficiente. Para o uso pessoal da Central Quant, simplicidade e composição explícita prevalecem sobre generalização desnecessária.

---

## 18. Relação com os demais documentos

- `00-Vision.md`: missão e princípios superiores;
- `01-Architecture.md`: arquitetura-alvo, autoridades e contratos normativos;
- `02-Trading-Philosophy.md`: disciplina de interpretação do mercado;
- `04-Execution-Flow.md`: fluxo detalhado de execução;
- `05-Broker-Integration.md`: contrato Broker/Exchange;
- `06-Bot-Architecture.md`: contrato e independência dos bots;
- `07-Risk-Management.md`: limites e decisões de risco;
- `08-Lifecycle.md`: máquina de estados por trade;
- `09-Learning-System.md`: outcomes, analytics e learning;
- `Glossary.md`: vocabulário canônico;
- `KNOWN_DEBT.md`: dívidas confirmadas referenciadas neste catálogo;
- `adr/`: decisões específicas subordinadas à arquitetura.

---

## 19. Status final do catálogo

Este catálogo documenta **40 componentes arquiteturais oficiais** e **7 bots atuais**.

Distribuição do estado arquitetural:

| Estado | Quantidade |
|---|---:|
| ALINHADO | 4 |
| PARCIALMENTE ALINHADO | 21 |
| LEGADO | 1 |
| MIGRAÇÃO PLANEJADA | 13 |
| AUSENTE | 1 |
| **Total** | **40** |

O documento está APPROVED pelo CTO. A classificação descreve a relação entre implementação atual e arquitetura-alvo; não autoriza alteração de código, configuração ou operação.

---

## 20. Componentes previstos

Os componentes abaixo fazem parte da evolução prevista da Central Quant, mesmo sem implementação atual. Sua presença neste catálogo registra direção arquitetural; contratos, autoridades, dependências e critérios de ativação deverão ser definidos antes da implementação.

### 20.1 Simulation Engine

- **Owner previsto:** Trading.
- **Finalidade prevista:** Simular estratégias e lifecycles com dados controlados, sem criar posições reais.
- **Relação principal:** Bots, Decision, Risk, Lifecycle, Analytics e Testing Infrastructure.
- **Status:** PREVISTO.

### 20.2 Replay Engine

- **Owner previsto:** Infrastructure.
- **Finalidade prevista:** Reproduzir eventos e sequências históricas de forma determinística para auditoria e validação.
- **Relação principal:** Event Bus, History Manager, Lifecycle, Analytics e Testing Infrastructure.
- **Status:** PREVISTO.

### 20.3 Market Regime Detector

- **Owner previsto:** Trading.
- **Finalidade prevista:** Classificar condições e regimes de mercado como contexto observável para estratégia, decisão e risco.
- **Relação principal:** Market Data, Bot / Strategy, Decision, Risk e Analytics.
- **Status:** PREVISTO.

### 20.4 AI Research Layer

- **Owner previsto:** Learning.
- **Finalidade prevista:** Apoiar pesquisa quantitativa, avaliação de hipóteses e geração de recomendações auditáveis.
- **Relação principal:** Analytics, Learning, Simulation, Replay e Human Supervision.
- **Status:** PREVISTO.

### 20.5 Scenario Engine

- **Owner previsto:** Executive.
- **Finalidade prevista:** Avaliar cenários de risco, exposição e comportamento estratégico antes de decisões de política.
- **Relação principal:** Risk, Portfolio, Capital Allocator, Analytics e Executive Layer.
- **Status:** PREVISTO.

Componentes previstos não possuem autoridade operacional automática. Sua implementação deverá preservar isolamento de produção, lifecycle independente, ownership comprovável, disaster stop físico em LIVE e aprovação arquitetural aplicável.

---

# Roadmap Arquitetural

Os componentes abaixo fazem parte da visão arquitetural da Central Quant, mas ainda não necessariamente possuem implementação própria.

### Simulation Engine

- **Objetivo:** Permitir a simulação controlada de estratégias, decisões, risco, execução e lifecycle sem produzir exposição real.
- **Responsabilidade dominante:** Executar cenários simulados de forma determinística, isolada e reproduzível.
- **Motivo de existir futuramente:** Validar comportamento e hipóteses antes de qualquer adoção em PAPER ou LIVE.

### Replay Engine

- **Objetivo:** Reproduzir sequências históricas de dados e eventos para análise, auditoria e validação.
- **Responsabilidade dominante:** Reconstruir uma linha temporal determinística sem alterar o estado operacional original.
- **Motivo de existir futuramente:** Permitir investigação de incidentes, comparação de decisões e teste de regressões sobre evidências reais preservadas.

### Market Regime Engine

- **Objetivo:** Identificar e disponibilizar o regime de mercado como contexto para bots, Decision e Risk.
- **Responsabilidade dominante:** Classificar condições de mercado de forma estruturada e auditável, sem gerar ordens.
- **Motivo de existir futuramente:** Tornar explícita a influência do ambiente de mercado sobre decisões, risco e avaliação de estratégias.

### Scenario Engine

- **Objetivo:** Avaliar cenários alternativos de risco, exposição, capital e comportamento estratégico.
- **Responsabilidade dominante:** Produzir projeções e comparações de cenário sem modificar posições, políticas ou lifecycle.
- **Motivo de existir futuramente:** Apoiar decisões executivas e preparação para condições adversas antes que elas ocorram.

### AI Research Layer

- **Objetivo:** Apoiar pesquisa quantitativa, formulação de hipóteses e avaliação de modelos com rastreabilidade.
- **Responsabilidade dominante:** Produzir análises e recomendações de pesquisa, sem autoridade de execução ou alteração autônoma de LIVE.
- **Motivo de existir futuramente:** Expandir a capacidade de investigação e aprendizado mantendo supervisão humana e integridade estatística.

### Portfolio Optimizer

- **Objetivo:** Avaliar alternativas de alocação entre bots, estratégias e exposições.
- **Responsabilidade dominante:** Recomendar distribuições de capital ajustadas a risco, correlação, concentração e evidência de performance.
- **Motivo de existir futuramente:** Melhorar o uso do capital sem eliminar os limites impostos por Risk, Executive Policy e supervisão humana.

### Multi-Broker Layer

- **Objetivo:** Permitir integração futura com mais de um executor ou custodiante por contratos uniformes e explícitos.
- **Responsabilidade dominante:** Selecionar e coordenar adapters de broker autorizados sem transferir ownership, lifecycle ou decisão estratégica para serviços externos.
- **Motivo de existir futuramente:** Reduzir dependência operacional de um único executor e permitir evolução controlada da infraestrutura de execução.

Esses componentes não fazem parte da implementação atual. Sua ausência não representa dívida técnica: eles representam evolução planejada da arquitetura. Nenhum deles possui autoridade operacional até que contratos, dependências, testes, governança e aprovação arquitetural sejam formalmente definidos.

---

# Critério para novos componentes

Um novo componente somente deve ser criado quando possuir:

- responsabilidade dominante própria;
- autoridade própria e limites explícitos;
- contratos próprios;
- dependências claramente definidas;
- justificativa arquitetural.

Componentes não devem ser criados apenas para separar arquivos. A organização física do código pode mudar sem exigir uma nova responsabilidade arquitetural.

---
