# Débitos Conhecidos

Status: DRAFT
Versão: 0.1
Última revisão: 2026-07-11
Responsável: CTO
Implementação: Codex
Aprovado: Não

---

## Objetivo

Registrar dívidas técnicas confirmadas no estado atual da Central Quant, com critérios objetivos para acompanhamento e resolução.

---

## Escopo

Este registro cobre somente condições verificadas no repositório por inspeção estática. Funcionalidades futuras, novas estratégias, novos robôs e melhorias opcionais não são classificadas como dívida técnica.

---

## Conteúdo

### TD-001 — Concentração de responsabilidades em `main.py`

- **ID:** TD-001
- **Título:** Concentração de responsabilidades em `main.py`
- **Categoria:** Arquitetura
- **Situação atual:** `main.py` possui 47.139 linhas e concentra aplicação HTTP, composição do runtime, carregamento de bots, decisão, risco, execução, auditoria, reconciliação, relatórios, aprendizado e rotas administrativas.
- **Motivo pelo qual existe:** Funcionalidades de domínios distintos foram incorporadas incrementalmente ao mesmo módulo, inclusive por blocos de patch e versões sucessivas.
- **Impacto:** Alterações locais exigem compreender um módulo com muitos domínios e dependências compartilhadas.
- **Risco:** Regressões por acoplamento, dificuldade de isolamento em testes e dificuldade para determinar a autoridade final de cada fluxo.
- **Prioridade:** ALTA
- **Condição para resolução:** Responsabilidades operacionais separadas em módulos com contratos explícitos, preservando compatibilidade, e `main.py` limitado à composição e exposição da aplicação.
- **Sprint provável:** Sprint 4 ou posterior
- **Classificação:** ACEITA

### TD-002 — Wrappers e redefinições sucessivas do Execution Engine

- **ID:** TD-002
- **Título:** Wrappers e redefinições sucessivas do Execution Engine
- **Categoria:** Código
- **Situação atual:** `run_execution_engine` possui oito definições em `main.py`. As versões capturam implementações anteriores por variáveis `_ORIGINAL_*` e acrescentam auth resolver, dry-run hard kill, pilot guard, notificação, watchdog, cooldown, auditoria e Falcon live audit.
- **Motivo pelo qual existe:** Controles operacionais foram adicionados como camadas posteriores sobre o runner existente, em vez de serem compostos em um pipeline único.
- **Impacto:** O comportamento efetivo depende da ordem de definição e da cadeia completa de wrappers.
- **Risco:** Uma nova camada pode ignorar, duplicar ou alterar involuntariamente uma garantia anterior.
- **Prioridade:** CRÍTICA
- **Condição para resolução:** Existência de um único entrypoint de execução com etapas declaradas, ordenadas e testadas, sem redefinições sucessivas.
- **Sprint provável:** Sprint 3
- **Classificação:** ACEITA

### TD-003 — Redefinições duplicadas em módulos operacionais

- **ID:** TD-003
- **Título:** Redefinições duplicadas em módulos operacionais
- **Categoria:** Código
- **Situação atual:** Há definições duplicadas em `broker.py`, `execution_engine.py`, `bots/falcon.py`, `real_pnl_r_mapper.py`, `history_manager.py` e `executive_policy_learning.py`. No Falcon, funções de entrada, TP50 e management loop possuem versões anteriores e posteriores no mesmo arquivo.
- **Motivo pelo qual existe:** Versões mais recentes foram acrescentadas preservando implementações anteriores no mesmo módulo.
- **Impacto:** A definição final substitui a anterior, enquanto alguns wrappers mantêm referências para versões intermediárias.
- **Risco:** Manutenção na definição errada, divergência entre comportamento aparente e efetivo e cobertura incompleta das versões realmente ativas.
- **Prioridade:** ALTA
- **Condição para resolução:** Cada responsabilidade possuir uma única definição ativa; versões legadas removidas somente após caracterização e testes de compatibilidade.
- **Sprint provável:** Sprint 4
- **Classificação:** ACEITA

### TD-004 — Efeitos colaterais durante importação

- **ID:** TD-004
- **Título:** Efeitos colaterais durante importação
- **Categoria:** Runtime
- **Situação atual:** `main.py` chama `start_central_runtime_once()` em escopo global. Os módulos dos bots iniciam threads em escopo global ou chamam funções de startup no final do arquivo. Diversos módulos também criam diretórios durante importação.
- **Motivo pelo qual existe:** Definição de módulo e bootstrap operacional não estão completamente separados.
- **Impacto:** Importar componentes para teste, inspeção ou reutilização pode iniciar loops, notificações, clientes externos ou escrita de estado.
- **Risco:** Runtime duplicado, chamadas externas acidentais e testes inseguros ou não determinísticos.
- **Prioridade:** CRÍTICA
- **Condição para resolução:** Importações sem inicialização operacional; bootstrap realizado somente por entrypoint explícito e testado.
- **Sprint provável:** Sprint 2
- **Classificação:** PLANEJADA

### TD-005 — Ausência de Network Kill Switch na suíte

