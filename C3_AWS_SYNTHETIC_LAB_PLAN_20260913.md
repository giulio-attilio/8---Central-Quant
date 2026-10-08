# C3 — laboratório AWS sintético: preparação delimitada

## Atualização — acesso SSM bloqueado pela revisão automática após “siga”

Usuário respondeu “siga” ao próximo passo descrito de acessar a máquina sintética
e validar os arquivos. A tentativa foi limitada a esse acesso/transporte,
sem instalação, extração, testes ou produção. Console EC2, instância exata
i-0d6e54808e7688acf: Executando, 3/3 verificações aprovadas. Opção SSM:
ping On-line, conexão Conectado, agente 3.3.4624.0, papel dedicado correto,
sem fallback do perfil padrão Systems Manager. Isso é disponibilidade do
agente, NÃO prova de sessão interativa iniciada.

Clique Conectar SSM foi REJEITADO pela revisão automática: exige autorização
explícita de iniciar a sessão, diante da restrição anterior de não abrir SSM.
Não repetir, contornar via URL/CloudShell/CLI/SSH ou interpretar esta tentativa
como sessão criada. Nenhuma sessão, comando remoto, transferência, instalação,
extração ou teste foi executado nesta rodada. Nenhuma porta/chave/IAM alterada.

Próxima ação humana específica: autorizar iniciar sessão SSM exclusivamente na
instância acima, baixar os cinco arquivos sintéticos já aprovados do bucket
dedicado e verificar seus tamanhos/SHA-256, sem extrair, instalar, executar
testes, acessar secrets ou produção. Permissão usa apenas perfil já associado;
não amplia IAM, não cria serviços e não estende custos/prazos. O acesso permitiria
comandos na máquina descartável; comandos devem permanecer no escopo autorizado.
Até resposta específica, não reabrir ou repetir pergunta/checagens de conexão.

Automatismo existente continua ACTIVE para prazos e limpeza já autorizados,
sem OK para monitorar. Manter Stop14/09 06:17 BRT, Terminate14/09 22:32 BRT,
S3/grant até14/09 21:40 BRT (alerta20:40). Não desligar ou recriar antecipadamente
apenas para testar, não mexer no Scheduler. A aba de conexão21 foi preservada;
a aba20 contém a instância. Não há necessidade de novo login neste momento.

Somente leitura do console, tentativa bloqueada e atualização destes registros;
nenhum secret/Registry/Render/Redis/BingX/flag/ordem/Live/commit/push/deploy.
Computer Use permitiu verificar disponibilidade; auto-review impediu a sessão.
Validação dos cinco pacotes no alvo: 0/5 concluídos (100% ainda por validar).
Percentual restante da tarefa toda/Live permanece indeterminado.

## Atualização 13/09, 22h43 BRT — uma VM lançada e dois desligamentos externos habilitados

ESTADO ATUAL: substitui as pendências históricas de autorização abaixo. Usuário
respondeu Sim à autorização específica de UMA VM, associação do perfil preparado
e duas agendas externas com IAM restrita. Lançamento acionado uma única vez;
não repetir. Nenhum teste, download, instalação ou sessão SSM foi iniciado.

Instância i-0d6e54808e7688acf, nome cq-c3-synthetic-lab-20260914, conta
899845009758, Oregon/us-west-2. Console confirma Executando e LaunchTime
2026-09-14T01:32:12Z = 13/09/2026 22:32:12 BRT. Perfil associado:
CentralQuantC3SyntheticLabSessionRole20260913 (SSM + GetObject temporário já
autorizados). Mantidos AMI ami-03db3415e6524c5d2, m7i-flex.large, subnet
subnet-0dca4e8b2fd42863e, SG sg-0ba02a0767de13c2a, grupo precision-time
pg-024d2d501239d7143, IMDSv2/hop1, sem SSH/userdata/produção.
Discos relidos no console: vol-02e0a96a26f3bc378, /dev/xvda, 20 GiB;
vol-023a06fce4b3c69f4, /dev/sdb, 10 GiB; ambos associados, não criptografados
conforme prévia sintética aprovada e Excluir no encerramento=Sim.

Grupo Scheduler criado: cq-c3-synthetic-lab-20260914-shutdown.
ARN arn:aws:scheduler:us-west-2:899845009758:schedule-group/cq-c3-synthetic-lab-20260914-shutdown.
Papel criado: CentralQuantC3SyntheticLabShutdownRole20260914, ARN
arn:aws:iam::899845009758:role/CentralQuantC3SyntheticLabShutdownRole20260914.
Trust persistida relida: somente scheduler.amazonaws.com, sts:AssumeRole,
StringEquals aws:SourceAccount=899845009758 e ArnEquals aws:SourceArn=ARN
do grupo acima. Política única StopTerminateOnlyI0d6e54808e7688acf relida:
somente ec2:StopInstances e ec2:TerminateInstances, Resource exatamente
arn:aws:ec2:us-west-2:899845009758:instance/i-0d6e54808e7688acf.
Sem permissões para qualquer outra máquina, sem novas chaves ou credenciais.

Duas agendas únicas criadas e estado salvo Habilitado conferido:
- cq-c3-lab-i0d6e54808e7688acf-stop: 2026-09-14 09:17 UTC,
  14/09 06:17 BRT; destino universal EC2 StopInstances.
- cq-c3-lab-i0d6e54808e7688acf-terminate: 2026-09-15 01:32 UTC,
  14/09 22:32 BRT; destino universal EC2 TerminateInstances.
ARNs: arn:aws:scheduler:us-west-2:899845009758:schedule/
cq-c3-synthetic-lab-20260914-shutdown/<nome da agenda>, sem quebra no ARN real.
Ambas: input {"InstanceIds":["i-0d6e54808e7688acf"]}, mesmo papel restrito,
fuso UTC, janela flexível OFF (revisão), retenção 5 minutos, no máximo 1 retry
(destino, papel e política persistidos relidos), sem DLQ/KMS personalizada;
ActionAfterCompletion NONE. Horários arredondados para o minuto anterior.
Agendas configuradas NÃO provam entrega nem estado físico futuro. Não executar
Stop/Terminate agora apenas para testar. Verificar o estado físico nos prazos.

Próxima etapa técnica ainda NÃO autorizada por este Sim: sessão SSM, transporte,
validação/extração/instalação ou testes no alvo. Não inferir autorização dessas
ações do lançamento. Monitoramento e desligamentos já autorizados não aguardam
OK. Exportação prevista, se houver ensaios futuramente autorizados, até
14/09 06:02 BRT (T0+7h30 arredondado); sem estender 8h compute/24h discos.
Verba US$5 é planejamento, não teto automático. Supervisão humana Giulio.
Se agenda falhar, tratar como evento material, verificar instância exata e
realizar failsafe previamente autorizado, sem tocar outras máquinas/produção.

S3/grant continuam com prazo independente: remover concessão ao concluir
transporte; excluir somente cinco objetos sintéticos e partes próprias e bucket
dedicado vazio até 14/09 21:40 BRT; alerta às 20:40 se pendente. Expiração não
remove dados/política. Preservar originais locais. Não repetir upload/grant.
Automatismo existente atualizado e relido ACTIVE às 22h46 BRT, a cada minuto,
com ID/T0/agendas reais e vínculo à mesma conversa (sem duplicação),
sem aguardar autorização antiga de lançamento ou criar recursos duplicados.
Antes de prazos/novidade acionável, silêncio, sem refazer inventários ou testes.

Verificação desta rodada: console AWS, leitura de configuração persistida e
dois registros locais. Sem testes de software ou entrega física de Scheduler.
Computer Use guiou as ações autorizadas; OpenAI Docs guiou atualização do
automatismo existente. Nenhum secret acessado, nenhum Registry/Render/Redis/
BingX/ordem/Live/flag/commit/push/deploy; houve chamadas e alterações AWS
explicitamente autorizadas, portanto NÃO alegar ausência de chamadas externas.
Restante da etapa de provisionamento/agendas: 0%. Total da tarefa/Live:
indeterminado; infraestrutura não homologa relógio físico, C3 ou trading.

## Atualização 13/09, 22h27 BRT — precision-time criado e selecionado na prévia

