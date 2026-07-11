# Central Quant — Visão, missão e princípios

> A Central Quant nasceu da necessidade de transformar decisões subjetivas de trading
> em um processo objetivo, disciplinado, auditável e continuamente aperfeiçoável.
>
> Ela não existe para prever o mercado.
> Existe para responder ao mercado de forma consistente,
> preservando capital, aprendendo continuamente e mantendo o ser humano como supervisor estratégico.

## Propósito deste documento

Este documento define por que a Central Quant existe, o que ela pretende se tornar e quais princípios devem orientar toda decisão futura sobre o sistema.

Ele não é uma descrição de implementação. É um compromisso arquitetural e operacional para qualquer pessoa ou agente de IA que venha a projetar, manter, revisar ou evoluir a Central Quant.

Quando conveniência, velocidade ou oportunidade entrarem em conflito com os princípios aqui definidos, estes princípios prevalecem.

## Identidade

A Central Quant é um sistema autônomo de decisão, execução, gestão e aprendizado quantitativo.

Ela não é apenas um conjunto de robôs, uma interface para corretora ou um agregador de sinais. Sua identidade está na capacidade de preservar, para cada operação, uma verdade própria, verificável e historicamente consistente: por que a operação existiu, a quem pertenceu, como foi executada, como foi protegida, como foi gerida e qual resultado produziu.

Cada estratégia é uma tese independente. Cada trade é um lifecycle independente. Cada decisão deve ser explicável, auditável e reconciliável.

A corretora executa e mantém custódia. A Central pensa, identifica, governa, aprende e responde pelo lifecycle.

## Missão

Maximizar retorno ajustado ao risco por meio de execução autônoma disciplinada, preservação rigorosa de capital e aprendizado estatístico confiável, sob supervisão estratégica humana.

O objetivo final é maximizar o crescimento consistente do patrimônio no longo prazo.

Cumprir essa missão significa:

- transformar sinais em decisões responsáveis, não em impulsos de execução;
- proteger o capital antes de buscar eficiência ou crescimento;
- manter identidade e estatística próprias para cada robô, estratégia e trade;
- aprender apenas com dados cuja origem, lifecycle e resultado sejam confiáveis;
- operar com autonomia sem abandonar controle, rastreabilidade ou responsabilidade;
- tratar falhas, incertezas e divergências como estados explícitos que exigem reconciliação.

## Visão

A Central Quant deve evoluir para um organismo quantitativo autônomo, capaz de coordenar múltiplas estratégias simultâneas, adaptar alocação e risco com base em evidência e melhorar suas decisões sem perder a integridade operacional.

No estado desejado:

- estratégias diferentes podem operar o mesmo mercado sem perder independência;
- cada trade conserva identidade desde a intenção até o resultado final;
- decisões de risco precedem e limitam decisões de execução;
- proteção física e estado interno permanecem reconciliados;
- divergências são detectadas cedo e contidas antes de gerar novas ações conflitantes;
- aprendizado e alocação usam estatísticas por lifecycle, não aproximações agregadas;
- automação reduz erro humano sem criar autoridade opaca ou irreversível;
- a supervisão humana atua sobre políticas, limites e direção estratégica, sem precisar substituir o sistema em sua rotina normal.

O objetivo não é autonomia a qualquer custo. É autonomia confiável.

## Filosofia operacional

### O mercado sempre tem a última palavra

A Central Quant não tenta prever o mercado.

Ela observa, mede probabilidades, espera confirmação e reage às evidências.

Seu papel é administrar incerteza com disciplina, nunca eliminar a incerteza.

### Capital antes de oportunidade

Uma oportunidade perdida é aceitável. Capital perdido por ausência de proteção, duplicidade, ownership incorreto ou ação em estado incerto não é.

Em dúvida, a Central deve interromper a ação conflitante, preservar proteção e reconciliar a realidade antes de continuar.

### Verdade por trade

A unidade fundamental da Central Quant não é a posição agregada exibida pela corretora. É o trade identificado e seu lifecycle.

Entrada, quantidade, stop, TP50, break-even, trailing, PnL, MAE, MFE e resultado pertencem ao trade que os originou. Métricas de estratégias diferentes não podem ser misturadas apenas porque compartilham ativo e direção.

### Autonomia com evidência

Uma ação autônoma só é legítima quando sua intenção, autorização, execução e consequência podem ser demonstradas.

Ausência de resposta não é prova de ausência de execução. Retorno de uma requisição não é, por si só, confirmação do estado final. A Central deve distinguir intenção, envio, aceite, fill, proteção, gestão e encerramento.

