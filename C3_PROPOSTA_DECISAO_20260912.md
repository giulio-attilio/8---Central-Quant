# Central Quant — proposta técnica para decisão

Data: 12/09/2026. Escopo: decisão documental sobre a infraestrutura da autoridade C3 e o caminho de homologação. Não autoriza compra, implantação, reparo de dados ou Live.

Estado atual: usuário autorizou o estudo documental da alternativa externa; resultado na seção 15. A mudança apenas da manutenção foi rejeitada por não preservar o domínio de armazenamento/lock. Nenhuma candidata foi aprovada para provisionamento. O suporte respondeu na seção 11; mapa temporal e passagem de validade estão nas seções 12/13. Os trechos anteriores são histórico, não nova pendência de autorização do estudo nem aprovação de implantação.

## 1. Decisão recomendada

**NO-GO para contratar ou implantar agora a infraestrutura como solução pronta para Live. GO somente para fechar a especificação técnica das dependências ainda não qualificadas.**

Existe código offline relevante e há uma arquitetura candidata, mas não foi demonstrada uma composição operacional que reúna identidade autenticada, consumo único resistente a restaurações, tempo confiável e recuperação completa. Comprar serviços não resolve automaticamente essas lacunas. Não recomendo pagar mais contando que o trading financiará a contratação.

Minha recomendação arquitetural é preservar a Central e os serviços existentes, separar a autoridade de manutenção da execução de trading e manter a semântica transacional PostgreSQL na referência atual. A candidata para qualificação é uma entrada autenticada por IAM/Lambda, um ledger PostgreSQL e uma testemunha de consumo independente do domínio de backup local. Essa candidata **não está homologada, não é declarada a mais barata e não está aprovada para provisionamento**.

O entregável desta rodada é esta decisão, acompanhada de custos condicionais, impedimentos verificáveis e marcos de aceite. Não é promessa de retorno a Live em uma data já conhecida.

## 2. O que está comprovado — e o que não está

O [inventário de infraestrutura](C:/Users/giuli/OneDrive/Documentos/GitHub/8---Central-Quant/.worktrees/c3_final_release_promote_20260910/C3_INFRASTRUCTURE_METADATA_INVENTORY_20260911.md) registra a inspeção somente leitura concluída às 03:13 UTC de 12/09:

- Render: workspace Hobby, um membro, serviço existente e disco de 2 GB em `/data`. A interface mostrou snapshots diários com retenção de sete dias. Nenhuma restauração foi executada.
- Upstash: Redis existente em Oregon, Pay As You Go. A interface mostrou somente a ACL `default`, ativa e ampla; Daily Backup desativado e nenhuma entrada na lista consultada. Isso não prova ausência de persistência, replicação ou cópias externas, nem identifica a credencial efetivamente usada pela Central.
- Não foi demonstrada, nesses recursos, uma autoridade C3 autenticada com recuperação e consumo único qualificados. Isso é ausência de comprovação, não afirmação de impossibilidade técnica dos produtos.

No código local, o [gate do preflight](C:/Users/giuli/OneDrive/Documentos/GitHub/8---Central-Quant/.worktrees/c3_final_release_promote_20260910/main.py:56906) exige o vetor completo: coordenação habilitada e pronta, ativação runtime permitida, exatamente 19 writers registrados, todos registrados, zero mutações em andamento, lock compartilhado, armazenamento de lease, interlock do Registry, recibo de ativação, hashes, rollback, recuperação de startup e kill switch válidos. Não basta `coordination_ready=true`.

Esse é um fato sobre a fonte local, **não um resultado atualizado do preflight em produção**. O selo “Live” do Render também não comprova trading real habilitado ou seguro.

Os testes offline anteriores demonstram propriedades de contratos e composições sintéticas. Não demonstram latência, relógio, IAM, TLS, recuperação ou durabilidade dos serviços reais. Não serão somados para produzir um percentual de prontidão.

## 3. Arquitetura de referência e reutilização

| Componente | Decisão proposta | Limite atual |
| --- | --- | --- |
| Central, Registry e Redis existentes | Preservar; não migrar nem desligar nesta etapa | Reutilização não certifica a autoridade C3 |
| Coordenador, locks de arquivo e leases duráveis | Reutilizar o desenho existente e exigir a mesma instância na composição | Falta qualificação de todos os writers e da recuperação física |
| Entrada da autoridade | Qualificar chamada IAM a versão fixa de Lambda, sem endpoint público alternativo | Provedores e composição operacional ainda não homologados |
| Ledger de manutenção | Manter a semântica PostgreSQL da referência | Permissões, TLS, transações e recovery precisam de prova no alvo |
| Testemunha de consumo | Estado autenticado independente da restauração local, com retenção suficiente contra replay | Serviço, protocolo e recuperação conjunta ainda não qualificados |
| Fonte temporal | Definir e provar intervalos de tempo com incerteza e deadlines locais conservadores | Bloqueador técnico aberto; não basta usar o relógio do processo |

A separação de manutenção é obrigatória: uma autorização para reparar ou reconciliar não pode conceder permissão de iniciar runtime/trading. O código já contém essa distinção; provisionamento não deve contorná-la.

O [ledger de autorização existente](C:/Users/giuli/OneDrive/Documentos/GitHub/8---Central-Quant/.worktrees/c3_final_release_promote_20260910/trade_registry_c3_maintenance_authorization_v1.py) explicita que o SQLite local não é proteção contra rollback e exige consumo independente antes do registro local. As variantes de autoridade pública não se tornam compatíveis com todos os bindings legados apenas por terem nomes ou campos semelhantes. A composição exata precisa ser resolvida pela engenharia.

Não recomendo, nesta decisão, substituir PostgreSQL por DynamoDB de forma transparente: a alternativa muda semântica e recovery, exigindo qualificação própria. Também não recomendo tratar Redis ou hashes fornecidos pelo chamador como autoridade autenticada pronta. Cinco chaves KMS são uma hipótese da candidata anterior, não requisito universal do C3.

## 4. Contratos operacionais que precisam ser fechados

### Identidade e permissões

A entrada deve autenticar a identidade específica do serviço, com condições de emissor, audiência e subject, e autorizar apenas a versão fixa da função prevista. O chamador não deve poder assinar como a autoridade, alterar políticas, apagar evidências ou administrar chaves. Emissão, revogação, reserva e recibo precisam de responsabilidades separadas, mesmo quando a implementação permitir compartilhar algum recurso.