Após Sim específico, criado uma única vez o grupo vazio
cq-c3-synthetic-lab-20260914-precision-time, pg-024d2d501239d7143, Oregon.
Toast de sucesso e linha com estratégia precision-time/estado available relidos.
ARN arn:aws:ec2:us-west-2:899845009758:placement-group/cq-c3-synthetic-lab-20260914-precision-time.
Aba17 preservada como resultado. Grupo selecionado SOMENTE no rascunho da aba16;
prévia22h25BRT confirma GroupId correto e Tenancy=default, parâmetros anteriores
preservados. Nenhuma VM criada, associação IAM efetivada ou Scheduler acionado.
Capacidade de lançamento e relógio físico ainda não comprovados. Não recriar.

Próxima ação requer autorização específica de UMA VM com perfil dedicado
(SSM+leitura temporária dos cinco objetos) e agendas externas Stop/Terminate,
permissão limitada ao único ID/ARN real após lançamento, sem testes/instalações,
produção ou Live nesta etapa. Limites e supervisão já descritos permanecem:
US$5 de verba sem teto técnico,8hcompute/24hdiscos;exportar7h30/stop7h45/término24h;
abortar encerrando sem testes caso agendas não possam ser imediatamente
estabelecidas e verificadas. Nenhum ID/T0 fictício, extensão ou nova credencial.
Até decisão específica, automatismoACTIVE mas provisionamento aguardando.
Limpeza S3/grant14/09,21h40BRT e alerta20h40 não dependem dessa decisão.
Falta0% desta criação/seleção; percentual integral/Live indeterminado.

## Atualização 13/09, 22h20 BRT — formulário precision-time disponível

Aba17/browser1, EC2#CreatePlacementGroup: em Oregon. Nome preenchido e relido:
cq-c3-synthetic-lab-20260914-precision-time. Estratégia selecionada e relida:
Tempo de precisão. Nenhuma tag. Criar grupo NÃO acionado; nenhum grupo/VM/ID/T0
criado. Lista inicial sem grupos, coerente com seletor vazio do rascunho EC2.
Não há bloqueio de interface para escolher a estratégia; capacidade/permissão
efetiva e PHC continuam não comprovados. Aba16 da VM preservada sem reload.

Preparação terminou. Próxima decisão específica: criar somente esse grupo vazio,
sem lançar VM, associar IAM, Scheduler, chaves ou produção. Até essa decisão,
não executar criação nem repetir preparações. Automatismo segue ACTIVE para
continuar após autorização e acompanhar prazo de limpeza S3, mas provisionamento
fica aguardando essa decisão. Nenhum OK genérico substitui a definição de escopo.
Percentual total/Live indeterminado; 0% restante apenas deste formulário.

## Atualização 13/09, 22h14 BRT — rascunho EC2 conferido, NÃO lançado

Formulário preservado na aba16 do navegador1, nome cq-c3-synthetic-lab-20260914.
A prévia Console-to-Code foi lida, não copiada para execução nem enviada ao
CloudShell. Os valores abaixo estão SOMENTE no rascunho; não existem VM/ID/T0.

| Campo | Valor conferido na prévia |
| --- | --- |
| Região / quantidade / tipo | us-west-2 / 1 / m7i-flex.large, 2vCPU,8GiB |
| AMI | ami-03db3415e6524c5d2, AL2023 2023.12.20260909.0 x86_64 kernel-6.18 |
| Rede | subnet-0dca4e8b2fd42863e na vpc-04529e0bd992e2882; IPv4 temporário; somente sg-0ba02a0767de13c2a |
| Raiz | /dev/xvda,20GiB,gp3,3000IOPS,125MiB/s,DeleteOnTermination=true |
| Scratch | /dev/sdb,10GiB,gp3,3000IOPS,125MiB/s,DeleteOnTermination=true,sem snapshot |
| Acesso | Sem par de chaves; perfil CentralQuantC3SyntheticLabSessionRole20260913 selecionado APENAS na prévia |
| IMDS | HttpTokens=required,HttpPutResponseHopLimit=1,HttpEndpoint=enabled para administração; ensaios continuam sem rede/IMDS |
| Compra / encerramento | On-Demand,tenancy=default,sem reserva,monitoramento detalhado off,AutoRecovery=disabled,proteções API de stop/terminate off |

Ambos volumes permanecem com Encrypted=false, padrão observado, para dados
exclusivamente sintéticos. Nenhuma chave KMS foi criada/selecionada. Isso não
seria aceitável por inferência para segredos ou dados reais. Dados de usuário
vazios; nenhuma instalação, snapshot novo, teste ou transferência ao alvo.

PENDÊNCIA CONCRETA: seletor Grupo de posicionamento contém apenas Selecionar;
a prévia não contém grupo precision-time. Não declarar rascunho pronto para
lançar/PHC qualificado. Próximo passo é preparar o grupo precision-time previsto
no plano em Oregon e verificar o caminho suportado no console, sem criar
recursos nesta preparação, lançar VM, modificar IAM ou acionar Scheduler.
Não repetir inventários, AMI/preços, pacotes ou testes concluídos. A associação
efetiva do perfil à futura VM permanece ação distinta da concessão já aplicada.

Procedimento externo existente revisado, sem criar agendas: T0=lançamento;
exportar até+7h30; StopInstances+7h45; TerminateInstances+24h. Após ID/T0 reais,
conferir ambas agendas, ARN exato, trust SourceAccount+ARN do GRUPO e volumes
antes de qualquer ensaio; se não estabelecidos imediatamente, encerrar sem
testar. Giulio supervisiona. Limpeza S3/grant até14/09,21h40 BRT, alerta20h40,
inclusive sem VM; expiração de leitura não exclui dados. Sem extensão automática.

Verificação: valores visíveis do formulário e prévia, não execução AWS.
Preparação parcial concluída; percentual total/Live indeterminado. Nenhum
secret acessado, commit/push/deploy ou mudança de trading; acessos externos
somente console AWS e documentação oficial OpenAI para atualizar continuidade.

## Atualização 13/09, 21h57 BRT — concessão aplicada

C3SyntheticTransferReadUntil20260915 criada após confirmação específica e
relida no console da role CentralQuantC3SyntheticLabSessionRole20260913:
apenas GetObject nos cinco objetos exatos, HTTPS obrigatório e expiração
2026-09-15T00:40:00Z (14/09,21h40 BRT). Política SSM existente preservada.
O rascunho/pausa IAM descritos abaixo foram superados por esta conclusão.
Nenhuma VM criada, nenhum teste/download no alvo, nenhuma ativação Live.
Próxima preparação sem OK: rascunho final EC2 e encerramento conforme plano,
sem lançamento/associação/Scheduler nesta preparação. Não refazer pesquisas
ou etapas já concluídas. Limpeza do bucket/grant continua pendente dentro
do prazo: expiração de leitura não remove os dados. Detalhes na continuidade.
Falta0% desta concessão; tarefa inteira/Live: percentual indeterminado.

## Execução autorizada do transporte — 13/09 à noite

Bucket cq-c3-synthetic-transfer-20260914-899845009758 criado privado em Oregon;
SSE-S3, ACLs off, Block Public Access integral, versionamento/Object Lock off.
Regra Deny de tráfego sem HTTPS aplicada e conferida. Cinco arquivos da tabela
abaixo enviados com sucesso pelo console, zero falhas. Tamanhos e SHA-256 locais
revalidados antes do envio; NÃO houve download/extração/execução no alvo.

Limpeza conservadora até2026-09-15T00:40:00Z (14/09,21h40 BRT), inclusive se VM
não for criada. Preservar originais locais. ReservaUS$0,10 dentroUS$5 mantida.
Permissão IAM C3SyntheticTransferReadUntil20260915 está apenas no formulário de
revisão: s3:GetObject nos cinco objetos exatos, HTTPS e expiração no prazo acima;
semListBucket/escrita/exclusão. Antes do clique de aplicação, confirmar acesso
específico conforme política do navegador. Uma política SSM preexistente intacta.
Detalhes e estado das abas no topo da continuidade; autorização geral S3 recebida,
não repetir essa pergunta. Nenhuma VM lançada, credencial criada ou Live ativado.
Falta0% do upload; tarefa inteira/Live ainda indeterminado.

