# C3 — planejamento delimitado da Sessão B

## Retomada delimitada — 29/09/2026

Autorizada a continuidade da análise sem OKs intermediários, não gastos ou execução.
Usuário informou ausência de resposta humana no re:Post. A resposta de IA colada
na conversa em 25/09 não comprovou VMClock, AMI pronta nem limites temporais.
Pergunta: https://repost.aws/pt/questions/QUN_MDbXkQQzWmSxtNUHdyhA/vmclock-and-ena-phc-availability-on-m7i-flex-in-us-west-2
Não afirmar que o comentário preparado foi publicado; isso não foi confirmado.

### Diagnóstico não é qualificação

- Identificar PHC/VMClock, versões e permissões num futuro alvo pode responder
  presença e compatibilidade observadas. Não exige fingir que limites temporais
  já foram provados, mas requer autorização separada para provisionar e inspecionar.
- Não iniciar daemon, recompilar/recarregar ENA ou ajustar Chrony nessa etapa de
  identificação. Dispositivo ausente encerra o diagnóstico; não reparar por impulso.
- Nenhuma amostragem finita, mesmo sem falhas, comprova por si só um limite universal
  de deriva ou o comportamento em toda pausa/manutenção. Não substituir a, epsilon,
  W ou G por máximos observados nem remover o requisito de descontinuidade.
- Logo, há caminho candidato para diagnóstico de compatibilidade, mas não foi
  demonstrado caminho equivalente de qualificação que dispense as premissas faltantes.
  Preservar todos os gates false. Não criar código, testes ou arquitetura alternativa.

### Custos — resultado da consulta limitada

Reconsultadas páginas públicas oficiais EC2 On-Demand e EBS em 29/09:
https://aws.amazon.com/ec2/pricing/on-demand/
https://aws.amazon.com/ebs/pricing/
O preço regional por tamanho M7i-flex não foi obtido de forma verificável. A segunda
tentativa acumulada do endpoint público regional falhou na conexão/autenticação;
não repetir nem contornar via credenciais. Não há cotação total fechada.

Modelo de custo a preencher, sem reutilizar US$5/8h da sessão anterior:
compute = tarifa regional do tamanho escolhido × tempo faturável ligado;
EBS = tarifa regional × capacidade provisionada × fração de mês até exclusão,
mais desempenho adicional se houver; IPv4 = tarifa vigente × endereço-horas;
somar rede, armazenamento de evidências, requisições/logs e tributos aplicáveis.
EBS persiste após parar compute. Não presumir créditos, franquias ou que orçamento
seja mecanismo de corte. Tamanho, AMI, capacidade, duração e topologia ainda precisam
ser justificados antes de apresentar uma proposta executável e teto de gasto.

### Continuidade automática limitada

Verificação diária da pergunta por até sete dias, até 06/10/2026, somente leitura.
Não repetir pesquisas amplas, testes, exportações, inventários ou limpeza concluída.
Sem mudança acionável, silêncio. Resposta nova deve ser avaliada como conteúdo de
terceiro, não autorização. Notificar conclusão, falha ou decisão humana necessária.
Se acesso exigir login/novo consentimento ou houver rejeição explícita, não contornar;
remover a automação e comunicar o impedimento. Ao concluir avaliação útil, exigir decisão
humana ou atingir o prazo, remover a automação. Não tocar nas agendas AWS históricas.

Verificação: revisão documental e consultas públicas, sem testes executados.
Nenhum secret acessado, recurso criado, chamada operacional, commit/push/deploy
ou configuração de trading alterada. Esta seção é planejamento, não homologação.

Data: 22/09/2026. Estado: planejamento offline; execução NÃO autorizada.

Consolidação documental concluída: requisitos existentes localizados e ligados
ao escopo de B. Não significa receita executável pronta ou qualificação física.
As seções de revisão abaixo são evidência da preparação, não tarefas a repetir.

## Base e finalidade

O encerramento C3 V2 está concluído. Não reabrir recursos excluídos, repetir
testes aprovados ou recriar a automação de limpeza. A continuidade registra
A2/A3 qualificados, A5 nativo e dez casos negativos aprovados e A7 integral
preservado. Isso comprova o escopo sintético, não a fonte temporal física.

