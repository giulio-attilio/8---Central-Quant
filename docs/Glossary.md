# Glossário

Status: DRAFT
Versão: 0.1
Última revisão: 2026-07-11
Responsável: CTO
Implementação: Codex
Aprovado: Não

---

## Objetivo

Estabelecer o vocabulário oficial usado para descrever decisões, trades, execução, risco, gestão, aprendizado e operação da Central Quant.

---

## Escopo

Este glossário inclui somente termos presentes no projeto e em sua documentação oficial. As definições descrevem o significado dos termos na Central Quant, sem especificar implementação.

---

## Conteúdo

### Analytics

- **Nome:** Analytics
- **Definição:** Conjunto de análises e métricas usado para interpretar desempenho, exposição, qualidade e comportamento das estratégias.
- **Onde é utilizado:** Relatórios, rankings, avaliação de performance, contexto executivo e suporte à decisão.
- **Relação com outros termos:** Consome dados de Trade, Outcome, MAE, MFE e Registry; apoia Decision, Learning e Confidence.

### Bot

- **Nome:** Bot
- **Definição:** Unidade autônoma que representa uma estratégia ou família de estratégias e mantém identidade operacional própria.
- **Onde é utilizado:** Geração de Signal, gestão de Trade, atribuição de Ownership, métricas e limites de Exposure.
- **Relação com outros termos:** Produz Signal, origina Trade, possui Lifecycle próprio e é governado por Risk e Executive Policy.

### Break-even

- **Nome:** Break-even
- **Definição:** Estado de gestão em que a proteção do trade é movida para uma referência destinada a reduzir ou eliminar o risco remanescente da entrada.
- **Onde é utilizado:** Gestão de posições após condições de progresso do trade, especialmente depois de TP50.
- **Relação com outros termos:** É uma transição de Lifecycle relacionada a TP50, Trailing, Position e Disaster Stop.

### Broker

- **Nome:** Broker
- **Definição:** Camada responsável pela relação operacional com a corretora, incluindo validação, envio, consulta, confirmação e reconciliação de ordens.
- **Onde é utilizado:** Execution, consulta de Position, criação de Disaster Stop, fechamentos e Recovery.
- **Relação com outros termos:** Recebe uma Execution autorizada, interage com Fill e Position e devolve evidências ao Lifecycle e ao Registry.

### Broker READY

- **Nome:** Broker READY
- **Definição:** Estado em que as verificações exigidas para considerar o broker disponível e apto a participar de uma execução foram satisfeitas.
- **Onde é utilizado:** Pré-validação de Execution, piloto real, verificação operacional e relatórios de saúde.
- **Relação com outros termos:** Precede LIVE e Execution; não substitui Decision, Risk, Dry Run ou confirmação de Fill.

### Central Position

- **Nome:** Central Position
- **Definição:** Posição que a Central reconhece como pertencente a um Trade registrado e ao respectivo Lifecycle.
- **Onde é utilizado:** Relatórios de posições, Registry, reconciliação, gestão e comparação com a corretora.
- **Relação com outros termos:** Exige Ownership; diferencia-se de Manual Position e não deve ser inferida apenas de Position agregada.

### Confidence

- **Nome:** Confidence
- **Definição:** Medida consolidada do grau de confiança atribuído a uma avaliação, decisão ou estado executivo.
- **Onde é utilizado:** Visão executiva, relatórios, priorização e suporte a políticas e decisões.
- **Relação com outros termos:** É informada por Analytics, Outcome, Pipeline, Risk e Learning; apoia Decision e Executive Policy.

### Decision

- **Nome:** Decision
- **Definição:** Resultado de uma avaliação que determina se uma intenção deve ser permitida, reduzida, bloqueada ou mantida apenas para observação.
- **Onde é utilizado:** Entre Signal, Risk e Execution, além de relatórios e auditoria.
- **Relação com outros termos:** Avalia Signal, pode usar Decision Score e Executive Policy e condiciona Execution.

### Decision Score

- **Nome:** Decision Score
- **Definição:** Pontuação consolidada usada como evidência quantitativa de apoio a uma Decision.
- **Onde é utilizado:** Avaliação de sinais, políticas de execução, relatórios e mecanismos adaptativos.
- **Relação com outros termos:** Combina informações de Analytics, Risk, Confidence e contexto; não substitui as restrições de Execution.

