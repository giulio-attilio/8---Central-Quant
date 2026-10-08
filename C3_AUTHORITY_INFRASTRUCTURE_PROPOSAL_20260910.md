# C3 — proposta de infraestrutura da autoridade de manutenção

## Entrada autenticada preservando PostgreSQL — decisão de desenho 23:41 UTC

Esta seção fecha a análise da porta de entrada, NÃO fecha a arquitetura para
contratação. B continua incompleta: rede privada Render não autentica uma API
própria. A substituição integral do ledger por DynamoDB continua rejeitada pelos
motivos anteriores. Não repetir essa comparação ou os 20 testes de emissão.

**Candidata híbrida para homologação futura:** executar o consumidor em Lambda,
chamado por AWS Invoke síncrono com IAM; manter o ledger PostgreSQL separado no
Render e o testemunho de reservas separado do backup desse ledger. Isso elimina
a necessidade de uma API HTTP privada de autenticação própria, sem trocar a
semântica SQL por PutItem. É mudança proposta de hospedagem do consumidor,
não migração da Central/Redis nem adaptação runtime implementada.

### Identidades e transporte — requisitos fechados de desenho

| Fronteira | Restrição exigida antes da homologação |
| --- | --- |
| Central → AWS | Role cliente exclusiva via OIDC do workspace/serviço exatos; `lambda:InvokeFunction` somente na versão numérica aprovada do consumidor; sem Sign, GenerateMac, escrita em banco/testemunho ou PassRole |
| Entrada Lambda | `InvocationType=RequestResponse`; negar entrada pública Function URL, triggers alternativos e principals extras; SDK oficial, sem verificador SigV4 próprio; não confiar em `principal`/`ClientContext` fornecido no payload |
| Resposta Lambda | Conferir versão executada, ausência de FunctionError, limites e assinaturas C3; HTTP 200 não basta. Sem retry automático que possa reemitir permissão; ambiguidade mantém claim consumido |
| Consumidor → PostgreSQL | Identidade SQL própria, SELECT/INSERT apenas nos objetos fixos, sem ownership, UPDATE/DELETE/TRUNCATE ou administração; segredo exclusivo do consumidor, nunca da Central |
| Emissores e raiz | Manter finalidades e roles separadas; cada Sign limitado à sua chave. GenerateMac da raiz apenas no emissor administrativo separado; cliente verifica, não emite |