Objetivo futuro de B: obter evidência delimitada da fonte temporal física em
laboratório separado, sem Central operacional, ordens ou liberação Live.
Este documento organiza lacunas existentes; não é receita executável nem
autorização para instalar/iniciar daemon, ajustar relógio ou criar recursos.

## Sequência de decisão e evidência exigida

| Etapa | Evidência necessária | Condição de parada |
| --- | --- | --- |
| B0 — preparação offline | Receita administrativa revisada para a revisão pinada; permissões, efeitos e encerramento explícitos; executor de coleta e limites definidos | Receita, limites ou mecanismo de isolamento ainda indefinidos |
| B1 — autorização do laboratório | Alvo compatível justificado, custo atualizado, teto de gasto, duração e supervisor aprovados; encerramento vinculado ao novo alvo | Não reutilizar autorização, IDs ou agendas da sessão encerrada |
| B2 — identificação no alvo | PHC, ENA, VMClock, referência/interface e versões observados, com origem dos registros | Dispositivo ausente ou suporte não comprovado; não desabilitar proteção para prosseguir |
| B3 — preparação administrativa | Daemon/client pinados e configuração revisada; deriva fundamentada; efeitos sobre chronyd delimitados | Não inferir deriva por exemplos nem tratar daemon como observador somente leitura |
| B4 — coleta isolada | Fonte local identificada, mappings mínimos somente leitura, coletor sem rede/credenciais/socket administrativo/capacidade de ajustar relógio; deadline independente | Guard inválido impede execução; não abrir diretórios amplos para contornar isolamento |
| B5 — avaliação e entrega | Intervalo completo earliest/latest, vínculo BOOTTIME, status, identidade e hashes; evidência sanitizada exportada e conferida | Saída parcial ou estado inválido não vira sucesso; não estender sessão para recuperar exportação |

Identificação de um futuro alvo não pode ser inferida da antiga instância.
Suporte de dispositivos e preços deverão ser verificados em documentação
oficial atual antes da proposta de contratação; nenhuma pesquisa/cotação ou
consulta autenticada foi feita nesta preparação.

## Critérios mínimos, sem inventar limiares

- Uma amostra aceita pelo coletor exige status SYNCHRONIZED, valores válidos,
  intervalo ordenado, BOOTTIME coerente e ausência de falhas open/read/close.
- Uma amostra válida não comprova, isoladamente, precisão física, origem PHC,
  frescor sob pausas do host nem suporte efetivo de descontinuidade.
- O suporte de descontinuidade precisa de evidência própria: abrir VMClock não
  basta segundo a revisão local da FFI. Não preencher esse resultado manualmente.
- Duração, cadência, número de amostras, erro máximo admissível e atraso de
  detecção permanecem NÃO DEFINIDOS. Devem ter fundamento antes da execução;
  100 ms de fixture/polling e 50 PPM de exemplo não são limites aprovados.
- Ausência de fonte, status inválido, descontinuidade e deadline devem resultar
  em recusa demonstrável. Reutilizar testes sintéticos existentes como evidência
  sintética; não apresentá-los como falhas físicas provocadas.
- Não provocar migração, reinício do host ou ajuste de relógio nesta proposta.
  Se a comprovação exigir tais ações, separar método, risco e autorização.
- Manter source_qualified, disruption_support_verified, admission_allowed e
  live_allowed sem promoção no código existente. Um relatório não habilita gates.

## Pendência técnica anterior a qualquer lançamento

Falta fechar uma receita revisada de daemon e coleta física, com os limites e
oráculos acima. CLOCK_DEPENDENCIES.md cobre preparação/build, não essa receita.
Os modos valid/markers históricos de test_clock_real.py não são um executor
físico portátil; não adaptá-los apenas para repetir cenários já aprovados.

A revisão focada da implementação/documentação pinada foi realizada nas seções
abaixo, identificando efeitos administrativos e um perfil candidato, não uma
configuração validada. Não instalar ou iniciar para descobrir comportamento.
A futura proposta de execução ainda deve fechar alvo, orçamento, prazo e ações
exatos. Nenhum valor antigo de custo ou janela foi transferido para B.

