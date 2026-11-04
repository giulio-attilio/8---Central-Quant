# Débitos Conhecidos

Status: DRAFT
Versão: 0.1
Última revisão: 2026-11-04 (TD-005 a TD-007 revalidados contra o checkout)
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

### TD-005 — Isolamento de rede não universal na suíte

- **ID:** TD-005
- **Título:** Isolamento de rede não universal na suíte
- **Categoria:** Testes
- **Situação atual:** Não há bloqueio global aplicado a todo `pytest`. Existe o runner selado `tests/run_falcon_pilot_minimal_offline.py`, que, antes de importar os módulos selecionados, bloqueia sockets externos, DNS, HTTP, subprocessos e leitura de `.env`, e redireciona persistência para diretório temporário. Ele protege as suítes selecionadas para execução pessoal, mas não qualquer comando de teste do repositório.
- **Motivo pelo qual existe:** O isolamento foi implementado no runner offline das regressões críticas, não como política universal de toda a suíte.
- **Impacto:** As execuções feitas por esse runner têm fronteiras reproduzíveis; testes executados fora dele não herdam automaticamente a mesma garantia.
- **Risco:** Um comando pytest arbitrário pode tentar acessar serviços ou arquivos externos se um teste/import tiver esse comportamento.
- **Prioridade:** CRÍTICA
- **Condição para resolução:** Expandir uma fronteira fail-closed para todos os comandos de teste suportados, com testes próprios; enquanto isso, usar exclusivamente o runner selado nas suítes de segurança que importam o runtime.
- **Sprint provável:** Sprint 2
- **Classificação:** PARCIALMENTE RESOLVIDA; RUNNER SELADO LIMITADO ÀS SUÍTES SELECIONADAS

### TD-006 — Ausência de simulador CCXT/BingX integrado reutilizável

- **ID:** TD-006
- **Título:** Ausência de simulador CCXT/BingX integrado reutilizável
- **Categoria:** Testes
- **Situação atual:** Há vários doubles locais por módulo (`FakeExchange`, `ExchangeProbe`, `ReadOnlyExchange` e semelhantes) cobrindo create/fetch/cancel, timeouts, fills, constraints, stops e closes. Não existe um simulador CCXT/BingX reutilizável único que modele ciclo de vida coerente entre ordem, fill, posição e stop em todos esses testes.
- **Motivo pelo qual existe:** Os contratos foram testados por cenários específicos e controlados, não por um estado de exchange sintético compartilhado.
- **Impacto:** Regressões por incompatibilidade entre os doubles de módulos distintos ou por sequência completa de estados podem escapar aos testes isolados.
- **Risco:** Uma sequência combinada de timeout, fill parcial, cancelamento e leitura posterior pode se comportar diferentemente da soma dos testes unitários.
- **Prioridade:** CRÍTICA
- **Condição para resolução:** Simulador determinístico e reutilizável que cubra apenas a superfície CCXT usada no caminho pessoal; provar que ele acrescenta cobertura de sequência além dos doubles já existentes antes de ampliar o harness.
- **Sprint provável:** Sprint 2
- **Classificação:** PARCIALMENTE COBERTA POR DOUBLES; SIMULADOR INTEGRADO AUSENTE

### TD-007 — Limite de integração real da execução LIVE

- **ID:** TD-007
- **Título:** Limite de integração real da execução LIVE
- **Categoria:** Testes
- **Situação atual:** O checkout possui suítes offline dedicadas ao broker/Falcon, entrada e fill, proteção inicial e replacement do stop, cancelamento, idempotência/identidade, ownership, fechamento e reconciliação. O runner `--extra` seleciona 25 módulos relevantes e, no HEAD local atual, passou 916 testes, com 1 skip e 1 caso deliberadamente deselected; `--stop-readback` passou 12. Isso é evidência sintética local, não integração real da corretora.
- **Motivo pelo qual existe:** O caminho real ainda é protegido por PAPER/DRY_RUN e a meta proíbe ordens reais; portanto, testes de rede com conta real não são uma opção de validação.
- **Impacto:** A maioria dos contratos de segurança pode ser regressada offline, mas a semântica real de execução/fills/stops da BingX e a integração de produção não foram provadas por essas suítes.
- **Risco:** Diferenças do exchange, configuração da conta, latência e estado de produção podem invalidar hipóteses dos doubles mesmo com os testes locais verdes.
- **Prioridade:** CRÍTICA
- **Condição para resolução:** A cobertura offline dos principais contratos está presente; completar as lacunas de sequência relevantes com simulador reutilizável se isso demonstrar cobertura adicional. Integração LIVE real não é autorizada por esta meta e deve permanecer um limite explicitamente não verificado.
- **Sprint provável:** Sprint 2
- **Classificação:** COBERTURA OFFLINE PRESENTE; INTEGRAÇÃO REAL NÃO VALIDADA/PROIBIDA PELA META

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

### TD-010 — Confirmação inicial do disaster stop no release implantado

- **ID:** TD-010
- **Título:** Confirmação inicial do disaster stop no release implantado
- **Categoria:** Broker
- **Situação atual:** O código do release implantado `598c4d4` já consulta o stop por ID exato após a criação e valida identidade, status ativo, lado/posição, quantidade e evidência material do trigger antes de marcar `stop_operationally_armed`. Se a consulta estiver ausente, conflitante ou inválida, o stop não é considerado armado e a entrada retorna como falha crítica para reconciliação. O contrato também passou em 12 testes offline no checkout atual.
- **Motivo pelo qual existe:** A resposta de criação isolada não basta para comprovar proteção operacional; a leitura posterior independente foi adicionada para fechar essa lacuna.
- **Impacto:** O código implantado contém a garantia de read-back, mas não há evidência de uma operação real na BingX que demonstre o comportamento do exchange nem de uma posição de produção protegida.
- **Risco:** Falhas específicas do exchange, configuração de conta ou comportamento do runtime podem divergir dos testes sintéticos; não inferir prontidão LIVE.
- **Prioridade:** CRÍTICA
- **Condição para resolução:** A implementação está presente no release `598c4d4` e os contratos exatos/fail-closed passam offline. A evidência de comportamento da corretora e de posição real protegida permanece ausente; essa validação não deve ser feita por esta meta, que proíbe ordens reais.
- **Sprint provável:** Sprint 2
- **Classificação:** IMPLEMENTADA NO RELEASE; COMPORTAMENTO EXTERNO NÃO COMPROVADO

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
| TD-005 | Isolamento de rede não universal | PARCIALMENTE RESOLVIDA; RUNNER SELADO PARA SUÍTES CRÍTICAS |
| TD-006 | Ausência de simulador CCXT/BingX integrado reutilizável | PARCIALMENTE COBERTA POR DOUBLES |
| TD-007 | Limite de integração real da execução LIVE | TESTES OFFLINE PRESENTES; INTEGRAÇÃO REAL NÃO VALIDADA/PROIBIDA |
| TD-008 | Ownership parcialmente conciliado por símbolo e lado | PLANEJADA |
| TD-009 | Lifecycle operacional distribuído e parcialmente implícito | PLANEJADA |
| TD-010 | Confirmação inicial do disaster stop no release implantado | IMPLEMENTADA NO CÓDIGO; EXCHANGE NÃO VALIDADO |
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