O OIDC gerenciado do Render é uma opção documentada para planos Pro ou superiores; sua configuração implica mudanças posteriores no serviço. Isso não torna o upgrade obrigatório para qualquer arquitetura nem autoriza fazê-lo agora. [Documentação Render OIDC](https://render.com/docs/oidc).

IDs, versões e epochs devem ser concretos e vinculados a uma raiz autenticada, com rotação e recuperação definidas. Alias mutável ou hash declarado pelo próprio solicitante não comprova origem. O ledger deve limitar o consumidor às operações necessárias, sem ownership administrativo ou poderes de apagar o histórico. Conexões PostgreSQL precisam validar certificado e hostname; indisponibilidade não autoriza reduzir TLS ou abrir acesso irrestrito.

**Aceite:** identidade errada, versão errada, raiz revogada, recibo adulterado e privilégio excedente são rejeitados; a identidade legítima executa somente a operação prevista. Política escrita sem teste no alvo não basta.

### Tempo e expiração

Os contratos combinam janelas UTC assinadas e orçamento monotônico local. A especificação deve explicar como uma janela confiável vira um deadline local sem ignorar atraso de rede, pausa do processo ou incerteza do relógio.

Uma eventual fonte remota deve autenticar a resposta, vinculá-la a um desafio e ao contexto da requisição, declarar seu intervalo de incerteza e propagar conservadoramente atraso e tempo decorrido. O intervalo observado inteiro deve estar contido na validade autorizada; mera interseção não basta. Respostas repetidas, expiradas ou com regressão não podem prolongar validade.

ClockBound é documentado para EC2 Linux e depende de medições específicas; isso não comprova a mesma garantia no Render ou Lambda. Adicionar EC2 seria nova decisão de arquitetura e custo, não item implicitamente incluído. [AWS: comparação de timestamps com ClockBound](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/compare-timestamps-with-clockbound.html).

**Aceite:** especificação quantitativa de incerteza e atraso, provedor compatível com o ambiente escolhido e ensaios de atraso, expiração, regressão e reinício. Esse trabalho é da engenharia; não cabe ao usuário escolher hashes ou inventar limites temporais.

### Recuperação e não repetição

Ao detectar restauração ou transação pendente, o startup deve impedir novas mutações até reconciliar Registry, ledger, claims consumidos e obrigações PREPARED/RESOLVED sob o mesmo coordenador e lease. Não se emite readiness antes disso. Uma resposta perdida não pode levar à execução duplicada: primeiro se consulta o resultado durável da mesma identidade de operação.

A testemunha independente deve continuar atual quando o backup local for restaurado. Se ela também tiver sido restaurada, estiver indisponível ou não comprovar frescor, o sistema entra em quarentena. Uma nova identidade/epoch só pode ser admitida após adjudicação autenticada, preservando obrigações e histórico; nunca como forma de esquecer um consumo anterior.

**Aceite:** restauração isolada, perda de resposta, reinício entre cada gravação, ledger atrasado, testemunha indisponível e restauração conjunta não permitem repetição nem readiness prematura. O ensaio offline anterior mostra por que a independência é necessária; não certifica um serviço real.

## 5. Custos: o que acrescenta, o que não substitui

O relato do usuário foi de aproximadamente US$ 100 de Render + Redis no mês e US$ 100 de ChatGPT. São despesas históricas informadas, não faturas auditadas nem valores fixos garantidos. A candidata abaixo **acrescenta infraestrutura; não substitui essas despesas**.

| Hipótese mensal da candidata híbrida | US$ | Base / ressalva |
| --- | ---: | --- |
| Workspace Render Pro | 25,00 | [Mudança oficial de planos](https://render.com/changelog/updated-plans-for-render-workspaces) |
| Compute PostgreSQL | 6,00 | Referência histórica da proposta anterior; cotação atual pendente |
| Armazenamento PostgreSQL, 5 GB × 0,30 | 1,50 | Hipótese anterior; cotação atual pendente |
| Cinco chaves KMS × 1,00 | 5,00 | Hipótese de quantidade; [preço KMS](https://aws.amazon.com/kms/pricing/) |
| NAT, 730 h × 0,045 | 32,85 | Exemplo publicado para Ohio, não cotação confirmada de Oregon |
| Um IPv4 público, 730 h × 0,005 | 3,65 | [Preços VPC/NAT/IPv4](https://aws.amazon.com/vpc/pricing/) |
| Um secret armazenado | 0,40 | [Secrets Manager](https://aws.amazon.com/secrets-manager/pricing/) |
| **Subtotal condicional** | **74,40** | **Não é orçamento fechado nem teto** |

Faltam cotar consumo de Lambda, capacidade e armazenamento da testemunha, chamadas KMS/Secrets Manager, tráfego/NAT, logs, retenção, backups, impostos, redundância e eventual serviço temporal. O cálculo supõe um NAT e um IPv4; não inclui alta disponibilidade. O número não deve ser apresentado como preço confirmado na região final.

Os valores anteriormente discutidos de US$ 30 ou US$ 44,50 não são o custo completo desta candidata. O serviço de API Render da alternativa anterior não foi somado novamente, pois a entrada candidata é Lambda. Não prometo uma solução de US$ 30 pronta para Live.

Preparar esta decisão não contrata infraestrutura adicional. As despesas existentes e o uso do assistente continuam sujeitos aos planos atuais. Não há economia prometida nem justificativa para ativar trading para pagar serviços ainda não qualificados.

## 6. Marcos cobráveis até uma decisão de Live

| Marco | Responsável pela entrega | Evidência necessária para encerrar |
| --- | --- | --- |
| M0 — proposta para decisão | Agente | Este documento: recomendação, custos condicionais e bloqueadores explícitos |
| M1 — especificação fechada | Engenharia/agente | Uma candidata única com identidade, tempo, recovery, interfaces exatas, critérios negativos e custo completo; ou rejeição fundamentada da candidata |
| M2 — autorização operacional delimitada | Usuário, após M1 | Aprovação da topologia, teto de gasto e escopo de homologação; não um OK genérico |
| M3 — homologação isolada | Engenharia/operador autorizado | Testes no alvo sem dados reais nem trading, incluindo falhas, restore e TLS; evidências sanitizadas |
| M4 — composição runtime e release | Engenharia, com autorização específica | Mesmas instâncias, 19 writers, recuperação, rollback e gate completo; revisão e release controlado |
| M5 — preflight de produção | Operador autorizado | Evidência atual de todos os gates, sem ordens e dentro do escopo autorizado |
| M6 — piloto Live | Decisão humana separada | Limites, proteção física, abortos, kill switch e observação aprovados após os marcos anteriores |

M1 não significa produzir mais um wrapper ou harness equivalente aos existentes. Deve fechar as dependências reais, ou demonstrar por que a candidata deve ser abandonada. Não repetir inspeções de conta e testes já concluídos sem uma hipótese nova e justificável.

O próximo trabalho documental útil é a especificação quantitativa da fonte temporal e da recuperação entre domínios, seguida da compatibilidade das interfaces. Não depende de novo OK para escrever. Contratação, credenciais, mudanças de infraestrutura e ensaios operacionais continuam fora dessa autorização documental.

Não há hoje base para um prazo de Live ou percentual restante confiável: os marcos têm dependências e não pesos conhecidos. **Percentual para Live: indeterminado.** Qualquer nova data deve identificar o entregável, as dependências, o critério de aceite e o responsável; não converter tempo de automatismo em previsão de prontidão.

## 7. O que fazer agora e limites desta entrega

O usuário não precisa comprar nada, criar chaves, alterar Render ou enviar outro OK para receber esta proposta. A recomendação imediata é manter o estado operacional sem mudanças e usar M1 como próximo critério de cobrança técnica.

Riscos residuais: arquitetura candidata pode não satisfazer os contratos; custo final pode superar o subtotal; fonte temporal pode exigir outra topologia; recuperação conjunta pode exigir adjudicação manual; restrição de ACL sem inventário pode interromper a Central. Backup e privilégio mínimo são importantes, mas não substituem autenticação e proteção contra replay. Não restringir diretamente a ACL `default` nesta etapa.

Nesta rodada documental: nenhum código operacional foi alterado; nenhum teste, servidor, bot ou processo de trading foi executado; nenhum secret foi acessado; não houve chamadas operacionais a contas ou serviços, mudanças de permissões, flags, commit, push ou deploy. Houve consulta a documentação pública primária. Validação limitada a leitura do documento, existência das referências locais e conferência aritmética.

Referência de histórico e alternativas, não substituto desta decisão: [proposta anterior](C:/Users/giuli/OneDrive/Documentos/GitHub/8---Central-Quant/.worktrees/c3_final_release_promote_20260910/C3_AUTHORITY_INFRASTRUCTURE_PROPOSAL_20260910.md).

Modelo recomendado para M1: GPT-6 Astra, esforço Alto. Automatismo mantido ativo conforme a configuração verificada; isso agenda retomadas, não significa execução técnica contínua quando não há rodada em andamento.

## 8. Avanço M1 — especificação temporal e recuperação, 12/09 03:36 UTC

Esta seção acrescenta uma derivação de projeto, não implementação ou homologação. Não repete a suíte temporal concluída. Fecha a regra de propagação que um provedor candidato precisaria satisfazer e diferencia consumo de autorização de conclusão do reparo.

### 8.1 Intervalo remoto: hipótese física explícita

Seja `q` o contador monotônico local em milissegundos. Para transportar uma observação remota com validade finita, é necessário um limite certificado `a > 0` para seu avanço mínimo: em todo trecho admitido, `Δq >= a × Δt_real`. Usar `a <= 1` é conservador. Resolução e erro de leitura entram em uma margem não negativa `ε`. **Esses parâmetros não foram comprovados para o ambiente Render/Lambda escolhido.** Detectar regressão não prova que o contador avançou durante suspensão ou pausa relevante.

Protocolo candidato:

1. Antes de enviar o desafio imprevisível, registrar `q_s` e a identidade da sessão local. A resposta autenticada vincula desafio, contexto, identidade/epoch do provedor e intervalo UTC `[L_s,U_s]`, amostrado depois de receber aquele desafio. Resposta em cache sem esse vínculo não serve.
2. Após receber e verificar a resposta inteira, registrar `q_v`. Com contador qualificado, o atraso real entre envio e verificação é no máximo `T = ceil((q_v-q_s)/a + ε)`. A amostragem ocorreu dentro desse percurso; portanto `[L_s, U_s+T]` é um intervalo conservador na verificação. Não descontar metade do RTT nem presumir rede simétrica.
3. Em cada checagem posterior `q_i`, atualizar o teto para `U_i = U_s + ceil((q_i-q_s)/a + ε)`; manter `L_i=L_s` é conservador, embora possa recusar mais operações. Amostra nova nunca renova o deadline já admitido.
4. Validar o intervalo inteiro dentro da validade: `N <= L_i <= U_i < E`. Não basta haver interseção parcial. Também exigir `U_i-L_i <= W`, com `W` aprovado e demonstrável, não copiado dos fixtures.

Se `a` não tiver limite positivo, ou se uma suspensão invalidar essa hipótese sem ser detectada, não há teto finito comprovado para `T`. **A resposta deve ser recusada; assinatura e relógio remoto correto não corrigem esse problema do consumidor.** Reinício invalida a sessão e seus deadlines, não recupera o orçamento inicial.

A escala de tempo também deve ser comum aos emissores e ao consumidor. A AWS documenta smear de leap seconds no NTP e comportamento diferente no PTP. Não misturar os dois como se fossem a mesma escala durante o evento; exigir mapeamento conservador com erro incluído no intervalo ou recusar a janela afetada. As fórmulas pressupõem essa escala compatível. [AWS: sincronização e leap seconds](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/set-time.html).

O [cálculo offline existente](C:/Users/giuli/OneDrive/Documentos/GitHub/8---Central-Quant/.worktrees/c3_final_release_promote_20260910/trade_registry_c3_public_authority_offline_v2.py:42) recebe `[L,U]` pronto; não implementa nem autentica este protocolo. Seus limites de 300 s para a janela e 5 s para o orçamento são limites do experimento, não política de produção aprovada.

### 8.2 Deriva, deadline e momento do efeito

No ponto de checagem, sejam `B` os milissegundos locais restantes até o último deadline e `R=min(5000,B,E-U_i)`. A função existente calcula esse `R` sob suas premissas sintéticas. Para o provedor físico candidato, uma conversão conservadora, quando `0<a<=1`, é `δq=floor(a×(R-G))`, em que `G>=0` cobre a margem real qualificada entre a última checagem e o evento cuja validade se pretende garantir. Exigir `R>G`, `δq>0` e reduzir o deadline a `min(D_anterior,q_i+δq)`.

Isso não transforma checagens cooperativas em interrupção física. Se o efeito puder ocorrer sem limite após a checagem, não existe `G` finito demonstrado: o contrato precisa de enforcement no receptor ou deve limitar sua afirmação à admissão/aceitação do recibo. No consumidor atual, commit tardio ou ambíguo pode consumir o claim e impedir recibo; **não se promete que timeout desfaça o commit**. Revalidar antes de usar uma permissão continua obrigatório.

Exemplo apenas aritmético: com `a=0,9999`, `ε=0`, percurso de 80 ms locais e intervalo remoto de largura 10 ms, o teto de atraso é 81 ms e a largura propagada é 91 ms. Se `R=2000 ms` e `G=50 ms`, admitir no máximo 1949 ms locais. Os números ilustram a fórmula; não são SLA medido, configuração recomendada ou prova de que 100 ms de largura sejam viáveis.

Decisão temporal: não aprovar a candidata com `datetime.now`, observação UTC fornecida pelo chamador ou transporte remoto que ignore o contador local. ClockBound oferece uma referência documentada para EC2 Linux; não certifica este consumidor em Render/Lambda. [AWS ClockBound](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/compare-timestamps-with-clockbound.html). Uma alteração de hospedagem para resolver isso precisa entrar no desenho e no orçamento, não ser escondida em uma dependência.

Busca pública focal desta rodada não encontrou uma especificação suficiente desses limites no Render/Lambda. Isso não prova que seja impossível obtê-la. Não se converte precisão habitual em garantia: a próxima evidência aceitável precisa declarar limites e falhas detectáveis, ou motivar outra fronteira de execução. Consultar repetidamente a mesma página de ClockBound sem resolver o lado consumidor não constitui avanço.

### 8.3 Recuperação: matriz normativa da candidata

A chave de não repetição é `(namespace, claim)`, preservada entre rotação de assinatura e restauração. O claim atual deriva de escopo, raiz e nonce; trocar validade ou assinatura não deve recriar uma autorização. Alterar namespace/raiz não é mecanismo autorizado de retry.

| Observação autenticada, após bloquear admissão | Decisão segura |
| --- | --- |
| Testemunha atual sem claim; ledger sem claim; sem operação anterior pendente | Elegível para nova solicitação somente após todos os demais gates; ausência de linha isolada não comprova esse cenário |
| Testemunha tem claim; ledger não tem linha | Claim permanece queimado; investigar reserva sem commit ou restore do ledger; não retomar assinatura nem repetir execução |
| Testemunha tem claim; ledger tem digest correspondente | Consumo confirmado, não sucesso do reparo; não assinar novamente. Reconciliar o estado da operação separadamente |
| Ledger tem claim, mas testemunha atual não o reconhece | Violação de consistência: quarentena, sem exclusão da linha, nova permissão ou readiness |
| Digests, identidade ou geração divergem | Quarentena e adjudicação autenticada; não escolher automaticamente o registro mais conveniente |
| Testemunha indisponível, restaurada ou sem prova de atualidade | Nenhuma conclusão de ausência pode ser aceita; manter bloqueio mesmo que o ledger local pareça limpo |
| Qualquer obrigação PREPARED/UNRESOLVED ou efeito ambíguo | Reconciliar pelas evidências duráveis da própria operação sob o mesmo coordenador/lease; consumo por si só não resolve a obrigação |

O [consumidor PostgreSQL](C:/Users/giuli/OneDrive/Documentos/GitHub/8---Central-Quant/.worktrees/c3_final_release_promote_20260910/trade_registry_c3_postgres_consumption_offline_v1.py) guarda namespace, claim e digest, não o resultado completo do reparo. O [consumidor público](C:/Users/giuli/OneDrive/Documentos/GitHub/8---Central-Quant/.worktrees/c3_final_release_promote_20260910/trade_registry_c3_public_authority_offline_v2.py:641) reserva antes do commit e não compensa a reserva após falha. Logo, o runbook deve distinguir **autorização consumida**, **recibo aceito localmente** e **reparo concluído**. Não inferir os dois últimos a partir do primeiro.

A recuperação precisa de uma consulta autenticada e atual ao claim e de evidência durável do efeito, não de reexecução do endpoint de consumo. São requisitos de portas operacionais futuras; não existem como serviço comprovado nesta rodada. O ledger mínimo não reconstrói um recibo perdido, e o contrato atual proíbe reemiti-lo. Uma reserva órfã exige tratamento operacional explícito, não exclusão automática.

Retenção: não apagar tombstones de consumo apenas porque a janela assinada expirou. Backups antigos, mudanças de chave e novas validades não podem tornar o claim reutilizável. Desativação de um namespace exige invalidação durável também dos caminhos de restauração e preservação da cadeia de adjudicação.

### 8.4 Compatibilidade real das interfaces e encerramento desta análise

A emissão/recepção V3 completa está em funções de **harness de teste**, em [test_c3_public_authority_wire_offline_v2.py](C:/Users/giuli/OneDrive/Documentos/GitHub/8---Central-Quant/.worktrees/c3_final_release_promote_20260910/tests/test_c3_public_authority_wire_offline_v2.py:633), não em um consumidor operacional V3 pronto. O [autorizador V1](C:/Users/giuli/OneDrive/Documentos/GitHub/8---Central-Quant/.worktrees/c3_final_release_promote_20260910/trade_registry_c3_maintenance_authorization_v1.py:150) espera um mapping específico, verificadores de tipo exato, binding local e recibo V1. Um DTO V3 ou um retorno `bounded` do harness não atende esse contrato.

Decisão de compatibilidade: proibir conversão por renomeação de campos e fallback V3→V1/V2. A futura implementação deve assumir explicitamente a fronteira V3, separar validade UTC de deadline local, preservar o consumo único e demonstrar a vinculação ao coordenador. Não importar funções de teste como provider nem enfraquecer os checks atuais para fazê-las passar.

Resultado desta extensão: regras matemáticas, matriz de recuperação e incompatibilidade concreta documentadas. **M1 permanece parcial**, pois ainda faltam um provedor temporal que satisfaça as hipóteses físicas, portas autenticadas de recuperação e cotação completa dessa topologia. Não se criarão mais fixtures para declarar essas provas concluídas. Prosseguir apenas com evidência técnica nova que possa qualificar ou eliminar uma candidata, ou com escopo operacional específico; nenhum novo OK genérico resolve essas lacunas.

## 9. Decisão de hospedagem e informação externa necessária

### 9.1 Mover somente a autoridade não qualifica a cadeia inteira

A [composição local de manutenção](C:/Users/giuli/OneDrive/Documentos/GitHub/8---Central-Quant/.worktrees/c3_final_release_promote_20260910/trade_registry_c3_maintenance_activation_offline_v1.py:222) cria o deadline local, chama o autorizador e verifica novamente os controles antes e depois de cada fase. Quando recebe um coordenador existente, exige a mesma função de relógio e as mesmas dependências físicas. Portanto, mover somente o consumidor da autoridade de Lambda para EC2 não prova a validade dos prazos no lado que continuará junto à Central. Esta é uma conclusão do fluxo local, não uma medição de produção.

**Distinção importante:** o [permit do coordenador](C:/Users/giuli/OneDrive/Documentos/GitHub/8---Central-Quant/.worktrees/c3_final_release_promote_20260910/trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1.py:419) verifica frame ativo, instância, processo/thread, handle físico não liberado, lease QUIESCED e epoch. Não é um lease distribuído que concede ownership só porque um TTL acabou. O lock fica mantido durante a manutenção. A lacuna temporal não demonstra, por si só, possibilidade de dois writers simultâneos ou falha operacional atual.

Os [adaptadores de armazenamento](C:/Users/giuli/OneDrive/Documentos/GitHub/8---Central-Quant/.worktrees/c3_final_release_promote_20260910/trade_registry_closed_identity_conflict_repair_writer_runtime_storage_adapters_v1.py:125) também usam contadores locais para limitar espera por lock e tentativas de replace. Esses timeouts precisam ser separados da validade da autorização na homologação. Não transformar todos os relógios em uma única dependência remota nem trocar timestamps locais por UTC indiscriminadamente.

Decisão: **não adicionar uma instância EC2 como correção isolada**. Para recomendá-la, seria preciso explicar a garantia temporal em todos os pontos de admissão e efeito, ou alterar deliberadamente a fronteira de execução. Não está autorizada uma migração da Central/Registry, nem mudança de semântica para eliminar requisitos de validade. O orçamento de US$ 74,40 não contempla essa migração.

### 9.2 Evidência nova sobre ClockBound e limites

O repositório oficial descreve daemon e cliente locais, com intervalo de incerteza e estado de sincronização. Não é um endpoint HTTPS pronto de autoridade temporal. O README consultado apresenta exemplo com versão `3.0.0-alpha.0`; isso não é seleção de versão aprovada para produção. [AWS ClockBound, repositório](https://github.com/aws/clock-bound).

A documentação do daemon descreve VMClock para detectar perturbações de relógio em manutenção de máquinas virtuais. A disponibilidade depende de kernel e suporte efetivo do provedor; instalar uma biblioteca não comprova presença do dispositivo. O daemon exige privilégios para a operação documentada. Nada disso foi instalado ou testado nesta rodada. [AWS ClockBound, daemon e VMClock](https://github.com/aws/clock-bound/blob/main/docs/clockbound-daemon.md).

Essa evidência torna a investigação objetiva: precisamos saber quais garantias e sinais o consumidor realmente pode usar no ambiente gerenciado. Não assumir que a indicação geral de sincronização por NTP forneça limites de erro, detecção de suspensão ou acesso ao estado necessário. Também não afirmar que esses recursos são impossíveis no Render só porque não foram encontrados nas páginas consultadas.

### 9.3 Consulta técnica preparada — não enviada

Destinatário proposto: suporte técnico do Render. Sem nomes de estratégias, conteúdo do Registry, endpoints privados, identificadores de conta, credenciais ou anexos operacionais. A mensagem abaixo pode ser enviada somente após autorização específica de comunicação externa; nenhum ticket foi criado.

Assunto: Garantias de relógio e detecção de descontinuidade em Web Service Linux

Estamos avaliando uma função de manutenção que deve recusar permissões expiradas e interromper admissão quando a referência temporal deixa de ser confiável. Antes de contratar recursos adicionais, precisamos confirmar:

1. Existe especificação documentada de erro máximo do relógio civil disponível no container e uma forma suportada de observar erro/estado de sincronização por leitura? Uma estimativa típica ou percentil não substitui limite e condição de validade.
2. Para contadores monotônicos Linux usados pela aplicação, quais garantias e sinais existem durante suspensão, manutenção, troca de host ou alteração da referência de hardware? É possível detectar descontinuidade e invalidar a sessão antes de admitir novas ações?
3. Há acesso suportado a VMClock, PHC, estado de sincronização do host ou mecanismo equivalente? Não queremos presumir acesso privilegiado ou instalar um daemon que ajuste o relógio do host.
4. Qual escala e tratamento de leap seconds são usados, e como mudanças de sincronização são comunicadas à aplicação?
5. Caso essas garantias não sejam oferecidas no produto, podem confirmar explicitamente a limitação e indicar eventual modalidade suportada, com requisitos e custos? Não solicitamos alteração de plano ou configuração.

**Critério de decisão após a resposta:** informação suficiente permite fechar as hipóteses e preparar homologação isolada; resposta negativa elimina a candidata que depende dessas garantias; resposta genérica sobre horário normalmente correto mantém o NO-GO. A engenharia interpreta e documenta a resposta — não transfere ao usuário a escolha de parâmetros ou de hashes.

### 9.4 Limite do avanço atual

Concluída a análise da mudança isolada para EC2 e preparada a consulta. Não há provedor temporal ponta a ponta homologado nem orçamento operacional completo. A próxima evidência para esta candidata depende de informação do fornecedor não presente nas fontes consultadas e, depois, de ensaio autorizado no ambiente alvo. A autorização atual para documentação pública e IAM limitado não autoriza enviar tickets ou mensagens em nome do usuário.

Não contratar, instalar ClockBound, modificar IAM/Render, migrar dados ou alterar gates para contornar a pendência. Não repetir estas análises em cada heartbeat. Manter o automatismo ativo e silencioso quando não houver informação nova ou outro trabalho independente necessário; não alegar implementação contínua durante essa espera.

## 10. Consulta enviada e escalonada ao suporte humano — 12/09/2026

O usuário respondeu “Sim” ao pedido específico de envio ao suporte Render sem credenciais, dados operacionais, contratação ou mudanças na conta. A consulta foi enviada pelo botão Contact support do dashboard autenticado, em inglês, preservando as cinco perguntas da seção 9.3 e a proibição expressa de mudança de plano, provisionamento, configuração ou cobranças. Nenhum arquivo foi anexado; nenhum log, secret ou conteúdo do Registry foi incluído. O contato fica naturalmente associado à sessão de suporte da conta, mas não foram inseridos identificadores operacionais na mensagem.

Envio confirmado pela mensagem visível na conversa, posteriormente marcada Seen. Assunto: **Clock guarantees and discontinuity detection in Linux Web Services**. Canal: [dashboard Render, Contact support](https://dashboard.render.com/). A interface não exibiu número de ticket nem link direto da conversa; não inventar identificador.

A primeira resposta veio do **AI Agent**, não de um engenheiro. Ela afirmou não haver garantias ou mecanismos documentados para os pontos de relógio, mas marcou as conclusões centrais como `[No source]`. Portanto, não foi aceita como comprovação definitiva de capacidade ou limitação do produto.

Foi enviado um único follow-up pedindo confirmação humana ou especificação aplicável, sem dados adicionais nem autorização de gastos. O atendimento então confirmou que escalonou a consulta à equipe. Informou que a resposta não seria imediata e que notificaria pelo próprio chat e por e-mail. **Não foi informado prazo de resposta.** Não há resposta técnica humana observada até a leitura de aproximadamente 03:51 UTC de 12/09.

O automatismo existente foi mantido ACTIVE e ajustado para ler somente esta conversa de suporte, no máximo a cada 15 minutos, sem reenviar mensagens, abrir outros tickets ou acessar configurações/dados. A frequência geral das retomadas permanece inalterada. A próxima checagem fica não antes de 04:06 UTC de 12/09, dependendo de app, máquina, sessão e uso disponíveis. Notificar somente resposta material, falha que exija ação ou decisão necessária.

Ao receber a resposta humana, confrontá-la com as hipóteses e critérios das seções 8 e 9. Uma resposta de suporte não é, por si só, homologação física ou autorização Live. Respostas genéricas mantêm a lacuna explícita; não comprar recursos ou flexibilizar gates por inferência.

Nesta rodada, as habilidades de navegação e OpenAI Docs orientaram a verificação do envio e a atualização do acompanhamento existente. Houve comunicação externa autorizada ao suporte e consulta de documentação pública. Não houve acesso a secrets, dados operacionais, execução de testes ou processos de trading, alterações de código/flags/infraestrutura, commit, push ou deploy. Os únicos arquivos locais editados foram esta proposta e a continuidade; o prompt da automação foi atualizado pelo recurso próprio do aplicativo.

## 11. Resposta humana e decisão — leitura em 12/09/2026 21:21 UTC

Jason, identificado na conversa como atendente humano, informou que não responderia às perguntas detalhadas, confirmou que os sistemas usam NTP e indicou que a aplicação deve verificar desvios relevantes. Não forneceu especificação, limite de erro, sinais de descontinuidade ou alternativa suportada. Fonte: mesma conversa no [dashboard Render, Contact support](https://dashboard.render.com/), agora intitulada **Clock accuracy guarantees**; identidade confirmada pelo texto original e follow-up. A UI mostrava resposta de 15h atrás; não há horário exato confirmado nem número de ticket.

### 11.1 O que a evidência fecha — e o que não fecha

| Exigência das seções 8/9 | Evidência recebida | Decisão |
| --- | --- | --- |
| Limite UTC e estado de sincronização observável | Apenas confirmação de NTP | Não demonstrada |
| Limite de avanço do contador e detecção de perturbação | Nenhuma especificação | Não demonstrada |
| Escala/leap seconds e margem até efeito | Nenhuma especificação | Não demonstrada |
| Recuperação durável e prevenção de replay | Fora da resposta | Continua pendente, independentemente do relógio |

Verificar diferença entre dois relógios pode detectar alguns desvios; essa resposta não demonstra um limite absoluto nem continuidade do contador entre verificações. Não interpretar a menção a segundos como tolerância contratual aprovada. Também não interpretar a recusa em detalhar como prova de impossibilidade física ou defeito em produção.

**Decisão: encerrar a espera por esta consulta e rejeitar, para provisionamento, a candidata que depende dessas garantias ainda não demonstradas no consumidor Render.** Não contratar a topologia condicional de US$ 74,40, não alterar o ambiente atual e não liberar Live com base nessa resposta. Isso encerra a avaliação desta premissa da candidata; não fecha toda a especificação M1 nem recomenda automaticamente migração.

### 11.2 Próxima decisão técnica, sem compra ou mudança de contrato

Antes de propor outro serviço, executar uma revisão focal offline da necessidade: para cada requisito temporal, identificar a origem no contrato, o risco evitado e o ponto real de admissão/efeito. Separar expiração de autorização assinada, prazo cooperativo de execução e exclusão física de writers — propriedades diferentes. O fato de o suporte não fornecer limites não autoriza reduzir nenhuma delas.

Critério de aceite dessa revisão: mapa rastreável dos requisitos ao código existente, distinção entre requisito operacional e hipótese de fixture, e conclusão fundamentada sobre manter a exigência ou submeter uma mudança explícita de arquitetura/semântica à decisão humana. Não implementar mudança, criar novo harness, presumir parâmetro físico ou repetir a comparação de EC2 isolado. A revisão documental não requer novo OK; qualquer nova contratação, migração ou integração segue sem autorização.

O automatismo permanece ativo, com esta revisão como continuidade e sem polling repetitivo da conversa já respondida. As habilidades de navegação e OpenAI Docs orientaram leitura e ajuste do acompanhamento. Nenhuma mensagem nova foi enviada. Apenas documentos locais e o prompt de continuidade foram alterados; sem secrets, dados operacionais, código/testes, flags, ordens, infraestrutura, commit, push ou deploy. Percentual restante para Live: indeterminado.

## 12. Mapa dos requisitos temporais — revisão offline em 12/09 21:27 UTC

Inspeção estática dos arquivos da worktree; nenhum módulo foi importado ou executado. Os caminhos abaixo são relativos à worktree deste documento; números são linhas observadas nesta revisão, não referências a uma versão publicada.

| Propriedade e risco evitado | Origem e ponto de verificação | Natureza e decisão |
| --- | --- | --- |
| Recusar autorização fora da validade, inclusive observação que cruza a expiração | `trade_registry_c3_public_authority_offline_v2.py:42`, especialmente 59–64; request V3 em 68–104 | Propriedade necessária do protocolo V3 proposto. O intervalo é recebido pronto; a função não autentica o relógio. Manter recusa integral; não afirmar que o runtime já a executa |
| Limitar largura de incerteza a 100 ms | `tests/test_c3_public_authority_wire_offline_v2.py:633`, chamada em 665 | Valor literal do harness. A função do módulo experimental offline recebe a largura como argumento, não fixa 100. Não há demonstração nesta cadeia de que Live exija precisão de 100 ms. Não converter fixture em SLA ou motivo isolado para comprar infraestrutura |
| Janela de até 300 s e orçamento de até 5 s | `trade_registry_c3_public_authority_offline_v2.py:59`, 64, 104, 739 e 783 | Caps codificados do experimento, não tolerância ao erro de relógio. Continuam obrigatórios para usar este contrato tal como está; escolha operacional ainda precisa ser fundamentada, não alterada nesta revisão |
| Limitar manutenção e recusar resultado atrasado | `trade_registry_c3_maintenance_activation_offline_v1.py:34`, 113–136, 222 e 273–298 | Default 30 s, lock 1 s, máximo configurável 300 s. Checagens cooperativas antes/depois de callbacks e após release. Não há interrupção forçada nem promessa de desfazer efeito após timeout |
| Não emitir recibo após consumo/commit tardio | `trade_registry_c3_public_authority_offline_v2.py:694`, 703–716; `trade_registry_c3_maintenance_authorization_v1.py:238`, 258–268 | A reserva ou commit podem preceder a recusa final. Manter claim consumido e reconciliação; prazo excedido não equivale a ausência de escrita |
| Exclusão de writers durante manutenção | `trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1.py:419`, 471–557 | Mesma instância/frame/thread/processo, handle não liberado, lease QUIESCED, epoch/inventário e zero inflight. Não é concessão que expira por TTL UTC. Precisão de 100 ms não é premissa desse predicado |
| Tempo máximo de espera pelo lock | `trade_registry_closed_identity_conflict_repair_writer_runtime_storage_adapters_v1.py:179`, 200–209; handle em 89–122 | Timeout controla tentativas de aquisição; o handle adquirido é liberado explicitamente. Não confundir atraso de timeout com transferência automática de ownership. Garantias do filesystem/lock continuam a exigir homologação |
| Não reutilizar autorização após reinício/restore | `trade_registry_c3_maintenance_authorization_v1.py:150`, 233–268; claim V3 em `trade_registry_c3_public_authority_offline_v2.py:116` | Claim não depende de validade nem de nova assinatura; consumo independente e retenção continuam exigidos. Melhor relógio não substitui histórico durável/anti-rollback |

### 12.1 Fronteira real: V3 ainda não autoriza a composição

O receptor V3 em `tests/test_c3_public_authority_wire_offline_v2.py:633` retorna somente diagnóstico e durações. Seu docstring diz expressamente que não emite permit, não autentica fonte temporal e não mantém estado entre chamadas. O request V3 também declara, em `trade_registry_c3_public_authority_offline_v2.py:68`, que não é autorização de execução.

A composição recebe de `_authorize(request, binding)` apenas `True`/`False` (`trade_registry_c3_maintenance_activation_offline_v1.py:240`). O deadline da manutenção já foi criado em 222 e continua sendo usado em 274/281/282. Portanto **não existe nesta interface retorno que carregue o vencimento epoch V3 ou reduza o deadline da manutenção ao orçamento calculado pelo receptor V3**. Isso é uma lacuna de uma futura composição, não evidência de bypass atual: V3 não está integrado. O binder em `main.py:33465` aceita exatamente o autorizador V1; `main.py:33490` impede iniciar runtime quando a composição de manutenção está vinculada.

Há ainda uma premissa de escala a explicitar antes de qualquer provider: o autorizador V1 passa `int(now)` como `now_epoch` ao revogador (`trade_registry_c3_maintenance_authorization_v1.py:176`), enquanto o binding utiliza o deadline do relógio injetado da composição. Não presumir que contador monotônico seja UTC nem ligar um provider remoto por mera compatibilidade de tipos. Esta revisão não determina defeito em produção; nenhuma configuração real foi lida.

### 12.2 Conclusão e decisão recomendada

**Manter as garantias de validade, não repetição, coordenação e falha fechada; não exigir nem comprar, por enquanto, uma solução de precisão de 100 ms como condição universal para Live.** O valor é sintético, e exclusão de writers é outra propriedade. A rejeição da candidata na seção 11 continua válida pela falta de prova das premissas daquela candidata, não por uma impossibilidade geral do Render.

O próximo resultado necessário é definir documentalmente a passagem de validade V3 para a admissão local: quais evidências autenticadas chegam, qual deadline só pode diminuir, em quais fronteiras a validade é rechecada e como tratar efeito tardio/ambíguo sem retry. Não retornar um simples booleano e alegar que o prazo remoto automaticamente rege toda a manutenção. Não usar o helper de testes como provider.

Para evitar uma promessa inexistente, distinguir no desenho: (a) admissão e aceitação de resultados dentro da validade; (b) conclusão física de todo efeito antes da expiração. A composição atual só oferece checagens cooperativas. A garantia (b), se requerida, precisa de enforcement no ponto do efeito e tratamento de resultados ambíguos; não pode ser prometida por uma troca de relógio. Qualquer mudança de semântica, integração ou provisionamento será submetida separadamente, sem executar nada agora.

Revisão focal concluída. Não é homologação ou remoção de gate de preflight. Validação: leitura estática das funções e pontos de chamada citados; nenhum teste repetido porque não houve alteração de código. Apenas esta proposta e a continuidade foram editadas. Nenhum secret ou dado real acessado, nenhuma chamada externa, nenhum commit/push/deploy ou alteração de configuração de trading. Risco residual: fonte física e recovery ainda não qualificados, interface V3 sem composição operacional.

## 13. Passagem de validade V3 para admissão local — especificação proposta, 12/09 21:30 UTC

Esta seção é desenho para decisão, não novo contrato Python, adapter, permit ou implementação. Preserva os gates existentes e não altera os limites de 300 s/5 s do experimento. A largura de incerteza admitida depende de qualificação, não de copiar 100 ms dos testes. Reutiliza a consistência criptográfica de `trade_registry_c3_public_authority_offline_v2.py:289` e a coordenação descrita na seção 12, sem atribuir-lhes capacidades que não possuem.

### 13.1 Entradas e resultado que o booleano não transporta

A futura fronteira de autorização precisa entregar evidência verificada vinculada à tentativa, não uma duração solta. Conteúdo lógico mínimo:

| Grupo | Vínculo exigido |
| --- | --- |
| Solicitação | Escopo maintenance-only, root/namespace fixados, claim estável, digest canônico da solicitação e inventário dos 19 writers |
| Autoridade | Cadeia request/policy/head/reservation/consumption consistente, identidades/epochs fixados, desafios da tentativa e política atual não revogada |
| Consumo | Prova autenticada de primeiro consumo, digest correspondente no ledger e referência à obrigação de recovery; ausência/ambiguidade não significa autorização livre |
| Tempo comum | Janela efetiva `[N,E)` e identidade/epoch/escala da fonte qualificada; observação atual inteira `[L,U]` contida em `[N,E)`, com incerteza e atraso incluídos |
| Execução local | Mesma tentativa/sessão e mesmas instâncias confiáveis de relógio e coordenador; deadline anterior e deadline admitido, que só pode diminuir |

A cadeia histórica válida pode ser aceita repetidamente pelo verificador estático, conforme seu próprio docstring (linhas 293–297). Logo, assinatura correta não comprova frescor ou primeiro consumo. Evidência serializada não restaura sozinha a sessão local. DTOs futuros deverão ter representação protegida; não registrar assinaturas, caminhos, conteúdo operacional ou credenciais em telemetria. Nenhuma nova estrutura foi criada aqui.

### 13.2 Ordem e conservação do prazo

1. Fixar tentativa, contexto de armazenamento e deadline local inicial antes de chamadas externas. Identidade do claim deve permanecer compatível com a referência; não gerar nova identidade para repetir um efeito ambíguo.
2. Validar a cadeia, a política atual e o consumo único com dependências autenticadas. Cada chamada consome o orçamento existente. Falha depois da reserva mantém o claim consumido e exige reconciliação; não emitir recibo substituto.
3. Calcular `N=max(inícios)` e `E=min(vencimentos)` de request/policy/head/reservation. Consumo precisa estar vinculado exatamente à reservation, como exige o verificador atual. Exigir `N <= L <= U < E`; não basta assinatura, relógio pontual ou intervalo parcialmente sobreposto.
4. Derivar um limite local conservador pelas premissas qualificadas da seção 8. Na transferência entre autorização e manutenção, usar `D_novo <= min(D_anterior, D_derivado)`, na mesma escala e sessão local. Não recomeçar o orçamento ao receber evidência, entrar no lock ou mudar de fase. A conversão precisa considerar também o tempo gasto na própria validação.
5. Após a aquisição do lock e antes/depois de cada fase, revalidar prazo, fonte temporal, política atual, controles de trading, kill switch e permit da mesma instância. Uma amostra/política mais recente nunca estende `D_novo`. Regressão, mudança de sessão ou perda de confiabilidade recusam nova admissão.
6. Antes de aceitar conclusão, repetir as checagens e verificar a liberação da manutenção. Resultado tardio não vira sucesso. A limpeza necessária para liberar recursos não é nova autorização para executar reparo ou trading; falha de limpeza permanece explícita e impede readiness.

O adaptador futuro não poderá transformar esse resultado em `True` e descartar seus limites. O binding V1 permanece incompatível até uma alteração explícita e revisada da interface; não alterar `main` ou usar conversão implícita como fallback. Isto preserva a distinção entre desenho V3 e código executável atual.

### 13.3 Resultado incerto e reinício

| Evento | Consequência obrigatória |
| --- | --- |
| Recusa antes de consumo/efeito | Não admitir manutenção; não alegar que toda autoridade remota permaneceu intacta sem prova |
| Timeout ou perda de resposta durante consumo | Não executar manutenção nem tentar novo consumo; consultar evidência durável pelo mesmo claim no fluxo de recuperação autorizado |
| Callback retorna após prazo ou com resultado ambíguo | Não aceitar conclusão nem iniciar próxima fase; preservar obrigação e evidências, sem compensação ou retry automático |
| Reinício ou troca da instância local | Invalidar a evidência local de admissão; não reutilizar deadline anterior, recibo serializado ou novo nonce para repetir a ação |
| Obrigação pendente ao reiniciar | Bloquear writers e reconciliar sob coordenação e autoridade adequadas, conforme seção 8.3; nenhum estado limpo inferido de expiração |

Não se promete que qualquer efeito físico termine antes de `E`: a composição existente é cooperativa. Se essa garantia física fizer parte do contrato operacional escolhido, seu ponto de enforcement precisa ser especificado e homologado antes de integração. Uma checagem feita no cliente seguida de chamada bloqueante não basta. A especificação não relaxa a garantia; deixa sua comprovação como pré-condição, sem convertê-la silenciosamente em simples checagem de admissão.

### 13.4 Critérios de aceite e limite desta entrega

Uma futura implementação precisa recusar: evidência histórica reapresentada; claim já consumido; namespace/root/instância/coordenador trocado; UTC usado como contador ou contador usado como epoch; intervalo cruzando início/fim; resultado que chega depois do prazo; fonte temporal que perde validade; nova amostra que tenta renovar orçamento; revogação após consumo; restart entre reserva, commit e execução; obrigação PREPARED/UNRESOLVED ainda aberta. Casos sintéticos verificam regras, não certificam o provedor físico.

**Passagem de validade especificada documentalmente.** Permanecem decisões técnicas não fechadas: fonte física suportada para o executor, interface autenticada e atual de recovery da testemunha, e qualificação do ponto de efeito. Não há implementação runtime autorizada por esta entrega, nem contrato de custo novo. A próxima avaliação útil deve verificar viabilidade ponta a ponta e custo da menor topologia que satisfaça essas pré-condições; não produzir outro contrato/harness substituto nem pedir ao usuário para inventar parâmetros físicos.

Validação desta rodada: confronto com o verificador V3 e os pontos de chamada já rastreados, leitura final dos documentos. Nenhum teste executado porque nenhum código mudou. Apenas proposta e continuidade alteradas, sem secrets, dados reais, chamadas externas, processos operacionais, commit/push/deploy, configurações ou ativação Live. M1 permanece parcial; percentual restante para Live indeterminado.

## 14. Parecer final de viabilidade no escopo atual — 12/09 21:34 UTC

**Resultado: nenhuma candidata está aprovada para provisionamento, e não há base para declarar qual é a solução mínima ou mais barata que satisfaz o conjunto de requisitos.** Isso é conclusão sobre a evidência disponível, não prova de impossibilidade técnica do Render ou de qualquer provedor. A avaliação documental solicitada está entregue; a especificação operacional M1 continua incompleta.

### 14.1 Por que o custo mínimo ainda não pode ser calculado

| Opção já examinada | Lacuna que impede qualificá-la | Consequência para custo/decisão |
| --- | --- | --- |
| Usar apenas os recursos atualmente inventariados | Não há testemunha C3 autenticada/atual e recovery qualificados, nem fonte temporal do executor demonstrada | Não apresentar custo incremental zero como solução pronta |
| Candidata híbrida IAM/Lambda + PostgreSQL + testemunha independente | A entrada autenticada é um desenho; faltam tempo no executor, recuperação da testemunha e integração exata | Subtotal da seção 5 é histórico e condicional, não cotação, teto ou preço de solução homologada |
| Acrescentar EC2 somente para a autoridade | Não resolve por si só os pontos de admissão/efeito que continuam no executor Render | Não comprar como correção isolada e não somar uma instância ao subtotal como se fechasse o sistema |
| Mudar a fronteira do executor de manutenção | Ainda não foi aprovada como direção arquitetural; exige definir acesso ao Registry, todos os writers, armazenamento/locks e recovery sem enfraquecer a exclusão | Não é uma pequena troca de relógio nem migração implícita; exige decisão delimitada antes de detalhar topologia e cotação |

Nenhuma nova cotação pública ou conta foi consultada nesta rodada. Não renovar os preços antigos com a data de hoje nem descontar créditos AWS ou supor cancelamento de Render/Redis/ChatGPT. Sem uma candidata tecnicamente admissível e dimensionada, uma soma exata de serviços seria falsa precisão.

### 14.2 Dependências concretas, não mais um harness

Para fechar M1 faltam três evidências relacionadas: (1) fonte temporal utilizável pelo executor com limites e falhas detectáveis compatíveis com a validade escolhida; (2) implementação e procedimento de recovery que consultem estado autenticado/atual da testemunha fora do domínio restaurado; (3) fronteira de execução que preserve o mesmo domínio de coordenação dos writers e trate efeitos tardios/ambíguos. Escrever outro DTO, repetir testes sintéticos ou reenviar a consulta ao Render não produz essas evidências.

A escolha de um provedor, tamanho, política temporal e orçamento continua sendo trabalho técnico; não é pedido para o usuário escolher hashes, parâmetros de relógio ou detalhes de banco. A decisão humana necessária é de **escopo de arquitetura**, porque mover o local de execução pode afetar custo, operação e armazenamento da Central.

### 14.3 Direção proposta para decisão, sem execução

Recomendo avaliar uma alternativa em que a **fronteira completa de execução da manutenção**, e não apenas a autoridade de assinatura, possa usar um ambiente com relógio observável. Antes de qualquer migração, a alternativa precisa demonstrar como mantém exclusão com os writers que acessam o mesmo Registry. Não propor um escritor remoto sobre o disco ativo por suposição. Se isso exigir mover também writers/armazenamento ou alterar a semântica de validade, explicitar a expansão e rejeitar a alternativa caso ela exceda o escopo aprovado.

Decisão solicitada: aceitar ou não o estudo documental dessa mudança de fronteira. Aceitar o estudo NÃO autoriza criar recursos, chaves ou serviços, pagar, mover dados, alterar IAM/Render, implementar runtime, fazer deploy ou ativar Live. O estudo deverá entregar uma única alternativa com dependências e custo cotável, ou sua rejeição fundamentada; não iniciar outra sequência ilimitada de contratos.

Até essa decisão, não há próximo passo operacional autorizado. Manter o automatismo ativo e silencioso sem refazer o parecer; não anunciar execução técnica durante a espera. Uma informação nova e suficiente sobre o ambiente atual também pode reabrir a avaliação sem exigir mudança de hospedagem.

Somente esta proposta e a continuidade foram alteradas, conferidas por leitura. Não houve alteração de código, testes, acesso a secrets/dados reais, chamadas externas, operações de infraestrutura, commit/push/deploy ou mudanças de trading. Nenhum preço foi atualizado ou serviço contratado. Riscos residuais permanecem explícitos; Live não liberado e percentual restante indeterminado.

## 15. Estudo autorizado: manutenção fora do Render — 12/09/2026

O usuário respondeu “sim” à pergunta de estudar esta alternativa somente no papel, sem migração de produção ou gastos. A autorização da seção 14.3 está satisfeita; não solicitá-la novamente. Foram consultadas fontes públicas oficiais e o inventário de writers no código local, sem acessar contas ou dados reais.

### 15.1 Restrição física encontrada

O Render documenta que um disco persistente é acessível somente pela instância do serviço à qual está anexado; outros serviços não o acessam. Transferir arquivos é uma operação diferente de compartilhar armazenamento ativo. [Render: limitações dos discos](https://render.com/docs/disks#disk-limitations-and-considerations).

O inventário `_EXPECTED_WRITERS` em `trade_registry_closed_identity_conflict_repair_writer_coordination_contract_v1.py:56` contém 19 superfícies lógicas, em `trade_registry.py` e `main.py`, incluindo abertura, atualização, fechamento, restore e bootstrap. **Não são 19 servidores que possam ser movidos individualmente.** O backend em `trade_registry_closed_identity_conflict_repair_writer_runtime_storage_adapters_v1.py:162` adquire lock do sistema operacional sobre um arquivo; o coordenador usa esse domínio nas mutações e na manutenção.

Inferência de arquitetura: repetir o mesmo namespace/hash em um arquivo AWS não trava o arquivo do Render. Copiar Registry, lease e WAL para outra máquina tampouco transfere exclusão ou prova que a cópia continua atual. Um serviço AWS que chama de volta um endpoint de escrita no Render deixa o ponto de efeito no Render; isso não resolve a premissa temporal desse executor. Não criar SSHFS, NFS, polling de arquivos ou endpoint de reparo para disfarçar a diferença.

**Alternativa estreita rejeitada:** mover somente a manutenção, mantendo o disco ativo e os writers atuais no Render, não é uma implantação compatível com os contratos atuais.

### 15.2 Única candidata de colocação identificada, ainda não aprovada

Para preservar o mecanismo local de lock, a candidata de referência teria de colocar no mesmo host Linux: o executor da manutenção, o núcleo da Central que contém todos os writers do Registry, o próprio Registry, WAL, lease e arquivo de lock. O armazenamento persistente seria próprio desse host, não uma montagem do disco Render. A autoridade de emissão/consumo e sua testemunha continuariam fora do domínio de restauração desse núcleo e com privilégios separados; uma cópia de backup do mesmo host não é testemunha independente.

Em uma migração futura seria obrigatório impedir escrita no núcleo antigo antes de admitir escrita no novo, validar a transferência consistente, reconciliar pendências e manter trading desligado até novo preflight. Rollback não pode simplesmente religar uma cópia antiga: exige impedir dupla escrita e reconciliar os efeitos já confirmados. Nada disso foi executado, automatizado ou autorizado neste estudo. Não há sincronização bidirecional proposta, active-active ou transferência de ownership por símbolo/lado.

Essa candidata **é migração do núcleo e armazenamento da Central**, não apenas de um auxiliar C3. A outra possibilidade — mover exclusivamente um servidor de armazenamento e converter todos os writers em clientes remotos — mudaria interfaces, transações e coordenação distribuída. Ela não é tratada como fallback transparente nem desenvolvida neste estudo delimitado.

### 15.3 Alvo temporal para eventual laboratório, não promessa de produção

Como referência documental, EC2 Linux com ClockBound permite observar precisão temporal; o erro do PHC não deve ser tratado como zero apenas porque um daemon não recebeu o limite. A AWS descreve como compor o limite completo. [AWS: ClockBound e limite de erro](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/compare-timestamps-with-clockbound.html).

A documentação atual lista a família M7i entre as compatíveis com placement group `precision-time`, disponível nas regiões comerciais, sujeito à capacidade. PHC requer Linux e ENA compatível; isso é elegibilidade documentada, não comprovação de disponibilidade da conta, kernel, VMClock ou qualidade medida da instância. Uma referência cotável de laboratório poderia usar uma instância M7i Linux em Oregon; tamanho, AMI e versão de ClockBound ainda precisam de seleção, sem inferir suporte de todos os mecanismos a partir da família. [AWS: requisitos de tempo de precisão](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configure-ec2-ntp.html).

Primeiro ensaio físico, se futuramente aprovado, usaria somente Registry/WAL sintéticos e writers simulados. Deveria verificar fonte/estado/erro, perda de sincronização, reinício, contenção de lock e recovery. Um ensaio temporal bem-sucedido não autoriza dados reais, nem qualifica sozinho a autoridade independente ou a migração do núcleo.

### 15.4 Custos e conclusão para decisão

Não reutilizar o subtotal da candidata Lambda como orçamento desta migração. A composição de custos muda:

| Parcela | Unidade para cotação futura | O que falta |
| --- | --- | --- |
| Host Linux do núcleo/laboratório | Tipo de instância × horas ligadas | Tamanho compatível e capacidade necessária; não dimensionados por dados reais neste estudo |
| Sistema e armazenamento persistente | Volumes EBS, tamanho/desempenho e retenção | Dimensionamento, snapshots e teste de restore |
| Autoridade e testemunha independentes | Compute, armazenamento, chaves e operações | Implementação/recovery e separação de permissões ainda não qualificados |
| Rede, acesso e observabilidade | Endereços, tráfego, endpoints/NAT quando necessários, logs | Topologia fechada, limites e política de acesso |
| Transição e operação | Período de sobreposição e eventual redundância | Plano de corte, rollback e responsabilidades operacionais |

As páginas oficiais de [EC2 On-Demand](https://aws.amazon.com/ec2/pricing/on-demand/) e [EBS](https://aws.amazon.com/ebs/pricing/) foram consultadas, mas não foi obtida uma cotação regional completa para esta candidata. Não informar valor mensal como se estivesse fechado. Durante qualquer sobreposição, as despesas existentes permanecem; nenhum cancelamento de Render/Redis/ChatGPT, economia ou desconto de créditos está assumido.

**Conclusão do estudo autorizado: rejeitar a mudança isolada da manutenção e não recomendar migração do núcleo apenas como atalho para liberar Live.** A candidata de colocação é uma mudança operacional material e continua sem custo completo, fonte temporal física homologada ou recovery independente pronto. O estudo não demonstrou que ela seja a menor ou mais barata solução viável.

A decisão seguinte, se o usuário quiser prosseguir nessa direção, é tratar uma eventual migração do núcleo/Registry como projeto de arquitetura e homologação explicitamente delimitado, com orçamento e critérios de corte/rollback antes de qualquer execução. Não iniciar essa migração nem ampliar o estudo indefinidamente por um OK genérico. O estudo solicitado aqui está concluído; não há mais uma etapa equivalente de documentação a repetir automaticamente. Informação técnica nova sobre o ambiente atual também pode permitir outra avaliação, sem migração.

Somente esta proposta e a continuidade foram alteradas e conferidas. Sem código/testes, secrets, contas/dados reais, ordens, IAM/Render, commit/push/deploy ou ativação de trading. Chamadas externas somente às fontes públicas acima. Automatismo mantido ativo, mas avanço para a candidata ampla depende de decisão específica de escopo; não há execução técnica em segundo plano prometida. Percentual restante para Live: indeterminado.