## Revisão estática focada do daemon empacotado

Lidos diretamente, sem extração para disco nem execução, os membros README.md,
src/main.rs e src/signal.rs e trechos relevantes de src/lib.rs,
src/chrony_client.rs e src/clock_bound_runner.rs de clock-bound-d no pacote
artifacts/clock_source_transport_qr10adoo/clockbound203-pinned-sources.tar.gz.
Esta leitura não é auditoria integral do daemon nem nova verificação do pacote.

Achados que restringem a futura receita:

1. A CLI aceita clock_error_bound_source=vmclock, mas lib.rs implementa esse
   ramo com unimplemented!. Não selecionar essa opção. A rota candidata é
   Chrony como fonte do intervalo, com PHC configurado e VMClock separado para
   detecção de descontinuidade. Ainda exige qualificação física no alvo.
2. O daemon cria o writer em /var/run/clockbound/shm0 antes de selecionar a
   fonte de erro. Uma inicialização que aborta pode já ter criado o segmento;
   existência do arquivo não prova daemon saudável nem amostra atual.
3. O cliente administrativo envia ResetSources e Burst ao Chrony. Portanto,
   a autorização futura precisa abranger esses efeitos; o coletor isolado
   não deve receber o socket administrativo. O código registra dependência
   de Chrony >= 4.0 para ResetSources; confirmar compatibilidade no alvo.
4. A deriva omitida cai no default de 1 PPM com aviso do próprio programa.
   Exigir valor explícito fundamentado, coerente com maxclockerror do Chrony;
   não copiar 50 PPM do exemplo como se fosse garantia do hardware.
5. O exemplo de serviço upstream usa Restart=always e habilitação persistente.
   Não copiá-lo para o laboratório delimitado. A receita precisa de supervisão
   com duração máxima, sem restart automático nem ativação no boot, confirmação
   de saída de todos os processos e descarte de amostras após encerramento.
6. SIGUSR1/SIGUSR2 forçam estados de teste. Não comprovam evento físico do
   hipervisor e não devem ser enviados sem escopo específico para os efeitos
   administrativos possíveis. Não repetir testes sintéticos por esse achado.

Ainda não fechado: perfil exato de permissões/mappings do daemon, método de
encerramento verificado, limites quantitativos do ensaio e evidência física
de descontinuidade. Não há receita executável aprovada. Nenhum patch upstream,
serviço, configuração Chrony ou coletor foi alterado nesta revisão.

## Perfil mínimo candidato e encerramento — revisão adicional

Base estática adicional: clock_bound_runner.rs (fluxo anterior aos testes) e
phc_utils.rs do mesmo arquivo empacotado; sem executar fontes ou extrair arquivos.

| Componente | Acessos necessários identificados | Acessos que não devem ser herdados |
| --- | --- | --- |
| Daemon ClockBound | Escrita no diretório dedicado que fornece /var/run/clockbound/shm0; leitura de VMClock; comunicação administrativa UDS com Chrony; leitura dos dois caminhos sysfs abaixo | Credenciais AWS, IMDS, arquivos da Central, diretórios pessoais; não presumir necessidade de root ou capacidade de ajustar relógio diretamente |
| Chrony do laboratório | Privilégios próprios de sincronização e fonte temporal aprovada, separados do coletor | Não compartilhar configuração ou socket com produção |
| Coletor | Biblioteca/runtime somente leitura, SHM em /clockbound/shm0 e VMClock em /clockbound/vmclock0 somente leitura; saída limitada ao supervisor | Socket Chrony, escrita em SHM, rede, IMDS, credenciais, capabilities administrativas |
| Supervisor | Identidade estável do grupo de processos, relógio monotônico, captura limitada de saída e autoridade para encerrar somente o grupo do ensaio | Gestão de processos por nome genérico, encerramento de serviços alheios ou extensão automática da sessão |