- **ID:** TD-005
- **Título:** Ausência de Network Kill Switch na suíte
- **Categoria:** Testes
- **Situação atual:** Não existe `conftest.py`, fixture global ou outro mecanismo de teste que bloqueie sockets, HTTP, CCXT, Telegram e Redis externo. O único teste importa `main.py` diretamente.
- **Motivo pelo qual existe:** A suíte atual foi criada para smoke tests de histórico e Event Bus, sem infraestrutura global de isolamento de rede.
- **Impacto:** Não há garantia automatizada de que um teste falhará imediatamente ao tentar acessar serviço externo.
- **Risco:** Chamadas externas involuntárias durante testes locais, especialmente devido aos efeitos colaterais de importação.
- **Prioridade:** CRÍTICA
- **Condição para resolução:** Bloqueio global fail-closed validado por testes próprios e instalado antes da importação de módulos da aplicação.
- **Sprint provável:** Sprint 2
- **Classificação:** PLANEJADA

### TD-006 — Ausência de Fake Exchange

- **ID:** TD-006
- **Título:** Ausência de Fake Exchange
- **Categoria:** Testes
- **Situação atual:** Não há fake local da interface CCXT/BingX para ordens, posições, fills, stops, precision, limits, hedge mode e one-way mode.
- **Motivo pelo qual existe:** Os testes existentes não exercitam broker nem execução real simulada.
- **Impacto:** Os caminhos LIVE não podem ser testados de forma determinística e sem rede com estados controlados da exchange.
- **Risco:** Comportamentos de timeout, aceite parcial, stop rejeitado e reconciliação permanecem sem validação automatizada.
- **Prioridade:** CRÍTICA
- **Condição para resolução:** Fake Exchange determinístico cobrindo o subconjunto de operações usado pelo broker e validado pela suíte local sem rede.
- **Sprint provável:** Sprint 2
- **Classificação:** PLANEJADA

### TD-007 — Ausência de suíte de integração para execução LIVE

- **ID:** TD-007
- **Título:** Ausência de suíte de integração para execução LIVE
- **Categoria:** Testes
- **Situação atual:** Existe somente `tests/test_history_eventbus_smoke.py`. Não há testes dedicados ao broker, Falcon LIVE, disaster stop, idempotência, ownership, TP50 real, stop replacement ou reconciliação.
- **Motivo pelo qual existe:** A cobertura atual está concentrada em histórico, Event Bus, métricas e comportamento PAPER.
- **Impacto:** Garantias operacionais definidas no `AGENTS.md` não possuem verificação automatizada correspondente.
- **Risco:** Regressões em caminhos que enviam, protegem ou gerenciam posições reais podem não ser detectadas antes da operação.
- **Prioridade:** CRÍTICA
- **Condição para resolução:** Suíte sem rede cobrindo os cenários LIVE mínimos definidos no `AGENTS.md`, incluindo falhas, timeout, recovery, ownership e gestão parcial.
- **Sprint provável:** Sprint 2
- **Classificação:** PLANEJADA

### TD-008 — Ownership parcialmente conciliado por símbolo e lado

- **ID:** TD-008
- **Título:** Ownership parcialmente conciliado por símbolo e lado
- **Categoria:** Ownership
- **Situação atual:** O Manual Position Awareness constrói chaves de posição com símbolo e lado e usa essas chaves para classificar correspondências Central × BingX como `CENTRAL_LIVE_MATCHED` ou `MANUAL_OR_EXTERNAL_POSITION`.
- **Motivo pelo qual existe:** A visão agregada de posições da corretora é conciliada com a visão Central por uma chave comum disponível nos dois conjuntos.
- **Impacto:** A correspondência indica coexistência no mesmo símbolo/lado, mas não demonstra a origem de cada quantidade.
- **Risco:** Uma posição manual ou de outro lifecycle pode ser considerada casada com uma posição Central sem prova suficiente de ownership.
- **Prioridade:** CRÍTICA
- **Condição para resolução:** Classificação e gestão exigirem evidência por trade UUID, lifecycle UUID, client order ID, exchange order ID ou fills; símbolo/lado permanecer apenas como indício de exposição.
- **Sprint provável:** Sprint 3
- **Classificação:** PLANEJADA

### TD-009 — Lifecycle operacional distribuído e parcialmente implícito

- **ID:** TD-009
- **Título:** Lifecycle operacional distribuído e parcialmente implícito
- **Categoria:** Arquitetura
- **Situação atual:** Estado e transições de lifecycle aparecem distribuídos entre bots, `trade_registry.py`, `paper_lifecycle.py`, broker, histórico, reconciliação e múltiplos blocos de `main.py`. Não existe uma especificação única e aprovada de estados e transições.
- **Motivo pelo qual existe:** Cada fase operacional e cada bot incorporaram seus próprios campos, eventos e regras de gestão ao longo da evolução do projeto.
- **Impacto:** A interpretação de estados como entrada enviada, protegida, TP50 pendente, runner protegido e fechamento reconciliado depende de múltiplas fontes.
- **Risco:** Transições inconsistentes, atualização antecipada de estado e divergência entre Registry, bot e corretora.
- **Prioridade:** ALTA
- **Condição para resolução:** Máquina de estados oficial documentada e aplicada por trade/lifecycle, com transições confirmadas e contratos compartilhados.
- **Sprint provável:** Sprint 3
- **Classificação:** PLANEJADA