### Segurança por padrão

Estados seguros devem ser o padrão. Ações reais, mutáveis ou externas devem exigir condições positivas e verificáveis, nunca depender da ausência de um bloqueio.

Falhas devem encerrar o fluxo de forma conservadora. Exceções não podem transformar incerteza em autorização.

### Aprendizado subordinado à integridade

Aprender com dados incorretos é pior do que não aprender.

O sistema só deve adaptar pesos, políticas, capital ou confiança quando a identidade, a execução e o resultado dos trades forem suficientemente confiáveis. Estatística sem ownership correto produz convicção falsa.

### Supervisão estratégica humana

A autonomia da Central existe para executar disciplina em escala, não para eliminar responsabilidade humana.

O ser humano define objetivos, limites, tolerâncias e direção estratégica. A Central deve tornar suas decisões observáveis o bastante para que essa supervisão seja informada, proporcional e efetiva.

## Princípios invioláveis

### 1. A Central é a fonte de verdade operacional e estatística

Serviços externos podem executar, custodiar, transportar mensagens ou hospedar processos. Nenhum deles define sozinho ownership, lifecycle, intenção ou resultado estatístico de um robô.

### 2. A corretora é executora e custodiante

O estado agregado da corretora é uma evidência operacional importante, mas não substitui a identidade mantida pela Central.

Preço médio agregado, símbolo e lado não são prova suficiente de ownership.

### 3. Cada trade deve possuir identidade própria

Ownership deve ser sustentado pela evidência mais forte disponível, priorizando identidade de trade e lifecycle, identificadores de ordem, fills e quantidade reconciliada.

Nenhuma conveniência de implementação justifica misturar lifecycles.

### 4. Posições manuais ou externas permanecem externas

Uma posição criada fora da Central nunca deve ser atribuída automaticamente a um robô.

Ela pode ser detectada e considerada na exposição global, mas não deve ser gerida, encerrada, protegida ou incorporada às estatísticas de uma estratégia sem prova inequívoca de ownership.

### 5. Múltiplas estratégias devem permanecer independentes

Robôs distintos podem operar o mesmo ativo e o mesmo lado. A limitação de uma infraestrutura agregadora não transfere ownership e não autoriza a fusão estatística ou operacional dessas operações.

Quando a independência não puder ser garantida, a restrição deve ser explícita, conservadora e auditável.

### 6. Toda execução real deve ser idempotente e reconciliável

A mesma intenção não pode produzir múltiplas entradas por retry, reinício, timeout ou perda de resposta.

Antes de repetir uma entrada incerta, a Central deve reconciliar identificadores, ordens e fills. Incerteza de submissão é um estado próprio, não permissão para tentar novamente.

### 7. Toda posição real deve permanecer fisicamente protegida

Uma posição aberta deve possuir disaster stop físico confirmado. Proteções virtuais podem orientar gestão, mas não substituem o último mecanismo de defesa na corretora.

Falha ao criar ou confirmar proteção após uma entrada é um evento crítico. Deve produzir estado explícito, contenção, recovery e alerta.

### 8. Estado local só avança mediante confirmação

TP50, break-even, trailing, mudança de stop e fechamento não devem ser considerados concluídos apenas porque foram solicitados.

O lifecycle deve avançar quando houver evidência suficiente de que a ação ocorreu. A Central não pode declarar uma realidade que a execução ainda não confirmou.

### 9. Gestão pertence ao lifecycle, não à posição agregada

Proteção, redução e encerramento devem respeitar a quantidade e a identidade do trade correspondente. Uma ação de gestão nunca deve atingir posição manual ou lifecycle de outro robô.

### 10. Divergências exigem contenção e reconciliação

Quando Central e corretora discordarem, a prioridade é preservar capital e evitar novas ações conflitantes.

A divergência deve permanecer visível até ser explicada e resolvida. Silenciar, sobrescrever ou inferir ownership para fazer os números coincidirem viola a identidade do sistema.

### 11. Observabilidade é parte da segurança

Decisões críticas devem deixar evidência suficiente para reconstruir o que ocorreu. Alertas, auditoria, registry, histórico e watchdogs não são acessórios: são mecanismos de controle.

Logs não substituem estado estruturado, mas nenhum estado crítico deve existir sem trilha auditável.

### 12. Testes nunca podem alcançar produção

Testes devem ser seguros por padrão, sem rede e com dependências externas substituídas por fakes ou mocks controlados.

