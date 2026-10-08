# C3 — decisão sobre histórico independente mínimo

Data: 10/09/2026 BRT; consultas concluídas em 11/09/2026 UTC.
Escopo: análise documental, sem implementação, contratação ou acesso operacional.
Base local: worktree `c3_final_release_promote_20260910`, HEAD
`d9e12e9daa8f606c3649370bbbf1551650979eb6`, preservando alterações existentes.

Atualização posterior à entrega: seção 11 quantifica armazenamento e
monitoramento em um cenário ilustrativo. Não transforma o cenário em cotação
regional completa nem autoriza nova infraestrutura.

## 1. Decisão executiva

**Nenhuma das duas opções examinadas foi demonstrada como completa, segura e
operável por até US$30 adicionais/mês. Não contratar nem integrar agora.**
Isso não significa que seja matematicamente impossível cumprir o orçamento;
significa que faltam uma cotação regional completa e evidência de implementação.

A candidata mais enxuta é manter a Central onde está e concentrar a autoridade
em AWS Lambda + DynamoDB + KMS, com histórico de recuperação em S3 sob
administração separada. A autenticação do serviço usaria OIDC gerenciado do
Render, que exige Pro. Não adicionar outro serviço Render nem PostgreSQL.
O subtotal fixo seria US$29/mês, antes de consumo, retenção, auditoria e outros
itens. Não apresentar esse subtotal como preço final.

A alternativa concreta com Render Hobby e certificados curtos emitidos por
AWS Private CA, via IAM Roles Anywhere, já excede o limite: US$54/mês de base,
antes dos demais itens. Ela ainda acrescenta o problema de matricular e renovar
a identidade do serviço com segurança. Não recomendada neste orçamento.

Render Standard, disco `/data` de 2 GB e Redis atuais permanecem. Os valores
são adicionais, não substituem suas faturas. Não foi demonstrado que essa
infraestrutura seja requisito universal de todo retorno a Live; este parecer
é sobre a autoridade de manutenção C3 investigada, não sobre todos os gates.

## 2. Evidência e limite do experimento anterior

Lidos `AGENTS.md`, `C3_AUTHORITY_INFRASTRUCTURE_PROPOSAL_20260910.md` e
`C3_SUPERVISED_MAINTENANCE_FEASIBILITY_20260910.md`, especialmente sua seção 8.
Os 45 testes ali registrados passaram porque verificaram as asserções do
experimento. O controle negativo observou **dois efeitos** quando o histórico
local e o da autoridade foram restaurados e houve nova aprovação. Portanto,
aprovação humana, assinatura e desafio novo não corrigem o rollback conjunto.
Nenhum desses testes foi repetido nesta análise.

O inventário informado pelo usuário basta para esta decisão: workspace Hobby,
compute Standard, Oregon, disco de 2 GB. Conta AWS, responsáveis independentes
e recursos reutilizáveis não estão comprovados. Não presumir ausência nem
reaproveitamento. Não solicitar novamente capturas do mesmo inventário.

## 3. Duas opções concretas

| Aspecto | 1 — AWS concentrada + Render Pro/OIDC | 2 — mesma autoridade + Hobby/Private CA |
| --- | --- | --- |
| Central | Serviço atual, sem migração | Igual |
| Autoridade | Lambda com URL autenticada, DynamoDB, quatro chaves KMS | Igual |
| Histórico independente | S3 versionado com retenção protegida em conta de auditoria separada | Igual |
| Identidade Render→AWS | Token OIDC curto → sessão AWS temporária → chamada assinada | Certificado X.509 curto → IAM Roles Anywhere → sessão temporária |
| Recurso adicional de identidade | Upgrade Hobby→Pro | Private CA em modo short-lived e mecanismo seguro de matrícula/renovação |
| Base mensal adicional | US$25 + US$4 = **US$29** | US$50 + US$4 = **US$54** |
| Limite de US$30 | Suficiência não demonstrada; margem inferior a US$1 antes dos extras | Excedido pela base |
| Parecer | Preferida apenas para cotação/qualificação posterior | Descartar neste orçamento |