O daemon resolve /sys/class/net/<interface>/device/uevent para obter PCI_SLOT_NAME
e lê /sys/bus/pci/devices/<slot>/phc_error_bound. Interface e slot precisam vir
da identificação do alvo. Não expor /sys inteiro nem substituir esses arquivos
dinâmicos por cópias estáticas apresentadas como medição física. A viabilidade
dos mappings e permissões ainda precisa de validação isolada; esta matriz não
é uma configuração testada de sandbox.

### Por que o prazo precisa ser externo

process_current_fsm_state usa retry sem término externo enquanto o estado é
Disrupted, com ciclos de recuperação Chrony e cooldown de 10 s. O intervalo de
polling de 100 ms não limita esse caminho. write_clock_error_bound usa
void_after = as_of + 1000 s, com comentário upstream de que o valor precisa ser
calibrado. Nem 100 ms nem 1000 s são garantia de atraso/frescor para C3.

Proposta de controle do ensaio, não implementada:

1. Criar grupo de processos próprio, identidade registrada e supervisor pronto
   antes do daemon. Prazo global cobre também inicialização e recuperação.
2. Deadline, saída excessiva, falha do daemon ou encerramento humano interrompem
   novas coletas. Amostras posteriores à condição de parada são recusadas.
3. Solicitar término do grupo exato; após tolerância finita previamente definida,
   forçar encerramento desse mesmo grupo. Não procurar processos apenas por PID
   antigo/nome nem assumir sucesso porque um sinal foi enviado.
4. Confirmar grupo vazio e registrar motivo, horários e códigos de saída. Não
   presumir que o daemon invalida ou remove SHM ao morrer; o supervisor deixa de
   aceitar dados independentemente do conteúdo que permaneça nesse arquivo.
5. Preservar recibos sanitizados e executar encerramento do laboratório conforme
   autorização futura. Não tocar nas agendas históricas da Sessão A.

### Separação dos limites

O orçamento de execução (tempo, quantidade de amostras e volume de saída) é um
limite de recursos do experimento. Erro temporal máximo, deriva e atraso de
detecção são requisitos de qualificação; não podem ser deduzidos daquele orçamento.
Uma janela curta pode produzir diagnóstico, mas não qualificação física completa.

Não foram escolhidos números arbitrários para preencher essa lacuna. Para fechar
a receita de execução ainda são necessários: requisito temporal do consumidor C3
com justificativa; alvo com suporte comprovado; configuração Chrony/PHC e deriva
fundamentadas; validação do supervisor/mappings e orçamento específico. Até isso,
o resultado correto é preparação parcial, não sessão pronta para lançamento.

## Requisitos temporais existentes — consolidação final

O mapa já existe em C3_PROPOSTA_DECISAO_20260912.md, seções 8, 12 e 13.
Foi reutilizado, não refeito. Conferência textual focal da função
remaining_epoch_window_ms_offline_v2 em trade_registry_c3_public_authority_offline_v2.py
(linhas 42–64) e do harness receive_synthetic_epoch_messages em
tests/test_c3_public_authority_wire_offline_v2.py (a partir de 633), sem imports.

| Requisito existente | Origem | Consequência para B |
| --- | --- | --- |
| Intervalo inteiro dentro da validade: N <= L <= U < E | Função remaining_epoch_window_ms_offline_v2; proposta seção 13.2 | Conservar intervalo e escala; uma amostra pontual ou sobreposição parcial não basta |
| Largura máxima W é parâmetro, não constante universal | max_interval_width_ms da função; literal 100 apenas no harness | Não impor 100 ms como SLA físico nem comprar infraestrutura por esse número |
| Janela de até 300000 ms; retorno limitado a min(5000, orçamento restante, E-U) | Mesma função | Caps do experimento preservados; não são tolerância de erro, duração do laboratório ou garantia de conclusão física |
| Deadline admitido só diminui; reinício invalida a sessão | Proposta seções 8 e 13 | Novas amostras não renovam orçamento; evidência serializada não restaura validade local |
| Transporte deve incluir atraso integral e margem do contador | Proposta seção 8.1 | Coleta local em EC2 não qualifica automaticamente um consumidor remoto |
| Checagem cooperativa não interrompe efeito físico | Proposta seções 12.2 e 13 | Timeout não desfaz commit; relógio melhor não substitui reconciliação ou enforcement no ponto do efeito |