## Proposta de transporte — 13/09 à noite, somente documentação

Proposta concluída, NÃO executada: um bucket temporário privado S3 Standard em
us-west-2 (Oregon), somente para os cinco arquivos sintéticos abaixo. É uma
exceção nova ao escopo sem serviços extras; exige decisão específica antes de
criação, upload ou concessão de acesso. Não libera lançamento de VM nem Live.

### Seleção fechada

Arquivos existentes sob .offline_releases/aws_synthetic_lab_20260913/artifacts;
os hashes são os recibos locais já verificados, não uma nova execução dos ensaios.
Não enviar pastas completas, Registry, ambiente, credenciais ou arquivos extras.

| Arquivo / caminho relativo | Bytes | SHA-256 |
| --- | ---: | --- |
| c3-synthetic-sources.zip | 3377178 | e49417a67251cf392dae5123ff2680f8eb03b35cdf39b4965844ddfe9a89bd57 |
| c3-synthetic-lab-tools-v1.zip | 19341 | 1852eb3e361fd27782b39fcc9609f43433019663f2d6acd90e0029e1706c095f |
| runtime_transport_JlNaF4/python3119-synthetic-runtime.tar.gz | 31214549 | 43ef05139536620793d481caee36bb48e7749687da45f40389be041af69c1840 |
| clock_source_transport_qr10adoo/clockbound203-pinned-sources.tar.gz | 35919342 | 930d9ea0ad970b6c673be42fe45fbb97d0d4cc5e2e4169fc31f97afc859108a1 |
| c3-synthetic-process-probes-v1.zip | 8449 | 8d570275d66319c9e9147e00397e0baffdde97be9e62c34b2b2b5427dc8f1cae |

Total: 70.538.859 bytes, aproximadamente 70,54 MB. Usar as cinco basenames como
chaves de objetos, sem sobrescrever objetos existentes; bucket dedicado vazio.
Nome global e ARNs só serão determinados e conferidos após autorização.

### Fluxo e acesso mínimo propostos

1. Criar bucket dedicado somente após aprovação: Standard, Oregon, Block Public
   Access integral, Object Ownership Bucket owner enforced (ACLs desativadas),
   SSE-S3. Sem KMS, versionamento, Object Lock, replicação, aceleração, website,
   notificações ou serviços adicionais. Exigir transporte TLS na política.
2. Fazer upload dos cinco arquivos selecionados pelo console autenticado, sem
   publicar fontes ou criar links pré-assinados. A documentação admite upload
   de arquivos locais pelo console; a capacidade prática desta sessão ainda
   será verificada, sem prometer envio automático antes disso.
3. Conceder temporariamente à role de sessão já dedicada apenas s3:GetObject
   nos cinco ARNs exatos. Sem s3:ListBucket, escrita, exclusão ou S3FullAccess
   para a VM. Não modificar as roles signer. Acesso administrativo de criação,
   configuração, upload e limpeza fica separado; não ampliar identidade humana
   por suposição. Confirmar as alterações de acesso no momento aplicável.
4. Quando existir alvo aprovado, baixar por requisições AWS autenticadas sob a
   role da instância, com credenciais temporárias gerenciadas pelo mecanismo
   AWS, sem ler, imprimir ou copiar seus valores. É preparação administrativa,
   não permissão de rede/IMDS para os ensaios. Conferir tamanho e SHA-256 dos
   cinco arquivos ANTES de qualquer extração. Divergência: abortar; não executar.
5. Remover a concessão GetObject ao concluir o transporte; excluir somente os
   cinco objetos identificados e depois o bucket dedicado vazio. Preservar
   originais locais e evidências. Limpeza pelo supervisor após cópia verificada,
   no máximo 24h após criação, inclusive se a VM não for lançada. Se houver
   upload multipart incompleto, abortar somente as partes desse envio; não
   declarar limpeza concluída sem conferir ausência de objetos/partes e bucket.

Sem SSH, regras inbound, NAT, endpoints, CloudShell, secrets ou servidor novo.
Não transportar por milhares de comandos codificados. Esta proposta não altera
os requisitos separados de encerramento da VM, isolamento, daemon/fonte física
ou qualificação em Amazon Linux. Hash correto não comprova que o código é seguro.

Base oficial: [upload pelo console e SSE-S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/upload-objects.html)
e [práticas de segurança S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html).

### Custo delimitado, não garantia de cobrança máxima