### Disaster Stop

- **Nome:** Disaster Stop
- **Definição:** Proteção física mantida na corretora para limitar o pior caso de uma Position real quando a gestão normal da Central não puder atuar.
- **Onde é utilizado:** Abertura e proteção de trades LIVE, verificação pós-execução, watchdog e Recovery.
- **Relação com outros termos:** Protege Position e Runner; deve ser confirmado pelo Broker e preservado durante TP50, Break-even e Trailing.

### Dry Run

- **Nome:** Dry Run
- **Definição:** Modalidade de validação que prepara e verifica uma execução sem enviar ordem real.
- **Onde é utilizado:** Preview de ordens, verificação do Broker, validação de payload e controles de segurança.
- **Relação com outros termos:** Pode validar Execution e Broker READY, mas não produz Fill nem Position real e não equivale a LIVE.

### Execution

- **Nome:** Execution
- **Definição:** Processo que transforma uma Decision autorizada em uma tentativa controlada de operação, acompanhada de evidências de envio e resultado.
- **Onde é utilizado:** Pipeline operacional entre decisão, broker, registry e lifecycle.
- **Relação com outros termos:** É precedida por Signal, Decision e Risk; utiliza Broker e pode produzir Fill, Position e Disaster Stop.

### Execution Orchestrator

- **Nome:** Execution Orchestrator
- **Definição:** Autoridade de planejamento e coordenação que organiza uma intenção executável, sua identidade e suas condições antes do executor.
- **Onde é utilizado:** Planejamento de execução, validação, idempotência, auditoria e encaminhamento para PAPER ou LIVE.
- **Relação com outros termos:** Conecta Decision, Pipeline e Execution; deve preservar Idempotency e Reconciliation.

### Executive Policy

- **Nome:** Executive Policy
- **Definição:** Diretriz de governança que condiciona decisões, exposição, expansão, bloqueios ou prioridades da Central Quant.
- **Onde é utilizado:** Camada executiva, decisão, risco, alertas, aprendizado e relatórios.
- **Relação com outros termos:** Atua sobre Decision, Risk e Exposure; pode ser informada por Analytics, Confidence, Outcome e Learning.

### Exposure

- **Nome:** Exposure
- **Definição:** Medida da quantidade de capital, risco ou concentração atualmente associada a posições, lados, símbolos, bots ou estratégias.
- **Onde é utilizado:** Gestão de risco, alocação de capital, limites de posições e visão de portfólio.
- **Relação com outros termos:** Deriva de Position e Trade; é avaliada por Risk e pode influenciar Decision e Executive Policy.

### Fill

- **Nome:** Fill
- **Definição:** Evidência de que uma ordem foi executada total ou parcialmente, com preço e quantidade efetivamente realizados.
- **Onde é utilizado:** Confirmação de entrada e saída, cálculo de métricas, Ownership, Reconciliation e Outcome.
- **Relação com outros termos:** Resulta de Execution pelo Broker; fundamenta Trade, Position, Lifecycle e estatística.

### Idempotency

- **Nome:** Idempotency
- **Definição:** Garantia de que a mesma intenção operacional não produzirá múltiplas execuções por retry, reinício ou perda de resposta.
- **Onde é utilizado:** Planejamento, execução real, identificação de duplicidade e reconciliação.
- **Relação com outros termos:** Depende da identidade de Trade, Execution e Registry; trabalha em conjunto com Reconciliation.

### Learning

- **Nome:** Learning
- **Definição:** Processo de avaliar resultados históricos confiáveis para ajustar conhecimento, pesos, políticas ou recomendações.
- **Onde é utilizado:** Avaliação de Outcome, pesos adaptativos, políticas executivas e relatórios de evolução.
- **Relação com outros termos:** Consome Outcome e Analytics; influencia Confidence, Decision e Executive Policy.

### Lifecycle

- **Nome:** Lifecycle
- **Definição:** Ciclo de vida completo e independente de um Trade, desde sua intenção até o encerramento e avaliação final.
- **Onde é utilizado:** Registro de entrada, proteção, TP50, Break-even, Trailing, fechamento, Recovery e Outcome.
- **Relação com outros termos:** Organiza Signal, Decision, Execution, Fill, Position, Registry e gestão do Trade.

### LIVE

