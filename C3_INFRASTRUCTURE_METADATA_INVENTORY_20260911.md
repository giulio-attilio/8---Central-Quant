# C3 — inventário parcial de metadados da infraestrutura

## Atualização autorizada — 12/09/2026, 03:13 UTC (00:13 BRT)

O usuário respondeu SIM à inspeção somente leitura de permissões e recuperação
no Render e Redis, sem credenciais, conteúdo de bancos ou alterações. Sessões
existentes usadas; nenhuma autenticação, criação, configuração ou compra feita.
Esta atualização substitui somente as lacunas explicitamente verificadas abaixo;
as seções posteriores permanecem como histórico, inclusive a antiga tentativa
AWS e a antiga ausência de consulta às ACLs. AWS não foi consultada nesta rodada.

### Evidências visíveis novas

| Superfície | Observação direta | Limite da conclusão |
| --- | --- | --- |
| Render / Disk | Disco de 2 GB em `/data`; snapshots diários retidos sete dias; sete entradas de 5 a 11/09; mais recente mostrada como September 11, 2026 at 8:57 PM | Fuso da apresentação não verificado; nenhuma cópia aberta/restaurada. O painel alerta perda das alterações posteriores à cópia escolhida |
| Render / Workspace settings | Plano Hobby confirmado; seletor mostra 1 member; Team Members e medidas adicionais de Security condicionadas a Pro; Audit Logs também requer Pro; Authentication SAML/SCIM requer Scale | Não prova ausência de MFA pessoal ou falha de segurança geral. Não foram consultados tokens, contas adicionais ou auditoria bruta |
| Upstash / ACL do banco robo-sinais-bingx | On 1, Off 0; único usuário listado `default`, ON; KEYS `~*`; CAT `+@all` | Não aparece identidade C3 dedicada/restrita nessa lista. Não foi verificada a credencial realmente usada pela Central, nem permissões do painel/cloud ou rotas REST alternativas |
| Upstash / Backups do mesmo banco | Daily Backup desligado; tabela vazia com `No data`; ações Restore e Backup & Export disponíveis, não acionadas | Não comprova ausência de persistência, réplicas ou cópias externas; demonstra somente ausência de backups listados nessa tela |