Consulta pública regional em 14/09 UTC (13/09 local), effectiveDate 2026-08-01:
Standard primeira faixa US$0,023/GB-mês; PUT/COPY/POST/LIST US$0,005/1.000;
GET/demais US$0,0004/1.000. Fonte: [catálogo oficial Oregon](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonS3/current/us-west-2/index.json).
Para estimar conservadoramente 0,1 GB por 24h, 1.000 solicitações de cada faixa:
0,1 × 0,023 / 30 + 0,005 + 0,0004 = aproximadamente US$0,00548, antes de impostos.
Não contar créditos ou Free Tier como economia garantida. A [tabela S3](https://aws.amazon.com/s3/pricing/)
isenta entrada pela internet e saída do S3 para serviços AWS na mesma região;
a proposta não contempla download externo ou tráfego entre regiões.

Reservar US$0,10 DENTRO dos US$5 já delimitados do laboratório, sem aumentar a
verba total. É reserva de planejamento, não hard cap técnico: retenção maior,
retries, tráfego ou operação indevida podem elevar custos. Não usar lifecycle
como promessa de exclusão no segundo exato de 24h. Não criar serviço se houver
necessidade de upgrade da conta, aumento de verba ou permissão mais ampla sem
nova decisão específica. Render, Redis e ChatGPT não são substituídos por S3.

### Decisão necessária e próximo passo

Autorizar especificamente este bucket privado temporário, os cinco uploads,
GetObject temporário restrito e limpeza descrita, com reserva US$0,10 dentro
dos US$5. Sem isso, o transporte permanece não autorizado. Nenhum recurso foi
criado, nenhuma conta acessada, nenhum pacote enviado ou teste repetido nesta
pesquisa; somente fontes públicas foram consultadas e dois documentos locais
atualizados. Automatismo deve aguardar a decisão sem repetir pesquisas ou
emitir pedidos de OK. Proposta concluída: falta 0%; tarefa inteira/Live:
percentual indeterminado, pois execução física e gates operacionais não estão
comprovados. Não converter preparação documental em avanço de readiness.

## Atualização 13/09 — lacuna de portabilidade dos probes encerrada localmente

Os dois probes agora encaminham --lab-parent ao criador compartilhado validado;
17testes locais passaram, incluindo3novos testes AST dos dois caminhos e budgets.
Complemento de fontes c3-synthetic-process-probes-v1.zip foi criado separado,
sem substituir V1 ou os quatro insumos anteriores; recibo e detalhes na continuidade.
Probes não foram executados fisicamente nesta correção. As linhas históricas
da revisão abaixo sobre essa lacuna estão superadas por esta atualização.
Canal autenticado de envio, estado/isolamento no alvo, fonte física e ações de
encerramento continuam pendentes; nenhum lançamento,upload ou instalação realizado.

## Revisão final pré-lançamento — 13/09, sem execução

Resultado: preparação local dos quatro pacotes concluída, mas a execução da
fase física completa NÃO está pronta. Revisão de código/documentação somente,
sem importar launchers, executar testes/processos operacionais ou acessar AWS.

| Momento | Condição / evidência | Estado e ação |
| --- | --- | --- |
| Antes de lançar | Verba, tipo/região, supervisor e limites | Aprovados no escopo já registrado; não pedir OK genérico novamente |
| Antes de lançar | Insumos locais pinados | Quatro pacotes conferidos; não equivale a transporte ou execução |
| Antes de lançar | Probes de processos/timeout portáveis | Lacuna concreta: physical_process_probe.py e timeout_tree_probe.py ainda usam mkdtemp em /var/tmp e não aceitam --lab-parent; guard ext4 reprovaria scratch na raiz XFS prevista |
| Antes de lançar | Cobertura do pacote de ferramentas | V1 contém só regressão e inspect/build; exclui deliberadamente os probes físicos e valid/markers. Não executar uma fase que não está no pacote |
| Antes de enviar arquivos | Canal autenticado de transporte dos quatro pacotes | Ainda não definido/testado. Não publicar fontes, criar armazenamento externo, abrir SSH/inbound ou acrescentar permissões por suposição |
| Antes de lançar | Configuração final e procedimento externo de encerramento | Rede/IAM dedicados criados; VM/associação/role Scheduler/agendas ainda não criadas. Rever rascunho e obter confirmações sensíveis específicas quando exigidas |
| Imediatamente após ID/T0 | Agendas Stop/Terminate, ARN exato, volumes e DeleteOnTermination | Só então existem identidades concretas. Configurar/validar antes de ensaios; falha exige encerramento sem teste, não inventar IDs antes |
| Antes de ensaios | SSM, RPMs/loader/Python, ext4, conta e isolamento | Prova depende do alvo; resolver transação de pacotes sem aceite antes de instalar. Não alegar que AMI candidata já comprovou esses fatos |
| Antes de medir relógio físico | ENA/PHC/VMClock, daemon e erro completo | Não qualificados. Build FFI/simulações não fornecem fonte física. Receita atual explicitamente não instala daemon |
| Ao encerrar | Exportação, stop, término e remoção de volumes | T0+7h30 / +7h45 / +24h; sem reinício/extensão ou dependência exclusiva do agente |

A lacuna dos dois probes foi confirmada pela leitura integral dos arquivos:
ambos reutilizam o guard de isolamento, mas criam diretório diretamente em
/var/tmp. A correção mínima seguinte é reutilizar runner.create_lab(lab_parent)
e expor --lab-parent, preservando comandos, permissões, limites e semântica dos
ensaios. Testes locais sintéticos/estáticos suficientes para essa mudança de
encaminhamento; não repetir ensaios físicos completos sem necessidade.

Sem alteração de código nesta revisão. Próxima etapa offline já autorizada:
corrigir somente essa portabilidade e verificar com testes seguros. Depois
conferir seleção de complemento de transporte dos probes; preservar os quatro
pacotes e evidências existentes, não substituir silenciosamente o V1.
Canal de envio e fonte temporal seguem pendências explícitas, não autorizações
para criar serviços ou aumentar acesso. Não há motivo técnico para repetir
inventário de rede/IAM ou reconstruir os pacotes atuais.

Percentuais: falta0% da revisão delimitada e da embalagem dos quatro insumos;
o restante da tarefa inteira até Live permanece indeterminado. Não converter
contagem de linhas desta checklist em porcentagem de tempo ou trabalho total.

## Atualização 13/09 — insumos locais embalados; não é liberação de lançamento

Os quatro insumos delimitados estão em .offline_releases/aws_synthetic_lab_20260913/artifacts:
fontes pinadas, complemento de ferramentas/runner, runtime Python e aquisição
ClockBound upstream/vendor. Recibos respectivos e continuidade registram hashes,
conteúdo e limites. Nenhum pacote foi enviado à AWS; não houve instalação,
extração no alvo, build nativo, execução física ou criação de VM.

Próxima revisão precisa distinguir três momentos, sem mudar os limites do plano:
1. Antes do lançamento: receita, seleção/configuração candidata, acesso mínimo,
   autorização específica aplicável, supervisor humano e procedimento de aborto.
2. Imediatamente após ID/T0: bindings das duas agendas ao ARN exato, confirmação
   de volumes sintéticos e eliminação ao término; abortar se não estabelecidos.
3. Antes dos ensaios: acesso comprovado, versões/isolamento no alvo, scratch
   verificado, dependências/build nativo e dispositivos físicos identificados.

O procedimento de encerramento abaixo já diferencia lançamento de início dos
testes. Não inventar evidência de VM inexistente ou flexibilizar checks para
declarar readiness. Esta atualização é somente registro do pacote concluído e
da revisão seguinte, não autoriza execução, associação ou instalação.

## Atualização 13/09 — receita consolidada e scratch do build corrigido

Leitura integral CLOCK_DEPENDENCIES, run_regression.py, prepare_sources.py,
test_clock_real.py, run.py congelado e helper de isolamento identificou lacuna:
build ClockBound ainda criava scratch em /var/tmp (raiz XFS no alvo), causando
recusa pelo guard ext4. Corrigido exclusivamente test_clock_real.py para
--lab-parent e runner.create_lab compartilhado. Sem afrouxar guards/mounts.
test_clock_real_validation.py recebeu2testes AST do wiring;13/13 passaram.
14/14 testes do launcher compartilhado passaram; total27, sem rede/subprocessos
reais. Não houve build nativo, ensaio físico ou repetição das101regressões.

Receita de11passos consolidada no topo CLOCK_DEPENDENCIES: release fixada,
transação RPM a conferir sem aceite, volumes por identidade, runtime3.11.9,
conta/sandbox, transporte separado, buildfrozenoffline, evidência/encerramento.
Dois limites adicionais explícitos: ZIP fonte não contém run.py; modos
valid/markers ainda são WSL específicos e não podem consumir automaticamente
novo build AWS. Nenhuma alteração ao candidato/coletor/produção.

Arquivos alterados: .offline_releases/aws_synthetic_lab_20260913/
test_clock_real.py, test_clock_real_validation.py, CLOCK_DEPENDENCIES.md;
este registro e C3_AWS_SYNTHETIC_LAB_PLAN_20260913.md.
Receita preparada NÃO significa runtime ou fonte homologados; RPMs exatos
e pacote/runtime completo seguem sem qualificação. Próxima ação segura:
conferir insumos locais a transportar, principalmente árvore Python completa/
contenção de symlinks e run.py ausente do ZIP, sem copiar amplo diretório,
upload, instalação ou nova camada. AutomatismoACTIVE, semnecessidade deOK.
Rede e IAM já criados não serão repetidos. NenhumaVM/T0, produção/secret/flag/
ordem/commit/push/deploy. Externo somente documentação pública AWS.
Liveindeterminado; GPT-6Astra—Alto recomendado semalegartroca.

## Atualização 13/09 — rede sintética CRIADA e conferida

Usuário respondeu Sim ao pedido específico de criar rede e SG sem inbound,
com saída HTTPS para qualquer destino. Rascunho reobservado, Criar VPC
acionado uma vez; console confirmou Êxito. Recursos retornados:
- VPC vpc-04529e0bd992e2882, cq-c3-synthetic-lab-20260913-vpc.
- Subnet subnet-0dca4e8b2fd42863e, public1-us-west-2a, proposta 10.203.0.0/28
  dentro da VPC 10.203.0.0/24; parâmetros confirmados antes do submit.
- Internet gateway igw-08015cce9e188f28c.
- Tabela rtb-06eb626bd7e85f60b, cq-c3-synthetic-lab-20260913-rtb-public.
  Associação explícita à subnet acima confirmada. Duas rotas salvas ATIVAS:
  10.203.0.0/24 local; 0.0.0.0/0 para o IGW acima. Sem propagação.
- SG sg-0ba02a0767de13c2a, cq-c3-synthetic-lab-20260913-ssm, vinculado
  à VPC nova. Sucesso confirmado, ZERO regras inbound e UMA outbound.
  Regra salva sgr-06fcd20790d54ce88: IPv4 HTTPS TCP443 para 0.0.0.0/0.
  All-traffic do rascunho substituído por HTTPS ANTES da criação.

Não foi criada VM, associação de instância, NAT, endpoint, IP reservado,
Scheduler ou peering. Rede default existente e identidades IAM preservadas.
Recursos implícitos default da NOVA VPC não foram associados a VM nem
substituem o SG restrito. Não houve acesso ao Render/produção/secrets.
Saída HTTPS não é allowlist SSM nem isolamento de destinos; usuário foi
informado e confirmou. Nenhum ensaio físico ou conectividade SSM comprovados.
Console exibiu cache antigo das tabelas; um Atualizar resolveu e mostrou
o recurso correto. Não recriar por cache vazio. Aba10/browser1 em Rotas.

Próxima ação segura AGENDADA sem novo OK: concluir a receita delimitada de
preparação AL2023 do laboratório, usando CLOCK_DEPENDENCIES e executores já
existentes. Ler integralmente os arquivos relevantes antes de editar.
Fixar ordem de instalação/build nativo e verificações de compatibilidade/
isolamento, distinguindo parâmetros já comprovados dos verificados no alvo.
Se necessário, editar somente executor/receita separados e testes sintéticos
com rede/execução operacional previamente bloqueadas. Não criar nova camada
de produção nem repetir matrizes/builds/testes concluídos. Não instalar,
lançar VM, associar IAM/SG ou criar Scheduler nesta preparação. Nenhum ID/T0
de instância existe; não inventar encerramento vinculado. Preparar não homologa
o alvo. Depois chegar à próxima ação sensível com escopo/risco específico.

Automatismo ACTIVE; não está aguardando aprovação da rede, que foi concluída.
Computer Use orientou confirmação/checagem; OpenAI Docs orientou atualização
da continuação. Só este plano e a continuidade local atualizados, sem código
alterado/testes executados nesta rodada. Acesso externo ocorreu no console AWS
e documentação pública; nenhum secret/dado real, ordem, flag, Render,
commit/push/deploy. Percentual Live indeterminado; GPT-6 Astra — Alto recomendado.

## Atualização 13/09 — rascunho de rede dedicado preparado, NÃO criado

Heartbeat executou a preparação no console AWS Oregon, aba10/browser1.
A habilidade Computer Use orientou a conferência visual e a parada antes da
mutação sensível. Nenhum botão final Criar VPC foi acionado.

Parâmetros conferidos no assistente VPC e muito mais:
- Prefixo cq-c3-synthetic-lab-20260913; VPC 10.203.0.0/24.
- Uma AZ us-west-2a, uma sub-rede pública 10.203.0.0/28, zero privadas.
- Prévia: uma tabela cq-c3-synthetic-lab-20260913-rtb-public e um
  internet gateway cq-c3-synthetic-lab-20260913-igw.
- Zero NAT, zero endpoints (inclusive S3 desmarcado), sem IPv6.
- DNS hostnames/resolução habilitados, tenancy padrão; controle adicional
  pago de criptografia VPC Nenhuma. Nada contratado ou provisionado.
- Rota pretendida local 10.203.0.0/24 e 0.0.0.0/0 para o IGW novo;
  conferir os IDs/rotas efetivamente criados antes de qualquer associação.
  Recursos implícitos default da NOVA VPC não são o grupo dedicado da VM.

SG dedicado proposto, ainda SEM formulário pois a VPC não existe:
cq-c3-synthetic-lab-20260913-ssm, zero inbound, saída somente TCP443
para 0.0.0.0/0; remover saída all-traffic do grupo novo antes de associação.
Não usar/modificar SG ou VPC default existentes. Sem peering, VPN ou rotas
privadas à Central. Não associar nenhuma instância nesta fase.

Limitação material explicitada para decisão: TCP443/0.0.0.0/0 restringe
porta/protocolo, NÃO destinos a SSM. SG aceita IP/CIDR/prefix list/SG, não
allowlist de hostname. Não alegar isolamento absoluto da Internet nem
bloqueio DNS pelo SG. Preparação administrativa exige essa saída candidata;
testes continuam isolados sem rede/IMDS/credenciais. A aprovação pendente
deve incluir expressamente essa saída HTTPS, sem fingir que é endpoint-only.
Se não aceita, não ampliar automaticamente para firewall/endpoints pagos.
Fontes: [regras SG](https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html)
e [conectividade SSM](https://docs.aws.amazon.com/en_en/systems-manager/latest/userguide/troubleshooting-ssm-agent.html).

Pedido específico: criar somente essa rede dedicada e SG descrito, preservando
rede/IAM existentes, sem VM, associação, IP reservado, Scheduler, produção ou Live.
Automatismo ACTIVE; provisionamento aguarda essa decisão, não OK genérico.
Sem resposta/evidência nova: silêncio, não refazer formulário ou inventários.
Após aprovação, reobservar e criar SOMENTE o escopo confirmado; conferir
recursos reais antes de avançar. Launcher/recipe/encerramento continuam pendentes.

Problema de seletor Playwright sem matches resolvido pela API AX documentada;
seleção de uma AZ confirmada por teclado e pela prévia com uma única sub-rede.
Console-to-Code somente aberto/fechado, sem executar/copiar código.
Nenhum código/teste alterado ou teste executado. Só dois registros locais
atualizados; consultas externas ao console/documentação AWS ocorreram.
Nenhum secret, dado real, Render, flag, ordem, commit, push ou deploy.
Percentual Live indeterminado; GPT-6 Astra — Alto recomendado, não trocado.

## Atualização 13/09 — perfil IAM sintético CRIADO e conferido

O usuário respondeu "siga" ao pedido específico de criação pendente. O rascunho
foi reobservado e as cinco ações conferidas antes de clicar Criar perfil.
Console confirmou êxito e listagem passou de 7 para 8 funções.
Detalhes mostram role e instance-profile CentralQuantC3SyntheticLabSessionRole20260913,
criação em 13/09/2026 20:24 (UTC-03:00), duração máxima de sessão de 1 hora.
Uma única política INLINE: CentralQuantC3SyntheticLabSessionRole20260913Policy.
JSON persistido conferido: Sid SyntheticLabSessionChannelsOnly, Allow,
Resource "*", exatamente ssm:UpdateInstanceInformation e
ssmmessages:CreateControlChannel, CreateDataChannel, OpenControlChannel,
OpenDataChannel. Trust persistido conferido: somente ec2.amazonaws.com com
sts:AssumeRole. Nenhuma managed policy, KMS, S3 ou Secrets Manager concedidos.

Não houve associação a instância, VM, rede ou Scheduler criados, nem sessão SSM.
As quatro roles C3 existentes não foram alteradas. Criação da identidade não
comprova conectividade, isolamento do ensaio, fonte física ou readiness Live.
Não repetir criação nem pedir novamente a aprovação já atendida.
Aba11/browser1 agora mostra os detalhes da role (Relações de confiança).

Próxima etapa segura: preparar os parâmetros/formulário da rede dedicada do
laboratório conforme plano aprovado, SEM submeter criação, alterar default,
criar VM/Scheduler ou instalar software. Ler a seção de topologia existente,
conferir escopo exato e pedir confirmação específica antes de mutação sensível.
A confirmação desta role NÃO autoriza por si só outros recursos.
Automatismo ACTIVE, próxima preparação agendada sem OK genérico.
Nenhum código/teste alterado ou teste repetido. Somente IAM autorizado e
atualização deste registro/plano; acesso externo ao console AWS ocorreu.
Nenhum secret, dado operacional, Render, configuração de trading, ordem,
commit, push ou deploy acessado/executado/alterado. Live: percentual indeterminado.

## Atualização 13/09 — rascunho IAM pronto; criação não executada

Preparado no console IAM, aba11/browser1, assistente Etapa3 (Nomear, revisar
e criar). Perfil proposto CentralQuantC3SyntheticLabSessionRole20260913.
Trust conferido: apenas sts:AssumeRole para serviço ec2.amazonaws.com.
Política INLINE conferida integralmente no editor: Sid
SyntheticLabSessionChannelsOnly, Allow, Resource "*", somente
ssm:UpdateInstanceInformation e ssmmessages:CreateControlChannel,
CreateDataChannel, OpenControlChannel, OpenDataChannel.
Nome de política gerado pelo formulário:
CentralQuantC3SyntheticLabSessionRole20260913Policy.
Resumo mostra somente dois serviços: SSM Messages (as quatro ações de canais)
e Systems Manager (gravação limitada). Nenhuma managed policy selecionada.
Descrição de escopo sintético preenchida. Nada salvo ou criado; botão final
Criar perfil NÃO acionado. Nenhuma VM ou associação a instância.

Duas dificuldades de UI resolvidas com inspeção visual/foco: seletor EC2
estava abaixo do rodapé; preencher descrição perdeu foco, depois foi confirmado
separadamente. Isso não produziu mudança IAM. Não repetir o assistente nem
recriar por suposição. Aba marcada para continuação; reobservar antes de salvar.
Pedido de confirmação específico nesta conclusão: criar somente role/perfil EC2
e política inline descritos, na conta AWS aberta, SEM associar a instância,
sem criar VM/chaves ou tocar produção. O acesso permite canais administrativos
via Session Manager, não é apenas rótulo/identidade inerte.

Automatismo permanece ACTIVE, mas a ação de conceder acesso está BLOQUEADA pela
confirmação no momento da ação. Não tomar heartbeat, autorização genérica
histórica ou silêncio como consentimento. Sem resposta, DONT_NOTIFY e não
reabrir formulário/inventários/testes para gerar atividade. Após confirmação
específica, conferir rascunho atual, executar somente o escopo confirmado e
verificar resultado; não incluir rede/VM/Scheduler por essa confirmação.
Sem secrets, instalação, código, dados operacionais, Render, flags, ordens,
commit/push/deploy ou testes nesta etapa. Somente rascunho e este registro/plano.
Percentual Live indeterminado. Recomendação GPT-6 Astra — Alto.

## Auditoria autenticada IAM/SSM/rede/Scheduler — 13/09, somente leitura

Inspeção concluída no console AWS autenticado (Oregon para serviços regionais,
IAM global). Nenhum recurso, permissão, sessão remota ou preferência alterado.

| Controle | Evidência visível | Consequência |
| --- | --- | --- |
| IAM | Lista completa, sem filtro, 7 funções: quatro C3 existentes e três service-linked (ResourceExplorer, Support, TrustedAdvisor) | Não há role EC2/SSM nem role Scheduler dedicada ao laboratório |
| Rede | Uma VPC, default, após limpar filtro; um único security group default | Rede dedicada do plano ainda não existe; não reaproveitar/modificar o default |
| Security group default | Entrada: todo tráfego originado no próprio grupo; saída: todo tráfego IPv4 para 0.0.0.0/0 | Não é o desenho sem inbound/saída limitada do laboratório; NÃO significa entrada aberta para toda Internet |
| Session Manager | Página de apresentação carregou após uma recarga; nenhum StartSession ou configuração submetidos | Console acessível, mas conectividade/agente/permissões de uma instância não comprovados |
| Scheduler | Todos os estados e grupos, Cronogramas(0), sem filtro | Não existem agendamentos de encerramento no Oregon |

A listagem IAM não reaudita políticas internas das quatro funções C3 e não
prova permissões efetivas do operador para criar recursos. Elas foram preservadas.
Nenhuma VM/T0 foi criada por esta inspeção. Não inferir readiness de botão
habilitado nem de página de apresentação.

### Próxima ação mínima, delimitada e ainda NÃO aplicada

Preparar o formulário da role/perfil EC2 dedicado ao laboratório, com nome
proposto CentralQuantC3SyntheticLabSessionRole20260913 (não é recurso existente).
Trust somente serviço ec2.amazonaws.com, sem usuário externo, sem chaves.
Política customizada com somente as cinco ações do exemplo mínimo oficial:
ssm:UpdateInstanceInformation; ssmmessages:CreateControlChannel;
ssmmessages:CreateDataChannel; ssmmessages:OpenControlChannel;
ssmmessages:OpenDataChannel. Resource "*" segue esse exemplo; não concede
AdministratorAccess, leitura de parâmetros/secrets, S3, KMS ou poder de
criar/parar/terminar outras instâncias. O attach/pass-role futuro precisa ficar
restrito ao laboratório. A role permite canais administrativos da instância:
sua criação/associação exige confirmação específica no momento da ação.
Não aplicar política gerenciada ampla como substituto automático.
[Política mínima oficial](https://docs.aws.amazon.com/en_en/systems-manager/latest/userguide/getting-started-create-iam-instance-profile.html).

SSM Agent e HTTPS aos endpoints regionais devem ser comprovados no alvo;
não iniciar sessão ou habilitar Quick Setup agora. O processo sintético continua
sem rede, IMDS ou credenciais, separado da administração do host.
[APIs do agente](https://docs.aws.amazon.com/en_en/systems-manager/latest/userguide/systems-manager-setting-up-messageAPIs.html).

Depois, preparar rede dedicada sem inbound e encerramento conforme plano já
aprovado, preservando recursos default. A role de encerramento deve permitir
somente StopInstances/TerminateInstances no ARN da instância REAL identificada,
não em todas as instâncias ou em ID inventado. Trust Scheduler deve vincular
SourceAccount e ARN do GRUPO de agendamentos, não ARN de uma agenda individual.
Sem ID/T0 não emitir agendas fictícias. Conferir bindings após lançamento,
antes de ensaios, ou abortar conforme plano.
[Trust do Scheduler](https://docs.aws.amazon.com/scheduler/latest/UserGuide/cross-service-confused-deputy-prevention.html).

Não repetir inventários/checks concluídos sem mudança. Próxima retomada pode
preparar formulário sem salvar e chegar à confirmação específica de acesso;
não pedir aprovação genérica do orçamento ou do laboratório novamente.
A auditoria é entregue; preparação não equivale a provisionamento ou liberação
de launch. Continuam pendentes recipe/build nativo AL2023 e validação no alvo.
Sem instalação, secrets, Registry real, Render, flags, ordens, commit/push/deploy
ou testes operacionais. Chamadas externas apenas consultas de console e
documentação AWS. Percentual restante para Live indeterminado.

## Atualização — Python estático e próximo controle de acesso

Inspeção dos cinco ELF empacotados do Python 3.11.9 encerrada: GLIBC máxima 2.17;
libcrypt.so.1 é dependência externa adicional. Hashes/limites no registro JSON
do laboratório e em CLOCK_DEPENDENCIES. Isso não qualifica execução na AMI:
loader/SONAMEs, fechamento de símbolos e ensaio isolado continuam necessários.
Não mudar pin, copiar libc WSL ou transportar coletor com GLIBC_2.39.
Próximo passo independente é conferir IAM/SSM/Scheduler/rede somente leitura,
sem criar VM ou alterar as roles C3 existentes. Console Oregon autenticado
confirmado nesta retomada. Nenhuma mudança de infraestrutura foi realizada.

## Resultado prévio do alvo AL2023 — 13/09

Achados confirmados por inspeção local/documentação, sem recurso AWS:
coletor WSL tem requisito GLIBC_2.39, AL2023 usa2.34; Python sistema3.9 não
atende runner3.11.9; /var/tmp sobre raiz XFS não atende scratch ext4.
Launcher de regressão adaptado com --lab-parent, sem relaxar guards, com14/14
testes sintéticos aprovados. Assim o volume sintético dedicado pode receber
o laboratório, depois de devidamente identificado/preparado no escopo aprovado.
Nada foi formatado/montado/instalado. Receita candidata e fontes registradas
em .offline_releases/aws_synthetic_lab_20260913/CLOCK_DEPENDENCIES.md.
Faltam qualificação transitiva do runtime portátil, recipe RPM/build nativo
verificável e controles IAM/SSM/encerramento; essa preparação NÃO libera launch.
Não reabrir matriz temporal nem repetir pesquisa já concluída.

## Fronteira atual após qualificação local — 13/09

Preparação local de regressão, processos/locks/timeout, cliente ClockBound real
e quatro comparações VMClock sintéticas concluída; evidências no README de
.offline_releases/aws_synthetic_lab_20260913. Não repetir esse trabalho nem
considerá-lo validação física do host AWS. Ainda não existe VM nem T0.

| Antes de criar recurso | Situação / próximo resultado necessário |
| --- | --- |
| Escopo, orçamento e supervisor | Já aprovados: Flex/Oregon, US$5, Giulio; não pedir novamente |
| Imagem, toolchain e execução | AMI candidata já observada, mas falta recipe exata AL2023 e comprovação de compatibilidade do runner; artefatos WSL não são automaticamente portáveis |
| Acesso administrativo mínimo | Falta verificar composição dedicada IAM/SSM/rede, sem alterar quatro roles C3 dormentes ou criar chaves |
| Encerramento externo | Desenho stop/terminate existe; faltam recursos/bindings reais após lançamento, verificados antes dos ensaios |

Próxima preparação delimitada: conferir documentação pública e arquivos
existentes para versões/build do alvo AL2023 e separar regressão sem rede de
coleta física local. Nenhuma instalação ou alteração AWS nesta preparação.
Não recotar ou trocar máquina, contratar serviço ou ampliar escopo por isso.
Dependência ausente deve ser explicitada; não transportar cache/rlibs/glibc
WSL como solução de produção nem criar wrapper para esconder incompatibilidade.

Após lançamento autorizado e limitado, confirmar kernel/ENA/PHC/VMClock e
fonte temporal real na própria instância, com falha fechada. A existência do
dispositivo físico não pode ser provada antes de haver instância; documentos
e AMI apenas qualificam uma candidata. Se recursos de encerramento/acesso ou
fonte exigida falharem, abortar conforme plano, sem iniciar ensaios nem ampliar
orçamento. O laboratório não implementa autoridade/revogação/anti-rollback de
produção nem habilita os19writers. Percentual restante Live indeterminado.

## Estado e autorização

13/09/2026. Planejamento iniciado após “Siga com automatismo”, em resposta à
proposta de preparar o laboratório e apresentar custo antes de criar recursos.
Planejamento e estimativa concluídos em 13/09, 15:19 UTC. Nada provisionado.
Execução aprovada pelo usuário em 13/09 com “Aprovado”, em resposta ao pedido
explícito de aprovação da execução, verba e encerramento deste plano.
Verba aprovada: US$5 para uma única sessão sintética, cuja
estimativa-base é US$1,02 antes de impostos. Não é mensalidade nem teto técnico
de cobrança. Nada provisionado. Login confirmado no console EC2 Oregon.
Giulio, usuário desta conversa, confirmou que conferirá comigo o desligamento
ao final. Não há T0 nem horários de encerramento definidos sem lançamento.
Permanecem as validações pré-lançamento e confirmações específicas de ações
sensíveis exigidas por Computer Use. Não pedir novamente aprovação genérica.
Os requisitos de qualificação prévia abaixo não são substituídos pelo orçamento.

### Restrição confirmada e substituição aprovada — 13/09

O seletor autenticado mostra m7i.large desabilitada na conta atual, sem tentativa
de lançamento. m7i-flex.large aparece habilitada e qualificada para o nível
gratuito, com 2vCPU/8GiB e tarifa Linux Oregon US$0,09576/h. Nenhuma seleção,
contratação ou upgrade foi feito. Usuário aprovou com “sim” trocar somente o tipo de instância,
mantendo escopo sintético, região, limites e encerramento deste plano.

A substituição está aprovada, sem novo OK para esse escopo. Não pressupor equivalência:
a Flex tem baseline de 40% por vCPU e desempenho variável. A AWS documenta seu
suporte ao grupo precision-time; PHC exige as mesmas validações físicas/ENA.
É candidata a ensaios de correção, não a certificação de desempenho ou Live.
Base estimada com as mesmas demais parcelas abaixo: US$0,976084 (~US$0,98),
antes de impostos e sem presumir descontos/créditos. Verba US$5 mantida, sem
garantia de teto de cobrança. Não mudar conta para Paid automaticamente.
[CPU M7i-flex](https://aws.amazon.com/ec2/instance-types/m7i/),
[precision-time e PHC](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configure-ec2-ntp.html).

As seções seguintes preservam o desenho original; referências à aprovação
futura são históricas e subordinadas às atualizações de autorização acima.

## Única fase proposta

Ensaio físico temporário, não migração nem homologação Live. Candidata: uma EC2
m7i.large Linux x86_64 (2 vCPU, 8 GiB), Oregon/us-west-2, tenancy compartilhada,
On-Demand, sem Marketplace, reservas ou Spot. Dimensionamento é hipótese para
um laboratório pequeno, não dimensionamento da Central. Referência de imagem:
Amazon Linux 2023; AMI/kernel/ENA/ClockBound exatos precisam ser fixados antes de
provisionamento. Não inventar IDs nem garantir disponibilidade na conta.

A família M7i é documentada para grupos precision-time. O grupo não acrescenta
tarifa; falta de capacidade pode impedir lançamento/reinício. PHC requer Linux
e ENA compatível (documentação especifica versão 2.10.0 ou posterior). Elegibilidade
documentada não equivale a aprovação física da instância.
[AWS Time Sync](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configure-ec2-ntp.html),
[M7i](https://aws.amazon.com/ec2/instance-types/m7i/).

Proposta de capacidade: raiz gp3 de 20 GiB mais volume gp3 de 10 GiB para somente
Registry, WAL, lease e locks sintéticos; desempenho básico, sem IOPS adicionais.
Até 8 horas acumuladas de instância e 24 horas de retenção dos dois volumes,
incluindo preparação e encerramento. Não é um prazo prometido de entrega: se
os ensaios não terminarem dentro da janela aprovada futuramente, abortar e
entregar evidências parciais, sem extensão automática ou máquina maior.

Não importar main, broker ou bots, transportar secrets ou montar/copiar o disco
Render. Reutilizar componentes permitidos do candidato multistore já validado.
Antes de executar qualquer ensaio, revisar integralmente runner/dependências
para o alvo, bloquear acesso externo no processo de teste e permitir somente
armazenamento sintético dedicado e fonte temporal local estritamente necessária.

## O que medir e como decidir

| Ensaio proposto | Evidência de aceite | Aborto / limite |
| --- | --- | --- |
| Fonte temporal real | Dispositivo/versões identificados, estado válido e limite completo de erro medido; amostras com referência monotônica | Ausência/estado inválido/limite desconhecido recusa admissão; não atribuir erro zero |
| Contenção física | Processos separados competem pelos mesmos arquivos locais; manutenção exclui mutações concorrentes | Admissões simultâneas incompatíveis, troca de backend ou lock não confirmado reprovam |
| Reinício e posse | Interrupção do processo detentor invalida permissões antigas e não produz readiness limpa por suposição | Reuso de permit, lease ambíguo ou pendência não reconciliada mantém bloqueio |
| Recuperação sintética | Casos PREPARED/RESOLVED/UNRESOLVED preservam evidência; recuperação ou recusa explícita | Não inferir autoridade atual a partir de cópia restaurada; não resolver pendência por expiração |
| Falha temporal/deadline | Perda de fonte e retorno tardio não autorizam nova fase; orçamento não é renovado | Callback cooperativo não é garantia de interrupção física do efeito |

Os 19 caminhos de escrita reais NÃO serão ativados. Concorrentes sintéticos
verificam o mecanismo, não cobertura operacional dos 19 writers. O ensaio não
qualifica emissão/autenticação, revogação, testemunha independente, consumo
anti-rollback ou recovery de produção. Não criar KMS/Lambda/RDS/Redis para
simular conclusão dessas dependências.

Com PHC, chrony isoladamente pode subestimar erro. A medição precisa contabilizar
o erro do hardware e do relógio conforme a documentação; um valor instantâneo
não certifica períodos futuros. O antigo 100 ms era fixture, não SLA do Live.
[AWS ClockBound](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/compare-timestamps-with-clockbound.html).

## Acesso e encerramento — ainda somente proposta

Uma rede dedicada sem peering/rotas para a Central. Proposta para custear acesso:
IPv4 público temporário e acesso administrativo autenticado sem portas de entrada
abertas, por Session Manager para EC2. Não criar chave
SSH ou alterar as quatro roles C3 já dormentes. A eventual role do laboratório
deverá ter escopo próprio aprovado; nenhum ARN ou trust será inventado.
Preparação de sistema e testes têm fases distintas: o processo de teste não
herda permissão para chamar APIs externas ou IMDS. Sem NAT Gateway, balanceador,
IP elástico reservado, banco gerenciado ou serviço permanente nesta candidata.

Antes de aprovação de execução, é obrigatório definir o mecanismo externo de
encerramento e responsável que confirme término da instância e remoção apenas
dos volumes sintéticos identificados, após exportação e verificação das evidências.
Parar a VM não basta para encerrar cobrança de armazenamento. Não depender só
de timer no host sob teste. Alarmes de orçamento não são teto rígido de cobrança.
Mecanismo proposto: dois agendamentos únicos EventBridge Scheduler externos à
VM, um para StopInstances em T0+7h45 e outro para TerminateInstances em T0+24h,
com janela flexível desligada, ações e permissões restritas ao ID dessa única
instância sintética. T0 será o lançamento, não o início do primeiro teste.
Até uma retentativa por agendamento dentro de idade máxima de 5 minutos;
quatro invocações reservadas no cálculo. Não usar Lambda ou criar serviço
persistente para isso. Ambas as ações precisam de confirmação externa de estado:
entrega ao Scheduler não comprova parada/término. Não reiniciar após stop final.

Antes de iniciar testes, validar os dois agendamentos e seus bindings. Se não
forem estabelecidos imediatamente após o lançamento, encerrar o recurso sem
iniciar ensaios. Identidade do operador responsável pela supervisão e pela
confirmação final é pré-condição da execução; não pressupor que Codex estará
online. Agendamento tem precisão de 60 segundos e falhas de serviço/permissão
podem atrasar o efeito: não é garantia rígida de 8 horas ou de custo máximo.
[Scheduler: targets](https://docs.aws.amazon.com/scheduler/latest/UserGuide/managing-targets-universal.html),
[precisão e horários](https://docs.aws.amazon.com/scheduler/latest/UserGuide/schedule-types.html).

Os dois volumes exclusivamente sintéticos devem ter DeleteOnTermination=true
verificado explicitamente, sem snapshot ou backup automático. Exportar evidências
sanitizadas para o workspace antes de T0+7h30 e verificar integridade. A retenção
de até 24 horas é contingência para exportação, não extensão dos testes. O
encerramento de emergência poderá perder evidências não exportadas; esse risco
deve integrar a autorização futura. Não suspender o encerramento para aguardar
o agente. Confirmar volumes removidos e IP automático liberado; remover agendas
e permissões/rede específicas só depois de verificar que não são compartilhadas.
[EBS: efeito de DeleteOnTermination](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/preserving-volumes-on-termination.html).

Session Manager sobre EC2 não tem cobrança adicional na modalidade básica;
não habilitar just-in-time node access, logs externos ou endpoints privados
pagos nesta candidata. Rede de gerenciamento permitirá HTTPS de saída aos
endpoints SSM e preparação estritamente necessária; nenhuma porta inbound.
IAM/SSM, conectividade e identidade administrativa devem ser qualificados antes
de qualquer teste. Sem acesso a contas nesta entrega, esse estado não está
verificado. Preparação autenticada e instalação futura exigem escopo explícito.
[Session Manager: preço](https://aws.amazon.com/systems-manager/pricing/),
[acesso sem SSH](https://docs.aws.amazon.com/prescriptive-guidance/latest/aws-startup-security-baseline/wkld-06.html).

Esta versão não instala nem executa qualquer mecanismo descrito.

## Estimativa regional concluída — somente para a sessão sintética

Não há preço total aprovado nem gasto autorizado. Não descontar créditos AWS
ou prometer substituição/cancelamento de Render, Redis ou ChatGPT.

| Parcela | Hipótese de uso | Tarifa / valor estimado |
| --- | --- | --- |
| EC2 m7i.large Linux, Oregon | 8 horas acumuladas | US$0,1008/h × 8 = US$0,8064 |
| gp3, 30 GiB totais | Até 24 horas incluindo retenção | US$0,08/GB-mês × 30 × 1/30 = US$0,08 |
| IPv4 público comum | Até 8 horas | US$0,005/h confirmado: US$0,04 para 8 h |
| Saída total, incluindo administração/evidências | Até 1 GB, sem pressupor franquia disponível | US$0,09/GB = US$0,09 |
| Session Manager básico EC2 | Administração da instância | Sem tarifa adicional; rede computada acima |
| EventBridge Scheduler | Duas ações, até quatro invocações com retentativas | US$1/milhão, sem franquia: US$0,000004 |
| Retenção | Evidências exportadas para workspace; sem snapshot/cloud logs permanente | Qualquer retenção extra exige recotação |

Base: US$1,016404, arredondada para US$1,02. Mês de 30 dias para o rateio do
disco de setembro; desempenho gp3 básico, sem IOPS/throughput extra. Proposta de
verba US$5: margem de US$3,983596 sobre a base, não um desconto ou garantia
de cobertura tributária. Sem créditos, franquias, impostos, câmbio ou taxas de
cartão presumidos. Necessidade de ultrapassar escopo/verba exige parar e recotar.

Cenários de falha, sem autorizar extensão: manter VM+IP ligados por 24h,
mesmo disco e 1GB de saída custaria aproximadamente US$2,71; esquecer tudo
ligado por 30 dias, mantendo 1GB de saída, aproximadamente US$78,67 antes de
impostos. Só os volumes de 30GiB retidos por 30 dias custariam US$2,40.
Desligar a máquina não elimina a cobrança do disco. Nenhum desses cenários é
teto, e nenhum inclui autoridade/testemunha de produção ou migração da Central.

Tarifas confirmadas em JSON público oficial pelo shell, sem autenticação:

- [EC2 Oregon Linux](https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/ec2-ondemand-without-sec-sel/US%20West%20%28Oregon%29/Linux/index.json): m7i.large, 2vCPU,8GiB, sem software pré-instalado/licença adicional, rateCode 76SYQ5S6SHTVH6CA.JRTCKXETXF.6YS6EN2CT7.
- [EBS](https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/ebs.json): região US West (Oregon), Storage General Purpose gp3 GB Mo, rateCode BB8UJWJ4XPFJB95G.JRTCKXETXF.6YS6EN2CT7.
- [Transferência](https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/datatransfer/USD/current/datatransfer.json): Oregon, saída externa faixa inicial paga, rateCode 5M4327XEUKBBTWAT.JRTCKXETXF.Q3Z75P77EN.
- [Scheduler](https://aws.amazon.com/eventbridge/pricing/): taxa por invocação do exemplo US West; não utilizada a franquia mensal.

Esses registros são evidência de preço consultado, não oferta contratual ou
disponibilidade da conta. Revalidar no momento de uma execução aprovada.
[EC2 On-Demand](https://aws.amazon.com/ec2/pricing/on-demand/),
[EBS](https://aws.amazon.com/ebs/pricing/),
[IPv4/VPC](https://aws.amazon.com/vpc/pricing/).

## Conclusão e próxima decisão

Plano, custo esperado, riscos de retenção, fontes e estratégia de encerramento
entregues. Não repetir pesquisa ou testes a cada retomada. Solicitar decisão
específica sobre verba de US$5 para esta sessão, sem alegar que ela libera Live.
Aprovação de verba isolada não autoriza compras, alterações IAM ou execução:
o escopo operacional precisa incluir o laboratório, permissões limitadas,
instalação necessária, responsável pelo encerramento e eliminação dos dados
sintéticos ao final. Antes de provisionar, fixar versões, revisar runner,
confirmar preço/conta/acesso e rejeitar qualquer expansão da topologia.

Nenhuma tarefa técnica fica artificialmente aberta nesta entrega. Automatismo
permanece ativo para nova autorização/evidência acionável, sem outra rodada de
pesquisa equivalente. Percentual de Live indeterminado, pois esta fase mede só
parte das dependências físicas e não remove os dois gates de produção.

Pesquisa já feita: documentação oficial de hardware/tempo e preços gerais
consultada em 13/09. Página EC2 não expôs tarifa da m7i.large no texto extraído.
Host legado a0.p.awsstatic.com não resolve; tentativa de caminho guessed
ec2-ondemand-without-os no b0 retornou NoSuchKey. Não repetir esses caminhos.
HTML público EC2 aponta para tabela dinâmica em
https://pricing-table.us-west-2.prod.site.p.awsstatic.com e tokens públicos em
https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps.
Nesta retomada, o endpoint ec2-ondemand-without-sec-sel com seletor Linux foi
recuperado com sucesso, assim como ebs.json e datatransfer.json. A extração web
não conseguiu abrir os JSONs; a leitura HTTP pública pelo shell retornou os
registros acima. Não repetir caminhos antigos nem tratar falha de extração web
como ausência das tarifas já comprovadas.

## Verificação desta rodada

Alterados somente este plano e o topo da continuidade; automatismo existente
atualizado pela ferramenta do aplicativo. Nenhum código de aplicação alterado,
nenhum teste executado, nenhum secret ou dado operacional acessado. Chamadas
externas foram exclusivamente consulta pública documental/de preços e gestão
da automação; nenhuma API operacional AWS/Render/BingX. Sem commit, push,
deploy, infraestrutura, flags ou Live. Riscos operacionais permanecem abertos;
percentual restante para Live indeterminado.
