# C3 — acesso piloto à raiz HMAC (matriz sintética de emissão/verificação observada)

## Estado mais recente — evidência fornecida pelo humano em 04/10/2026

- Na conta `899845009758`, com a chave piloto `arn:aws:kms:us-west-2:899845009758:key/62b8d8d4-4e96-4c6c-804f-856600ac09ac`, o humano confirmou por `sts get-caller-identity` as sessões assumidas separadas `C3PilotRootHmacIssuerRole20261003/c3-pilot-root-hmac-issuer` e `C3PilotRootHmacVerifierRole20261003/c3-pilot-root-hmac-verifier`. As chamadas KMS usaram explicitamente `--region us-west-2` e a mensagem sintética `C3-HMAC-SYNTHETIC-20261004`, com `HMAC_SHA_256`.
- Na role emissora, `kms:GenerateMac` retornou uma tag e `kms:VerifyMac` recebeu `AccessDeniedException` com negação explícita na política da chave. Na role verificadora, `kms:VerifyMac` para a mesma mensagem e tag retornou `True`, enquanto `kms:GenerateMac` recebeu `AccessDeniedException` com negação explícita na política da chave. São resultados positivos/negativos efetivamente relatados pelo humano, não uma leitura direta da AWS por este agente.
- Para limpar os ambientes CloudShell temporários em `us-east-2`, o humano adicionou temporariamente `cloudshell:DeleteEnvironment` limitado a cada ARN de ambiente. Após a exclusão, as capturas mostraram `No active tabs` para os dois ambientes; não houve consulta independente para confirmar o estado remoto. As políticas CloudShell temporárias foram então removidas das duas roles. Capturas do IAM mostraram somente `C3PilotRootHmacIssuerGenerateOnly20261004` na emissora e somente `C3PilotRootHmacVerifierVerifyOnly20261004` na verificadora.
- Esta matriz comprova somente a separação de `GenerateMac`/`VerifyMac` para essa mensagem e chave piloto, nas duas sessões observadas. Não comprova por si só bloqueio de algoritmo incorreto, outra chave, principal base/sem MFA, perda de resposta, integração de workload, disponibilidade, anti-rollback ou operação de produção. Não registrar a tag sintética como credencial ou chave secreta.
- Próximo gate: revisar as políticas efetivas após a limpeza e completar a matriz negativa ainda não executada, se houver autorização específica para novas chamadas AWS. Separadamente, qualificar o vínculo C3 `root/storage/key/epoch`, a identidade de workload, a atualidade/anti-rollback e os demais requisitos do plano de liberação antes de cogitar integração. O adaptador permanece default-off; gates C3, Render, LIVE e trading permanecem intocados e fechados.

## Continuação local — revisão estática do próximo gate em 04/10/2026

- `KmsRootHmacVerificationProviderV2` continua default-off, recebe cliente injetado e ARN fixo, e recusa respostas sem `MacValid is True`, `KeyId` igual ao ARN e `MacAlgorithm=HMAC_SHA_256`. A identidade do atestado é o SHA-256 do ARN completo. O teste AWS relatado consultou somente `MacValid` no CLI; por isso não observou os campos completos da resposta exigidos pelo adaptador.
- `InjectedRootAuthorityVerifierV2`, no modo remoto explícito, envia ao provider os 64 bytes ASCII do hash hexadecimal do payload e a tag de 32 bytes. A mensagem sintética usada no teste de permissões AWS não exercitou esse formato de atestado C3. Os testes locais existentes cobrem o contrato com cliente KMS falso e recuperação sintética, inclusive recusas e `production_ready=false`/`live_allowed=false`; não são prova de chamada AWS integrada.
- Na busca estática de usos Python, a construção de `KmsRootHmacVerificationProviderV2` aparece no harness sintético, não em uma composição operacional de startup. O provider de estado e a fonte de revogação atuais leem envelopes em arquivo local com geração positiva e hash, mas isso não estabelece uma referência externa independente de atualidade/anti-rollback após restore.
- Próxima unidade segura é delimitar, sem ativar, a matrícula operacional imutável `root/storage/key/epoch`, a fonte externa de atualidade/revogação, o prazo de verificação e a identidade de workload. Antes de qualquer teste AWS adicional, pedir autorização específica e formular matriz com payload sintético no formato real e observação da resposta completa, além dos negativos ainda pendentes. Nenhuma dessas tarefas equivale a liberar os dois bloqueios do último preflight (`TRADE_REGISTRY_PERSISTENT_OK` e `TRADE_REGISTRY_C3_WRITER_COORDINATION_READY`).