- **Nome:** LIVE
- **Definição:** Modo operacional em que uma Execution autorizada pode produzir ordens e posições reais na corretora.
- **Onde é utilizado:** Piloto real, broker, gestão de posições, auditoria e reconciliação.
- **Relação com outros termos:** Exige Decision, Risk, Broker READY, Idempotency, Fill, Disaster Stop e Registry; diferencia-se de PAPER, Observation Only e Dry Run.

### MAE

- **Nome:** MAE
- **Definição:** Maximum Adverse Excursion, medida do maior movimento desfavorável observado durante o Lifecycle de um Trade.
- **Onde é utilizado:** Estatística de desempenho, análise de risco, avaliação de estratégia e aprendizado.
- **Relação com outros termos:** É uma métrica de Trade usada por Analytics, Outcome e Learning, em conjunto com MFE.

### Manual Position

- **Nome:** Manual Position
- **Definição:** Posição aberta fora do Lifecycle controlado por um bot ou pela Central Quant.
- **Onde é utilizado:** Awareness de posições externas, cálculo de exposição e reconciliação com a corretora.
- **Relação com outros termos:** É uma Position sem Ownership da Central; não deve ser tratada como Central Position nem gerida por um Bot.

### MFE

- **Nome:** MFE
- **Definição:** Maximum Favorable Excursion, medida do maior movimento favorável observado durante o Lifecycle de um Trade.
- **Onde é utilizado:** Estatística de desempenho, avaliação de saída, análise de estratégia e aprendizado.
- **Relação com outros termos:** É uma métrica de Trade usada por Analytics, Outcome e Learning, em conjunto com MAE.

### Observation Only

- **Nome:** Observation Only
- **Definição:** Modo em que a Central avalia e registra uma intenção sem encaminhá-la para execução de mercado ou simulação de posição.
- **Onde é utilizado:** Planejamento, diagnóstico, acompanhamento de decisões e validação do Pipeline.
- **Relação com outros termos:** Pode produzir Decision e evidência analítica, mas não produz Fill, Position LIVE ou Trade PAPER.

### Outcome

- **Nome:** Outcome
- **Definição:** Avaliação consolidada do resultado de um Trade após seu encerramento ou conclusão relevante.
- **Onde é utilizado:** Estatísticas, learning, políticas, performance e relatórios.
- **Relação com outros termos:** Deriva do Lifecycle, Fill e Trade; alimenta Analytics, Learning e Confidence.

### Ownership

- **Nome:** Ownership
- **Definição:** Relação comprovada entre uma operação, sua identidade, o bot ou estratégia responsável e as evidências de execução correspondentes.
- **Onde é utilizado:** Registry, lifecycle, reconciliação, gestão de posições e estatísticas por estratégia.
- **Relação com outros termos:** Liga Trade, Bot, Fill, Position e Registry; distingue Central Position de Manual Position.

### PAPER

- **Nome:** PAPER
- **Definição:** Modo de simulação em que a Central mantém um Trade e seu Lifecycle sem criar uma Position real na corretora.
- **Onde é utilizado:** Validação de estratégias, lifecycle simulado, outcomes e aprendizado sem execução real.
- **Relação com outros termos:** Usa Signal, Decision, Trade e Outcome, mas se diferencia de LIVE, Dry Run e Observation Only.

### Pipeline

- **Nome:** Pipeline
- **Definição:** Sequência coordenada de etapas que conduz dados e decisões entre sinal, risco, execução, lifecycle, resultado e aprendizado.
- **Onde é utilizado:** Status operacional, saúde dos componentes, execução PAPER e LIVE e relatórios executivos.
- **Relação com outros termos:** Integra Signal, Decision, Risk, Execution, Outcome, Learning e Analytics.

### Position

- **Nome:** Position
- **Definição:** Exposição aberta em um mercado, representada por direção e quantidade e sujeita a proteção e gestão.
- **Onde é utilizado:** Broker, risco, exposição, relatórios, lifecycle e reconciliação.
- **Relação com outros termos:** Pode corresponder a Central Position ou Manual Position; resulta de Fill e deve respeitar Ownership.

### Reconciliation

- **Nome:** Reconciliation
- **Definição:** Processo de comparar evidências internas e externas para determinar o estado real de uma ordem, posição, proteção ou encerramento.
- **Onde é utilizado:** Timeout, retry, divergência Central × corretora, recovery, auditoria e fechamento.
- **Relação com outros termos:** Usa Registry, Fill, Position e identificadores de Execution; sustenta Idempotency, Ownership e Lifecycle.