Pro custa US$25/mês de workspace, além de compute. OIDC está disponível em Pro
ou superior; emite tokens curtos, gerenciados pelo Render. Na opção 1, restringir
emissor, audience e subject ao serviço exato, não a todo o workspace.
[Preços Render](https://render.com/pricing),
[OIDC Render](https://render.com/docs/oidc).

Na opção 2, Roles Anywhere troca prova X.509 por credenciais temporárias.
Não elimina a custódia da chave do cliente nem autentica sozinho a emissão
inicial do certificado. A variante concreta aqui cotada usa Private CA
short-lived: US$50/mês por CA e US$0,058 por certificado, com validade de até
sete dias. Por exemplo, 30 emissões custariam mais US$1,74/mês. Não é a tarifa
de toda solução possível com Roles Anywhere: uma CA externa existente poderia
ter outro custo, mas nenhuma foi comprovada. Não inventar PKI gratuita ou usar
chaves AWS permanentes para fechar a conta.
[Roles Anywhere](https://docs.aws.amazon.com/rolesanywhere/latest/userguide/introduction.html),
[Private CA](https://aws.amazon.com/private-ca/pricing/).

## 4. Localização, confiança e responsabilidades propostas

Proposta regional: AWS `us-west-2` (Oregon), próxima da região informada para
o serviço Render. Proximidade não garante rede privada nem latência medida.
Não se propõe NAT Gateway, máquina sempre ligada, API Gateway, PostgreSQL,
Kubernetes, Redis adicional ou migração da Central.

- **Central/Render:** somente invocar operações restritas e consultar seu estado.
  Sem permissão de assinar grants, apagar consumo, restaurar tabelas ou trocar
  raízes. A identidade de transporte não autoriza por si só uma manutenção.
- **Conta AWS de autoridade:** funções separadas por permissão para aprovação,
  consumo e emissão de recibo; DynamoDB mantém reserva/política atuais. Permissões
  administrativas e de deploy não pertencem ao papel da Central.
- **Conta AWS de auditoria:** S3 recebe evidência antes da liberação da ação.
  Seu administrador e recuperação de conta não podem depender das credenciais
  de deploy da Central ou de um backup compartilhado. A conta de autoridade
  não pode apagar versões, reduzir retenção ou mudar o destino confiável.
- **Responsável autenticado de segurança:** matrícula inicial das raízes, aprovação
  do plano exato, rotação/revogação e revisão de recuperação. Sessões temporárias
  e autenticação forte; não distribuir credenciais permanentes. Não foi
  identificado nem contratado esse responsável nesta análise.
- **Responsável operacional:** ensaios de restauração e reconciliação, resposta
  a alertas e comprovação dos interlocks. Se for a mesma pessoa acumulando
  funções, registrar essa concentração, não chamar isso de dupla aprovação.

URL Lambda com `AWS_IAM` requer permissões de invocação apropriadas e pode
restringir o caminho à URL. Não usar `NONE` como solução de autenticação.
O serviço não receberia credenciais BingX nem capacidade de enviar ordens.
[Autenticação Lambda](https://docs.aws.amazon.com/lambda/latest/dg/urls-auth.html).

Quatro chaves preservam os papéis já estudados: pedido, política, referência e
recibo. É premissa de continuidade do contrato, não prova de que quatro seja
o mínimo criptográfico universal. KMS protege a chave privada, mas o serviço
autorizado a assinar continua sendo parte da confiança. Rotação assimétrica
exige substituição controlada; manter chaves públicas históricas e política
atual de revogação, sem reabrir claims consumidos. Não confiar só em alias.
[Chaves KMS](https://docs.aws.amazon.com/kms/latest/developerguide/symmetric-asymmetric.html),
[Rotação KMS](https://docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html).

## 5. Fluxo mínimo a qualificar — ainda não implementado

1. Autenticar serviço e emissor da aprovação separadamente. Validar plano exato,
   alvo, identidade/lifecycle, origem, candidato, limites, deadline, época e
   política vigente. Não transportar o Registry para a autoridade; limitar a
   metadados aprovados e hashes, que também exigem cuidado de privacidade.
2. Derivar uma identidade estável **da ação lógica**, não do nonce, assinatura
   ou época. Uma revisão que muda o plano não pode disfarçar a mesma ação como
   outra. A regra de equivalência precisa de ensaio, não apenas hash novo.
3. Consumir atomicamente no DynamoDB: condição de política/geração + inserção
   única da ação. Transações são atômicas dentro de uma conta/região; o token
   idempotente de dez minutos não substitui o registro durável sem TTL de replay.
   [Transações DynamoDB](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html).
4. Registrar reserva e vínculo do plano no histórico independente antes de
   emitir qualquer autorização utilizável. Exigir evidência confirmada da
   gravação protegida, sequência e identidade do destino. Falha intermediária
   deixa ação consumida/pendente; não apaga reserva para facilitar retry.
5. Revalidar interlocks, orçamento, revogação e deadline no ponto de admissão
   do efeito local, sob coordenação e fencing a qualificar. Uma consulta remota
   seguida de efeito local não é transação distribuída: existe corrida entre
   revogação e execução. Sua semântica e limite precisam ser definidos e testados.
6. O executor local precisará de WAL, identidade de transação e reconciliação.
   Só confirmar conclusão depois de evidência do efeito; recibo de consumo
   não equivale a efeito concluído nem a readiness.
7. Perda de resposta: consultar a mesma ação. `RESERVED`, `PREPARED` ou resultado
   desconhecido não permitem reaplicar. Se houve efeito sem confirmação,
   reconciliar e registrar a conclusão; não emitir outro grant de execução.

**Não existe transação atômica DynamoDB + S3 + Registry nesta proposta.** A ordem
conservadora sacrifica disponibilidade e pode consumir uma ação sem executá-la.
Garantir uma reserva única não prova efeito exatamente uma vez, sobretudo após
restore local. A composição real permanece não demonstrada.

S3 Object Lock protege versões retidas, mas permite novas versões e marcadores
de exclusão. Escrita condicional pode impedir sobrescrita; `If-None-Match`
pode aceitar uma chave cujo estado atual seja marcador de exclusão. Portanto,
Object Lock não é sozinho o ledger de consumo nem atestado de atualidade.
Exigir restrição de exclusão/sobrescrita, confirmação de versão, continuidade
do head e leitura das versões relevantes, não somente um `GET` da versão atual.
[Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html),
[Escritas condicionais](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html).

Retenção proposta: claims/tombstones permanecem enquanto uma restauração puder
reintroduzir a ação; sem TTL automático. Para dimensionamento inicial, considerar
um ano de eventos detalhados protegidos, ainda sujeito a aprovação de custo.
Esse prazo não autoriza apagar tombstones ao final do ano. Compactação exige
checkpoint independente completo e verificável, ainda não implementado.

## 6. Recuperação: quatro ameaças diferentes

| Situação | Comportamento exigido | Limite |
| --- | --- | --- |
| Restore somente da Central | Bloquear manutenção; consultar autoridade atual e reconciliar WAL/efeitos por ação | Histórico externo retido impede nova admissão; não recria dados locais perdidos sozinho |
| Restore da autoridade | Quarentena; suspender admissões, confrontar histórico independente e reconstruir consumo/política antes de matricular novo destino | Backup da autoridade não certifica atualidade |
| Administrador comprometido | Revogar identidade, bloquear admissão e verificar evidência sob custódia independente | Separar contas reduz alcance; não resiste a compromisso simultâneo de todos os responsáveis |
| Perda/rollback de todas as referências | Permanecer bloqueado; sem retomada automática e sem reset dos claims | Nenhuma assinatura, MFA ou aprovação humana recupera história que deixou de existir |

DynamoDB restaura em nova tabela; parâmetros de segurança/recuperação precisam
ser revistos. Isso facilita reconhecer um destino diferente, mas não garante
que a aplicação o recuse. Proibir repontar silenciosamente aliases e exigir
matrícula autenticada da nova identidade após reconciliação.
[Restauração DynamoDB](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/pointintimerecovery_restores.html).

A barreira de quarentena precisa existir fora do mesmo conjunto restaurável:
um booleano `clean` recuperado do backup não serve. O arquivo S3 mais recente
também não basta se não houver prova de ausência de lacunas e de continuidade
até o último grant liberado. O protocolo de head/checkpoint, separação de
administradores e consulta obrigatória ainda precisam de qualificação.

Não prometer RTO ou recuperação automática neste estágio. Na perda total,
qualquer recuperação excepcional requer novas evidências externas confiáveis;
na ausência delas, a manutenção fica indisponível. Este serviço não deve ficar
no caminho de proteção das posições nem cancelar stops quando indisponível.

## 7. Custo incremental: cenário, não cotação fechada

USD/mês; sem compra, descontos promocionais ou abatimento presumido de franquias.
Região pretendida: Oregon. Os exemplos públicos AWS permitem aritmética, mas
não confirmaram todos os SKUs regionais/Ed25519 nem a demanda real. Não apresentar
o cenário como fatura garantida de `us-west-2`.

Base da opção 1: Pro US$25 + quatro chaves KMS a US$1 = US$29.
Assinaturas são cobradas separadamente. O exemplo público KMS de US$0,15/10.000
é ECC-256; não prova tarifa exata de Ed25519. Chaves adicionais durante rotação
aumentam a base. [Preços KMS](https://aws.amazon.com/kms/pricing/).

Para comparar volumes, N = autorizações de manutenção/mês, não trades ou
retomadas do Codex. Reutilizar hipóteses explícitas da proposta anterior:

- Dez invocações Lambda por ação, 512 MB, 250 ms faturáveis por invocação:
  N × 10 × (0,20/1.000.000 + 0,5 × 0,25 × 0,0000166667).
  [Preços Lambda](https://aws.amazon.com/lambda/pricing/).
- Oito unidades faturáveis de escrita e vinte de leitura DynamoDB por ação;
  1 GB médio armazenado com PITR. Referências: US$0,625/milhão de escritas,
  US$0,125/milhão de leituras, US$0,25/GB-mês + US$0,20/GB-mês PITR.
  Transações e tamanhos precisam caber nessas unidades, não contá-las como
  chamadas simples. [Preços DynamoDB](https://aws.amazon.com/dynamodb/pricing/).
- Até dez assinaturas KMS por ação. Auditoria exemplificada com trinta eventos
  de dados CloudTrail por ação, a US$0,10/100.000. Primeira cópia de eventos de
  gestão pode ter entrega gratuita, mas armazenamento não é gratuito por isso.
  [Preços CloudTrail](https://aws.amazon.com/cloudtrail/pricing/).

| N/mês | Lambda + requests DynamoDB | Dados CloudTrail | Opção 1: subtotal calculável, incluindo 1 GB/PITR | Se KMS igualasse o exemplo ECC-256, ainda antes de E |
| ---: | ---: | ---: | ---: | ---: |
| 100 | 0,00303 | 0,00300 | 29,45603 + S + E | 29,47103 + E |
| 1.000 | 0,03033 | 0,03000 | 29,51033 + S + E | 29,66033 + E |
| 10.000 | 0,30333 | 0,30000 | 30,05333 + S + E | 31,55333 + E |

S = tarifa efetiva das assinaturas Ed25519 na região, ainda não fechada.
E = itens necessários ainda não quantificados abaixo. Os valores da última
coluna são sensibilidade hipotética, não preço confirmado. Em 1.000 ações,
restariam apenas US$0,34 para E nessa hipótese; uma chave adicional já excederia
a margem. Isso não prova que o volume real seja 1.000 nem que custará exatamente
US$29,66. Na opção 2 somar US$25 a cada subtotal, além de emissão/renovação de
certificados e operação de identidade: troca-se Pro US$25 por CA US$50.

**E não pode ser definido como zero:**

| Item não fechado | Hipótese de dimensionamento / motivo |
| --- | --- |
| Histórico S3 protegido | 1 GB médio inicial, quatro PUTs e dez GET/LIST por ação para planejamento; versões e retenção acumulam. Tabela regional dinâmica não forneceu tarifa numérica verificável nesta consulta |
| Auditoria adicional | Logs administrativos, invalidações, eventos de falha/ataque e acessos de recuperação excedem a hipótese de trinta eventos por ação |
| Observabilidade | Ingestão/retenção de logs Lambda, alarmes e notificações; nunca registrar payloads/credenciais |
| Tráfego | Render→AWS, respostas AWS→Render, transferências de recuperação; franquia compartilhada com a Central não é capacidade livre comprovada |
| Restore e continuidade | Leituras/exportações, nova tabela, coexistência durante reconciliação, versões históricas e retenção não expirada |
| Chaves/identidade humana | Sobreposição de rotação, eventual identidade corporativa paga, dispositivos de autenticação e recuperação de conta |
| Outros | Impostos, câmbio, suporte e trabalho de implementação/operação; não incluídos nas tarifas parciais |

S3 cobra armazenamento, requisições e outras operações conforme classe/região;
não presumir que retenção independente tenha custo zero.
[Preços S3](https://aws.amazon.com/s3/pricing/).

O custo de autenticação Render→autoridade está incluído explicitamente no
upgrade Pro da opção 1; eventual tráfego permanece em E. Nenhuma chave AWS
permanente ou OIDC gratuito em Hobby foi pressuposto. A URL Lambda evita um
API Gateway adicional nesta topologia, sem eliminar custos de execução.
Alarmes, quotas e limites de concorrência não são teto financeiro garantido.

Não há total mensal completo defensável com as evidências disponíveis. Tampouco
há prova de operação humana gratuita ou de separação administrativa já existente.
Não recomendar aumento arbitrário para US$40/50: primeiro fechar os itens E/S.

## 8. Critérios objetivos antes de avançar

1. Cotação regional da opção 1 incluindo S/E, retenção e rotação, com volume
   declarado e margem; se exceder US$30, obter decisão de orçamento antes de gasto.
2. Identidades do serviço, emissor e administrador matriculadas por processo
   autenticado; provar que a Central não emite grants nem altera a autoridade.
3. Demonstrar consumo por ação lógica sob concorrência, mudança de nonce/época,
   revisionamento de plano e respostas perdidas, sem repetir efeito.
4. Provar fronteiras DynamoDB/S3/efeito, incluindo falhas antes/depois de cada
   confirmação, sem usar um log de teste como fonte de continuidade fictícia.
5. Ensaiar restore isolado e combinado, nova tabela/alias, revogação atrasada,
   marcadores/versões S3 e perda total. Sem evidência independente, bloquear.
6. Validar custódia e interoperabilidade KMS/Ed25519, deadlines reais, fencing,
   coordenação dos writers e recovery de startup. Testes antigos não certificam
   adaptador DynamoDB, protocolo S3 nem integração runtime ainda inexistentes.
7. Confirmar responsáveis e procedimento de recuperação praticável. Nenhum
   critério desta lista libera ordens, flags ou Live automaticamente.

## 9. Próximo passo limitado e encerramento

Recomendação: **não contratar agora**. Se houver continuidade autorizada desta
linha, o próximo entregável deve ser uma cotação fechada e revisão única dos
pontos de confiança da opção 1, sem código ou provisionamento. Não criar outra
sequência indefinida de contratos dormentes para contornar o contraexemplo.
Se não houver como fechar orçamento/recuperação, encerrar essa alternativa.

A menor decisão posterior é aceitar ou não o custo completo e a responsabilidade
operacional apresentados; não pedir ao usuário leigo para escolher componentes
às cegas. Esta análise não exige que ele faça qualquer alteração no Render.
O automatismo deve ser pausado ao entregar este relatório, conforme seu objetivo
finito, sem prosseguir automaticamente para implementação ou contratação.

Modelo/esforço recomendado: **GPT-6 Astra — Alto** (recomendação, não troca realizada).
Percentual restante para Live: **indeterminado**, pois não há checklist global
atualizado, ponderação mensurável nem preflight de produção nesta etapa.

## 10. Validação e segurança

Único arquivo de projeto criado nesta etapa: este relatório. Alterações
preexistentes foram preservadas. Revisão documental e aritmética apenas; nenhum
teste, aplicação, servidor, worker, bot ou processo operacional executado.
Não há mudança de código a promover nem ensaio de infraestrutura realizado.

Nenhum secret, `.env`, token, chave real, Registry ou dado operacional acessado.
Nenhuma chamada a conta/API operacional: as consultas externas foram somente
a documentação pública oficial. Nenhum commit, push, pull, merge, deploy,
provisionamento, contratação, ordem ou alteração de configuração de trading,
Render ou Redis. Riscos residuais e dependências não comprovadas estão explícitos;
o parecer não deve ser usado como atestado de readiness.

## 11. Complemento de custos após o aceite do usuário

O aceite para continuar foi tratado como análise segura da opção 1, não como
autorização de compra, acesso a contas, código ou reativação do automatismo.
Esta seção encerra a tentativa de fechar custos por documentação pública.

### Referências adicionais e limites

O guia oficial de custos da solução Automated Security Response publica
referências S3: US$0,023/GB-mês, US$0,005/1.000 PUT/COPY/POST/LIST e
US$0,0004/1.000 GET. São referências de uma solução com exemplos em N. Virginia,
não cotação regional comprovada de Oregon. Somente essas tarifas são utilizadas;
não estamos propondo instalar aquela solução ou importar seu orçamento completo.
[Guia oficial de custos AWS](https://docs.aws.amazon.com/solutions/latest/automated-security-response-on-aws/cost.html).

A página de preços CloudWatch fornece exemplos com US$0,30 por métrica
personalizada/mês, US$0,10 por métrica de alarme padrão/mês, US$0,50/GB de
ingestão e US$0,03/GB-mês de armazenamento de logs. Também são referências dos
exemplos publicados, não verificação de cada SKU em Oregon. Não descontar
franquias cuja disponibilidade na conta não foi conferida.
[Preços CloudWatch](https://aws.amazon.com/cloudwatch/pricing/).

A tentativa de consultar o catálogo público regional KMS por HTTPS falhou
na negociação da conexão; a abertura pelo navegador de pesquisa retornou erro
interno. Não foram fornecidas credenciais, desativada validação TLS ou alteradas
configurações. Não houve resultado tarifário aproveitável desses acessos.
Assim, a tarifa Ed25519 regional continua não confirmada; não equipará-la
silenciosamente ao exemplo ECC-256.

### Cenário expandido de 1.000 autorizações/mês

Manter as hipóteses de Lambda, DynamoDB, CloudTrail e quatro chaves da seção 7.
Detalhar os dez GET/LIST por ação como oito GET e dois LIST. Reservar para o
cenário quatro métricas personalizadas (pendências, divergência de continuidade,
recusas por política e falhas de reconciliação), seis alarmes padrão e 0,1 GB
de logs ingeridos e armazenados em média por mês. Alarmes adicionais poderiam
usar métricas nativas; não foi comprovado o desenho final de monitoramento.

| Parcela | Cálculo em USD/mês | Valor |
| --- | --- | ---: |
| Subtotal da seção 7, antes de S/E | Pro + quatro chaves + Lambda + DynamoDB/PITR + eventos CloudTrail modelados | 29,51033 |
| S3 armazenado | 1 GB médio × 0,023 | 0,02300 |
| S3 PUT e LIST | (4.000 + 2.000) / 1.000 × 0,005 | 0,03000 |
| S3 GET | 8.000 / 1.000 × 0,0004 | 0,00320 |
| Métricas personalizadas | 4 × 0,30 | 1,20000 |
| Alarmes padrão | 6 × 0,10 | 0,60000 |
| Ingestão de logs | 0,1 GB × 0,50 | 0,05000 |
| Armazenamento médio de logs | 0,1 GB × 0,03 | 0,00300 |
| **Subtotal expandido** | **Ainda sem S e custos residuais U** | **31,41953 + S + U** |

S continua sendo o preço efetivo das assinaturas KMS. U contém os itens de E
que não foram quantificados nesta seção: entrega de notificações, chamadas
adicionais de métricas/consulta, requisições e armazenamento adicional de logs
de auditoria, tráfego, recuperação, sobreposição de chaves, identidade humana,
impostos e trabalho operacional. Não duplicar as parcelas já incorporadas.
Se a tarifa KMS coincidisse com o exemplo ECC-256, o cenário passaria para
US$31,56953 + U; isso é sensibilidade, não cotação Ed25519.

Os volumes não foram medidos: 1 GB de histórico é média acumulada, não 1 GB
novo por mês; retenção e versões podem superar esse tamanho. Quatro métricas
e seis alarmes são uma escolha ilustrativa, não mínimo universal. Franquias
poderiam reduzir a fatura; não foram presumidas. Portanto, o resultado prova
apenas que **este cenário sem descontos excede US$30**, não que toda arquitetura
segura obrigatoriamente custa mais que esse limite. Rotação e recuperação
podem aumentar a conta mesmo com poucas autorizações.

### Encerramento e decisão necessária

Não foi possível obter uma cotação completa de Oregon com tarifa Ed25519,
todos os custos de operação e premissas verificadas. Isso é limite da evidência,
não justificativa para mais contratos dormentes ou contratação experimental.
O parecer continua **não aprovado para compra dentro de US$30**.

Manter o teto atual e a infraestrutura existente. Para retomar esta alternativa,
o próximo insumo necessário é uma estimativa regional verificável, incluindo
operação/recuperação, seguida da aceitação explícita do custo completo. Não
pedir um aumento arbitrário de orçamento nem outro OK rotineiro; não repetir
esta pesquisa sem nova evidência tarifária ou mudança real de premissas.
Isso não impede uma análise separada dos demais bloqueios de Live, mas não
declara esta infraestrutura obrigatória nem esses bloqueios resolvidos.

Somente este relatório foi atualizado; aritmética conferida. Nenhum teste ou
processo da aplicação executado. Nenhum secret, dado real, conta operacional,
commit, push, deploy, compra, configuração ou trading alterado. Consultas externas
restritas a documentação/catálogo público. O automatismo não foi reativado.
Modelo recomendado: GPT-6 Astra — Alto. Percentual restante de Live: indeterminado.