Revisão somente de fontes e documentos locais; nenhum teste executado, chamada externa ou alteração operacional nesta continuação.

### Matrícula candidata, não aplicada

Para o ARN piloto acima, `kms_root_hmac_key_id_sha256_v2` especifica SHA-256 dos bytes ASCII do ARN completo. O valor calculado localmente é `ac028d92dd7014bdad3e4bc05d9f9d736846d6b198014b346a7760854d200aa5`. Isto **não** atribui a chave a uma raiz de produção, não configura provider e não constitui emissão de atestado.

| Campo do atestado V2 | Contrato local já existente | Prova/decisão ainda faltante |
| --- | --- | --- |
| `root_identity_sha256` | Hash de 64 caracteres exigido pelo contrato | Identidade da raiz operacional e responsável autorizado por publicá-la; não inferir da chave ou do símbolo/robô |
| `storage_binding_sha256` | Comparado com os pins de leitura, recuperação e startup | Identidade estável e exata do armazenamento real, incluindo migração/restore e separação de backups; não substituir pelo caminho temporário do harness |
| `key_id_sha256` | No adapter KMS, hash do ARN imutável fixado | Matrícula autenticada que vincule a chave piloto, ou outra chave futura, à raiz e ao armazenamento corretos; a posse do ARN e uma tag válida isoladamente não bastam |
| `key_epoch` e `previous_attestation_sha256` | Época inteira positiva; primeira época sem anterior, posteriores exigem hash anterior | Autoridade externa monotônica para época/hash aceitos, rotação e revogação; um envelope local restaurável não impede rollback |
| `issued_at_epoch`/`expires_at_epoch` | Janela checada na admissão offline | Relógio qualificado, prazo de chamada KMS e rechecagem antes dos efeitos; uma chamada bloqueada não fica segura só por ter iniciado dentro da janela |

Critérios para a próxima prova offline, antes de qualquer wiring: recusar chave/ARN trocado, root ou storage divergente, época antiga e cadeia anterior inválida, estado revogado, resposta KMS ambígua, timeout e expiração durante a verificação; demonstrar que as recusas ocorrem antes dos stores. Testes atuais com fakes cobrem partes da verificação/recuperação, mas não qualificam uma autoridade externa de atualidade nem o runtime de produção. A escolha da autoridade externa e da identidade de workload é uma decisão operacional separada, ainda não autorizada.

As alternativas A/B/C de `C3_AUTHORITY_INFRASTRUCTURE_PROPOSAL_20260910.md` tratam principalmente da autorização pública de manutenção e sua referência independente. Não presumir que a escolha de uma dessas topologias matricule automaticamente a raiz HMAC de recuperação ou conceda credenciais KMS ao workload da Central; os dois vínculos exigem revisão própria.

## Desenho de referência aceito para análise offline — NÃO IMPLANTADO

O humano concordou em 04/10/2026 com a direção: Central permanece no Render; uma referência independente de época/hash fica no DynamoDB; a identidade de workload usa OIDC gerenciado do Render para obter credenciais temporárias de uma **nova** role de verificação. A concordância não autoriza upgrade, custos, criação de tabela/role/provedor OIDC, alteração da key policy, deploy ou liberação de trading. A fonte externa e a identidade ainda são hipóteses de desenho até qualificação e decisão operacional específica.