### TD-010 — Confirmação inicial do disaster stop não é demonstrada por leitura posterior

- **ID:** TD-010
- **Título:** Confirmação inicial do disaster stop não é demonstrada por leitura posterior
- **Categoria:** Broker
- **Situação atual:** Após a ordem market, o broker cria o disaster stop e considera o resultado da criação para decidir sucesso ou `LIVE_SENT_BUT_DISASTER_STOP_FAILED`. O fluxo inicial não demonstra uma consulta posterior obrigatória que confirme ordem aberta, status e quantidade protegida antes de concluir sucesso.
- **Motivo pelo qual existe:** O fluxo atual usa a resposta imediata de criação do stop como evidência principal e delega verificações adicionais a auditorias, lifecycle e watchdogs posteriores.
- **Impacto:** O estado protegido pode ser declarado antes de uma confirmação independente do stop na corretora.
- **Risco:** Posição real aberta com stop ausente, rejeitado posteriormente ou com quantidade divergente.
- **Prioridade:** CRÍTICA
- **Condição para resolução:** Confirmação obrigatória do stop por consulta ao broker, validando ID, status, lado e quantidade; estados pendente e recovery cobertos por testes sem rede.
- **Sprint provável:** Sprint 2
- **Classificação:** PLANEJADA

### TD-011 — Dependências sem versões fixadas

- **ID:** TD-011
- **Título:** Dependências sem versões fixadas
- **Categoria:** Dependências
- **Situação atual:** `requirements.txt` declara Flask, Gunicorn, Requests, Pandas, NumPy, CCXT e Upstash Redis sem versões. Não existe lockfile ou manifesto separado de desenvolvimento.
- **Motivo pelo qual existe:** O manifesto atual registra apenas os nomes dos pacotes necessários.
- **Impacto:** Instalações em datas ou ambientes diferentes podem resolver versões distintas.
- **Risco:** Alterações incompatíveis de dependências, especialmente CCXT, podem modificar contratos de execução sem mudança no repositório.
- **Prioridade:** ALTA
- **Condição para resolução:** Versões suportadas explicitadas e resolução reproduzível por lockfile ou mecanismo equivalente, incluindo dependências de teste.
- **Sprint provável:** Sprint 2
- **Classificação:** PLANEJADA

### TD-012 — Documentação técnica oficial ainda não preenchida

- **ID:** TD-012
- **Título:** Documentação técnica oficial ainda não preenchida
- **Categoria:** Documentação
- **Situação atual:** Os documentos de arquitetura, componentes, execução, broker, bots, risco, lifecycle, aprendizado, roadmap, glossário e ADRs existem apenas como templates DRAFT com espaços reservados para a Sprint 1.
- **Motivo pelo qual existe:** A infraestrutura documental foi criada antes da elaboração e aprovação das especificações oficiais.
- **Impacto:** Conceitos, responsabilidades, contratos e decisões ainda precisam ser inferidos do código e do inventário técnico.
- **Risco:** Engenharia e revisão podem adotar interpretações diferentes para os mesmos fluxos críticos.
- **Prioridade:** ALTA
- **Condição para resolução:** Documentos da Sprint 1 preenchidos, relacionados entre si, revisados pelo CTO e marcados como aprovados.
- **Sprint provável:** Sprint 1
- **Classificação:** EM TRATAMENTO

---

## Classificação consolidada

| ID | Dívida | Classificação |
|---|---|---|
| TD-001 | Concentração de responsabilidades em `main.py` | ACEITA |
| TD-002 | Wrappers e redefinições sucessivas do Execution Engine | ACEITA |
| TD-003 | Redefinições duplicadas em módulos operacionais | ACEITA |
| TD-004 | Efeitos colaterais durante importação | PLANEJADA |
| TD-005 | Ausência de Network Kill Switch na suíte | PLANEJADA |
| TD-006 | Ausência de Fake Exchange | PLANEJADA |
| TD-007 | Ausência de suíte de integração para execução LIVE | PLANEJADA |
| TD-008 | Ownership parcialmente conciliado por símbolo e lado | PLANEJADA |
| TD-009 | Lifecycle operacional distribuído e parcialmente implícito | PLANEJADA |
| TD-010 | Confirmação inicial do disaster stop não é demonstrada por leitura posterior | PLANEJADA |
| TD-011 | Dependências sem versões fixadas | PLANEJADA |
| TD-012 | Documentação técnica oficial ainda não preenchida | EM TRATAMENTO |

---

## Relação com outros documentos

- `00-Vision.md`
- `01-Architecture.md`
- `04-Execution-Flow.md`
- `05-Broker-Integration.md`
- `07-Risk-Management.md`
- `08-Lifecycle.md`
- `adr/ADR-001-BingX-Is-Executor.md`
- `adr/ADR-003-Manual-Positions.md`
- `adr/ADR-004-Disaster-Stop.md`
- `adr/ADR-007-Execution-Orchestrator.md`

---