### Recovery

- **Nome:** Recovery
- **Definição:** Processo controlado para restaurar segurança e consistência após falha, ausência de proteção ou divergência de estado.
- **Onde é utilizado:** Disaster Stop, registry, lifecycle, reconciliação de posições e watchdogs.
- **Relação com outros termos:** É acionado por divergências em Execution, Position, Registry ou Disaster Stop e depende de Reconciliation.

### Registry

- **Nome:** Registry
- **Definição:** Registro estruturado que preserva identidade, estado e evidências do Trade ao longo de seu Lifecycle.
- **Onde é utilizado:** Abertura, atualização, fechamento, recovery, ownership, relatórios e reconciliação.
- **Relação com outros termos:** Relaciona Trade, Lifecycle, Bot, Execution, Fill, Position e Outcome.

### Risk

- **Nome:** Risk
- **Definição:** Medida e conjunto de restrições usados para limitar perdas, concentração, tamanho e exposição antes e durante um Trade.
- **Onde é utilizado:** Decision, alocação de capital, sizing, limites de posições, proteção e gestão de portfólio.
- **Relação com outros termos:** Avalia Signal e Exposure, condiciona Execution e utiliza Position, Disaster Stop e Lifecycle.

### Runner

- **Nome:** Runner
- **Definição:** Quantidade remanescente de um Trade após uma redução parcial, mantida aberta para continuidade da gestão.
- **Onde é utilizado:** Gestão posterior ao TP50, redimensionamento de proteção, Break-even e Trailing.
- **Relação com outros termos:** É parte de Position e Lifecycle; deve permanecer protegido por Disaster Stop ou stop de gestão confirmado.

### Signal

- **Nome:** Signal
- **Definição:** Indicação produzida por um bot de que condições de uma estratégia foram identificadas para avaliação.
- **Onde é utilizado:** Início do fluxo decisório, eventos dos bots, relatórios e histórico.
- **Relação com outros termos:** É avaliado por Risk e Decision; pode originar Trade e Execution, mas não representa execução confirmada.

### TP50

- **Nome:** TP50
- **Definição:** Evento e ação de gestão associados à realização parcial planejada de uma posição, preservando uma quantidade remanescente.
- **Onde é utilizado:** Lifecycle de trades, gestão PAPER e LIVE, estatísticas e proteção do Runner.
- **Relação com outros termos:** Produz Runner, pode preceder Break-even e Trailing e exige confirmação de Fill e ajuste de proteção.

### Trade

- **Nome:** Trade
- **Definição:** Operação identificada e atribuída a um bot ou estratégia, com intenção, risco, execução, gestão e resultado próprios.
- **Onde é utilizado:** Registry, histórico, lifecycle, analytics, learning e relatórios.
- **Relação com outros termos:** Pode nascer de Signal e Decision, contém Lifecycle e Ownership e é avaliado por Outcome.

### Trailing

- **Nome:** Trailing
- **Definição:** Gestão progressiva da proteção que acompanha a evolução favorável de um Trade sem ampliar seu risco inicial.
- **Onde é utilizado:** Gestão de Runner e de posições após condições de ativação definidas pela estratégia.
- **Relação com outros termos:** Atua sobre Position dentro do Lifecycle e se relaciona a Break-even, TP50 e Disaster Stop.

### Watchdog

- **Nome:** Watchdog
- **Definição:** Mecanismo de supervisão contínua que identifica ausência de atividade, falhas ou divergências operacionais.
- **Onde é utilizado:** Runtime central, bots, posições reais, disaster stop, alertas e relatórios de saúde.
- **Relação com outros termos:** Observa Pipeline, Execution, Position, Registry e Disaster Stop e pode acionar alerta ou Recovery.

---

## Relação com outros documentos

- `00-Vision.md`
- `01-Architecture.md`
- `02-Trading-Philosophy.md`
- `03-System-Components.md`
- `04-Execution-Flow.md`
- `05-Broker-Integration.md`
- `06-Bot-Architecture.md`
- `07-Risk-Management.md`
- `08-Lifecycle.md`
- `09-Learning-System.md`
- `KNOWN_DEBT.md`

---