### Separação de responsabilidades proposta

| Componente | Permissão estritamente pretendida | Proibição relevante |
| --- | --- | --- |
| Role humana emissora do piloto | `kms:GenerateMac` na chave piloto, como já observado | Não verificar, publicar automaticamente uma raiz operacional ou assumir identidade de workload |
| Publicador de referência, identidade a definir | Avançar condicionalmente o head autenticado e registrar revogação; processo separado, auditável | Não conceder essa escrita à Central nem permitir apagar/reduzir época |
| Nova role OIDC do serviço exato da Central | `kms:VerifyMac` na chave ARN fixada e leitura forte da referência exata | Sem `GenerateMac`, escrita/exclusão/restauração da tabela, grants KMS ou administração |
| Administrador de recuperação | Recuperação excepcional documentada, fora do deploy da Central | Não trocar ARN da tabela/pins silenciosamente após restore |

O trust OIDC futuro deve fixar audiência `sts.amazonaws.com` e o `sub` do serviço Render exato (workspace, ambiente e serviço), não um curinga de workspace. Não reutilizar a role humana verificadora: sua trust atual exige o usuário nomeado e MFA. A key policy piloto hoje excetua somente essa role humana do `DenyVerifyMac`; uma role de workload não funcionaria até uma revisão específica da política e da IAM. Não editar ambas apenas porque o desenho foi aceito. OIDC gerenciado requer Render Pro ou superior. Em 04/10 o usuário elevou para US$ 50/mês adicionais o **teto de planejamento**, sem autorizar cobrança; custo total continua sem fechamento. [OIDC Render](https://render.com/docs/oidc), [planos Render](https://render.com/pricing), [preços KMS](https://aws.amazon.com/kms/pricing/).

### Head externo candidato e ordem de admissão

Um item autoritativo por `root_identity_sha256` em uma tabela cujo ARN seja fixado fora do backup do app deve conter, no mínimo, `storage_binding_sha256`, `key_id_sha256`, `key_epoch`, `head_attestation_sha256`, estado de revogação e versão do esquema. A forma final e a retenção histórica precisam de revisão; não usar TTL para apagar prova de uma época que possa reaparecer após restore. O publicador deve avançar por escrita condicional que compara head/época anteriores e nunca aceita diminuição, salto sem cadeia validada ou revogação removida. Leitura de um único item deve pedir consistência forte; se o estado for dividido em vários itens, a leitura precisa de snapshot transacional. Índice secundário eventualmente consistente não serve como autoridade de atualidade. [Consistência DynamoDB](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadConsistency.html), [transações](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html).

Na admissão, antes de tocar stores: identificar serviço/cliente, ler o head externo com prazo limitado, comparar `root/storage/key/epoch/hash` e revogação com o atestado local, verificar janela temporal e `VerifyMac` na chave fixada, e revalidar expiração/lease antes do primeiro efeito. Resposta ausente, ambígua, atrasada ou inconsistente deve fechar novas admissões. Nunca cancelar disaster stops ou gerir posições existentes por indisponibilidade dessa referência. O caminho atual de recuperação é sintético/default-off e não deve ser religado por este texto.

Restauração da Central exige confrontar o estado restaurado com o head externo. Restauração DynamoDB cria outra tabela: ela deve ficar em quarentena, sem trocar o ARN pinado automaticamente; somente evidência independente e procedimento autenticado podem decidir recuperação. Escrita condicional protege concorrência dentro da tabela selecionada, mas **não** resolve comprometimento administrativo ou troca maliciosa do destino. [Restore DynamoDB](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/pointintimerecovery_restores.html).

### Prova offline mínima antes de qualquer provisionamento

1. Com fakes de OIDC/STS, KMS e referência externa, validar a configuração pretendida para o `sub` exato, a ausência de caminho de `GenerateMac`/escrita no consumidor e a recusa antes dos stores para principal/ARN/algoritmo trocados. Fakes não provam permissões IAM efetivas; isso exigirá teste AWS autorizado separadamente.
2. Com estado local restaurado, provar rejeição de época/hash antigos frente ao head externo; testar concorrência de dois publicadores, timeout ou resposta perdida da escrita condicional, revogação e cadeia anterior inválida, sem avanço local antecipado.
3. Simular troca por tabela restaurada/mais antiga e indisponibilidade da referência ou KMS: nenhuma admissão nova, nenhum efeito nos stores, nenhuma ordem enviada e nenhuma proteção física existente removida.
4. Conferir deadline compartilhado, expiração durante `VerifyMac` e rechecagem antes do efeito. Manter `production_ready=false`, `runtime_integrated=false` e `live_allowed=false` nos resultados offline.

Antes da etapa operacional, ainda faltam estimativa integral (plano Render, compute, DynamoDB, KMS, logs/recovery e tributos), identidade exata do serviço, modelo de administração/recuperação da tabela e autorização separada para cada alteração de infraestrutura. Não tratar a aprovação deste desenho como autorização para executar esses itens.

As seções abaixo são histórico da preparação anterior aos testes. Onde mencionam ausência de chamadas KMS, isso descreve somente aquela etapa, não o estado mais recente acima.

## Estado anterior — relato humano de 04/10/2026, política pós-salvamento conferida por texto

- O humano autorizou especificamente conceder `kms:GenerateMac` só à role emissora e `kms:VerifyMac` só à role verificadora na chave piloto, sem testes AWS, Render ou trading.
- Capturas do console mostraram a política inline `C3PilotRootHmacVerifierVerifyOnly20261004` criada na `C3PilotRootHmacVerifierRole20261003` e a política inline `C3PilotRootHmacIssuerGenerateOnly20261004` criada na `C3PilotRootHmacIssuerRole20261003`. Os JSONs foram inspecionados antes de criar: cada um contém apenas sua ação, o ARN exato da chave e `kms:MacAlgorithm=HMAC_SHA_256`.
- O humano mostrou no editor KMS a substituição do `Deny` global pelas três negações propostas abaixo, mantendo `Enable IAM User Permissions`. As capturas cobriram o documento inteiro antes de salvar; em seguida informou `feito` e transcreveu a política exibida fora do editor. O texto pós-salvamento contém os quatro statements esperados, com os ARNs e `HMAC_SHA_256` corretos. Esta é uma conferência por evidência fornecida pelo humano, não leitura direta da AWS pelo agente nem teste de autorização efetiva. Não declarar acesso KMS funcional sem testes autorizados.
- Nenhuma chamada `GenerateMac`/`VerifyMac` foi executada nesta etapa. Nenhuma mudança de Render, credenciais, C3 gate, LIVE ou trading foi autorizada ou realizada. O adaptador continua default-off e o gate C3 permanece fechado.
- Próximo passo, se autorizado separadamente: testes positivos/negativos exclusivamente sintéticos de `GenerateMac`/`VerifyMac` nas duas roles, com custo/chamadas AWS explicitamente aceitos, antes de qualquer integração. As seções datadas abaixo preservam a evolução histórica e não devem ser interpretadas como estado atual quando disserem que as roles ainda tinham zero políticas.

## Estado observado em 03/10/2026

- Conta AWS `899845009758`, região `us-west-2`.
- Chave piloto de região única `HMAC_256`: `arn:aws:kms:us-west-2:899845009758:key/62b8d8d4-4e96-4c6c-804f-856600ac09ac` (`c3-pilot-root-hmac-20261003`).
- A política aplicada preserva a administração da conta e contém `Deny` para `kms:GenerateMac` e `kms:VerifyMac` com `Principal: "*"`. Portanto, uma nova permissão IAM isolada **não** basta para usar a chave: o `Deny` prevalece até uma alteração específica da política da chave.
- Nenhum usuário/role de uso criptográfico foi selecionado na criação da chave. Posteriormente foram criados `c3-pilot-root-hmac-issuer`, `c3-pilot-root-hmac-verifier`, `C3PilotRootHmacIssuerRole20261003` e `C3PilotRootHmacVerifierRole20261003`. A chave Ed25519 e `C3PilotSyntheticSignerRole20261003` são de outra finalidade e não devem ser reutilizadas para a raiz HMAC.
- Inspeção do IAM em 03/10/2026: cada usuário tem um dispositivo MFA (passkey/chave de segurança) e zero chaves de acesso; cada role tem zero políticas de permissão e confia somente no ARN do respectivo usuário, com `aws:MultiFactorAuthPresent=true`. Nenhuma permissão KMS foi concedida nesta etapa. Em 04/10/2026, o humano habilitou acesso ao console para ambos os usuários; a lista IAM confirmou `Habilitado` para emissor e verificador, e a página do verificador mostrou `Habilitado com MFA`, um dispositivo MFA e zero chaves de acesso. Não houve login observado desses usuários.
- O adaptador local `KmsRootHmacVerificationProviderV2` permanece default-off, exige ARN completo fixado e cliente injetado e não efetua descoberta de credenciais. Sua aprovação por testes offline não é prova de integração AWS ou prontidão para trading.

## Separação preparada para o piloto

| Identidade preparada | Confiança atual | Ação criptográfica futura proposta, não concedida | Limites pretendidos |
| --- | --- | --- | --- |
| `C3PilotRootHmacIssuerRole20261003` | Novo usuário humano `c3-pilot-root-hmac-issuer`, com MFA; ARN nominal fixado, sem trust amplo à conta | `kms:GenerateMac` | Apenas ARN da chave acima e `kms:MacAlgorithm=HMAC_SHA_256`; sem `VerifyMac`, `Sign`, grants ou administração |
| `C3PilotRootHmacVerifierRole20261003` | Novo usuário humano `c3-pilot-root-hmac-verifier`, com MFA; ARN nominal fixado, sem trust amplo à conta | `kms:VerifyMac` | Mesmo ARN e algoritmo; sem `GenerateMac`, `Sign`, grants ou administração |

Nesta fase, as identidades humanas de piloto estão separadas entre si e dos usuários `c3-pilot-key-admin` e `c3-pilot-synthetic-signer`, sem credencial programática permanente. Não ligar o verificador ao Render ou à Central enquanto a identidade de workload e os demais gates C3 não forem qualificados. O humano concluiu a configuração de MFA e habilitou login de console; não foi concedida política de identidade `sts:AssumeRole` aos novos usuários. Em 04/10/2026, relatou ter assumido com êxito, pelo console e separadamente, as roles do emissor e do verificador. Isso comprova apenas a troca observada pelo humano, não chamadas KMS, uso programático ou prontidão C3.

### Confiança aplicada; permissões criptográficas ainda não concedidas

1. Aplicado e inspecionado: a política de confiança de cada role menciona somente o ARN do respectivo usuário e condiciona `sts:AssumeRole` a `aws:MultiFactorAuthPresent=true`. A duração máxima da sessão é de 1 hora; não há principals alternativos.
2. Como a trust policy nomeia diretamente um usuário da mesma conta, a AWS não exige uma política de identidade adicional com `sts:AssumeRole` para essa role. Não anexar permissão redundante sem necessidade demonstrada; verificar eventuais denies explícitos ou permission boundaries antes de um teste autorizado. Sem acesso KMS direto.
3. A política de identidade da role deve citar o ARN **exato** da chave como `Resource` e apenas a ação da tabela, com `StringEquals` em `kms:MacAlgorithm=HMAC_SHA_256`.
4. A política da chave só poderá ser alterada quando ambas as identidades e suas relações de confiança estiverem revisadas. Não remover simplesmente o `Deny` global: substituí-lo por negações que continuem barrando `GenerateMac` para todos exceto o emissor e `VerifyMac` para todos exceto o verificador, além das permissões positivas estritas. Confirmar a semântica da exceção para sessões STS assumidas antes de salvar. Preservar caminho administrativo da conta para evitar chave irrecuperável.
5. Não criar grants nem usar alias como recurso de autorização ou como `KeyId` operacional. Fixar o ARN imutável na matrícula C3. Rotação exige nova chave/época e revisão separada.

## Verificação exigida antes de qualquer uso

- Inspecionar as políticas efetivas sem revelar credenciais. Garantir que o emissor não possa verificar e o verificador não possa emitir; usuários base não podem chamar KMS diretamente.
- Em sessão piloto isolada, executar testes positivos e negativos de `GenerateMac`/`VerifyMac` somente sobre mensagens sintéticas; chamadas reais AWS e eventual custo de requisição exigem autorização específica. Cobrir algoritmo incorreto, chave trocada, ausência de MFA, principal errado, resposta perdida e negação antes de liberar.
- Verificar no C3 o vínculo `root/storage/key/epoch`, a atualidade e o anti-rollback externos. Uma tag HMAC válida isoladamente não autoriza manutenção nem trading.
- Manter Render, flags LIVE, ordens e reconciliação real intocados; o gate permanece fechado.

## Próxima autorização necessária

Concluído conforme relato humano: cada usuário entrou pelo navegador com senha e passkey e assumiu somente sua respectiva role no console. Nenhuma chamada KMS foi feita; as roles seguem sem permissão criptográfica. Não registrar, exibir nem copiar senha, código ou passkey.

`aws login` da AWS CLI v2.32.0+ permanece uma alternativa futura, não necessária para esta prova. Exigiria política de identidade mínima para `signin:AuthorizeOAuth2Access` e `signin:CreateOAuth2Token`, restrita à conta, região e cliente `oauth2/public-client/localhost`. A política gerenciada `SignInLocalDevelopmentAccess` concede também o método `remote`; não anexá-la automaticamente. A AWS documenta que passkeys não são suportadas diretamente pelo CLI/API em operações MFA-protegidas; nenhum caminho programático é presumido nesta etapa.

A próxima mudança efetiva exigirá autorização específica e separada: conceder à role emissora somente `kms:GenerateMac`, à role verificadora somente `kms:VerifyMac`, ambas limitadas ao ARN fixo e a `HMAC_SHA_256`, e substituir cuidadosamente o `Deny` global da política da chave por negações que preservem a separação. Antes disso, conferir a política completa aplicada e revisar as exceções para sessões de roles assumidas e o caminho administrativo; não basta anexar políticas IAM enquanto o `Deny` global persistir. Após autorização e aplicação, testes positivos e negativos seriam exclusivamente sintéticos, com custo/chamadas AWS também autorizados separadamente. O gate C3 e trading continuam fechados.

## Proposta offline após leitura da política completa em 04/10/2026 — NÃO APLICADA

O humano forneceu a política completa da chave: somente `Enable IAM User Permissions` para o principal da conta e `DenyPilotMacUseUntilSeparatelyApproved` para `kms:GenerateMac`/`kms:VerifyMac` com `Principal: "*"`. Não há outra exceção na política transcrita. A proposta abaixo é um **rascunho para revisão**, não autorização para salvar na AWS. Conferir novamente a política efetiva e as políticas IAM/boundaries antes de qualquer aplicação; mudanças concorrentes invalidam este rascunho.

Substituir **apenas** o statement `DenyPilotMacUseUntilSeparatelyApproved` por três negações. Manter `Enable IAM User Permissions` inalterado para preservar administração e delegação IAM. O `aws:PrincipalArn` de uma sessão de role assumida corresponde ao ARN da role IAM, não ao ARN da sessão STS. As duas primeiras negações barram todos os demais principals, inclusive os usuários base e a role oposta. A terceira barra algoritmo diferente de `HMAC_SHA_256` mesmo para a role correta; a API exige `MacAlgorithm` nas duas operações. Nenhum `Allow` criptográfico amplo deve ser adicionado à key policy.

```json
{
  "Version": "2012-10-17",
  "Id": "key-consolepolicy-3",
  "Statement": [
    {
      "Sid": "Enable IAM User Permissions",
      "Effect": "Allow",
      "Principal": {"AWS": "arn:aws:iam::899845009758:root"},
      "Action": "kms:*",
      "Resource": "*"
    },
    {
      "Sid": "DenyGenerateMacExceptPilotIssuerRole",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "kms:GenerateMac",
      "Resource": "*",
      "Condition": {
        "ArnNotEquals": {
          "aws:PrincipalArn": "arn:aws:iam::899845009758:role/C3PilotRootHmacIssuerRole20261003"
        }
      }
    },
    {
      "Sid": "DenyVerifyMacExceptPilotVerifierRole",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "kms:VerifyMac",
      "Resource": "*",
      "Condition": {
        "ArnNotEquals": {
          "aws:PrincipalArn": "arn:aws:iam::899845009758:role/C3PilotRootHmacVerifierRole20261003"
        }
      }
    },
    {
      "Sid": "DenyOtherMacAlgorithms",
      "Effect": "Deny",
      "Principal": "*",
      "Action": ["kms:GenerateMac", "kms:VerifyMac"],
      "Resource": "*",
      "Condition": {
        "StringNotEquals": {"kms:MacAlgorithm": "HMAC_SHA_256"}
      }
    }
  ]
}
```

Depois, e somente em autorização separada para IAM, cada role receberia uma política de identidade própria. Exemplos de escopo (não anexados):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "AllowPilotGenerateMacOnly",
    "Effect": "Allow",
    "Action": "kms:GenerateMac",
    "Resource": "arn:aws:kms:us-west-2:899845009758:key/62b8d8d4-4e96-4c6c-804f-856600ac09ac",
    "Condition": {"StringEquals": {"kms:MacAlgorithm": "HMAC_SHA_256"}}
  }]
}
```

O bloco acima é **somente** para `C3PilotRootHmacIssuerRole20261003`. Para `C3PilotRootHmacVerifierRole20261003`, usar o mesmo `Resource` e `Condition`, trocando a ação por `kms:VerifyMac` e o `Sid` por `AllowPilotVerifyMacOnly`. Não anexar ambos à mesma role ou aos usuários base. Não conceder grants, acesso a aliases, administração ou permissões à Central/Render.

Antes de aplicar: revisão humana dos ARNs, da região e dos statements efetivos; validação de sintaxe e da semântica de `aws:PrincipalArn` para sessões assumidas; verificação de boundaries, SCPs e outros IAM allows/denies; caminho administrativo e rollback do documento original preservados. Depois de autorização específica, testar matriz positiva/negativa somente com mensagens sintéticas em sessão isolada e com autorização separada para chamadas/custos AWS. Não inferir prontidão de produção a partir desse teste. Trading permanece bloqueado.

Fontes AWS: [políticas KMS](https://docs.aws.amazon.com/kms/latest/developerguide/key-policies.html), [condição `kms:MacAlgorithm`](https://docs.aws.amazon.com/kms/latest/developerguide/conditions-kms.html), [role IAM com MFA](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-user.html), [AssumeRole para usuário nomeado na trust policy da mesma conta](https://docs.aws.amazon.com/cli/latest/reference/sts/assume-role.html), [login de CLI por credenciais do console](https://docs.aws.amazon.com/signin/latest/userguide/command-line-sign-in.html), [permissões de Sign-In](https://docs.aws.amazon.com/signin/latest/userguide/security-iam-awsmanpol.html), [limitação de passkeys no CLI/API](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_mfa_fido_supported_configurations.html). Base local: `C3_AUTHORITY_INFRASTRUCTURE_PROPOSAL_20260910.md`, seção “Decisão técnica da raiz e transporte”.