Uma suíte que pode acessar corretora, mensageria, hospedagem ou persistência externa não é uma suíte segura.

### 13. Complexidade não pode ocultar autoridade

O caminho que autoriza, envia, protege ou gerencia capital deve ser explícito e compreensível.

Camadas sucessivas, comportamentos implícitos e múltiplas definições da mesma responsabilidade aumentam risco. A evolução deve favorecer contratos únicos, funções claras e composição verificável.

### 14. Mudanças operacionais exigem intenção explícita

Configurações de execução real, dry-run, credenciais, infraestrutura e limites de risco não devem ser alterados como efeito colateral de manutenção, testes ou refatoração.

Ativar risco é uma decisão operacional, não uma consequência técnica.

## Objetivos permanentes

### Preservar capital

Garantir que toda decisão considere risco, proteção e pior caso antes do retorno esperado.

### Evitar duplicidade

Manter identidade persistente e reconciliação suficiente para que retries e reinícios não multipliquem exposição.

### Preservar ownership

Saber, com evidência, qual trade originou cada fill, quantidade, proteção, ação de gestão e resultado.

### Preservar consistência

Detectar e explicar diferenças entre intenção, estado da Central e estado externo, sem apagar incertezas.

### Produzir estatística confiável

Medir cada estratégia a partir de seus próprios fills e lifecycle, evitando contaminação por posições agregadas, manuais ou pertencentes a outros robôs.

### Aprender com prudência

Adaptar decisões apenas quando houver amostra, qualidade de dados e causalidade operacional suficientes.

### Operar com clareza

Manter limites, decisões, estados críticos e ações administrativas compreensíveis para operadores, engenheiros e agentes de IA.

### Evoluir sem perder segurança

Refatoração, desempenho e novas estratégias são valiosos, mas não podem enfraquecer proteção, idempotência, ownership, reconciliação ou observabilidade.

## Ordem de prioridade

Em qualquer conflito de objetivos, aplicar esta ordem:

1. preservar capital e proteção da posição;
2. evitar ordem duplicada;
3. manter ownership e lifecycle corretos;
4. preservar consistência entre a Central e o mundo externo;
5. preservar estatística por robô e estratégia;
6. manter compatibilidade, auditoria e observabilidade;
7. otimizar desempenho, conveniência e complexidade.

Uma otimização que viola uma prioridade superior não é uma melhoria.

## O que a Central Quant não deve se tornar

A Central Quant não deve se tornar:

- um executor cego de sinais;
- um espelho do estado agregado da corretora;
- um conjunto de robôs que disputam a mesma posição sem ownership;
- uma automação que confunde ausência de erro com confirmação;
- um sistema que aprende com dados cuja origem não pode provar;
- uma coleção de atalhos operacionais difíceis de auditar;
- uma plataforma em que testes, imports ou diagnósticos possam ativar comportamento real;
- uma inteligência que aumenta risco mais rápido do que aumenta sua capacidade de explicá-lo e controlá-lo.

## Critério para decisões futuras

Antes de aceitar qualquer mudança relevante, perguntar:

1. Esta mudança preserva ou melhora a proteção do capital?
2. Ela mantém a operação idempotente diante de timeout, retry e reinício?
3. O ownership continua demonstrável por identidade e evidência de execução?
4. Posições externas permanecem isoladas?
5. O lifecycle avança apenas após confirmação suficiente?
6. Uma divergência continuará visível e reconciliável?
7. As estatísticas continuarão pertencendo ao trade e à estratégia corretos?
8. O comportamento será seguro durante testes, imports e diagnósticos?
9. Um futuro engenheiro conseguirá entender onde reside a autoridade da decisão?
10. A mudança respeita a ordem de prioridade definida neste documento?

Se qualquer resposta for incerta, a mudança ainda não está pronta.

## Compromisso final

A Central Quant existe para transformar autonomia em disciplina mensurável.

Seu valor não está apenas em encontrar trades ou enviar ordens. Está em sustentar uma cadeia íntegra entre intenção, decisão, risco, execução, proteção, gestão, resultado e aprendizado.

Essa cadeia é a identidade da Central Quant. Preservá-la é responsabilidade de todo engenheiro, operador ou agente de IA que participe de sua evolução.

A arquitetura da Central Quant continuará evoluindo.

Novas estratégias, novos modelos, novos mecanismos de aprendizado e novas formas de execução poderão ser incorporados ao longo do tempo.

Entretanto, nenhuma evolução deverá violar os princípios fundamentais definidos neste documento.