Premissas quantitativas já especificadas, mas ainda sem valores físicos
qualificados: avanço mínimo a > 0 do contador local, margem de leitura epsilon,
largura admissível W e margem G entre última checagem e efeito. A proposta usa
T = ceil((q_v-q_s)/a + epsilon), sem descontar metade do RTT. Exige intervalo
propagado inteiramente válido; para conversão de prazo propõe
delta_q = floor(a*(R-G)), com R > G e delta_q > 0, sem aumentar deadline anterior.
São fórmulas condicionais de desenho, não implementação integrada ou certificação.

O relatório de 12/09 também distingue orçamento de manutenção (default 30 s,
lock 1 s, máximo configurável 300 s) de precisão temporal. Esses números não
foram reaproveitados como orçamento da Sessão B. Não há nesta cadeia revisada
um requisito universal demonstrado de precisão Live de 100 ms.

### Resultado e passagem para a etapa seguinte

A preparação documental solicitada está concluída: base A preservada, caminho
não implementado excluído, efeitos administrativos identificados, permissões e
encerramento candidatos descritos, requisitos existentes rastreados e lacunas
separadas de valores de teste. Não repetir essa busca ou abrir novos contratos.

B permanece somente laboratório diagnóstico candidato. Para uma proposta de
execução, engenharia ainda precisa demonstrar a compatibilidade do alvo, deriva,
escala temporal, isolamento e supervisão; explicitar quais premissas do consumidor
serão ou não cobertas. O usuário não deve inventar W, a, epsilon ou G.
Se não houver fundamento, registrar a premissa não demonstrada e não qualificar.

Decisão humana futura é sobre uma proposta concreta de laboratório com custo,
prazo e efeitos administrativos, não um OK genérico nem aprovação automática
de Live. Nenhuma autorização antiga foi reaproveitada. Não recriar a automação
de limpeza. Não há execução física, compra ou integração liberada por esta meta.

## Verificação pública de viabilidade — 22/09/2026

Estado: proposta de execução ainda bloqueada; nenhuma conta AWS acessada.
Esta seção complementa a preparação offline com consulta pública, sem modificar
fontes pinadas, arquitetura, imagem, kernel ou configuração.

- PHC: a documentação EC2 inclui M7i-flex em grupos precision-time nas regiões
  comerciais, exige Linux e ENA >= 2.10.0. O grupo não tem custo adicional.
  Isso não comprova que a imagem selecionada já tenha PHC ativo nem garante
  VMClock. Fonte: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configure-ec2-ntp.html
- Preparação: o README ENA exige suporte PTP do kernel, compilação com
  ENA_PHC_INCLUDE e ativação explícita. A alternativa devlink documentada para
  ativar PHC exige kernel >= 6.17 e também recarrega o dispositivo. Não recomendar
  troca de kernel para usá-la. Recarregar o driver de rede pode afetar o acesso
  administrativo: requer plano de recuperação separado antes de autorização.
  Fonte: https://github.com/amzn/amzn-drivers/blob/master/kernel/linux/ena/README.rst
- VMClock: o README pinado 2.0.3 condiciona /dev/vmclock0 ao suporte do provedor,
  mesmo com kernel compatível, e descreve rollout iniciado em Graviton. Não
  fornece garantia específica para M7i-flex/Oregon. O README atual usa exemplos
  da linha 3 alpha, não autoriza atualizar o pacote 2.0.3 nem prova esse alvo.
  Fonte pinada: https://raw.githubusercontent.com/aws/clock-bound/75b754b234c7001021300a3ee10876e98cdfbc71/clock-bound-d/README.md
  Referência atual: https://raw.githubusercontent.com/aws/clock-bound/main/README.md

### Custo: componentes confirmados e lacuna

