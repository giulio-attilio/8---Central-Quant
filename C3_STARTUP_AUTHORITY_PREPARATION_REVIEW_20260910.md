# C3 — preparação de startup e autoridade de manutenção

Data: 2026-09-10. Base: `d9e12e9` mais alterações offline da etapa anterior.

## Resultado

Preparado um binding explícito de manutenção antes de `start_central_runtime_once`.
O padrão é `None`, sem leitura, autenticação ou execução de manutenção no startup.
O binding e a partida compartilham `CENTRAL_RUNTIME_LOCK`: a manutenção não pode
ser vinculada após a partida ou substituir uma instância já vinculada.
Enquanto existir binding, a partida é negada antes de mudar `CENTRAL_RUNTIME_STARTED`.
Concluir a composição offline não limpa a barreira nem autoriza workers ou Live.
Não há chamada automática ao novo binder nem rota HTTP de ativação.

A autorização da composição agora pode usar uma assinatura real HMAC-SHA256,
verificada pelo componente `InjectedRootAuthorityVerifierV2` já existente.
O novo adaptador exige chave/época fixadas pela configuração confiável, raiz de
armazenamento fixada, consulta de revogação e ledger fixado por identidade de caminho.
O pedido assina escopo, raiz, nonce, prazo, quantidade de writers e modo de manutenção.
Hashes fornecidos no pedido ou um autenticador que apenas retorne `True` não
satisfazem o binding de startup.

O ledger SQLite é desligado por padrão. Seu provisionamento é explícito e nunca
ocorre durante a autorização. O consumo abre somente banco existente (`mode=rw`),
exige schema com chave primária e sem triggers, usa transação `BEGIN IMMEDIATE`,
`synchronous=FULL` e INSERT único, e confirma o registro após commit. Não atualiza,
apaga ou expira registros. Outra instância sobre o mesmo banco recusa replay;
trocar o banco por um arquivo vazio em outro caminho diverge do binding fixado
e é recusado. Isso não protege restauração no mesmo caminho; o ensaio posterior
em `C3_AUTHORITY_PROVISIONING_AND_CRASH_REVIEW_20260910.md` reproduz essa lacuna.

Prazo e revogação são reavaliados nas fronteiras de verificação e consumo. Uma
falha após commit pode consumir a autorização sem executar a manutenção; esse
resultado é intencionalmente fechado e não permite repetir a mesma autorização.

## Arquivos desta etapa

- `main.py`: estado inicial sem binding, binder explícito e bloqueio anterior à
  marcação de runtime iniciado; nenhum corpo de writer foi alterado.
- `trade_registry_c3_maintenance_authorization_v1.py`: adaptador de assinatura,
  revogação, pins e ledger SQLite de consumo único.
- `tests/test_trade_registry_c3_maintenance_authority_startup_v1.py`: assinaturas
  sintéticas, replay, concorrência, falhas, ledger e prefixo de startup extraído por AST.
- `tests/test_trade_registry_c3_maintenance_activation_offline_v1.py`: a checagem
  de isolamento agora permite o import local do binder, mas continua proibindo
  import automático e chamada automática a `run_offline` no `main.py`.
- `trade_registry_closed_identity_conflict_repair_writer_seam_binding_contract_v1.py`.
- `trade_registry_closed_identity_conflict_repair_runtime_writer_source_anchor_contract_v1.py`.
- `trade_registry_closed_identity_conflict_repair_runtime_writer_transaction_placement_contract_v1.py`.
  Nos três mapas, somente referências de linha dos 11 writers do `main.py` foram
  deslocadas: +1 antes do startup e +21 depois dele. Assinaturas, spans relativos,
  markers e exigências de proteção permanecem. O preflight não foi enfraquecido.
- `C3_MAINTENANCE_ACTIVATION_OFFLINE_REVIEW_20260910.md`: indicação de que é o
  relatório histórico da etapa anterior.
- Este relatório.

Os demais arquivos modificados já existentes no worktree foram preservados.

## Validação

Primeira rodada: 101 testes aprovados. A segunda rodada encontrou 109 aprovados
e uma falha de compatibilidade nas referências de linha após inserir código no
`main.py`. Os mapas foram corrigidos para as posições atuais.

Rodada final: **112 testes aprovados em 155,82 s**, incluindo autorização,
composição de manutenção, startup dormente, preflight estático e spans dos writers.
Verificação adicional dos markers de escrita, locks e guards: **3 aprovados em
69,96 s**. Os dois testes de banco ausente/schema inválido foram refinados para
atravessar a validação de pin e testar efetivamente o SQLite: **2 aprovados em
0,50 s**. Esses dois casos também pertencem à suíte anterior; não somar as rodadas
como um total de testes distintos. `git -c core.longpaths=true diff --check` passou.

Não foram executados a suíte integral do repositório, o runtime completo, testes
em Linux, testes de falha abrupta entre processos, testes de restauração de backup
nem o preflight ou qualquer operação de produção.

Os testes não importam nem executam o aplicativo completo. O controle inicial
de startup é extraído por AST, e a parte que iniciaria workers é substituída por
um marcador sintético. Rede e criação de subprocessos ficam bloqueadas no fixture.
Chaves são bytes sintéticos e todos os bancos ficam em diretórios temporários.
O ensaio anterior de lease física continua simulando apenas fsync de diretório
no Windows; não constitui atestado de durabilidade no Render/Linux.

## Pendências operacionais e limites

Esta etapa prepara interfaces e uma barreira, não uma ativação em produção.
Não configura chaves reais, pins, fonte de revogação, ledger nem sua política de
backup/restauração. A restauração de uma cópia antiga do ledger precisa impedir
reintrodução de autorizações consumidas; este módulo não resolve rollback externo
ou adulteração do armazenamento. Rotação exige provisionamento confiável e
preservação do histórico de consumo, nunca substituição automática por banco vazio.

O binding é local ao processo e protege o ponto `start_central_runtime_once`.
Não demonstra que outros processos ou o servidor HTTP estejam parados. A futura
instalação precisa ocorrer antes de servir requisições e antes de iniciar qualquer
writer, com a mesma instância e coordenação persistente em todos os participantes.
Não há neste patch transição do binding para admissão de runtime após manutenção.

A assinatura usa o verificador existente com provedor de chave injetado; a
autenticidade da raiz depende desse provisionamento confiável. O relógio do
verificador deve compartilhar o domínio temporal do binding. A revogação é
consultada nas fronteiras, não em uma transação distribuída com todos os serviços.
Os callbacks continuam cooperativos quanto ao prazo.

Próximo passo: validar o provisionamento e a composição completa de startup em
ambiente Linux isolado, incluindo múltiplos processos, falha abrupta e restauração
do ledger, antes de planejar uma instalação operacional. O bootstrap real,
reparo CLOSED e retorno a Live continuam fora desta execução.

Nenhum secret real ou `.env` acessado; nenhuma chamada externa, ordem, commit,
push ou deploy executado. Nenhuma flag de trading ou configuração do Render
alterada. Não há percentual fundamentado de trabalho restante para Live.