Invoke exige `lambda:InvokeFunction`; o status de transporte não codifica todos
os erros da função. A identidade do chamador não deve ser inventada a partir de
campos do evento: a fronteira depende das políticas efetivas e do pedido C3
assinado verificado pelo próprio consumidor. Permissões/ARNs concretos continuam
pendentes, sem wildcard para contornar sua ausência.
[AWS Invoke](https://docs.aws.amazon.com/lambda/latest/api/API_Invoke.html).

OIDC Render exige Pro e conexão com variável/redeploy; nenhum desses passos está
autorizado agora. As quatro roles dormentes não são a role cliente, nem um serviço
ativo; não reutilizar ConsumptionSigner como cliente da Central.
[Render OIDC](https://render.com/docs/oidc).

### Rede e custo — o subtotal de US$ 44,50 NÃO cobre esta candidata

Para restringir o PostgreSQL externo ao endereço do consumidor, a candidata usa
Lambda em sub-rede privada com NAT público e IPv4 estável. Não liberar o banco
para `0.0.0.0/0` nem presumir IP estável no Lambda padrão. O acesso é por internet
com TLS, não por rede privada entre provedores. Exigir hostname externo/SNI e
`sslmode=verify-full` com CA confiável; se a cadeia real não validar, abortar sem
reduzir para require. A compatibilidade do destino real ainda exige homologação.
[Rede Lambda](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc-internet.html),
[PostgreSQL Render](https://render.com/docs/postgresql-creating-connecting),
[validação TLS PostgreSQL](https://www.postgresql.org/docs/current/libpq-ssl.html).

Cálculo ilustrativo, 730 horas, UM NAT/IPv4 e UM segredo: base anterior sem API
privada Render = US$ 37,50; NAT a US$ 0,045/h = 32,85; IPv4 a US$ 0,005/h = 3,65;
segredo = 0,40. **Subtotal condicional US$ 74,40/mês adicionais**, mais Lambda,
DynamoDB/testemunho, chamadas KMS/Secrets Manager, tráfego/NAT por GB, logs,
backup/retenção e impostos. O valor NAT é o exemplo oficial de Ohio; NÃO é
cotação confirmada de Oregon. Compute PostgreSQL ainda é referência anterior.
Não descontar créditos ou supor substituição das contas existentes. Um único
NAT não configura alta disponibilidade; redundância aumenta esse subtotal.
[VPC/NAT/IPv4](https://aws.amazon.com/vpc/pricing/),
[Secrets Manager](https://aws.amazon.com/secrets-manager/pricing/).

### Prazo e recuperação — limites ainda reais, não mais um fake

PostgresConsumptionOfflineV1 continua apenas sintético: sua conexão injetada não
implementa TLS remoto, custódia de credenciais ou autenticação IAM. Leitura do
código confirmou verificação SQL de privilégios, fsync/synchronous_commit,
unicidade e commit antes de assinatura; não alterar escopo para chamá-lo real.

A fonte de tempo também NÃO está resolvida por escolher Lambda: a documentação
de ClockBound trata de EC2 Linux e de limites de erro medidos. Não estender essa
garantia a Lambda/Render, usar datetime.now como intervalo autenticado ou adotar
os 100 ms dos fixtures como SLA real. Uma fonte remota exigiria identidade,
freshness/desafio e propagação conservadora da incerteza e do tempo de viagem.
Não adicionar EC2 ou outra assinatura ao orçamento sem análise e autorização.
[ClockBound/EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/compare-timestamps-with-clockbound.html).

Restauração do ledger deve manter admissão bloqueada até conciliação com
testemunho fora do backup; restaurar ambos permanece fora da garantia. O plano
precisa de proprietário administrativo, retenção e procedimento de recuperação
concretos. IAM Invoke resolve a entrada, não essas duas dependências.

**Decisão:** não recomendar contratação B, C ou híbrida como solução pronta.
O desenho da entrada híbrida fica registrado, com custo e limites explícitos.
Antes de provisionar, falta uma fonte temporal qualificada e aprovação de uma
topologia/orçamento completos, inclusive recuperação. Nenhuma autorização
genérica ou novo harness substitui essas evidências. Não refazer esta análise
sem mudança de requisito, fornecedor/destino ou informação operacional relevante.

Somente esta proposta e C3_OFFLINE_CONTINUITY_20260911.md alterados. Sem código,
testes novos ou repetidos, imports operacionais, secrets/dados reais, IAM/Render,
commit/push/deploy ou flags. Chamadas externas somente a documentação pública.

---

## Emissão executável exclusivamente sintética — rodada 23:26 UTC

Fechada a lacuna de emissão apontada abaixo: o harness de testes agora executa
reserva da identidade → INSERT confirmado no ledger temporário → assinatura de
recibo novo → codec/recepção. Usa o SQLiteMaintenanceAuthorizationLedgerV1 já
existente, sem outro backend, endpoint, classe operacional ou conversão V3/V2.
Verifica pedido/pins/política/revogação e retém deadline admitido nas rechecagens.
O testemunho é um conjunto em memória protegido por lock, separado do SQLite;
não deve ser apresentado como autoridade autenticada ou persistente.

20 testes aprovados, zero falhas/erros/skips, 265 deselected, JUnit 1,644 s.
Falhas antes/depois de commit, resultado perdido, política alterada, expiração,
assinatura malsucedida/tardia e concorrência não emitem segundo recibo. Quatro
chamadas sincronizadas resultam em um commit/uma assinatura. Os callbacks usam
o ledger injetado atual, inclusive após recriação do objeto. Um oráculo SQL
independente exige linha/digest corretos antes da assinatura; confirmação falsa
sem escrita ou com digest divergente é recusada. Isso é oráculo de TESTE, não
novo interlock de assinatura em produção. Default-off não consulta dependências.

Controle de restauração demonstra a premissa essencial: restaurar apenas o
SQLite não desfaz consumo enquanto o testemunho permanece; restaurar ambos
permite replay no controle negativo. Logo, estes testes NÃO qualificam domínio
de backup, IAM, recuperação, fonte temporal ou persistência independente real.
Um recibo emitido é aceito pela recepção sintética com 1000 ms restantes;
recepção ainda não constitui consumo único local nem autorização runtime.

Evidência `.offline_validation/c3_dependency_assembly_20260911/cq-c3-lab-assembly-1kdwo02j/`;
SHA-256 JUnit `2ed41f386b6043293ad622ee10819f53e077c039ac1d9dbbd1ea049e2ed1e6ff`.
Hashes test/helper/módulo conferidos ao overlay, módulo público intacto
`851321a34905b2807e99f4e53d0267fef5e452050d94d59b8f2e5bcb5b093ee1`.
Lab UID999, zero rotas, fontes read-only, sem mounts Windows/download/servidor.
Não repetidos testes anteriores não afetados; sem PG físico/KMS/tempo real.

Alterações limitadas a `tests/test_c3_public_authority_wire_offline_v2.py`,
`tests/helpers/c3_dependency_assembly_lab.py`, esta proposta e continuidade.
Seletor `run-epoch-emission-offline`. Sem secrets, dados reais, chamadas externas,
flags, main, IAM/Render, commit/push/deploy ou ativação operacional.

Próxima dependência para integração: definir emissores autenticados, fonte
temporal qualificada e armazenamento independente com recuperação verificável.
As quatro roles dormentes não bastam; criação de chaves/serviços ou mudanças
no Render seguem fora da autorização atual. Não repetir esta unidade ou criar
novas camadas sintéticas para simular que tais recursos já existem. Este resultado
não afirma que toda validação offline terminou nem que Live está qualificado.

---

## Recepção composta em memória — rodada 23:09 UTC

Implementado harness apenas em `tests/test_c3_public_authority_wire_offline_v2.py`:
decodificação → assinaturas/vínculos → interseção temporal → orçamento local
restante. Reutiliza funções existentes sem novo wrapper de produção ou provider.
Decodifica reserva antes do consumo e conserva a referência explícita. Falhas
de leitura, assinatura ou pins param antes do cálculo temporal; default-off
para antes de decodificar. O módulo de implementação permanece intacto.

Observações UTC sintéticas e ticks monotônicos locais são entradas distintas.
A origem local nunca é comparada à época UTC. O harness considera orçamento
consumido até a observação após leitura/verificação e retém o último deadline
admitido nas rechecagens, recusando recuo monotônico. Recuo do horário civil não
restaura tempo já gasto. São regras da composição de TESTE, não um provider
operacional de relógio nem garantia física de interrupção de execução.

42 testes novos aprovados, zero falhas/erros/skips, 223 deselected, JUnit 0,717 s.
Trinta casos cruzam dez condições temporais com três origens locais: 0, 10000 e
10**12. Incluem validade atual, último milissegundo, antes/início cruzado,
expiração, evidência histórica, incerteza excessiva, verificação tardia e
orçamento local esgotado. Outros casos cobrem rechecagem/rollback, precedência
de recusa, default-off e repetibilidade deliberada sem consumo único.

O resultado contém somente estágio/durações. Uma mesma cadeia pode resultar em
`bounded` repetidamente antes da expiração, pois nenhum testemunho/ledger é
consultado. Isso impede apresentar o harness como autorização ou prova de
commit. Assinaturas e timestamps consistentes não substituem origem temporal
autenticada, atualidade do head, persistência independente ou consumo idempotente.

Evidência `.offline_validation/c3_dependency_assembly_20260911/cq-c3-lab-assembly-_78ax79z/`;
SHA-256 JUnit `ffaa23726c0de4e2ffd4f5ec8e7c6d0e64f53b0c236292ccfa15ff779fbaefb6`.
Hashes módulo/teste/helper conferidos ao overlay. Módulo público mantém SHA-256
`851321a34905b2807e99f4e53d0267fef5e452050d94d59b8f2e5bcb5b093ee1`.
Lab existente UID999, zero rotas, fontes read-only, sem mounts Windows ou
downloads/servidor. Não executados SDK/KMS/rede/tempo real/PG físico, preempção
ou consumo operacional. Testes anteriores não afetados não repetidos.

Quatro arquivos alterados: `tests/test_c3_public_authority_wire_offline_v2.py`,
`tests/helpers/c3_dependency_assembly_lab.py`, esta proposta e
`C3_OFFLINE_CONTINUITY_20260911.md`; seletor `run-epoch-reception-offline`.
Sem secrets/dados reais/chamadas externas, main, flag, IAM/Render, commit,
push ou deploy. Nenhuma autorização operacional ou ativação adicionada.

Próxima lacuna concreta: o fixture V3 fabrica uma cadeia assinada consistente,
mas não executa reserva → commit confirmado → assinatura de consumo. Testar
essa sequência em harness sintético, preservando o mesmo namespace/claim e
recusando reemissão após resultado perdido/falha. Reutilizar fixtures existentes
quando compatíveis; não adaptar um pedido V3 para V2, inventar escrita real ou
ligar o resultado ao runtime. Não reabrir formato/codec/recepção concluídos.

---

## Codec V3 estrito concluído — rodada 23:01 UTC

Implementados encode/decode no módulo público existente, sem alterar domínios,
assinaturas ou tipos já definidos. Wire é o JSON canônico da mensagem com
signature_hex adicionado. Encoders preservam os bytes da mensagem unsigned;
decoders exigem reconstituição byte a byte, sem normalizar entrada ambígua.
Funções `epoch_wire_encode_offline_v3` e `epoch_wire_decode_offline_v3` são
default-off, recebem escopo explícito e não fazem I/O ou verificação criptográfica.

Limites totais: 4243 bytes para pedido e 16531 para statements; a assinatura
lowercase128 adiciona exatamente 147 bytes ao JSON. O leitor verifica tamanho
antes do parser, UTF-8 estrito e objeto único. Recusa chaves repetidas inclusive
escapadas, números float/expoente/NaN/Infinity/negativos/fora da faixa segura,
campos faltantes/desconhecidos e tipos primitivos inválidos antes dos DTOs.
Não aplica defaults do dataclass a campos omitidos. Formas semânticas reutilizam
validadores anteriores, sem copiar regras de validade para o codec.
Ordem, espaços e escapes alternativos são recusados; compatibilidade permissiva
com JSON genérico não é objetivo deste formato canônico sintético.

Recibo de consumo referencia reservation_sha256, não contém a reserva inteira.
O decoder exige reserva fornecida explicitamente e com formato assinado válido,
confere hash e mantém essa mesma instância. Não busca nada pelo hash e não
inventa contexto. Chave/contexto/autenticidade da reserva exigem as verificações
criptográficas separadas já implementadas. Contexto extra em outros tipos é
recusado, não ignorado. Não existe conversor V2, parser operacional ou endpoint.

**Decode bem-sucedido não é autenticidade nem autorização.** Um teste altera o
nonce mantendo JSON válido: o codec devolve DTO, e a checagem de assinaturas
recusa. A cadeia completa codificada/decodificada preserva as cinco assinaturas,
mas ainda não comprova atualidade, reserva/commit real, anti-rollback ou consumo.

70 testes novos aprovados, zero falhas/erros/skips, 153 deselected, JUnit 0,660 s.
Cobertura: roundtrip/oráculo de inserção da assinatura, cadeia reconstruída,
duplicatas/canonicalidade/UTF-8/BOM/tipos/versões/excesso/profundidade, limites
antes do parser, tipos antes dos DTOs, reservas ausentes/trocadas/sem assinatura,
maior nonce escapado, 128 revogações e default-off. Não repetidos os testes
anteriores não afetados; formatos/verificadores existentes não modificados.

Evidência `.offline_validation/c3_dependency_assembly_20260911/cq-c3-lab-assembly-lrot_1v9/`;
SHA-256 JUnit `7ea8a714f80b08e70be1ce229356005e350d0060ae9ff98e4b8a8fdec744f78b`.
Hashes de módulo/teste/helper conferidos ao overlay. Laboratório existente,
UID999, zero rotas, fontes read-only, sem mounts Windows/download/servidor.
Sem testes de rede/SDK/KMS/tempo real/PostgreSQL físico ou processos operacionais.

Arquivos alterados: `trade_registry_c3_public_authority_offline_v2.py`,
`tests/test_c3_public_authority_wire_offline_v2.py`, `tests/helpers/c3_dependency_assembly_lab.py`,
esta proposta e `C3_OFFLINE_CONTINUITY_20260911.md`; seletor
`run-epoch-codec-offline`. Nenhum secret, Registry real, chamada externa, flag,
main, IAM/Render, commit/push/deploy nesta rodada.

Próximo passo: harness sintético de recepção usando os componentes existentes
(codec, assinaturas/vínculos, intervalo temporal e orçamento local), sem outro
wrapper ou provider. Recusar evidência histórica/expirada, incerteza e orçamento
esgotado mesmo quando assinaturas são consistentes; não converter isso em
autoridade operacional. Não repetir o codec concluído. Live não qualificado.

---

## Política, head, reserva e consumo temporais — rodada 22:46 UTC

Implementados no módulo público existente os três DTOs restantes:
`EpochPolicyOfflineV3`, `EpochAnchorOfflineV3` e `EpochConsumptionOfflineV3`.
Head/reserva compartilham tipo, mas têm purpose assinado e formato exclusivo:
head não admite claim; reserva exige claim válido. Todos são frozen e protegidos
em repr. Não há novo módulo, armazenamento, endpoint, signer ou runtime.

`epoch_statement_signing_message_offline_v3` valida tipo exato e limites e produz
ASCII/JSON canônico com versão `C3_PUBLIC_EPOCH_STATEMENT_SYNTHETIC_ONLY_V3`,
Ed25519 e purpose explícito. A política assina namespace, geração, issued_at/
expires em ms, revogações ordenadas únicas e identidade/época da chave.
Head/reserva assinam namespace, instância, geração/hash da política, digest do
pedido V3 completo, desafio, intervalo em ms e identidade/época da chave;
a reserva também inclui claim semântico estável. Não há tempo monotônico serializado.

Consumo assina digest da mensagem canônica da reserva e committed_digest, exigindo
igualdade. O objeto conserva a reserva para checagens independentes. O digest
não inclui os bytes da assinatura da reserva; a verificação conjunta exige
também sua assinatura válida e igualdade da reserva fornecida/incorporada.
Não interpretar o digest ou assinatura de consumo como observação de commit real.

Limites de referência: política com janela positiva até 300000 ms, head/reserva
até 5000 ms, épocas/gerações positivas e inteiros seguros, até 128 hashes de
revogação em tuple ordenada sem repetição, mensagem canônica sem assinatura até
16384 bytes. Bool/float/NaN, tipo desconhecido, versões inadequadas e formas
incompatíveis recusados. Esses limites não aprovam política operacional nem
limite HTTP, pois ainda não existe transporte/parser de entrada.

### Checagem conjunta implementada, explicitamente não operacional

`epoch_evidence_signatures_consistent_offline_v3` verifica pedido, política,
head, reserva e consumo com quatro chaves públicas distintas e épocas/pins
explícitos. Exige os mesmos namespace/root/instância, desafios de head/reserva
esperados, payload/claim, geração/hash de política e reserva incorporada; recusa
revogação de qualquer chave ativa. A validade do head precisa estar contida na
interseção pedido/política; a da reserva, contida no head. Não amplia validade.

O nome indica somente consistência de evidências assinadas. **Uma cadeia histórica
válida pode passar repetidamente.** Não há fonte de tempo atual, consulta ao head
autoritativo, proteção de rollback, gravação ou consumo único nesta função.
Essas garantias e revogação pós-commit continuam indispensáveis antes de qualquer
futura autorização operacional. Não ligar o booleano ao gate/runtime e não
tratar desafio fornecido pelo chamador como prova autônoma de atualidade.

### Testes e evidência

90 novos testes aprovados, zero falhas/erros/skips, 63 deselected, JUnit 0,725 s.
Oráculos literais independentes dos quatro purposes; alteração de campos,
formas inválidas, limite de revogações, versões/purpose/prehash, pins/chaves
distintas, default-off e separação V2. Dezesseis casos mantêm assinaturas válidas
e alteram vínculos, revogação ou contenção para provar recusa pela causa correta.
Não repetidos testes antigos não afetados; o pedido V3 e fluxos V2 ficaram intactos.

Evidência `.offline_validation/c3_dependency_assembly_20260911/cq-c3-lab-assembly-3i18j9va/`;
SHA-256 JUnit `8167e1687e3bee7e79716b900ba05ee9770abdb30de0fae70dfd89f110576331`.
Hashes de módulo/teste/helper conferidos ao overlay. Laboratório existente,
UID999, zero rotas, fontes read-only, sem mounts Windows/download/servidor.
Não executados testes SDK/KMS/rede/tempo real/PostgreSQL físico/cadeia operacional.

Cinco arquivos alterados: `trade_registry_c3_public_authority_offline_v2.py`,
`tests/test_c3_public_authority_wire_offline_v2.py`, `tests/helpers/c3_dependency_assembly_lab.py`,
esta proposta e `C3_OFFLINE_CONTINUITY_20260911.md`. Seletor
`run-epoch-statements-offline` no helper existente. Nenhum secret, dado real,
chamada externa, main, flag, IAM/Render, commit/push/deploy nesta rodada.

Próxima unidade necessária: codec estrito e limitado V3, sem transporte, sem
nova versão ou outro backend. Preservar bytes assinados e rejeitar ambiguidades
de JSON/tipo/versão antes de construir DTOs. Para consumo, receber a reserva
decodificada como dependência explícita e conferir digest, sem fabricar o objeto
a partir do hash. Manter separadas assinatura, atualidade e autoridade; não
repetir os formatos/auditorias já concluídos. Live continua não qualificado.

---

## Pedido com validade comum V3 — resultado da rodada 22:39 UTC

Implementada a primeira representação temporal versionada, exclusivamente no
módulo offline existente: `EpochRequestOfflineV3` contém namespace, root, nonce,
not_before_epoch_ms/expires_epoch_ms, key_id/key_epoch, escopo semântico,
writer_count, maintenance_only e assinatura protegida em repr. Dataclass frozen;
construção sem I/O. Nenhum deadline monotônico local está nesse objeto.

Três operações default-off: mensagem canônica sem assinatura, digest de identidade
de consumo e verificação criptográfica com pins explícitos. JSON ASCII canônico
com ordenação, sem espaços, domain/version `C3_PUBLIC_EPOCH_REQUEST_SYNTHETIC_ONLY_V3`,
algorithm Ed25519 e purpose request fixos. Todos os campos do pedido, exceto
signature_hex, estão cobertos. Não há parser de mensagens não confiáveis ou signer.
O módulo não cria/importa credencial operacional. Seeds de teste são públicas.

Validação exata de tipos, 19 writers, manutenção exclusiva, nonces 1..256 Unicode
válidos, hashes lowercase64, época positiva e valores temporais inteiros seguros;
janela máxima de referência 300000 ms. Mensagem canônica unsigned limitada a
4096 bytes; teste contempla 256 escalares não-BMP com maior escape e inteiros
máximos. Esse limite não qualifica tamanho do envelope HTTP com assinatura/headers.

Verificação requer raw32 da chave pública, época, namespace e root esperados,
todos injetados explicitamente; não usa identidade declarada pelo pedido como
âncora de confiança. Confiança desses pins é pré-condição externa. Signature_hex
é lowercase128. Ausência da biblioteca, formatos incompatíveis e exceções recusam.
Não há fallback V2/HMAC, troca de escopo ou adaptação automática do pedido antigo.

`epoch_request_signature_verified_offline_v3` pode retornar True repetidamente:
significa APENAS assinatura/contexto válidos, não prazo atual, revogação, raiz
autenticada, consumo, readiness ou autorização. `epoch_request_claim_offline_v3`
é somente identidade não verificada, preservando `{scope,root,nonce}` e exigindo
armazenamento sob namespace previamente fixado. Modificar validade/chave muda a
mensagem assinada, mas não essa identidade. Não ligar esses retornos a permits.

48 testes novos aprovados, zero falhas/erros/skips; 15 casos antigos deselected,
JUnit 0,523 s. Oráculo literal sem reutilizar serializer da implementação,
alteração de todos os campos, pins inválidos, domain/purpose/version/prehash,
tipos/tamanho/Unicode, assinatura inválida, biblioteca indisponível, default-off,
separação de tipos V2/V3 e identidade de replay. O consumidor antigo continua
rejeitando o tipo novo antes de qualquer porta. Não foram mudados fluxos V2.

Evidência `.offline_validation/c3_dependency_assembly_20260911/cq-c3-lab-assembly-ygkjihwu/`;
SHA-256 JUnit `a2ca6eb5a17701380f4a54fbd0901dc7d12df8171af50291134ea6161ebeb6c8`.
Hashes de módulo/teste/helper conferidos com overlay. Laboratório UID999, zero
rotas, fontes read-only e sem mounts Windows; Python existente, sem downloads.
Sem teste KMS/SDK/rede/fonte real de tempo/PostgreSQL físico ou execução operacional.

Arquivos: `trade_registry_c3_public_authority_offline_v2.py`,
`tests/test_c3_public_authority_wire_offline_v2.py`, `tests/helpers/c3_dependency_assembly_lab.py`,
esta proposta e continuidade. Nenhum secret, Registry real, chamada externa,
flag, main, IAM/Render, commit/push/deploy nesta rodada. Risco residual principal:
os outros três objetos do protocolo ainda usam o formato temporal V2; portanto
esta entrega NÃO é uma cadeia remota pronta nem uma alteração de runtime.

Próximo passo já delimitado: representação sintética compatível de política,
head/reserva e consumo, com contenção das janelas, todos os vínculos anteriores
e separação de versões; manter módulos/consumidores operacionais intactos. Não
refazer o pedido, os testes concluídos ou a comparação de infraestrutura.

---

## Modelo temporal offline — 11/09, conclusão às 22:31 UTC ou posterior

Concluído o cálculo puro no módulo público existente, sem alterar os DTOs,
assinaturas ou chamadas de consumo atuais. `remaining_epoch_window_ms_offline_v2`
é default-off, exige escopo sintético e retorna duração inteira em milissegundos
ou `None`. Seu resultado NÃO autentica um relógio, pedido ou emissor e NÃO concede
permissão. Nenhum consumidor/runtime foi ligado ao cálculo.

### Regra implementada e hipóteses que permanecem externas

Sejam N/E início/fim da validade, [L,U] intervalo conservador do horário atual,
B orçamento local restante e W largura máxima explicitamente escolhida:

- Exigir inteiros exatos entre 0 e 2**53-1; bool/float/ausência são recusados.
- Exigir `0 < E-N <= 300000`, `N <= L <= U < E`, `U-L <= W` e `B > 0`.
- Duração admitida: `min(5000, B, E-U)`. O instante E já está expirado;
  a duração retornada termina no máximo em E, não permite agir nesse limite.
- B deve ser medido contra o ÚLTIMO deadline monotônico local admitido. Cada
  rechecagem só encurta esse deadline: nunca reusar o orçamento inicial após
  passagem de tempo, recuo do horário civil, retry ou reinício.

Os limites 300 s/5 s são referências do experimento, não política operacional
aprovada. W não tem default inferido. A fonte confiável deve produzir intervalo
atualizado que inclua incerteza, atraso de coleta e desvio do relógio. Deriva do
relógio monotônico e tempo entre checagem e efeito precisam de margem e
qualificação próprias; o cálculo não demonstra essas propriedades físicas.
Revalidar antes/depois de cada porta; timeout após commit não apaga consumo.
Falha/ausência de fonte confiável exige recusa, não horário fornecido pelo cliente.

### Evidência final recuperada, sem repetir execução

25 testes aprovados, 0 falhas/erros/skips, 94 deselected pelo seletor específico;
JUnit 0,557 s. Inclui fronteiras, expiração incerta, tipos inválidos, budget
esgotado, rechecagem sem renovação e uma grade sintética com mais de mil casos
aceitos. A grade conta como UM teste, não como milhares de testes independentes.
Evidência: `.offline_validation/c3_dependency_assembly_20260911/cq-c3-lab-assembly-w_r4rlj1/`.
SHA-256 results.xml: `039e871acdb6b4e3127ba737a3ea12118e7dfec04ab1bd87b58d2d6e2dd1d915`.
Hashes de módulo, teste e helper conferidos com `result.json.overlay_sha256`.
Isolamento confirmado no relatório: UID 999, zero rotas, sem mounts Windows,
fontes read-only. Sem instalação, servidor ou acesso operacional. Não repetir os
96 testes anteriores: o caminho de consumo não foi alterado por esta função pura.
Não executados: fonte de tempo real, SDK, relógios físicos, rede ou PostgreSQL real.

Arquivos da unidade temporal: `trade_registry_c3_public_authority_offline_v2.py`,
`tests/test_c3_public_authority_offline_v2.py`, `tests/helpers/c3_dependency_assembly_lab.py`,
esta proposta e `C3_OFFLINE_CONTINUITY_20260911.md`. Nesta retomada só os dois
documentos foram editados; código e execução pertencem à rodada anterior e foram
verificados, não reapresentados como nova implementação.

### Decisão de formato: versão explícita, sem conversão V2 em trânsito

Inventário concluído no código: não basta trocar `binding.deadline`. A política
`RevocationsV2` assina `issued_at/expires_at`; `AnchorReceiptV2` assina deadline,
challenge, geração/hash da política e, na reserva, claim/payload. O recibo de
consumo assina o digest dessa reserva. Todos usam hoje o relógio compartilhado
do experimento. Portanto, **não publicar um serializer V2 como protocolo remoto**.

Para um próximo experimento versionado, a decisão é separar:

| Objeto | Validade comum assinada | Estado exclusivamente local |
| --- | --- | --- |
| Pedido | not_before_epoch_ms, expires_epoch_ms; namespace, root, nonce, 19 writers e manutenção exclusiva continuam vinculados | Deadline monotônico do chamador, nunca serializado nem reconstruído a partir de relógio alheio |
| Política | issued_at_epoch_ms, expires_epoch_ms; namespace, geração e revogações preservados | Fonte de tempo e orçamento de leitura |
| Head/reserva | not_before_epoch_ms, expires_epoch_ms, challenge e digest do pedido completo; geração/hash, namespace/instância, claim/payload preservados | Deadline do servidor não é devolvido como se fosse o do cliente |
| Consumo | Digest da reserva completa e evidência de commit, abrangendo transitivamente validade e pedido | Orçamento remanescente do cliente continua valendo após a resposta |

A janela efetiva de uma reserva deve ficar contida na do pedido e na validade
da política; uma resposta não pode ampliá-la. Ao retornar, o cliente verifica
a própria janela/monotônico e todos os vínculos, mesmo se o servidor disser
que terminou a tempo. Orçamentos locais limitam trabalho em cada host, NÃO
renovam o limite ponta a ponta; recibo tardio não autoriza o chamador. Fonte,
incerteza e política temporal não podem vir de campos não autenticados do pedido.

Domínios de hash/assinatura precisam de nova versão explícita e tipos dedicados
ao experimento sintético; V2 continua recusando novos tipos, sem autodetecção,
fallback HMAC, reassinatura automática ou troca de escopo para produção. Isso é
decisão de desenho, NÃO um protocolo novo já implementado/qualificado.

**Identidade de replay não é versão de assinatura.** Hoje `_verified_request_context_v2`
deriva claim de `{scope, root, nonce}` e o armazenamento reserva `(namespace, claim)`.
Trocar o scope junto com a versão muda o claim. Em uma futura versão sintética,
preservar o mesmo escopo semântico de manutenção e namespace/root/nonce na chave
de replay, mudando apenas o domínio de assinatura/formato. Não incluir chave,
época, validade, challenge ou versão de mensagem na identidade de consumo.
Root/namespace novos não herdam proteção automaticamente: exigem uma decisão
de migração autenticada e histórico preservado, fora desta unidade. Não fazer
migração do experimento para produção nem mapear escopos operacional/offline.

Verificação de replay **concluída na mesma rodada**, após conferir cobertura:
scope/root/namespace incorretos e rotação de época já eram cobertos. Acrescentados
três casos ausentes no teste existente: renovar prazo após expiração original,
trocar material Ed25519 sintético e fazer ambos. Payload novo/claim preservado,
reconstrução de cliente e consumidor, histórico intacto após recusa e controle
positivo com nonce distinto. Não simula migração de scope/root/namespace.

3 aprovados, zero falhas/erros/skips, 119 deselected, JUnit 0,812 s. Seletor novo
`run-replay-reissue-offline` no helper existente, sem novo launcher. Evidência:
`.offline_validation/c3_dependency_assembly_20260911/cq-c3-lab-assembly-5aotlr7u/`.
SHA-256 results.xml `54fc96f3de7dc6a8a9df3e5edd22affaa53146c62858d37393e7c85e70e7d400`.
Hashes conferidos com overlay; isolamento idêntico ao reportado acima. Nenhum
teste temporal anterior repetido. O módulo público permaneceu intacto; nesta
rodada foram editados teste público/helper/proposta/continuidade (quatro arquivos).

Próxima unidade: representação assinada sintética versionada da validade comum
e testes de hash/tamper/versão no módulo existente; preservar replay, sem
conversor V2, novo backend ou ligação ao consumidor. O inventário e a decisão
estão concluídos, não reabri-los como outra auditoria. Não repetir a comparação
DynamoDB nem os testes temporais sem mudança. Integração runtime, IAM operacional
e Live continuam não qualificados. Nenhum secret, chamada externa, flag, commit,
push ou deploy nesta retomada.

---

## Resultado da comparação de consumo — 11/09, após 22:07 UTC

**Não promover a alternativa C a substituição equivalente.** As transações
permitem reproduzir parte da semântica, mas a paridade de privilégio somente-inserir
e o tratamento de retries não estão comprovados. Mantido o consumidor PostgreSQL
offline existente; nenhum backend DynamoDB foi criado. Esta conclusão supera a
sugestão anterior de avançar diretamente para um consumidor AWS. A estimativa de
US$ 30 + variáveis não é uma solução pronta nem uma recomendação de contratação.

| Garantia existente | Mapeamento necessário na alternativa C | Conclusão desta avaliação |
| --- | --- | --- |
| Pedido assinado e vínculo de destino | Validar pedido completo e identidade do transporte antes de qualquer escrita | Lacuna comum corrigida APENAS para o pedido no consumidor offline; identidade remota continua pendente |
| Reserva por `(namespace, claim)` | Put condicionado à ausência, sem incluir época, chave ou instância restaurada na identidade do claim | Viável como semântica de aplicação; não usar somente ClientRequestToken |
| Política igual ao head na mesma decisão de reserva | ConditionCheck no item de política e Put no item de claim, numa transação | Não fazer leitura seguida de escrita desprotegida; itens distintos, mesma conta/região |
| Reserva precede commit e assinatura | Dois estágios preservados: testemunho independente primeiro, ledger depois | Não fundir tudo em rollback conjunto que desfaça a reserva após falha |
| INSERT sem UPDATE/DELETE/TRUNCATE | Privilégio de armazenamento precisa impedir substituição de evidência | Não demonstrado por permitir PutItem ou somente TransactWriteItems |
| Commit confirmado antes de recibo | Confirmação autenticada da gravação; só então assinatura vinculada ao mesmo digest | Resposta perdida não autoriza retry que gere nova permissão |
| Rotação e restauração não apagam consumo | Testemunho persistente fora do ledger restaurável; namespace estável | Restaurar ambos continua fora do modelo seguro, como no controle negativo existente |
| Instância correta | Matricular destino e identidade concreta; recusar troca/restauração não autorizada | Nome/ARN copiado e atributos restaurados não provam atualidade |
| Prazo e revogação antes da saída | Prazo total, leitura atual e conferência de política após commit | Timeout de SDK não desfaz efeito já confirmado; nunca compensar apagando claim |
| Least privilege verificado | Evidência independente de IAM/configuração, além do código de aplicação | Fake local ou resposta do próprio chamador não demonstram permissões efetivas |

Fundamentação: TransactWriteItems executa as ações atomicamente e não permite
duas ações no mesmo item. Seu token de idempotência vale dez minutos; chamadas
idênticas nesse intervalo podem retornar sucesso sem nova escrita. Esse sucesso
não deve ser convertido em novo recibo/novo desafio de autorização.
[API de transações](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_TransactWriteItems.html).

PutItem também pode substituir um item existente; attribute_not_exists é uma
condição da requisição, não um privilégio SQL INSERT. A documentação IAM de
transações governa Put pela permissão PutItem; EnclosingOperation restringe a
operação envolvente, mas não comprova a presença da condição esperada. **Inferência
para este desenho:** negar UpdateItem/DeleteItem e permitir PutItem não demonstra
preservação equivalente à role PostgreSQL, que é conferida por `_schema_valid`.
Não se conclui que DynamoDB seja inadequado em geral, somente que a proposta C
ainda não atende à equivalência exigida sem controles adicionais qualificados.
[PutItem](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_PutItem.html),
[IAM transacional](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis-iam.html)
e [condições IAM](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/specifying-conditions.html).

### Correção implementada no experimento existente

`PublicPostgresConsumerOfflineV2.consume_once` agora exige `request` e `binding`
completos e recomputa payload/claim, antes de consultar política, reservar ou
persistir. O construtor recebe explicitamente verifier de pedidos e root esperado;
as quatro identidades de assinatura permanecem distintas. Cliente e consumidor
reutilizam `_verified_request_context_v2`, sem lógica duplicada ou novo wrapper.
A composição exige a mesma instância do verifier e o mesmo root nos dois lados.

A validação exige escopo offline, manutenção exclusiva, 19 writers, nonce
limitado, root correto, assinatura request e prazo finito dentro do prazo assinado
e de cinco segundos. Chamadas legadas contendo só digests falham fechado. Isso é
uma mudança intencional da API do experimento offline, não do runtime publicado.
Assinatura comprova autorização do pedido; NÃO autentica sozinha o cliente de rede.
Nenhuma API, SDK ou integração foi criada. Os bloqueios de main ficaram intactos.

### Testes e limites

96 aprovados, zero falhas/erros/skips, 2 testes de PostgreSQL físico excluídos
explicitamente; JUnit 4,217 s. São 24 cenários novos de consumo direto e 72
regressões afetadas, incluindo concorrência, revogação, restauração, recibo perdido
e composição com manutenção/recuperação. Não somar isso como porcentagem Live.
Não foram repetidos os testes de formato HMAC/Ed25519 sem mudança pertinente.

Evidência final: `.offline_validation/c3_dependency_assembly_20260911/cq-c3-lab-assembly-v_7jiz3f/`.
JUnit SHA-256 `9b61d467a101c3f5875cbd5603a4e4baca3dae93d9daca82b5e8a2ae8be53018`.
Execução anterior de 94 testes preservada em `cq-c3-lab-assembly-zm66k04k`, hash
`25bb1995e71daa3bbd70889cc98490418afbe7ea9f99104eaf8fd284dbdeb468`;
a segunda execução acrescentou dois controles de origem de relógio, sem mudar
o módulo de implementação. Não somar as duas execuções como casos distintos.
Hashes dos quatro arquivos de código/teste comparados ao overlay efetivamente
executado. Python 3.11.9 já existente; laboratório sem rede, UID 999, fontes
read-only, imports/processos operacionais bloqueados. Nenhum PostgreSQL foi iniciado.

Arquivos alterados nesta rodada: `trade_registry_c3_public_authority_offline_v2.py`,
`tests/test_c3_public_authority_offline_v2.py`, `tests/helpers/c3_public_authority_fixture.py`,
`tests/helpers/c3_dependency_assembly_lab.py`, esta proposta e
`C3_OFFLINE_CONTINUITY_20260911.md`. Nenhum secret, Registry real, chamada operacional,
flag, IAM, Render, commit, push ou deploy foi acessado/alterado. Só documentação
pública consultada externamente. Risco residual: teste com servidor PostgreSQL
neste novo fluxo ainda não executado; o contrato SQL não foi alterado.

### Delimitação da serialização, concluída nesta mesma rodada

A chamada atual tem sete entradas: namespace, claim_sha256, payload_sha256,
challenge, deadline, request e binding, sendo request/binding objetos compostos.
A oitava entrada de um eventual envelope seria sua versão
explícita. Não confundir esse envelope futuro com um contrato já implementado.
Request preserva os cinco campos de SignatureV2; binding preserva os sete de
AuthorizationBindingV1. Campos desconhecidos, duplicados, UTF-8 inválido, números
não finitos, booleans em campos numéricos e payload acima do limite devem ser
rejeitados antes de construir DTOs. Um limite inicial proposto de 4096 bytes
precisa ser qualificado com o pior caso de nonce/escape, não é um limite já aplicado
ao transporte. Preservar representação numérica usada no hash (100 não é 100.0
no JSON canônico), assinatura e campos vinculados; nunca recalcular assinatura
ou converter escopo sintético em produção ao decodificar.

Bloqueio técnico que impede um simples serializer virar integração: o prazo
assinado atual é um número no relógio injetado do experimento. A composição
local compartilha relógio; o protocolo não define uma época comum entre máquinas.
Os dois novos controles recusam chamadas diretas com origens 0 e 10000 contra
um prazo 105, antes de consultar política/storage. Não permitem inferir que
qualquer desvio de relógio seja detectado, nem qualificam relógios distribuídos.

Antes de um formato operacional, separar validade assinada em época comum da
contagem monotônica local de orçamento, definir tolerância a desvio e rejeitar
origem desconhecida ou validade indeterminada. Isso exige decisão de protocolo
versionada e revisão dos vínculos; não alterar o prazo assinado em trânsito,
subtrair relógios de máquinas diferentes ou simplesmente somar cinco segundos
ao receber um pedido vencido. Não foi criado serializer/API para ocultar a lacuna.

Próxima unidade offline: definir esse modelo temporal e seus cenários de
expiração/desvio antes de escrever a codificação entre processos. Transporte
autenticado e privilégio do armazenamento permanecem pendentes; não inventar
IAM nem voltar à comparação DynamoDB concluída. Nenhuma contratação recomendada
antes de fechar essas condições.

---

## Decisão técnica da raiz e transporte — 11/09, após o plano

**Raiz: preferir HMAC-SHA256 com verificação remota sem exportação da chave.**
É uma recomendação de implementação futura, não um provider implementado.
A interface `authenticated_root_authority_attestation_verified_v2` já aceita
um objeto com `verify_root_authority_signature_v2`; não obriga o fornecimento
dos bytes secretos. O adapter concreto `InjectedRootAuthorityVerifierV2`, ao
contrário, resolve bytes e calcula HMAC localmente: ele NÃO é um adapter KMS.
Preservar esse caminho de referência e seus testes; não disfarçar um ARN como chave.

O payload assinado é SHA-256 do JSON canônico dos campos, excluindo assinatura
e hash final. A mensagem HMAC são os **64 bytes ASCII do hexadecimal**, não os
32 bytes do digest. A tag tem 32 bytes e ocupa 64 caracteres hexadecimais.
`VerifyMac` com HMAC_SHA_256 é compatível com essa semântica. Uma implementação
futura precisa mapear identidade matriculada para ARN concreto, fixar algoritmo,
validar identidade/algoritmo da resposta, aceitar somente MacValid booleano true
e tratar erros como recusa. Não aceitar alias mutável, KeyId escolhido pelo pedido
ou conteúdo arbitrário devolvido por um callback como autenticação operacional.
[VerifyMac](https://docs.aws.amazon.com/kms/latest/APIReference/API_VerifyMac.html).

Rejeitada a conversão direta para Ed25519 nesta interface: mudaria algoritmo,
tamanho da assinatura, atestado, verificadores e vínculos de recuperação. A
variante pública existente é sintética e nem inclui a finalidade root_authority.
Não adicionar essa finalidade ao conjunto atual de quatro chaves apenas para
encaixar a raiz. A preferência HMAC reduz mudanças de formato, mas não elimina
versionamento operacional, verificação de atualidade ou recuperação autoritativa.

Permissões futuras da raiz: emissor administrativo separado com GenerateMac
somente numa **quinta chave HMAC dedicada**; Central com VerifyMac, nunca
GenerateMac ou bytes da chave. Matricular root/storage/key/epoch por responsável
autenticado e fixar a correspondência a um ARN imutável. Rotação: nova chave e
época, vínculo ao atestado anterior e publicação monotônica da época aceita;
manter o histórico, sem autorizar nova manutenção com chave revogada. Não
substituir quatro roles existentes por uma role ampla. Custódia HMAC no KMS não
permite o modelo atual de obter chave bruta: [HMAC KMS](https://docs.aws.amazon.com/kms/latest/developerguide/hmac.html).

**Limite de segurança identificado:** HMAC válido não comprova atualidade.
`PersistentRootAuthorityRevocationSourceV2` aceita envelope local com hash e
geração positiva; isso não estabelece uma referência externa anti-rollback.
O provider da raiz também não prova fsync/atomicidade do emissor apenas por ler
um arquivo. Produção precisará consultar estado autoritativo externo atual,
com época/hash do atestado e revogação vinculados; backup local não basta.
A interface de verificação tampouco recebe deadline: o futuro transporte deve
ter orçamento explícito compartilhado com a admissão, tempo de chamada limitado
e rechecagem de expiração/lease antes de qualquer efeito. Não alegar que o
teste de exceção abaixo comprova interrupção de uma chamada bloqueada.

**Transporte: não publicar diretamente o consumidor de digests.**
`PublicMaintenanceAuthorizationOfflineV2` verifica o pedido no cliente;
`PublicPostgresConsumerOfflineV2.consume_once` recebe apenas namespace, claim,
payload, challenge e deadline. Ao separar processos, o servidor precisa receber
o pedido completo, recalcular seu vínculo, verificar assinatura, finalidade,
janela, namespace/root permitidos e identidade autenticada ANTES da reserva.
Uma chamada autenticada também não pode autorizar qualquer digest. Rede privada,
assinatura isolada ou OIDC de acesso à AWS não autenticam automaticamente uma
API própria no Render. Não criar um verificador SigV4 caseiro.

Direção recomendada para a próxima avaliação offline: **alternativa C, consumidor
e testemunho na AWS com entrada IAM**, em vez de introduzir autenticação própria
para a API privada Render da alternativa B. O acesso pode usar Invoke síncrono
com role cliente exclusiva e credenciais OIDC temporárias; se for adotada Function
URL, exigir AWS_IAM e as permissões/condições específicas documentadas, nunca
NONE. Somente a role cliente invoca consumo; apenas emissores próprios administram
pedidos/política, e a Central não escreve diretamente no ledger. A assinatura C3
do pedido continua obrigatória mesmo depois da autenticação IAM.
[Controle de acesso Lambda](https://docs.aws.amazon.com/lambda/latest/dg/urls-auth.html).

Essa recomendação **altera a referência de hospedagem do novo consumidor**, não
a Central já publicada, e ainda não substitui a alternativa B validada apenas
offline. A alternativa C exige demonstrar paridade de consumo com armazenamento
transacional DynamoDB: tabela de testemunho independente do ledger restaurável,
política atual e reserva condicionais, consumo queimado antes do recibo e nenhuma
compensação automática após resposta perdida. Leitura eventual ou token de
idempotência temporário não substituem o registro durável. Não habilitar backend
novo nem flexibilizar o type check PostgreSQL existente para simular compatibilidade.
[Transações](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html)
e [consistência](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadConsistency.html).

Impacto preliminar no subtotal anterior: B com quinta chave passa de US$ 43,50
para **US$ 44,50 + variáveis**; C sem novo compute/PG Render teria **US$ 30 +
variáveis** (Pro 25 + cinco chaves 5). Não são cotação final, teto de gasto,
economia garantida ou substituição das contas atuais. Não contratar nenhuma
alternativa antes de qualificar semântica, autenticação e recuperação.

### Evidência local nova, sem homologação AWS

`tests/test_c3_root_hmac_wire_offline_v2.py`: 14 testes aprovados, zero falhas,
erros ou skips; JUnit 0,177 s. Oráculo literal independente do JSON e HMAC por
implementação criptográfica separada; teste da interface sem resolução de chave,
formatos incompatíveis, resposta não booleana e exceção. Tudo em memória com
material público sintético. Não houve GenerateMac/VerifyMac real, SDK ou rede.
Evidência: `.offline_validation/c3_dependency_assembly_20260911/cq-c3-lab-assembly-dxp_kr78/`;
SHA-256 de results.xml `0aff7f708972e0b6d7f7c9ab1ba14dc345a062741f19adbad6917482bdd928a0`.
Reutilizado laboratório existente, UID 999, zero rotas e fontes read-only.
Somente teste novo, seletor do helper existente, proposta e continuidade editados.
Os 15 testes Ed25519 anteriores não foram repetidos. Nenhum módulo de produção,
secret, Registry real, chamada operacional, IAM, Render, flag, commit ou deploy
foi acessado/alterado nesta rodada; fontes públicas consultadas separadamente.

Próxima unidade necessária: avaliar a paridade de consumo da alternativa C
contra as garantias concretas do experimento existente, sem provisionar ou
implementar um backend operacional. Não repetir a decisão HMAC nem criar uma
nova camada de autorização apenas para marcar progresso.

---

## Plano vigente — 11/09/2026: preparar antes de contratar

Esta seção prevalece sobre pendências históricas abaixo. Planejamento concluído
nesta rodada; não é autorização de compra nem declaração de prontidão operacional.
A conta AWS e o MFA já foram verificados na rodada anterior. As quatro roles
CentralQuantC3RequestSigner, CentralQuantC3PolicySigner, CentralQuantC3AnchorSigner
e CentralQuantC3ConsumptionSigner existem, sem permissões anexadas e com trust
dormente Deny. Não são quatro serviços de assinatura funcionando. Não recriá-las.

### Escopo, localização e custos

Referência B: manter Central e Redis atuais; separar o serviço que consome
autorizações e seu PostgreSQL no Render, com testemunho de atualidade/reserva
e assinaturas na AWS. Não substituir automaticamente Render, Redis ou ChatGPT.
Oregon é a região proposta para aproximar os componentes; ainda não é uma
configuração aplicada. IAM é global: a URL do console não seleciona a região KMS.

| Item proposto | Quantidade/função | Referência mensal em USD |
| --- | --- | --- |
| Render Pro | Workspace com autenticação gerenciada OIDC; não é o compute da Central | 25 |
| Serviço privado Render | Uma API de consumo separada, compute inicial 512 MB | 7 |
| Render PostgreSQL | Um ledger separado, compute inicial 256 MB | 6 |
| Armazenamento PostgreSQL | Hipótese de dimensionamento: 5 GB a 0,30/GB | 1,50 |
| AWS KMS | Quatro chaves de assinatura, uma por finalidade, sem réplicas | 4 |
| AWS Lambda e DynamoDB | Um testemunho e uma tabela de política/reservas; uso sob demanda | Variável, ainda não cotado por volume |
| Operações KMS, logs, retenção, tráfego e excedentes | Conforme uso efetivo | Variável, não incluído no subtotal |

Subtotal de referência: **US$ 43,50/mês adicionais**, antes das variáveis,
impostos e câmbio. Não é teto, cotação final ou arquitetura de alta disponibilidade
dimensionada. Se os US$ 200 informados pelo usuário se repetissem, a soma ilustrativa
seria US$ 243,50 mais variáveis; a fatura atual não foi auditada. Créditos AWS não
foram descontados da projeção. Rotação com novas chaves e uma eventual autoridade
adicional de recuperação aumentariam o custo. Não presumir que quatro chaves
cobrem a raiz de recuperação. Nada desta lista foi contratado nesta rodada.

Fontes públicas consultadas em 11/09/2026: [preços Render](https://render.com/pricing),
[Pro a US$ 25](https://render.com/changelog/updated-plans-for-render-workspaces),
[armazenamento e custos Render](https://render.com/articles/how-much-does-cloud-application-hosting-cost-for-small-businesses),
[OIDC exige Pro ou superior](https://render.com/docs/oidc) e
[preços KMS](https://aws.amazon.com/kms/pricing/). KMS cobra US$ 1 por chave/mês;
requisições com chaves assimétricas não entram na franquia de 20 mil requisições.
As páginas de preços têm conteúdo dinâmico; valores devem ser reconfirmados na
tela de contratação. Não usar o exemplo ECC-256 da página como tarifa Ed25519.

### Identidades e permissões mínimas propostas

| Identidade | Quem poderia usá-la na implantação futura | Permissões e limites |
| --- | --- | --- |
| RequestSigner | Emissor administrativo identificado, sessão curta e MFA, separado da Central | Sign somente na chave de pedidos; não mudar política, consumir ledger ou emitir raiz de recuperação |
| PolicySigner | Controle administrativo de revogação, identidade explícita e sessão curta com MFA | Sign somente na chave de política e publicação controlada de versão crescente; nunca restaurar versão antiga |
| AnchorSigner | Função Lambda dedicada ao testemunho | Sign na chave de testemunho; leitura consistente e escrita condicional/transacional nos itens necessários da tabela; sem apagar reservas, restaurar tabela ou administrar IAM/KMS |
| ConsumptionSigner | Somente o novo serviço Render, identificado por OIDC | Sign na chave de recibos e invocar a função de testemunho; usuário SQL sem DDL, exclusão de consumo ou poderes de restauração |
| Cliente Central | Identidade distinta, ainda a qualificar no transporte escolhido | Solicitar consumo autenticado e consultar resultado; nenhum Sign, escrita direta no ledger ou administração da autoridade |
| Administrador de implantação | Identidade humana não-root explicitamente cadastrada | Gerenciar recursos delimitados e PassRole limitado à função necessária; nunca conceder esse papel ao runtime |

Essa tabela é um desenho, não políticas prontas para colar. Ainda faltam os IDs
do workspace/serviço, principals humanos, ARNs de recursos e a autenticação
cliente Central → API privada. Rede privada sozinha não autentica o solicitante.
Não inventar IDs nem habilitar wildcard para superar essa ausência. Para OIDC,
usar o provider do workspace real, audience sts.amazonaws.com e igualdade do
subject do serviço específico. Uma role por serviço Render; o cliente Central
não pode compartilhar ConsumptionSigner. Conectar OIDC exige variável e redeploy
do serviço, portanto está fora da autorização atual de não alterar Render.

As roles de emissão não devem ser atribuídas diretamente à Central. Separar
permissões não equivale a controle por duas pessoas: isso só existirá se houver
dois responsáveis distintos. A trust Lambda e PassRole exigem revisão específica;
não supor que uma condição SourceArn de função resolva o isolamento da role.

### Ordem de execução e critérios de parada

1. **Agora, sem contratação:** fechar no código existente o desenho da raiz
   autenticada de recuperação e do transporte entre cliente e consumidor.
   Comparar os requisitos HMAC atuais com verificação remota KMS e alternativa
   pública versionada; escolher tecnicamente antes de implementar. Não criar
   outra camada apenas para registrar a pendência. Manter os testes já aprovados
   como evidência histórica, sem repeti-los sem mudança.
2. **Antes de habilitar permissões:** completar o inventário de principals e IDs,
   revisar trust e ações por recurso, orçamento por volume e retenção, regras de
   rotação/recuperação e isolamento administrativo. A raiz não pode depender de
   hashes arbitrários fornecidos pelo solicitante nem de backup restaurável da
   própria Central. Ausência de qualquer vínculo mantém Deny e default-off.
3. **Homologação contratada, somente com autorização específica posterior:**
   criar recursos enumerados em namespace isolado, publicar serviços desativados,
   vincular cada identidade ao recurso exato e testar apenas dados sintéticos.
   Incluir ensaios de autenticação inválida, revogação, timeout, resposta perdida,
   repetição e restauração do ledger. Não tocar Registry real nem habilitar Live.
4. **Integração operacional separada:** somente depois de providers homologados,
   raiz de recuperação válida e recuperação de transações pendentes comprovada.
   O binder atual que proíbe startup permanece bloqueante. Depois, preflight
   atualizado; qualquer rearmamento Live é decisão separada, nunca consequência
   automática de comprar infraestrutura ou obter assinatura válida.

### Reversão e contenção

Primeiro impedir novas solicitações e suspender os emissores/assunção das roles;
preservar consumo já confirmado, reservas e evidência. Uma reserva consumida não
volta a disponível por timeout ou falha posterior. Não fazer rollback por apagar
tabela, reduzir versão de política, restaurar ledger antigo ou excluir chaves.
Preservar chaves públicas históricas e revogação monotônica. Nenhum rollback
pode ligar trading ou retomar writers sem recuperação validada. Retenção de
recursos pode continuar gerando custo; exclusão definitiva precisa de plano e
autorização próprios. Alertas de orçamento não são um limite financeiro rígido.

### Resultado e continuação

Não é necessário ampliar a autorização para a etapa 1. O próximo trabalho seguro
é a decisão técnica da raiz/transporte, não compra nem mudança de trust. Nova
autorização só será solicitada para uma operação externa concreta, com recursos,
impacto e custo apresentados. Automatismo confirmado ACTIVE nesta rodada; não
confundir agendamento com execução contínua garantida. Percentual restante para
Live: indeterminado. Não inferir porcentagem por quantidade de testes ou documentos.

Alteração apenas desta proposta e do registro de continuidade. Nenhum teste novo
foi executado por esta atualização documental; nenhuma chamada operacional,
secret, Registry real, commit, push, deploy ou configuração de trading foi tocado.
Foram consultadas somente fontes públicas externas para documentação e preços.

---

Data da análise: 10/09/2026, America/Sao_Paulo (11/09 em UTC).
Status: proposta somente; nenhuma contratação, implantação ou ativação.

Atualização do usuário: "Que eu saiba não" sobre conta AWS própria. Conta ainda
não confirmada; não confundir com a região AWS do serviço Upstash. Orientação
inicial somente: abrir cadastro e parar na escolha de plano, sem compra, recurso
ou envio de dados sensíveis ao agente. Cadastro completo requer meio de pagamento
e pode exigir validação de identidade. Para o controle de permissões previsto,
usar o fluxo avançado como referência; não aderir automaticamente à experiência
nova com permissões preconfiguradas. Nenhum plano pago escolhido.
Fontes públicas oficiais consultadas em 11/09/2026:
[Cadastro AWS](https://docs.aws.amazon.com/accounts/latest/reference/getting-started.html)
e [comparação de cadastros](https://docs.aws.amazon.com/accounts/latest/reference/sign-up-for-aws.html).

Atualização de orçamento do usuário em 11/09: US$ 30 adicionais NÃO são teto
rígido. O usuário informou US$ 100 de Render/Redis neste mês e US$ 100 de
ChatGPT: US$ 200 no mês informado. Não é fatura auditada nem mensalidade fixa
verificada. Flexibilidade para planejar não autoriza gasto ilimitado ou compra.
As antigas pendências de confirmação do teto abaixo estão superadas.

## Mapa mínimo de integração — revisão offline de 11/09

Estado final da unidade offline: a composição conjunta autorização pública →
manutenção → recuperação também passou, com 21 testes seletivos (10 novos).
Ver seção "Atualização — cadeia conjunta concluída" em
`C3_MAINTENANCE_SHARED_COORDINATOR_RESULT_20260911.md`. As próximas ações da
unidade 1 e da composição conjunta abaixo são históricas, não pendências.
O avanço operacional depende de destino/custódia definidos e autorização
específica; não é liberado por estes testes. Conta AWS própria ainda não identificada.

Atualização posterior: a unidade 1 abaixo foi implementada no harness existente
e validada, incluindo a autoridade pública em composição separada. Evidência:
`C3_MAINTENANCE_SHARED_COORDINATOR_RESULT_20260911.md` (164 + 7 aprovações em
duas execuções seletivas, sem integração runtime). Não tratar a injeção como
pendência novamente. A composição conjunta e as lacunas operacionais permanecem.

Mapa concluído por leitura dos componentes existentes, sem importar a aplicação,
executar manutenção ou mudar código. O caminho B continua sendo referência de
planejamento, não contratação autorizada. Comprar recursos não conecta estes gates.

| Ponto existente | Mudança necessária antes de integração | Evidência e teste de aceitação exigidos |
| --- | --- | --- |
| `trade_registry_c3_maintenance_activation_offline_v1.py`, `OfflineMaintenanceActivationV1.run_offline` | Permitir composição explícita com o mesmo coordenador de manutenção usado pela recuperação; hoje o harness constrói outro coordenador internamente | Rejeitar instância, backend, lease store ou raiz divergentes antes de consumir autorização; default-off sem I/O; permissão válida somente durante o lease; manter todos os indicadores de produção falsos |
| `main.py`, `_bind_c3_startup_maintenance_v1` | A futura montagem pública precisa de validação explícita equivalente à legada, não apenas aceitar um callable ou adicionar um tipo à condição | Assinatura, finalidade, namespace, expiração, revogação e consumo único; manter `C3_MAINTENANCE_BOUND_RUNTIME_START_FORBIDDEN`; não alterar este binder nesta etapa |
| `trade_registry_c3_public_authority_offline_v2.py`, `PublicPostgresConsumerOfflineV2` | Separar cliente da Central e serviço proprietário do consumo/assinatura quando houver implementação operacional; o experimento injeta tudo no mesmo processo | Central sem chave privada nem acesso direto de escrita ao banco da autoridade; rejeitar resposta perdida/atrasada, repetição, restauração e revogação; reserva consumida não é compensada por falha posterior |
| `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2.py`, `InjectedRootAuthorityVerifierV2` | Definir a autenticação da raiz durável de recuperação separadamente da autorização pública de manutenção | O verificador atual exige HMAC e assinatura de 64 caracteres hexadecimais; a variante pública usa Ed25519 com 128 e não possui finalidade `root_authority`. Não converter formatos, reutilizar assinatura entre finalidades ou declarar compatibilidade automática com KMS |
| Mesmo arquivo, `CoordinatedMultistoreStartupRecoveryV2` | Preservar a instância exata do coordenador, backend e plano de locks ao compor recuperação | Lease expirado, liberado, de outro contexto ou coordenador deve falhar; nenhum segundo store é tocado antes da validação conjunta; locks mantidos até concluir e liberados na saída |
| Boundary autenticado, seam runtime e cinco fontes `_c3_production_*_dormant_v1` de `main.py` | Fornecer evidências operacionais reais e recuperação autoritativa somente em etapa especificamente autorizada | Resultado sintético não pode virar readiness trocando `synthetic_only`, `production_ready` ou `runtime_integrated`; exigir recuperação de pendências, vínculo de raiz/storage, projeção durável e handoff protegido antes de liberar writers |

Há três provas distintas: autorização de manutenção, autoridade durável dos dados
recuperados e readiness final do startup. Uma assinatura válida da primeira não
substitui as outras duas. A fonte local de revogação da raiz também não equivale
à política pública assinada com prova de atualidade externa.

Ordem mínima proposta, reaproveitando módulos e testes já existentes:

1. Qualificar no harness existente a injeção do mesmo coordenador, exclusivamente
   offline e com dados sintéticos. Inspecionar seus validadores e testes antes de
   editar; preservar o caminho default-off e rejeitar divergências antes do consumo.
2. Delimitar os papéis e mensagens da autoridade pública versus raiz de recuperação,
   incluindo rotação, restauração, revogação e relógios/deadlines. Não duplicar o
   protocolo existente nem presumir que as quatro chaves orçadas cobrem toda a raiz.
3. Somente com contrato operacional e autoridade específicos, implementar e
   homologar os providers no destino; depois publicação controlada, preflight atual
   e decisão de rearmamento. Esses passos não estão autorizados por uma resposta
   sobre orçamento nem podem ser substituídos por testes offline.

Próxima unidade segura: a primeira acima. Nenhum novo wrapper, módulo ou harness
foi criado para este mapa. Os 267 testes são evidência histórica, não nova execução
nem porcentagem de readiness Live. Percentual restante continua indeterminado.

Alteração documental somente; nenhum secret, dado real, chamada externa, commit,
push, deploy ou configuração de trading foi acessado/modificado nesta revisão.

Atualização de 11/09/2026 após os 267 testes: a revisão do caminho mínimo foi
concluída na seção 5.3. As menções históricas a automação pausada e a revisões
pendentes abaixo não descrevem o estado atual. Nenhuma cotação foi renovada.

Inventário posterior autorizado registrado em
`C3_INFRASTRUCTURE_METADATA_INVENTORY_20260911.md`: Render confirmado e Redis
robo-sinais-bingx localizado na conta correta Upstash, Pay as You Go, AWS
US-WEST-2. Login errado anterior não comprova ausência de recurso. A qualificação
documental inicial confirma persistência, mas não comprova consumo global único
ou autoridade C3. Preservar o serviço; não tratar AWS da Upstash como conta AWS
própria. A comparação de alternativas pode continuar com documentação pública,
sem novo login, contratação ou mudança de produção.

## Resumo para decisão

A Central não precisa ser migrada para preparar esta autoridade. A proposta
é separar a autorização de manutenção e seu histórico do ambiente que poderá
ser restaurado. Isso não é um novo robô nem um serviço que decide ou envia trades.

Minha recomendação técnica é primeiro reaproveitar recursos já contratados SE
eles satisfizerem os requisitos abaixo. Se não existirem, a alternativa mais
aderente ao experimento atual é um serviço de manutenção e PostgreSQL no Render,
com a referência de consumo/revogação e as chaves em um domínio administrativo
AWS separado. Essa é uma recomendação de arquitetura, não uma decisão de compra.
Uma alternativa concentrada na AWS pode reduzir componentes sempre ligados,
mas exige substituir o consumidor PostgreSQL e repetir sua validação.

Há agora uma estimativa parcial com hipóteses explícitas nas seções 5.1–5.2, mas não
uma cotação mensal total garantida. Não há evidência para prometer custo zero
ou prazo de Live. Também não há evidência de que todo o retorno a Live se resuma a
esta autoridade: os gates operacionais reais não foram reavaliados.
Atualização decisiva: usuário confirmou workspace Hobby nesta conversa.
OIDC gerenciado Render→AWS exige workspace Pro ou superior.
Adotando essa opção e migrando de Hobby para Pro, a base adicional B passa de
US$ 18,50 para US$ 43,50/mês, antes de consumo e demais extras. Nesse cenário,
o envelope de US$ 30 é insuficiente. Standard do servidor não comprova Pro.

## 1. Inventário comprovado e desconhecidos

| Evidência local consultada | O que comprova | O que NÃO comprova |
| --- | --- | --- |
| `requirements.txt`, linhas 1–7 | Dependências Flask, gunicorn, requests, pandas, numpy, ccxt e upstash-redis | Serviço Upstash contratado, plano, capacidade, retenção ou segurança de uma conta |
| `trade_registry.py`, linhas 23–37; `main.py`, linhas 84–97 | Caminho configurável para dados, preferência por `/data` quando presente, fallback local e Registry em JSON | Volume persistente atualmente montado, conteúdo do Registry, backups ou flags reais |
| `trade_registry_c3_maintenance_authorization_v1.py`, classes de ledger e autorização | Implementação local SQLite e protocolo legado | Autoridade independente em produção |
| `trade_registry_c3_postgres_consumption_offline_v1.py`, linhas 1–40 | Consumidor PostgreSQL explicitamente sintético e default-off | Banco PostgreSQL operacional contratado ou conectado |
| `trade_registry_c3_public_authority_offline_v2.py`, cabeçalho e componentes públicos | Experimento por chave pública com portas injetadas e referência externa simulada | KMS real, serviço externo ou política de recuperação operacional |
| `C3_PUBLIC_AUTHORITY_OFFLINE_VALIDATION_20260910.md` | Registro da rodada anterior de 251 testes e limites do experimento | Nova execução de testes nesta análise ou readiness de produção |

A listagem dos arquivos não ignorados desta worktree não encontrou manifesto
Render, Dockerfile, Procfile ou arquivos YAML de implantação. Isso limita a
evidência local; não prova ausência de configuração no painel ou em outro lugar.
O histórico fornecido pelo usuário situa a Central no Render, mas nenhum painel,
API, shell remoto, conta, banco ou dado operacional foi acessado nesta revisão.

Desconhecidos na revisão inicial, antes das capturas abaixo: região e plano atuais; disco/backups; PostgreSQL já contratado;
existência de conta AWS; responsáveis administrativos; retenção desejada;
identidade de serviço disponível para autenticação Render→AWS; latência aceitável;
volume mensal de operações de manutenção. Não confundir esse volume com número
de trades nem com o intervalo da automação do Codex.

### Atualização com capturas fornecidas pelo usuário

O inventário básico do workspace mostrado foi complementado sem acessar a
conta: foram examinadas apenas as imagens enviadas nesta conversa. Elas mostram:

- Um Web Service `central-robos-bingx`, Python 3, plano de compute Standard,
  região Oregon. Standard identifica o serviço, não o plano de workspace.
- Dashboard com `Active (1)`, `Suspended (0)` e `All (1)`, sem projetos criados,
  listando somente a Central. Não há PostgreSQL ou serviço separado nessa lista;
  isso não exclui recursos em outros workspaces ou provedores.
- Disco com tamanho de 2 GB e caminho de montagem `/data`. O gráfico anterior
  sugere aproximadamente 1,6 GB utilizados (cerca de 80%); essa é uma estimativa
  visual, não uma medição exata nem prova de esgotamento iminente.
- A página informa snapshots a cada 24 horas disponíveis por sete dias e
  exibe um snapshot de 10/09/2026 às 20:57, conforme horário apresentado pelo
  painel. Não foi validado o fuso dessa exibição nem testada a restauração.
- O usuário respondeu que não sabe se possui conta AWS. Registrar como
  desconhecido, não como ausência de conta ou permissão para criar uma.

As imagens de origem são `codex-clipboard-ce956aa1-d0a3-440e-bcad-b70f3a73c35b.png`,
`codex-clipboard-d6725bdb-b802-4510-8d54-f9ba7cbccbf9.png`,
`codex-clipboard-f06d2c99-df65-497e-ae86-aeb425734f05.png` e
`codex-clipboard-05976db7-c497-49f9-b6e2-b39c3325203d.png`, anexadas pelo usuário.
Não foram copiadas para o repositório nem consultados arquivos operacionais.

Conclusão atualizada: já há disco persistente configurado para a Central, mas
não foi identificada uma autoridade independente reutilizável nesse workspace.
O mount `/data` é compatível com uma das opções previstas no código; sem ler a
configuração efetiva não comprova que todos os dados estejam gravados ali.
Snapshots disponíveis não comprovam integridade do Registry, restauração segura
de banco ou proteção anti-rollback. O selo Live do deploy não atesta trading.

Não são necessárias mais capturas para este inventário básico. Não orientar
Restore, Edit, aumento de disco ou criação de conta a partir dessas imagens.
A próxima etapa de planejamento é fechar uma estimativa atual para os recursos
adicionais das alternativas B/C, com região de destino e hipótese explícita de
uso de manutenção, sem assumir crédito AWS ou reaproveitamento não comprovado.
Contratação e escolha final permanecem pendentes; esta atualização não reativa
a automação nem autoriza operação em produção.

## 2. Onde ficaria cada parte na alternativa de referência

| Componente proposto | Local proposto | Responsabilidade e restrições |
| --- | --- | --- |
| Central e seu Registry | Hospedagem atual no Render, sem migração nesta proposta | Continuam sendo a verdade operacional/estatística dos trades; não recebem chaves privadas de autorização |
| API de consumo de manutenção | Serviço separado no Render, privado quando a topologia permitir | Valida pedidos, coordena reserva externa e commit; sem credenciais BingX e sem permissão de enviar ordens |
| Ledger de consumo | PostgreSQL gerenciado separado do disco do aplicativo | Registro único e durável de consumo; usuário de aplicação sem poderes de restauração ou exclusão |
| Referência de atualidade e reservas | DynamoDB + função de serviço na AWS, sob administração separada do deploy da Central | Mantém claims já reservados e geração de política; nunca é restaurado junto com o aplicativo |
| Quatro identidades de assinatura | Chaves assimétricas AWS KMS e papéis distintos | Requisição, política, referência e recibo; o papel da Central não pode assinar sua própria autorização |

Render oferece serviços privados sem exposição pública direta e armazenamento
PostgreSQL gerenciado. A topologia privada/região precisa ser confirmada antes
de escolher conexões. [Serviços privados Render](https://render.com/docs/private-services).

Disco persistente preserva arquivos entre deploys, mas seu snapshot restaura
estado anterior; não resolve a atualidade do histórico de autorizações. Apenas
os caminhos montados persistem. Não instalar PostgreSQL próprio no disco do app
para simular independência. [Discos Render](https://render.com/docs/disks).

Não são necessários Kubernetes, cluster multirregião ou um computador pessoal
ligado como autoridade de produção nesta proposta mínima. AWS aqui é uma opção
concreta de provedor, não um recurso que já foi encontrado na conta do usuário.

## 3. Alternativas comparadas

| Alternativa | Novos recursos | Benefício | Limite/decisão |
| --- | --- | --- | --- |
| A. Reaproveitar infraestrutura já contratada e qualificada | Possivelmente nenhum; ainda não comprovado | Menor custo incremental e menos contas | Precisa já haver armazenamento independente, custódia de chaves e separação administrativa; a dependência Upstash não prova isso |
| B. Render + autoridade externa AWS | API separada, PostgreSQL se inexistente, serviço de referência com DynamoDB/Lambda e KMS | Preserva o caminho PostgreSQL exercitado; separa backup do app da referência | Mais componentes e autenticação entre provedores; escolha de região e recuperação ainda precisam ser ensaiadas |
| C. Autoridade concentrada na AWS | Serviço de autorização, DynamoDB e KMS; Central permanece no Render | Pode dispensar API sempre ligada e PostgreSQL adicional | Muda a implementação de consumo; não é troca transparente nem está validada pelos 251 testes |
| D. Somente app/disco atual ou cache como autoridade | Nenhum | Sem contratação adicional | Não atende ao requisito demonstrado de restauração e independência; não recomendar para liberar manutenção real |

Recomendação: A somente após comprovação; na ausência dela, B como referência
de menor divergência do código testado. C é candidata se custo/operabilidade
justificarem a mudança; não implementá-la por conveniência sem decisão explícita.
O cenário R$ 0 continua possível para análise/laboratório, mas não foi comprovado
para uma nova autoridade operacional completa.

## 4. Contrato operacional que a infraestrutura precisa cumprir

Esta seção é desenho proposto, não um novo módulo nem política já implantada.

### Identidade, custódia e acesso

- A raiz confiável deve ser matriculada por um responsável autenticado, com
  registro auditável de identidade, chave pública, época, algoritmo e destino.
  Um hash entregue pelo chamador ou um alias que possa mudar silenciosamente
  não autentica essa origem. Fixar identidade concreta e conferir fingerprint.
- Separar administradores e permissões de requisição, revogação, reserva e recibo.
  O deploy da Central não deve poder alterar a política, apagar claims, restaurar
  a referência, trocar pins ou acessar a chave de emissão de autorizações.
- A API externa precisa autenticar o serviço chamador E verificar o pedido
  autorizado antes de reservar. Não expor uma porta que assine qualquer digest
  ou permita consumir arbitrariamente claims de terceiros.
- KMS mantém a chave privada assimétrica protegida; a verificação pode usar a
  chave pública fora do serviço. Isso não substitui as regras da aplicação.
  [Chaves assimétricas KMS](https://docs.aws.amazon.com/kms/latest/developerguide/symmetric-asymmetric.html).
- A documentação atual lista Ed25519; distinguir assinatura sobre mensagem
  RAW de variante prehashed. A interoperabilidade exata com o envelope V2 e
  a representação de chave pública do laboratório exige teste específico.
  [Especificações KMS](https://docs.aws.amazon.com/kms/latest/developerguide/symm-asymm-choose-key-spec.html).
- Uma API Lambda pode exigir AWS_IAM. OIDC gerenciado do Render foi identificado
  como opção de identidade de curta duração, condicionado ao plano (seção 5.2)
  e à validação das permissões. Não resolver isso distribuindo
  credenciais permanentes da conta ou chaves privadas pelo repositório.
  [Autenticação Lambda](https://docs.aws.amazon.com/lambda/latest/dg/urls-auth.html).

### Reserva, revogação e concorrência

Uma transação da referência deve verificar a geração/hash da política e criar
o claim somente se ausente. O registro usado para impedir replay não pode expirar
por TTL enquanto sua autorização puder reaparecer após restauração. Expiração
do pedido não apaga seu histórico. O token de idempotência da API do provedor
não substitui esse registro permanente: no DynamoDB sua janela é de dez minutos.
Usar leitura forte/transactional para a política, sem consultar réplica atrasada
ou índice eventualmente consistente. [Transações DynamoDB](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html).

Somente após reserva e commit confirmados pode existir recibo elegível. A mesma
autorização não volta a ficar livre se a resposta se perder. Um recibo de consumo
não comprova que a manutenção terminou e não pode ser transformado em readiness.
Cada chamada possui deadline real de transporte, limite de tamanho e validação
de contexto; os callbacks cooperativos do laboratório não são suficientes para
interromper I/O de produção bloqueado.

### Rotação e revogações

Criar nova chave/época por processo autenticado, distribuir o novo pin, validar
posse e compatibilidade e atualizar a política com geração crescente. Preservar
chaves públicas históricas para auditoria, sem aceitar autorizações novas sob
chave revogada. A recuperação não pode diminuir geração nem apagar claims.
KMS não oferece rotação automática de chaves assimétricas; exige fluxo manual
ou controlado de substituição. [Rotação KMS](https://docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html).

### Recuperação e disponibilidade

- Reserva sem commit confirmado: manter consumida/pendente; consultar evidência
  durável e reconciliar, sem emitir nova permissão de execução automaticamente.
- Commit confirmado sem recibo: tratar como consumo realizado; reconstruir
  evidência para auditoria, não reapresentar uma autorização de execução.
- Manutenção parcialmente executada: consultar WAL e estado autoritativo das
  obrigações; não considerar um atestado isolado como resolução durável.
- Referência, política ou signer indisponível: recusar novas admissões de
  manutenção. Isso não deve cancelar stops nem interromper a proteção de
  posições existentes. Esta proposta não coloca a autoridade no caminho de
  cada ordem ou decisão de estratégia.
- Restaurar app/SQLite/PostgreSQL: bloquear admissão, confrontar com referência
  externa atual e reconciliar antes de reabrir. Backup não é fonte de atualidade.
- Restaurar a própria referência: nova instância em quarentena, sem trocar
  automaticamente o destino/pin de confiança. DynamoDB restaura em nova tabela;
  isso NÃO autentica sua atualidade. Identificar também a instância, não somente
  nome/alias, e obter evidência completa independente. Se faltar histórico,
  permanecer bloqueado e exigir decisão de recuperação autenticada.
  [Restauração DynamoDB](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/pointintimerecovery_restores.html).

O objetivo mínimo é nenhum consumo confirmado voltar a ser utilizável após
recuperação. Não é promessa de disponibilidade contínua ou proteção contra
comprometimento simultâneo de todos os administradores. Duas contas controladas
pelo mesmo segredo e mesmo procedimento de restore não resolvem essa ameaça.
Auditoria de mudanças administrativas e recuperação deve ficar fora dos backups
da aplicação; seu formato/retenção e a resistência a alteração precisam de
validação própria antes de serem usados como prova.

## 5. Custos: o que é conhecido e o que falta

Valores em USD, sem conversão para reais, impostos, créditos promocionais ou
suposição de elegibilidade ao free tier. Consulta pública em 10/09/2026 BRT.

| Item | Evidência de custo | Como usar a informação |
| --- | --- | --- |
| Reaproveitamento de recursos existentes | Incremento ainda indeterminado | Não presumir recursos livres ou que uma dependência instalada é serviço pago |
| Quatro chaves gerenciadas KMS | US$ 1 por chave/mês: US$ 4/mês apenas de armazenamento das quatro chaves | Não é o preço da solução; chamadas assimétricas não entram na franquia gratuita de requisições; rotação com chaves adicionais pode aumentar a conta |
| API + PostgreSQL Render | Artigo oficial informa referência de aproximadamente US$ 13/mês para Starter web + Basic-256mb em julho/2026 | É exemplo histórico, não cotação atual nem dimensionamento desta API privada; a tabela atual dinâmica não ficou disponível na leitura pública usada |
| DynamoDB, função Lambda, chamadas KMS | Cobrança depende de região, operação, volume e duração | Levantar número de head/reserva/assinatura por manutenção; não contar somente pedidos finais |
| Backup, auditoria, armazenamento, egress, workspace, identidade e recuperação | Adicionais ainda não determinados | Incluir no orçamento e nos limites de uso antes de provisionar |

Fontes: [KMS pricing](https://aws.amazon.com/kms/pricing/),
[exemplo histórico Render](https://render.com/articles/how-much-does-cloud-application-hosting-cost-for-small-businesses),
[preços atuais Render](https://render.com/pricing),
[DynamoDB pricing](https://aws.amazon.com/dynamodb/pricing/),
[Lambda pricing](https://aws.amazon.com/lambda/pricing/).

Não apresentar US$ 4 ou a soma com o exemplo histórico como orçamento fechado.
Fórmula de B: serviço Render + PostgreSQL não reutilizado + armazenamento de
chaves + chamadas/execução + backup/auditoria/egress + eventuais custos de plano.
Região de destino dos novos serviços e volume são desconhecidos; Oregon foi
confirmado apenas para a Central pelas capturas. Não há faixa total defensável nesta revisão.
Para C, retirar os componentes Render adicionais e recalcular execução/estado
na AWS, além do custo de engenharia e revalidação. Definir alarmes de orçamento
antes da contratação, sem prometer que um alarme sozinho seja um teto de gastos.

PostgreSQL pago no Render possui recuperação point-in-time, com janela dependente
do plano; a opção Free não oferece essa recuperação. A capacidade de restaurar
continua separada da prova de atualidade. Não escolher plano gratuito como atalho
para um histórico autoritativo. [Backup Render](https://render.com/docs/postgresql-backups).

### 5.1. Atualização da estimativa após o inventário

Esta atualização substitui a impossibilidade anterior de quantificar qualquer
subtotal. Não substitui as ressalvas sobre custo total ou a aprovação de compra.
Consulta pública em 10/09/2026 BRT; nenhum acesso a contas de provedores.

**Custos incrementais, além da Central existente.** Não somar novamente seu
Web Service Standard e disco de 2 GB. Hipótese de implantação: novo serviço
Render na região Oregon; a região AWS é proposta como Oregon/us-west-2, ainda
sujeita a validação de identidade, disponibilidade, latência e cotação regional.
Os exemplos tarifários AWS abaixo são referências públicas de cálculo dos EUA,
não confirmação de todos os SKUs de Oregon. Nenhum crédito/free tier foi abatido.

#### Base publicada por componente

| Componente adicional | Hipótese de tamanho | USD/mês |
| --- | --- | ---: |
| Serviço Render separado | `0.5c-512mb`, antigo Starter | 7,00 |
| PostgreSQL Render | `0.1c-256mb`, antigo Basic-256mb | 6,00 |
| Armazenamento desse PostgreSQL | 5 GB escolhidos para planejamento × US$ 0,30/GB | 1,50 |
| Quatro chaves KMS | Quatro chaves × US$ 1/mês, sem réplicas ou chaves antigas adicionais | 4,00 |
| **Subtotal B: Render + AWS** | **Somente itens acima** | **18,50** |
| **Subtotal C: autoridade na AWS** | **Somente as quatro chaves; sem novos serviços Render** | **4,00** |

Os valores Render foram recuperados no conteúdo indexado da própria página
oficial de preços nesta consulta (US$ 7, US$ 6 e US$ 0,30/GB). A leitura direta
da página continua omitindo a tabela dinâmica; a tentativa HTTP pública local
falhou na negociação de conexão. Não foram desabilitadas validações TLS nem
acessado o painel. Conferir os itens no orçamento do provedor antes da compra.
[Preços Render](https://render.com/pricing).

Os 5 GB são escolha de cálculo, não mínimo obrigatório nem aumento do disco
atual. A documentação descreve armazenamento inicial e aumentos em blocos;
dimensionamento real ainda depende da validação. [Armazenamento PostgreSQL](https://render.com/docs/postgresql-creating-connecting).
KMS cobra armazenamento de chaves e requisições separadamente; operações
assimétricas não se beneficiam da franquia geral de requisições gratuitas.
[Preços KMS](https://aws.amazon.com/kms/pricing/).

#### Hipóteses explícitas para o consumo variável

Usar 100, 1.000 e 10.000 autorizações de manutenção/mês como cenários, NÃO
previsão de demanda real. Não são trades e não são retomadas do Codex. Para
comparação de ordem de grandeza, em cada autorização adotar:

- Dez chamadas Lambda, cada uma com 512 MB e duração média faturável de 250 ms.
  É hipótese, não benchmark; cold start, espera de rede e retries podem aumentar.
- Oito unidades faturáveis de escrita e vinte de leitura DynamoDB. Já são
  unidades de cobrança, não chamadas: transações, consistência e arredondamento
  por tamanho precisam ser contabilizados na implementação real.
- Até dez assinaturas KMS; verificações locais com chave pública não são novas
  chamadas KMS. Emissão, atualização de política, tentativas rejeitadas e rotação
  podem adicionar chamadas fora deste cenário.
- 1 GB médio de armazenamento DynamoDB e PITR, independentemente do número de
  pedidos da tabela abaixo. É uma provisão de cálculo para histórico acumulado,
  não autorização para apagar claims ou limitar sua retenção por conveniência.

Referências aritméticas: Lambda US$ 0,20/milhão de chamadas e
US$ 0,0000166667/GB-segundo; DynamoDB Standard US$ 0,625/milhão de unidades de
escrita, US$ 0,125/milhão de leitura, US$ 0,25/GB-mês de armazenamento e
US$ 0,20/GB-mês de PITR. Foram usados exemplos públicos, sem descontar franquias;
a aplicação ao SKU/região finais deve ser confirmada.
[Lambda](https://aws.amazon.com/lambda/pricing/),
[DynamoDB](https://aws.amazon.com/dynamodb/pricing/).

Fórmulas verificadas por cálculo local, sem executar a aplicação:

- Lambda = N × 10 × (0,20/1.000.000 + 0,5 × 0,25 × 0,0000166667).
- DynamoDB requisições = N × (8 × 0,625 + 20 × 0,125)/1.000.000.
- Armazenamento + PITR DynamoDB de 1 GB = 0,25 + 0,20 = US$ 0,45/mês.

| Autorizações/mês | Lambda | Requisições DynamoDB | B: parcial com armazenamento/PITR | C: parcial com armazenamento/PITR |
| ---: | ---: | ---: | ---: | ---: |
| 100 | 0,00228 | 0,00075 | 18,95 + S + E | 4,45 + S + E |
| 1.000 | 0,02283 | 0,00750 | 18,98 + S + E | 4,48 + S + E |
| 10.000 | 0,22833 | 0,07500 | 19,25 + S + E | 4,75 + S + E |

**S = assinaturas KMS ainda a cotar para Ed25519/Oregon.** A página fornece
exemplo ECC-256 de US$ 0,15 por 10.000 assinaturas, mas isso não foi tratado
como tarifa Ed25519 comprovada. Se a cotação desse algoritmo coincidir com o
exemplo, S seria US$ 0,015 / 0,15 / 1,50 nos três cenários; se não, recalcular.
**E = extras ainda não quantificados:** autenticação entre provedores, auditoria
durável e protegida, logs/alertas, retenção adicional, exportação/restauração,
egress, eventuais planos de workspace, impostos e outros recursos obrigatórios.
Não definir E como zero para apresentar um preço artificialmente fechado.

#### Sensibilidade e decisão recomendada

Como envelope PROVISÓRIO de planejamento, avaliar **US$ 30/mês adicionais para
B**, não como previsão garantida nem teto imposto pelo provedor. No cenário de
1.000 autorizações, sob S hipotético de US$ 0,15, isso deixaria aproximadamente
US$ 10,87 para E e diferenças tarifárias. A suficiência dessa folga NÃO foi
comprovada. Não contratar se a cotação completa ultrapassar o limite aprovado.

C economiza US$ 14,50/mês nos itens Render modelados, mas exige outra
implementação de consumo e recuperação. Seu parcial não significa que toda
a autoridade custará US$ 4,48. Não escolher C apenas pelo subtotal nem somar os
251 testes anteriores como validação de uma arquitetura ainda não construída.

O dimensionamento mínimo B não está comprovado. Pelos mesmos preços Render,
subir o banco de US$ 6 para a classe de US$ 19 acrescentaria US$ 13/mês; subir
a API de US$ 7 para US$ 25 acrescentaria US$ 18/mês. Qualquer dessas mudanças
pode invalidar o envelope de US$ 30. Não ativar crescimento automático sem
entender sua cobrança, e não prometer que alertas limitem despesas.

Recomendação técnica B condicionada à cotação dos itens S/E, sem reduzir
segurança para caber no orçamento. A descoberta da seção 5.2 impede tratar
US$ 30 como suficiente antes de conhecer o plano de workspace. Não há
necessidade de criar conta AWS nesta etapa. A automação continua pausada.

Nesta atualização, somente este relatório foi editado. Nenhum teste da Central,
acesso a secrets, chamada operacional, commit, push, deploy ou mudança de flags.
Houve somente leitura local, pesquisa pública de preços e cálculos aritméticos.

### 5.2. Revisão do custo de identidade e do envelope de US$ 30

O usuário indicou que US$ 30 caberia, mas perguntou se substituiria Render e
Redis. Foi esclarecido que a proposta é adicional; nenhum serviço existente
será cancelado ou substituído. A conversa não constitui contratação nem
aprovação de aumento acima desse envelope. Redis não foi auditado para remoção.

Foi encontrada uma opção gerenciada de autenticação: Render emite tokens
OIDC temporários para assumir um papel AWS, disponível em workspace Pro ou
superior. O vínculo deve restringir o serviço exato, além de audience e emissor;
não confiar em todos os serviços do workspace. A identidade de transporte não
substitui a autorização assinada nem permite à Central emitir seu próprio grant.
Nada foi configurado. [OIDC Render](https://render.com/docs/oidc).

O plano de workspace Pro publicado custa US$ 25/mês, além de compute. As
capturas comprovam compute Standard, mas não o plano do workspace. A existência
de botão Upgrade não basta para inferi-lo. [Preços Render](https://render.com/pricing).

| Situação do workspace atual | Incremento de plano para OIDC | Base adicional B antes de consumo/extras |
| --- | ---: | ---: |
| Pro ou superior já contratado e elegível | US$ 0 | US$ 18,50/mês |
| Hobby, com adoção de Pro | US$ 25/mês | US$ 43,50/mês |
| Plano ainda desconhecido | Não determinado | Não fechar cotação |

Na hipótese Hobby→Pro, o cenário anterior de 1.000 autorizações passa para
US$ 43,98 + S + E residual/mês. O custo de plano agora está destacado: não
contá-lo novamente dentro de E. S continua pendente para Ed25519/Oregon;
auditoria, retenção, tráfego e impostos continuam não fechados. A base já
ultrapassa US$ 30 sem depender dessas incertezas. C também não elimina por si
só a autenticação da Central Render→AWS: se usar o mesmo OIDC, deve incorporar
o mesmo eventual upgrade, apesar de retirar a API e o PostgreSQL adicionais.

IAM Roles Anywhere é outra possibilidade documental, não uma solução gratuita
pronta: exige certificados X.509 e uma autoridade certificadora, cuja custódia,
renovação e recuperação não estão definidas neste projeto. Não substituir OIDC
por credencial permanente nem inventar uma PKI apenas para ocultar o custo.
[Requisitos Roles Anywhere](https://docs.aws.amazon.com/rolesanywhere/latest/userguide/introduction.html).

O usuário confirmou **Hobby** por mensagem, sem acesso à conta. Não solicitar
novamente o plano nem uma captura para repetir a mesma informação. A opção B
com OIDC gerenciado fica fora do envelope de US$ 30; não recomendar upgrade ou
contratação com esse orçamento. Manter US$ 30 como limite de planejamento,
sem interpretar a confirmação do plano como aprovação de gasto maior.

Próxima revisão recomendada: verificar primeiro se a autoridade de manutenção
proposta é realmente pré-condição do caminho mínimo de recuperação, ou apenas
de uma automação futura; depois avaliar simplificação sem enfraquecer interlocks,
autenticação e proteção contra replay. Não presumir que manutenção manual
dispense esses controles. Essa revisão ainda não foi executada e não autoriza
produção, migração nem implementação de nova arquitetura. Render e Redis atuais
permanecem fora do escopo de remoção. A proposta não é infraestrutura obrigatória
comprovada para todo retorno Live; o percentual restante continua indeterminado.

Validação desta revisão: aritmética conferida (18,50 + 25 = 43,50; cenário
1.000 = 43,980333375 antes de S/E residual). Somente este Markdown foi alterado;
sem testes da aplicação, secrets, acesso operacional, commit, push, deploy,
contratação ou alteração de trading. Consultas externas limitadas a documentos
públicos. A automação não foi reativada.

### 5.3. Caminho mínimo revisado após a montagem dormente — 11/09/2026

Esta revisão usa somente fontes locais e relatórios existentes. Não executa
testes novamente: os 267 testes da integração dormente já foram concluídos,
e não houve mudança de código desde aquela rodada. Não atualiza preços, consulta
contas ou escolhe provedor. O plano Hobby e o envelope de US$ 30 adicionais
permanecem informações históricas do usuário, não autorização de compra.

**Conclusão: a topologia B não é requisito comprovado para voltar a Live.**
Ela foi uma proposta para hospedar uma variante de autoridade de manutenção.
O código exige propriedades de segurança, não aqueles produtos específicos.
Também não se demonstrou um caminho manual pronto que dispense essas propriedades.
Comprar serviços não fecha, por si só, as lacunas de composição operacional.

| Necessidade | Evidência atual no código | Consequência para o plano |
| --- | --- | --- |
| Coordenação e recuperação antes de readiness | `install_controlled_c3_closed_repair_writer_coordinator_v1` exige autoridade/interlock instalados por identidade, coordenador habilitado não maintenance-only e vetor completo; o preflight exige os mesmos gates | Continua obrigatória no caminho atual; não retirar a checagem para evitar infraestrutura |
| Mesmo coordenador na cadeia | A montagem de main agora vincula multistore e interlocks à mesma instância, desativada | Etapa concluída offline; não refazer nem tratá-la como autorização operacional |
| Persistência de locks, leases, WAL e estado resolvido | Builders exigem dependências físicas explícitas; startup permanece sem elas e não atesta recovery | Identificar armazenamento e garantias efetivos; existência do disco `/data` não atesta toda a cadeia |
| Autorização da manutenção automatizada | `AuthenticatedMaintenanceAuthorizationV1` exige consumidor monotônico assinado independente antes do ledger local; `OfflineMaintenanceActivationV1` só aceita etapas sintéticas | Consumo independente é necessário para a garantia contra restauração local desse protocolo, mas ele NÃO é um instalador de produção pronto |
| Variante de quatro identidades + PostgreSQL | `C3_PUBLIC_AUTHORITY_OFFLINE_VALIDATION_20260910.md` documenta a variante sintética; main não a importa. O binder legado exige o tipo `AuthenticatedMaintenanceAuthorizationV1` | Não tratar a variante por chave pública como plug-in operacional já compatível; tampouco transformar quatro chaves/KMS/PostgreSQL em compra obrigatória |
| Recuperação contra rollback | A referência SQLite documenta que restaurar ambos os bancos permite replay; a variante pública usa referência externa simulada | Uma alternativa precisa preservar atualidade fora do backup restaurado e ter recuperação definida. Dois arquivos no mesmo disco não resolvem isso |
| Admissão de runtime após manutenção | As cinco fontes de startup continuam DORMANT; o binding de manutenção bloqueia partida e não possui transição automática para Live | Ainda falta uma composição operacional atestada. Um recibo sintético ou compra de autoridade não substitui essa transição |

O último preflight real continua sendo o registro histórico das 07:53, com
dois bloqueios. Esta revisão não confirma o estado atual do servidor, nem
elimina os bloqueios de storage e coordenação. A garantia de bloqueio precisa
abranger todos os processos/writers participantes, não apenas um binder em memória.

**Sequência necessária, sem nova camada genérica:**

1. Inventariar metadados não sensíveis dos recursos existentes e a política de
   recuperação: quais stores/serviços persistem, quais são restaurados juntos,
   quem pode alterá-los, e se existe mecanismo de identidade/custódia reutilizável.
   Não voltar a perguntar plano Hobby ou tamanho do disco já informados.
2. Com essa evidência, selecionar uma topologia que preserve autenticação,
   consumo único e recuperação, e fechar custo incremental completo. A/B/C
   continuam alternativas, não compras aprovadas. Não introduzir uma nova
   arquitetura só para caber no subtotal parcial.
3. Delimitar a implementação operacional dos providers, transição de startup e
   ensaios no armazenamento alvo; separar homologação sintética de produção.
4. Só então propor execução controlada, sob autorização específica e mantendo
   trading desligado. Não converter o próximo inventário em deploy/bootstrap.

O inventário pode começar por descrições não sensíveis fornecidas pelo usuário.
Inspeção de contas/painéis/metadados operacionais exige autorização própria,
pois o automatismo atual proíbe acesso a esses serviços. Mesmo autorizada, essa
inspeção não pode abrir secrets, variáveis de ambiente, credenciais, Registry,
logs brutos ou dados de trades, nem criar/alterar recursos.

Não resta outra alteração offline necessária identificada nesta revisão antes
de obter essa informação. Não criar novo contrato, harness ou pacote apenas
para simular avanço. Não repetir os 267 testes sem mudança relevante. A montagem
dormente e a revisão do caminho mínimo estão concluídas; as decisões de destino
e confiança não podem ser inventadas a partir de fakes ou hashes de laboratório.

Arquivos editados nesta retomada: este documento e
`C3_OFFLINE_CONTINUITY_20260911.md`. Nenhum código/teste/pacote alterado. Nenhum
secret, dado real, chamada externa, processo operacional, commit/push/deploy,
flag ou ordem. Automatismo não alterado ou pausado. Percentual restante para
Live: indeterminado. Modelo/esforço sugerido: GPT-6 Astra — Alto.

## 6. Sequência de implantação — apenas planejada

### Comparação após inventário correto — 11/09/2026

Executada após a pergunta do usuário sobre ausência de status de trabalho.
Esta comparação é documental e local; não é cotação fechada, teste de provedor
ou decisão de compra. Reutiliza A/B/C existentes, sem inventar outra arquitetura.

| Caminho | Evidência técnica e compatibilidade | Custo/decisão atual |
| --- | --- | --- |
| A: Redis Upstash já contratado | Recurso localizado e persistência documentada, porém consistência eventual não comprova consumo global único; não há autoridade assinante/recuperação qualificada | Preservar para seu uso atual; não promover a autoridade C3 nem prometer custo incremental zero |
| B: consumidor PostgreSQL + referência/assinatura AWS | Menor divergência do experimento PostgreSQL, mas variante pública continua offline e não é aceita pelo binder de main; providers e recuperação reais ausentes | Com OIDC gerenciado, exige upgrade Hobby para Pro além dos serviços; orçamento completo de US$ 30 não demonstrado e subtotal histórico de US$ 43,50 já o excedia |
| C: consumo/referência/assinatura AWS | DynamoDB oferece primitivas condicionais/transacionais úteis, mas não existe consumidor dessa topologia validado neste código; muda a implementação e exige ensaio próprio | Dispensa API/PostgreSQL Render adicionais no desenho, não dispensa autenticação; com Pro e quatro chaves, US$ 29 antes dos demais custos, sem garantia de caber em US$ 30 |

Fontes públicas reconferidas: Render exige Pro ou superior para sua identidade
OIDC gerenciada e emite credenciais de curta duração. Não executar as instruções
de configuração da página. [OIDC Render](https://render.com/docs/oidc).
O resultado indexado da página oficial de preços confirma Pro US$ 25/mês mais
compute; a abertura direta não expôs a tabela dinâmica completa de compute.
Não renovar valores exatos de API/PostgreSQL a partir de trechos sem contexto.
[Preços Render](https://render.com/pricing).
KMS cobra US$ 1 por chave/mês e exclui operações assimétricas da franquia geral.
Quatro chaves correspondem à variante pública anterior, não exigência universal
de todo C3. [Preços KMS](https://aws.amazon.com/kms/pricing/).

O subtotal 25 + 4 = US$ 29 deixa apenas US$ 1 do envelope para todos os demais
custos de C. Isso NÃO prova que o total excederá US$ 30 em qualquer cenário,
mas impede afirmar que há orçamento completo garantido. Armazenamento,
requisições, assinatura, logs, recuperação, impostos e operação faltam fechar.
Não sugerir remover identidades, auditoria ou proteção para caber no subtotal.

DynamoDB verifica condições contra a versão mais recente do item; transações
podem agrupar verificações e consumo. A janela de idempotência de dez minutos
não substitui um claim persistente, e restore não atesta atualidade.
[Escritas condicionais](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/WorkingWithItems.html),
[Transações](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html).

Código conferido por leitura, sem imports: o contrato
`AuthenticatedMaintenanceAuthorizationV1` exige consumo independente durável
e assinado; `PublicMaintenanceAuthorizationOfflineV2` exige o consumidor
PostgreSQL concreto e se declara incompatível com o binder dormente de main.
Logo, C não pode ser selecionada como substituição transparente, nem B
considerada pronta após contratação. Não confundir capacidade do provedor
com implementação, privilégios e recuperação atestados.

Recomendação da comparação: manter Render e Redis atuais; não contratar nem
implementar substituição de consumidor neste momento. B segue referência de
menor divergência do experimento, não solução aprovada; C é alternativa que
exigiria decisão de desenho e revalidação. Nenhuma opção completa qualificada
dentro de US$ 30 foi demonstrada. O custo total permanece pendente, não zero.
A falta de uma conta AWS confirmada não bloqueou esta comparação pública.

Pendência delimitada: fechar custo completo e método de identidade de uma
topologia antes de propor provisionamento. Não refazer inventário/login ou
tests offline; uma futura análise de autenticação alternativa deve declarar
suas próprias exigências de custódia/rotação/recuperação, sem instalar soluções
ou usar credenciais permanentes por conveniência. Nenhum código/teste/produção
foi alterado nesta comparação; somente esta proposta e a continuidade.

### Autenticação sem upgrade — comparação concluída em 11/09/2026

Escopo: pesquisa pública e leitura dos contratos locais, sem contas, chaves,
downloads de executáveis, configuração, criação de recursos ou testes remotos.
O fato de evitar Pro não elimina a necessidade de autenticar o chamador.

| Alternativa | O que evita / o que exige | Conclusão para esta Central |
| --- | --- | --- |
| IAM Roles Anywhere com CA externa | Evita OIDC do Render; usa certificado X.509 e prova de posse da chave para obter credenciais AWS temporárias | Viável em princípio, mas CA, emissão, proteção de chave, renovação, revogação e responsável não estão comprovados. Não é substituição pronta ou gratuita no custo total |
| IAM Roles Anywhere com AWS Private CA | Terceiriza parte da operação da CA, não o ciclo completo do cliente | US$ 50/mês só pela CA de certificados curtos, antes de certificados/outros serviços; ultrapassa US$ 30 sem resolver sozinho o restante |
| API Gateway com mTLS | Autentica cliente por certificado, sem OIDC Render; exige domínio regional e cadeia confiável | Acrescenta CA/certificados, domínio, truststore, revogação e transporte; não dispensa autorização C3 nem comprova economia total |
| Autenticação na aplicação com pedido assinado | Pode operar sem AWS_IAM no ponto de entrada, se todo o protocolo de autenticação for implementado | Falta identidade de chamador autenticada, custódia, rotação, anti-replay e proteção contra abuso qualificadas. Não confundir assinatura de manutenção com autenticação do transporte; não criar endpoint público só para evitar Pro |
| Credenciais AWS permanentes na Central / retirar autenticação | Evitaria parte da configuração imediata | Não recomendar ou implementar como atalho neste escopo |

Fontes e limites da conclusão:

- Roles Anywhere admite CA externa ou AWS Private CA e requer trust anchor,
  perfil e políticas de IAM. Restringir emissor/identidade, não aceitar todos
  os certificados de uma CA. [Configuração e confiança](https://docs.aws.amazon.com/rolesanywhere/latest/userguide/getting-started.html).
  O cliente ainda precisa usar certificado e sua chave privada para obter
  credenciais temporárias; estas não eliminam o segredo de autenticação inicial.
  [Cliente](https://docs.aws.amazon.com/rolesanywhere/latest/userguide/credential-helper.html).
- Revogação no Roles Anywhere depende de listas importadas; consulta automática
  a OCSP/CDP não é suportada no modelo documentado. Renovação e atualização das
  listas precisam de processo próprio. A restauração de material antigo não
  pode revalidar identidade revogada.
  [Revogação](https://docs.aws.amazon.com/rolesanywhere/latest/userguide/trust-model.html).
- AWS Private CA custa US$ 50 por CA/mês no modo de certificados curtos ou
  US$ 400 no modo geral, mais itens aplicáveis. Não descontar trial como economia
  permanente. [Preço oficial](https://aws.amazon.com/private-ca/pricing/).
- O mTLS do API Gateway não verifica revogação do certificado automaticamente.
  Validação adicional é necessária; domínio padrão e rotas alternativas também
  não podem contornar o controle. O truststore em S3 não é custódia da chave
  privada do cliente. [mTLS](https://docs.aws.amazon.com/apigateway/latest/developerguide/rest-api-mutual-tls.html).
- Lambda Function URL com NONE e política pública pode ser invocada sem
  autenticação IAM. Autenticação de aplicação pode ser desenhada, mas não está
  pronta neste projeto; TLS por si só autentica o servidor, não o chamador.
  Rejeitar um pedido dentro da função não evita que ela seja invocada e possa
  consumir recursos. [Function URL](https://docs.aws.amazon.com/lambda/latest/dg/urls-auth.html).

Conferência local: `SignatureV2`/`Ed25519VerifierOfflineV2` vinculam propósito,
identidade, época e digest, exclusivamente no escopo sintético. Não são um
serviço de identidade ou emissor operacional. O protocolo legado exige consumo
independente e assinado; o HMAC antigo não é fallback aceito pela variante V2.
Não copiar chaves sintéticas, inventar uma CA, habilitar portas ou escrever um
novo wrapper para apresentar essa autenticação como concluída.

**Recomendação:** não implantar uma PKI própria apenas para poupar o upgrade.
Para o objetivo de pouca intervenção humana, manter OIDC gerenciado como
referência de planejamento, sujeito a custo total e decisão do usuário. Essa
preferência é julgamento de operabilidade, não prova de que toda alternativa
sem upgrade seja insegura ou de que nenhuma possa caber em US$ 30.

A pergunta de decisão agora é se o envelope adicional de US$ 30 pode ser revisto
para a proposta gerenciada. Isso não autoriza compras, upgrade, conta AWS,
provisionamento ou integração. Se o teto for rígido, registrar isso e não
selecionar uma alternativa que transfira silenciosamente a gestão de chaves
ao usuário. Só retomar a opção de CA externa com responsável e ciclo de vida
definidos; não pedir secrets para comprovar isso. Não repetir o inventário ou
esta comparação para produzir atividade enquanto falta essa decisão.

Validação: somente proposta e continuidade editadas; leitura de código, sem
imports/testes. Nenhum secret ou dado real acessado; nenhuma chamada operacional,
commit, push, deploy, alteração de flags ou ordem. Consultas externas foram
somente à documentação pública. Os 267 testes permanecem evidência anterior.

### Sequência operacional proposta (não executada)

#### Proposta mínima de planejamento após esclarecer o orçamento

Referência B, preservando Render/Redis existentes e sem AWS Private CA. Nenhum
item contratado. A preferência por B é para diminuir divergência do experimento
existente, não prova de que essa infraestrutura inteira seja requisito universal
para Live ou de que o código já seja operacional.

| Item adicional modelado | USD/mês | Hipótese/limite |
| --- | ---: | --- |
| Workspace Render Hobby para Pro | 25,00 | Identidade OIDC gerenciada; compute existente continua cobrado à parte |
| Serviço pequeno de manutenção separado | 7,00 | Classe 0.5c-512mb; dimensionamento ainda não comprovado |
| PostgreSQL pequeno separado | 6,00 | Classe 0.1c-256mb; não é aprovação de capacidade operacional |
| Armazenamento PostgreSQL de 5 GB | 1,50 | Provisão de cálculo, a US$ 0,30/GB; não confundir com o disco existente |
| Quatro chaves da variante de referência | 4,00 | US$ 1/chave; chamadas e rotação adicionais não incluídas |
| Subtotal fixo modelado | **43,50** | Não é custo total nem teto da fatura |

Os preços de compute/armazenamento foram reconfirmados por resultados
indexados com contexto da página oficial; a abertura direta continua sem a
tabela dinâmica completa. [Preços Render](https://render.com/pricing).
O número de chaves é específico da variante, não requisito universal.
[Preços KMS](https://aws.amazon.com/kms/pricing/).

**Custo completo = US$ 43,50 + consumo/armazenamento/backup da referência AWS
+ assinaturas + auditoria/alertas/tráfego + impostos e eventuais extras.**
Não apresentar US$ 43,50 como cotação final. Sob o cenário histórico de 1.000
autorizações de manutenção/mês, a parcela modelada de Lambda, requisições
DynamoDB e 1 GB com PITR é aproximadamente US$ 0,48, antes das assinaturas e
demais extras. O cenário é hipótese, não demanda medida; tarifas regionais e
retenção precisam de confirmação. Fontes públicas de cálculo:
[Lambda](https://aws.amazon.com/lambda/pricing/) e
[DynamoDB](https://aws.amazon.com/dynamodb/pricing/).

Somar ao gasto informado pelo usuário daria **US$ 243,50 mais variáveis**,
somente se os US$ 200 se repetissem e B fosse contratada nesse tamanho.
Não somar os US$ 50 de Private CA: pertenciam a outra alternativa descartada.
Não assumir gratuidade, cancelar serviços existentes ou atribuir à ativação
Live um retorno financeiro garantido. Esta soma é de despesas, não projeção
de lucro, recomendação de capital ou autorização para trading.

#### O que realmente falta no caminho para Live

Base: relatório local `C3_DORMANT_STARTUP_INTEGRATION_RESULT_20260911.md`.
Nenhum preflight atual foi executado; o histórico das 07:53 não é estado atual.

| Marco | Situação e critério de conclusão |
| --- | --- |
| Montagem dormente e interlocks pela mesma instância | Concluída offline, 267 testes; não repetir nem chamar de produção pronta |
| Dependências autenticadas/persistentes e recuperação | Ausentes no startup dormente. Precisam de implementação concreta, montagem e ensaio de falha/reinício; contratar infraestrutura não entrega esse código |
| Integração da variante de autoridade escolhida | A variante pública não é aceita pelo binder legado. Delimitar a alteração mínima nos componentes existentes antes de construir serviços ou novos wrappers |
| Homologação no armazenamento alvo | Ainda não executada; exige ambiente isolado e escopo próprio. Não usar dados ou credenciais reais de trading |
| Publicação e verificação operacional | Dependem de autorização específica; mudanças locais recentes não foram publicadas nesta etapa |
| Rearmamento do piloto | Só após critérios operacionais atuais aprovados, proteção e limites definidos; não inferir prontidão dos testes sintéticos ou da compra de serviços |

Recomendação imediata: **não contratar novos recursos agora**. Primeiro delimitar
o change-set mínimo da integração de autoridade, reaproveitando contratos e
sem novas camadas por atividade. Esse planejamento pode continuar sem outro OK;
não implementa runtime, não instala SDK, não acessa contas e não gera chaves.
Proposta de provisionamento só deve vir com dimensionamento, custo completo e
critérios de homologação definidos. Custos recorrentes não justificam retirar
interlocks, acelerar rearmamento sem evidência ou aumentar risco para pagar contas.

Resultado desta etapa: subtotal atualizado, despesas existentes esclarecidas e
marcos técnicos separados de compras. Não se obteve cotação completa garantida.
Somente proposta e continuidade editadas; sem código/testes, secrets, dados reais,
chamadas operacionais, compras, commit/push/deploy, flags ou ordens. Houve leitura
local, pesquisa pública e cálculo. Os 267 testes não foram repetidos.

1. Confirmar inventário não sensível: serviços, provedor, região, plano, disco,
   existência de PostgreSQL/KMS/conta AWS e responsáveis por backup e acesso.
   Não solicitar senhas, tokens, conteúdo do Registry ou capturas de secrets.
2. Escolher A/B/C e fechar estimativa, retenção e prazo aceitável de recuperação.
   Aprovar explicitamente qualquer novo custo, acesso ou recurso de produção.
3. Desenhar políticas de acesso, identidades concretas, fluxo de recuperação e
   separação de backups; revisar ameaças e dependências antes de provisionar.
4. Sob autorização própria, preparar ambiente de homologação sem credenciais
   BingX nem dados reais; implementar os adaptadores reais necessários,
   reutilizando a semântica existente e testando a interoperabilidade.
5. Ensaiar concorrência, resposta perdida, revogação, indisponibilidade e
   restauração; coletar evidência dos critérios abaixo. Não promover por testes
   apenas unitários ou por existência dos serviços gerenciados.
6. Somente após aprovação separada, planejar integração de manutenção no runtime
   com writers bloqueados, mesmos interlocks/lease e recuperação autoritativa.
   Manter trading desativado; não incluir alteração de flags nesta proposta.
7. Auditar o startup e executar o preflight permitido. Rearmamento/Live é outra
   decisão, condicionada a todos os gates operacionais, não só à autoridade C3.

## 7. Critérios de aceitação antes de produção

- Chave pública substituída, política antiga, época revogada, resposta repetida
  e pedido sem origem autenticada são recusados antes de admissão.
- Duas instâncias disputam o mesmo claim e no máximo uma obtém autorização;
  reinício, troca de época e backup local restaurado não liberam novo consumo.
- Falhas em cada fronteira reserva/commit/assinatura/execução deixam estado
  explícito, durável e reconciliável, sem replay de ação após resposta perdida.
- Recuperação da referência permanece bloqueada sem prova completa de
  continuidade; simular também a restauração coordenada de todos os stores e
  manter esse caso como limite, nunca como teste que certifica proteção.
- Permissões de aplicação não apagam claims, mudam políticas/raízes nem restauram
  bancos; auditoria comprova segregação. Credenciais da Central não emitem grants.
- Ausência de rede/política e estouro de deadline falham fechado sem remover
  proteção de posições; chaves e payloads sensíveis não aparecem em logs.
- Destino PostgreSQL valida versão, transações/timeouts, schema e privilégios.
  O laboratório usou PostgreSQL 18.6; compatibilidade no destino não foi atestada.
- Custos, operação, responsáveis e procedimento de recuperação são conhecidos.
  Nenhum desses itens emite por si só permissão de Live.

## 8. Decisões mínimas e encerramento

Não é necessário outro OK para considerar esta análise concluída. A próxima
informação útil é se já existem conta AWS e PostgreSQL contratados; se o usuário
não souber, o próximo escopo seria inventário somente leitura de metadados da
hospedagem, expressamente sem secrets. O inventário básico foi posteriormente
complementado pelas capturas acima, sem acesso direto à conta. AWS e serviços
em outros workspaces continuam desconhecidos.

Depois do inventário, decidir uso de provedor externo e orçamento informado.
Sem isso, não provisionar nem iniciar uma migração. Não exigir que o usuário
escolha componentes técnicos às cegas; apresentar a recomendação com custo
revisado assim que as informações não sensíveis estiverem disponíveis.

Esta sequência automática cumpriu seu objetivo: inventário local, alternativas,
custos conhecidos/desconhecidos, proposta e auditoria. A automação foi pausada
e seu estado PAUSED foi confirmado, para não repetir a análise ou ampliar o
escopo por conta própria.

## Validação e segurança desta revisão

Único arquivo criado: `C3_AUTHORITY_INFRASTRUCTURE_PROPOSAL_20260910.md`.
Nenhuma alteração em código/configuração; alterações preexistentes preservadas.
Nenhum teste executado, módulo operacional importado ou servidor iniciado.
Os 251 testes são evidência histórica da etapa anterior, não resultado novo.
Foram feitas consultas externas somente a documentação pública; nenhum acesso
a conta/painel/API operacional, .env, secret, token, dado real ou Registry.
Nenhum commit, push, merge, deploy, contratação, ordem ou mudança de trading.

Modelo/esforço recomendado para a próxima revisão técnica: GPT-6 Astra — Alto.
Percentual restante para Live: não mensurável sem inventário e critérios
operacionais atuais; não foi estimado artificialmente.