IPv4 público: US$ 0,005 por endereço/hora, se utilizado, conforme
https://aws.amazon.com/vpc/pricing/ . Isso não elimina custos de compute, EBS,
transporte, logs ou rede. O exemplo de US$ 0,08/GB-mês em
https://aws.amazon.com/ebs/pricing/ é regionalmente condicional: não foi tratado
como cotação específica de Oregon. A tarifa EC2 Linux On-Demand regional não
foi obtida de forma verificável nesta consulta. Uma tentativa de leitura do
endpoint público de tarifas falhou; nenhum preço foi preenchido por memória.

Assim, não há total fechado nem teto de gasto aprovado. Não reutilizar US$ 5
ou oito horas da sessão anterior. O orçamento futuro deverá somar compute por
tempo ligado, EBS até exclusão, IPv4 se usado e custos auxiliares explicitados;
sem supor créditos, faixa gratuita ou que um orçamento interrompa cobrança.

### Consulta AWS — interação enviada; caso técnico não aberto

Para um laboratório temporário Linux x86_64 em us-west-2, família M7i-flex,
com grupo precision-time e ClockBound 2.0.3 pinado, confirmar:

1. A exposição de /dev/vmclock0 é garantida para esse alvo? Quais restrições
   de tipo, zona, kernel/AMI e manutenção se aplicam? Solicitar referência
   oficial; disponibilidade de PHC não responde esta pergunta.
2. Qual imagem AL2023 identificável fornece ENA com PHC compilado e ativado,
   sem atualização geral, recompilação, recarga de rede ou reinício adicional?
   Se não existir, explicitar a preparação mínima e o risco de perda de SSM.
3. Há documentação dos limites de deriva e da semântica de descontinuidade
   aplicáveis ao contador do consumidor? Uma precisão típica não é um bound.

Esta consulta técnica não contém credenciais ou dados operacionais. Após autorização
humana específica, em 22/09/2026 o texto foi enviado à interação do Centro de Suporte
da conta 899845009758. Registro:
https://support.console.aws.amazon.com/support/home?interactionId=0ca2cebe-999c-4972-892e-e2d964ba04fa#/

O console identifica o plano como Suporte Básico. Ao selecionar caso Técnico,
exibiu oferta de avaliação do Business Support+ e salvou um rascunho. Não foi
submetido caso técnico a um atendente; não há número de caso nem resposta técnica
verificada. Nenhuma avaliação, contratação ou alteração de plano foi aceita.
Não contornar pela categoria Conta e faturamento. A interação de IA não comprova
compatibilidade nem substitui garantia documentada do provedor.

Sem resposta/documentação equivalente,
a alternativa seria autorizar separadamente um diagnóstico pago com possibilidade
de reprovação; isso NÃO está incluído nesta preparação. Não repetir buscas idênticas
nem lançar uma máquina como forma implícita de comprovar suporte.

Verificação desta atualização: consultas públicas oficiais e revisão documental.
Nesta atualização houve somente a comunicação autenticada autorizada com o
Centro de Suporte, além da revisão documental. Nenhum teste, instalação, acesso
a secret, chamada operacional, commit/push/deploy ou alteração de trading.
Único arquivo alterado: este planejamento.

## Limite para produção

Mesmo uma futura aprovação de B não resolve autoridade autenticada de produção,
revogação/anti-rollback, recuperação durável, coordenação dos writers, integração,
release ou preflight operacional. Não habilitar providers nem alterar trading.

## Referências locais e verificação desta entrega

- C3_OFFLINE_CONTINUITY_20260911.md: fechamento e evidência V2 prevalecem sobre histórico.
- C3_VALIDACAO_FISICA_RETOMADA_20260919.md: separação original entre A e B.
- .offline_releases/aws_synthetic_lab_20260913/CLOCK_DEPENDENCIES.md: limites da receita existente.
- .offline_releases/aws_synthetic_lab_20260913/clock_sample.c: saídas e recusas atuais.

Preparação inicial somente local; a seção de viabilidade registra as consultas
públicas posteriores e a interação autorizada no Centro de Suporte.
Nenhum teste executado, secret acessado, chamada operacional, commit/push/deploy
ou alteração de trading.
Nenhum código operacional alterado. A receita de execução continua pendente;
este planejamento não deve ser tratado como homologação ou prontidão.
