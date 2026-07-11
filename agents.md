# Central Quant — Regras obrigatórias para agentes de código

## 1. Objetivo do projeto

A Central Quant é o sistema autônomo de decisão, execução, gestão e avaliação estatística das estratégias. A BingX deve ser tratada como executora e custodiante, não como fonte principal da verdade operacional ou estatística.

O objetivo central é maximizar lucro ajustado ao risco, com execução autônoma e supervisão estratégica humana.

## 2. Princípios arquiteturais obrigatórios

1. A Central Quant mantém a verdade estatística de cada operação.
2. A BingX executa ordens e mantém custódia, mas não define ownership, lifecycle ou métricas dos robôs.
3. Cada robô e cada estratégia possuem entradas, stops, gestão, PnL, TP50, break-even, trailing e resultado independentes.
4. Múltiplos robôs podem operar o mesmo ativo e o mesmo lado simultaneamente, desde que cada operação mantenha identidade e lifecycle próprios.
5. Nunca usar o preço médio agregado da posição BingX como métrica estatística de um robô.
6. O preço de entrada operacional de cada trade deve vir do fill confirmado da respectiva ordem, quando disponível.
7. Matching por apenas símbolo e lado não comprova ownership.
8. Ownership deve preferir, nesta ordem: trade UUID, lifecycle UUID, client order ID, exchange order ID, fills e quantidade reconciliada.
9. Posições manuais ou externas abertas diretamente na BingX nunca pertencem ao Falcon nem a qualquer outro robô.
10. Posições manuais devem ser apenas detectadas e exibidas como exposição externa, sem gestão automática pela Central.
11. Posições manuais não devem bloquear globalmente o Falcon. Qualquer restrição por agregação da corretora deve ser explícita, auditável e não pode transferir ownership.

## 3. Regras de execução real

1. Nunca alterar automaticamente `ENABLE_REAL_TRADING`, `BROKER_DRY_RUN`, modo LIVE, credenciais, tokens, secrets ou configurações do Render.
2. Nunca iniciar servidor, worker, bot, scanner ou processo que possa enviar ordens sem autorização explícita.
3. Nunca realizar chamadas reais à BingX, Telegram, Render ou serviços externos durante testes locais.
4. Nunca executar commit, push, merge, pull, deploy ou alteração de infraestrutura sem autorização explícita.
5. Nunca acessar, imprimir, copiar ou modificar arquivos `.env`, secrets, tokens ou chaves de API.
6. Toda execução real deve ser idempotente e reconciliável.
7. Antes de retry de entrada, reconciliar por client order ID, exchange order ID e fills para evitar duplicidade.
8. Uma resposta perdida da corretora não deve ser interpretada automaticamente como ordem não executada.
9. Toda posição real deve possuir disaster stop físico confirmado na corretora.
10. A Central pode usar SL/TP virtuais para gestão normal, mas deve preservar um disaster stop físico de proteção.
11. Falha ao criar ou confirmar disaster stop após entrada é evento crítico e deve gerar estado explícito, recovery e alerta.
12. Nunca considerar uma ordem protegida apenas porque `create_order()` retornou sem erro; confirmar o estado da ordem quando a API permitir.
13. Durante cancelamento e recriação de stop, minimizar a janela sem proteção e manter rollback/failsafe.

## 4. Gestão de posições

1. TP50, break-even, trailing e fechamento final são controlados por trade/lifecycle, não pela posição agregada da corretora.
2. A quantidade parcial deve respeitar precision, contract size, minQty e minNotional.
3. Não abrir trade que não comporte a gestão parcial prevista, salvo regra explícita da estratégia.
4. Após TP50 confirmado, redimensionar a proteção do runner e confirmar a nova quantidade protegida.
5. Nunca atualizar o estado local de stop, TP50 ou fechamento antes da confirmação do broker.
6. Em divergência entre Central e BingX, preservar capital, interromper novas ações conflitantes e reconciliar antes de continuar.
7. Não fechar, alterar stop ou gerenciar posição manual/externa.

## 5. Falcon

1. O Falcon considera apenas suas próprias posições registradas e reconciliadas.
2. Uma posição manual ou externa na BingX nunca deve ser atribuída ao Falcon.
3. O Falcon deve manter idempotência persistente para entradas e retries.
4. O Falcon deve usar fill confirmado da ordem como base operacional para entrada, R, TP50, break-even, trailing, MAE, MFE e PnL.
5. O caminho direto `Falcon -> broker` deve respeitar as mesmas garantias de segurança, idempotência e reconciliação do Execution Orchestrator.
6. Nunca remover ou enfraquecer o disaster stop, TP50, break-even, trailing, auditoria, fallback ou watchdog sem autorização explícita.

## 6. Testes

1. Testes devem ser seguros por padrão e sem rede.
2. A suíte deve falhar imediatamente se qualquer código tentar acessar BingX, Telegram, Render ou outro serviço externo.
3. Usar mocks/fakes para exchange, broker, HTTP e persistência externa.
4. Cobrir, no mínimo:
   - entrada enviada e disaster stop rejeitado;
   - entrada aceita com timeout de resposta;
   - confirmação do disaster stop aberto e com quantidade correta;
   - recovery de posição sem stop;
   - idempotência entre retries e reinícios;
   - posição manual no mesmo símbolo e lado;
   - múltiplos robôs no mesmo símbolo e lado;
   - TP50 confirmado, pendente, rejeitado e com timeout;
   - falha ao redimensionar stop após TP50;
   - rollback e failsafe do runner;
   - fill real diferente do preço do sinal;
   - hedge mode e one-way mode;
   - precision, contract size, minQty e minNotional.
5. Não executar testes que importem módulos com efeitos colaterais reais sem bloquear rede e execução previamente.

## 7. Alterações de código

Antes de editar:

1. Ler este `AGENTS.md`.
2. Inspecionar o fluxo completo afetado.
3. Informar causa provável, arquivos envolvidos, plano e testes.
4. Não alterar arquivos fora do escopo sem justificar.
5. Preservar compatibilidade com Render e variáveis de ambiente existentes.
6. Evitar novos wrappers, monkey patches e redefinições sucessivas de funções.
7. Preferir funções únicas, explícitas e testáveis.
8. Não duplicar lógica já existente em outro módulo.
9. Não alterar comportamento de outros robôs sem necessidade comprovada.
10. Não apagar logs, registries, histórico ou dados operacionais.

Depois de editar:

1. Executar somente testes seguros e locais.
2. Informar todos os arquivos modificados.
3. Apresentar o diff resumido e os principais trechos alterados.
4. Informar testes executados, resultados e testes não executados.
5. Informar riscos residuais e possíveis regressões.
6. Confirmar explicitamente:
   - nenhum secret foi acessado;
   - nenhuma chamada externa foi feita;
   - nenhum commit, push ou deploy foi executado;
   - nenhuma configuração de trading real foi alterada.

## 8. Prioridade em caso de conflito

Quando houver conflito entre velocidade, conveniência e segurança operacional, seguir esta ordem:

1. Preservar capital e proteção da posição.
2. Evitar ordem duplicada.
3. Manter ownership e lifecycle corretos.
4. Preservar consistência Central × BingX.
5. Preservar estatística por robô/estratégia.
6. Manter compatibilidade e observabilidade.
7. Otimizar desempenho e reduzir complexidade.

## 9. Regra de parada

Se uma alteração puder enviar ordem real, remover proteção, misturar ownership, alterar quantidade, afetar reconciliação, expor secrets ou modificar produção, interromper e solicitar autorização explícita antes de prosseguir.
