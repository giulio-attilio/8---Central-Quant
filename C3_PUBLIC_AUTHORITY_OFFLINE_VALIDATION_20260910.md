# C3 — composição de autoridade por chave pública, exclusivamente offline

Data: 2026-09-10. Objetivo limitado da sequência automática: autenticação por
chave pública, revogações assinadas confrontadas com referência externa
simulada, consumidor PostgreSQL sintético, restauração/regressão e auditoria
dos limites de produção. Esse objetivo offline foi concluído; não é readiness
de produção, deploy, runtime ou Live.

## Arquivos desta etapa e resumo do diff

- `trade_registry_c3_public_authority_offline_v2.py` (novo): verificação Ed25519
  usando somente chave pública; assinaturas vinculam versão, propósito,
  identidade, época e digest. Quatro identidades distintas protegem requisição,
  política, referência externa e recibo de consumo. A política assinada precisa
  coincidir com geração e digest de uma resposta externa assinada a um desafio
  fresco. A mesma instância de guard é exigida no consumidor e na autorização.
  Reserva externa única antecede commit PostgreSQL e assinatura do recibo;
  falha posterior não compensa nem libera a reserva. Há conferência final do
  relógio após a última validação de política, recusando regressão temporal.
  Todos os componentes são default-off, com escopo sintético explícito.
- `trade_registry_c3_postgres_consumption_offline_v1.py` (alterado): extrai a
  transação existente para `commit_digest_once`, compartilhada pelos dois
  protocolos. `CommittedDigestOfflineV1` é um resultado de armazenamento sem
  assinatura, não uma autorização. O consumidor HMAC anterior continua
  assinando somente após commit confirmado. As validações SQL, unicidade,
  durabilidade, privilégios, identidade, encerramento e deadlines são mantidas.
- `tests/helpers/c3_public_authority_fixture.py` (novo): quatro chaves Ed25519
  fictícias e reproduzíveis, políticas assinadas, ledger SQLite temporário e
  simulador de referência externa com reserva atômica por namespace e claim.
  Seu estado é somente em memória e não pertence aos backups locais do teste.
- `tests/test_c3_public_authority_offline_v2.py` (novo): 53 cenários incluindo
  default-off, adulteração, falta da biblioteca criptográfica, revogação das
  quatro identidades, política antiga ou divergente, resposta antiga, falhas
  após reserva/commit, prazos, relógio regressivo, concorrência, restauração e
  composição de manutenção com lease físico temporário e operações sintéticas.
- `tests/helpers/c3_postgres_lab.py` (alterado): inclui a nova suíte e fixture
  no perfil já isolado; reutiliza as ferramentas PostgreSQL existentes.
- Este relatório (novo).

Não foram alterados nesta etapa `main.py`, o verificador HMAC
`trade_registry_c3_maintenance_authorization_v1.py`, o harness de manutenção,
requirements, os adaptadores operacionais de autoridade/revogação ou flags.
As alterações anteriores e os demais arquivos não rastreados da worktree
foram preservados, sem stage ou commit.

## Cadeia efetivamente testada

Requisição assinada → política assinada + head externo fresco → reserva externa
única → INSERT/commit PostgreSQL → recibo assinado → ledger SQLite local →
revalidação final → harness de manutenção offline com lease temporário.

Os testes com PostgreSQL usam o adaptador concreto, não a substituição em memória
usada nos testes unitários. Um caso faz dump real do banco sintético antes do
consumo, autoriza, restaura o dump em outro banco sintético e restaura o SQLite;
a referência simulada retida recusa o reuso. Outro conecta a autorização ao
harness de manutenção existente: bootstrap, recovery e postflight são operações
sintéticas, recebem o mesmo permit, e o resultado continua com
`production_ready`, `runtime_integrated`, `runtime_activation_allowed` e
`live_allowed` iguais a false. Não executa o startup real da Central.

## Evidência final

**251 testes aprovados, zero falhas, erros ou ignorados.** São 53 da nova suíte,
39 do consumidor PostgreSQL e 159 das cinco suítes anteriores de regressão.
Tempo do pytest: 208,01 segundos; JUnit: 208,001 segundos. A rodada anterior de
243 testes também passou, mas não é somada ao resultado final.

Laboratório final: `/var/tmp/cq-c3-lab-pg-an3gykey`.
JUnit: `scratch/results-postgres.xml`, SHA-256
`026a7e636d6505614be4bdf5b96df91d4a879ae4a689e41bd227486ce4eac6df`.
Manifesto: `manifest.json`, SHA-256
`ad3d32d8b9a4510cc65808735632db8282f5eb20130b8ba8141822f4042dec08`.
Os 79 arquivos Python exportados foram comparados com a worktree: zero
divergências. Nenhum `postmaster.pid` permaneceu nos clusters desta rodada.
Arquivos sintéticos de teste e relatórios foram preservados para auditoria.