Fontes autenticadas observadas, sem exportar conteúdo:
[Render Disk](https://dashboard.render.com/web/srv-d8rtuv9o3t8c73ehav5g/disks),
[Render Workspace settings](https://dashboard.render.com/w/tea-d8gnnuojo6nc73ep3lg0/settings),
[Upstash ACL](https://console.upstash.com/redis/209ca0cc-5106-4f11-89b7-97e7dc6d532b/rbac?teamid=0),
[Upstash Backups](https://console.upstash.com/redis/209ca0cc-5106-4f11-89b7-97e7dc6d532b/backups?teamid=0).

### Decisão e próximos limites

Os recursos atuais não demonstram uma autoridade C3 pronta com privilégio mínimo,
consumo único e recuperação independente. Isso NÃO determina compra obrigatória
de Pro/AWS, nem transforma backup diário em requisito suficiente para Live.
Separar higiene operacional do Redis de qualificação da autoridade C3.

Não restringir/desativar `default` diretamente: a conexão e os comandos necessários
à Central não foram inspecionados. Uma futura migração de acesso exigiria inventário
de comandos/chaves a partir do código, identidade dedicada, teste de compatibilidade
e rollback antes de retirar acesso antigo. Não gerar tokens ou definir ACL por palpite.
Uma futura política de backup exige conhecer cobertura, retenção, custo e destino
e ensaio de restauração isolado; não acionar switches ou Restore nesta autorização.
Nenhum desses passos constitui recuperação autenticada anti-rollback por si só.

Inspeção encerrada. Não repetir login, inventário/ACL/backup ou chamar banco/preflight
para simular progresso. Fonte temporal, emissores autenticados e recuperação da
autoridade permanecem dependências reais já documentadas. Alterações de produção,
permissões e serviços exigem aprovação específica, não OK genérico.

Somente este inventário e a continuidade local editados; código/testes intactos.
Não executados testes (nenhuma alteração funcional), main, comandos Redis, shell
remoto, backup/restore/export, commit/push/deploy ou alteração de flags/Live.
Navegação externa somente leitura ocorreu. Nenhum secret/credencial ou conteúdo
de Registry/trades foi lido. Na passagem pela página Details, foram lidos somente
rótulos de navegação, não campos de conexão; a habilidade de navegação orientou
a inspeção limitada e a preservação de controles sensíveis.

Data da consulta: 2026-09-11. Escopo autorizado pelo usuário: somente leitura
de metadados não sensíveis dos recursos existentes. Não inclui autenticação
automatizada, secrets, dados de trades/Registry, alterações ou provisionamento.

## Render: observado diretamente no painel

| Item | Evidência observada |
| --- | --- |
| Workspace | My Workspace; Active (1), Suspended (0), All (1) |
| Único serviço listado | central-robos-bingx; Web Service; Python 3; Oregon |
| Identificador | srv-d8rtuv9o3t8c73ehav5g |
| Compute | Standard; seleção atual 1 CPU e 2 GB de RAM |
| Disco | 2 GB, mount path `/data` |
| Snapshots | Painel informa captura a cada 24 horas e retenção de sete dias; lista capturas de 4 a 10 de setembro de 2026 |
| Escala | Painel informa que scaling não é suportado em servidores com disco |
| Origem do deploy | giulio-attilio/8---Central-Quant, branch main |
| Commit publicado | 17e767c14b7c90c97a01bc5173f4fd94985672cc |
| Deploy | dep-dahtplbm8hqs73dc393g; status de implantação Live; descrição: fix(preflight): keep registry storage status read-only |

Fontes consultadas: [workspace](https://dashboard.render.com/),
[serviço](https://dashboard.render.com/web/srv-d8rtuv9o3t8c73ehav5g),
[disco](https://dashboard.render.com/web/srv-d8rtuv9o3t8c73ehav5g/disks) e
[compute](https://dashboard.render.com/web/srv-d8rtuv9o3t8c73ehav5g/compute).

Não há PostgreSQL nem serviço de autoridade separado na listagem desse
workspace. Isso não comprova ausência em outros workspaces, contas ou provedores.
Hobby é informação anterior do usuário, não confirmação nova deste inventário.
O status Live do Render significa implantação disponível, não trading habilitado
nem readiness de trading. Flags e preflight não foram consultados nesta etapa.

Não foram obtidos uso numérico atual do disco, quantidade de processos/writers,
localização efetiva do Registry ou comprovação de recuperação. A lista de
snapshots não demonstra restauração segura, anti-rollback, integridade ou
segregação administrativa. O fuso dos horários dos snapshots não foi confirmado.
As correções locais mais recentes continuam sem publicação nesta etapa.

## Outros provedores: limites encontrados

- A primeira consulta Upstash mostrou Personal sem bancos, mas o usuário
  esclareceu que havia entrado na conta errada. Essa observação NÃO descreve
  a infraestrutura da conta correta nem constitui evidência de ausência de Redis.
- [Upstash — Redis](https://console.upstash.com/redis): após novo login manual
  e novo `feito`, a listagem da conta correta mostra um banco
  **robo-sinais-bingx**, plano **Pay as You Go**, provedor de hospedagem **AWS**,
  região **US-WEST-2**, no espaço **Personal**. O rótulo AWS identifica a
  hospedagem da Upstash, não comprova conta AWS própria, KMS ou autoridade C3.
  A listagem mostra 4,1 milhões de comandos, armazenamento médio de 48 MB e
  custo de US$ 8,19; o período dessas métricas não aparece nessa página.
  Separadamente, a Home informa uso neste mês de US$ 8,19. Não é mensalidade
  fixa, previsão de fatura final nem custo incremental de uma autoridade C3.
  Banco localizado por metadados; conexão efetiva da Central a ele não foi
  verificada, pois não foram abertas variáveis, credenciais ou dados.
  Somente Home e listagem foram consultadas; nenhuma página de detalhes do
  banco, URL de conexão, token, comando Redis ou criação/importação foi usada.
- AWS: tentativa de abrir `https://console.aws.amazon.com/` terminou em timeout;
  a seleção posterior encontrou página de erro bloqueada pela política do
  navegador. Não houve contorno da restrição, login ou leitura de recursos.
  Existência de conta, recursos, custódia e segregação permanecem desconhecidas.

## Conclusão e continuidade

O Render existente está parcialmente caracterizado. Ainda não há evidência
suficiente para escolher uma autoridade persistente autenticada reutilizável,
afirmar necessidade de contratar um provedor específico ou fechar custo total.
Login correto e localização do Redis concluídos; não pedir novamente nem
solicitar abertura de Personal. Não criar banco ou contratar serviço por
inferência. Não abrir credenciais, conteúdo de bancos ou dados de trades.
Não repetir o inventário concluído do Render sem mudança relevante.

### Qualificação documental do recurso localizado

Consulta pública de 11/09/2026, sem testar o banco real:

- Upstash documenta persistência habilitada, com armazenamento em memória e
  disco. Portanto não é correto rejeitá-lo genericamente como cache volátil.
  [Durabilidade](https://upstash.com/docs/redis/features/durability).
- A documentação descreve replicação assíncrona e consistência eventual;
  consistência causal por conexão não demonstra consumo global linearizável
  sob concorrência, failover e partição. Essa lacuna impede qualificar, com a
  evidência atual, esse recurso como referência única de consumo C3.
  [Consistência](https://upstash.com/docs/redis/features/consistency).
- ACL por comando/chave é documentada para bancos pagos; isso não comprova
  configuração efetiva, identidade de emissão, segregação administrativa ou
  custódia de assinatura para o C3. Não foram consultadas ACLs ou credenciais.
  [Segurança](https://upstash.com/docs/redis/features/security).
- Backup/restore é documentado, mas restaurabilidade não comprova atualidade
  após rollback. Nenhum backup real foi aberto ou executado.
  [Backup](https://upstash.com/docs/redis/features/backup).

Decisão limitada: preservar o Redis existente e não promovê-lo a autoridade
C3, nem conectá-lo ao harness. A persistência existente elimina a hipótese de
que não há Redis, mas não fecha autenticação/consumo único/recuperação do contrato.
Não é uma declaração de impossibilidade de qualquer arquitetura com Upstash.
Próximo trabalho seguro: comparar documentalmente as alternativas restantes
para identidade e consumo independente com os contratos já existentes e o
envelope histórico de US$ 30 adicionais, sem escolher contratação por inferência.
Não condicionar essa análise pública/offline a novo OK ou novo login AWS.

Este relatório, a continuidade local e o apontamento da proposta foram alterados. Não houve mudança
de código nem execução de testes; os 267 testes anteriores não foram repetidos.
Houve navegação externa autorizada para metadados (Render, Upstash e tentativa
AWS) e consulta à documentação pública Upstash, não chamadas externas de testes.
Nenhum secret, dado de trade/Registry,
shell remoto, ordem, alteração de configuração, recurso novo, restauração,
commit, push ou deploy foi acessado/executado por esta etapa.

Percentual restante para Live: indeterminado; inventário parcial não equivale a
readiness operacional. Modelo/esforço recomendado: GPT-6 Astra — Alto.