Isolamento verificado antes dos imports: UID 999, namespaces privados, zero
rotas externas, sem discos Windows/diretórios pessoais visíveis, fontes somente
leitura, área ext4 temporária, capabilities zeradas e NoNewPrivs. PostgreSQL
usa socket Unix privado e nenhum listener TCP. `main.py` é texto para AST,
nunca importado ou iniciado pelo laboratório.

Ferramentas já disponíveis: cryptography 46.0.5, PostgreSQL 18.6, psycopg 3.3.2,
pytest 9.0.2 e bubblewrap 0.11.1. Não houve instalação/download nesta etapa;
a preparação PostgreSQL anterior permanece em `/var/tmp/cq-c3-pg-tools-7lj3eong`.
O launcher tem limite de 900 segundos e os testes usam isolamento sem rede.

Conferências adicionais: `git diff --check` sem erros de whitespace nos arquivos
rastreados (somente avisos LF/CRLF preexistentes); cinco fontes desta etapa sem
whitespace final. Hash de `main.py` inalterado entre snapshots e worktree:
`62b985fc9f7ef49d94ebc2d16945d3301e4603bf4c661ebd10461083bd529b03`.
Hash do verificador HMAC igual ao snapshot da etapa anterior:
`1e2fa06fe820159a51268e0f48c708d2533d294ca38ff779ae00b4401663e264`.

## Auditoria final: limites e riscos residuais

1. **Raiz de confiança ainda sintética.** Verificar uma assinatura com uma chave
   pública fornecida explicitamente não autentica como essa chave foi obtida.
   As chaves de teste são públicas/reproduzíveis; nunca podem ser usadas em
   produção. Não há custódia real, matrícula autenticada de raízes, distribuição
   de pins, autorização administrativa ou procedimento operacional de rotação.
   A mudança de época testada não é uma implementação de rotação de chaves reais.
2. **Referência externa somente simulada.** Sua independência, atomicidade e
   retenção de claims são premissas do experimento, não infraestrutura entregue.
   O controle negativo restaura também o conjunto de claims e permite reuso:
   ele comprova a limitação, NÃO proteção anti-rollback. O controle negativo
   PostgreSQL anterior continua aprovado pelo mesmo motivo. Todos os bancos
   continuam no mesmo computador, sem independência administrativa real.
3. **Recuperação demonstrada é recusa de replay.** Não existe recuperação
   operacional implementada para reserva consumida sem commit, perda de signer
   ou indisponibilidade da referência. A reserva é conservadoramente perdida;
   não há retry/compensação automática, nem projeção autoritativa de resolução
   das obrigações reais. Disponibilidade e reconciliação administrativa seguem
   pendentes de desenho e implementação em um serviço confiável.
4. **Portas injetadas são confiáveis.** Relógio, signer, conector, leitor de
   política e referência não são isolamento contra código hostil no processo.
   O domínio temporal deve ser coerente. Deadlines das portas são cooperativos;
   a conferência posterior recusa respostas tardias, mas não interrompe callback
   bloqueado. O banco impõe adicionalmente limites SQL.
5. **Runtime preservado, não corrigido por este experimento.** A revisão estática
   de `main.py` confirma binding inicialmente None e aceitação apenas do tipo
   legado pelo binder; o novo tipo V2 não foi conectado. Os adaptadores
   operacionais de revogação/autoridade antigos não foram substituídos, e seus
   limites anteriormente identificados não passam a estar resolvidos em produção.

Não executados: suíte integral do repositório, startup completo, preflight real,
Render/BingX, reparo CLOSED real, backup/restore de infraestrutura externa,
queda física de energia, cenários multirregião, deploy ou trading.

## Encerramento do escopo e próximo passo real

Os critérios desta sequência offline estão concluídos. A automação foi
pausada e seu estado PAUSED foi confirmado, conforme seu próprio limite, sem criar novos contratos artificiais nem
aguardar um OK rotineiro. O próximo avanço depende da escolha de uma autoridade
real independente, custódia e distribuição autenticada de chaves, recuperação
de reservas/estado e modelo administrativo de backup. Provisionamento, custos,
credenciais e integração exigem escopo e permissões próprios. Nada neste
relatório autoriza deploy, rearmamento ou retorno a Live.

Nenhum secret, arquivo .env ou dado real foi acessado. Nenhuma chamada externa
foi feita durante os testes ou a retomada final; houve consulta à documentação
pública de criptografia na preparação desta implementação. Nenhuma chamada a
serviços operacionais, ordem, commit, push, deploy ou alteração de configuração
de trading real. Nenhum dado operacional ou histórico foi removido.

Modelo/esforço recomendado para eventual etapa de autoridade de produção:
GPT-6 Astra — Alto. Percentual restante para Live: não mensurável com segurança.

Referência técnica consultada na implementação:
[Ed25519 — cryptography](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/).
