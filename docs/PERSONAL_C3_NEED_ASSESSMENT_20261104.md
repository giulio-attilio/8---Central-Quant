# Avaliação da necessidade de C3 distribuído para uso pessoal — 2026-11-04

## Decisão atual

Para a topologia observada do Central Quant pessoal — um serviço Render, uma
instância, um processo iniciado por `python main.py` e uma conta — não foi
demonstrada necessidade de colocar o signer ou a coordenação C3 distribuída no
caminho crítico. Manter C3 dormente/default-off e não implementar signer nem
ativar coordenação nesta etapa. Preservar todo o código C3 existente.

Esta é uma conclusão proporcional às evidências disponíveis, não uma prova de
que os writers estão corretos em produção nem uma aprovação para trading LIVE.

## Evidências observadas

- A inspeção somente de leitura do Render em 2026-11-04 identificou o serviço
  `central-robos-bingx`, plano Standard, uma instância, disco persistente de
  2 GB em `/data`, comando `python main.py` e auto-deploy desligado. O release
  em execução era `598c4d4`; não houve deploy nem leitura de variáveis/secrets.
- Reconsulta somente de leitura em 2026-11-04 confirmou o mesmo serviço,
  repositório `giulio-attilio/8---Central-Quant`, branch
  `codex/personal-readiness-20261103`, uma instância e allowlist de rede
  `0.0.0.0/0`. O deploy ativo continua `598c4d4505c3aec6d4de9a6b762cc1576f604374`
  (`live`), com auto-deploy desligado. A exposição de rede é pública; o gate
  HTTP global do próprio release autentica as rotas da aplicação, exceto o
  `/healthz` mínimo de liveness. Não foram consultados valores de variáveis.
- Revalidação somente de leitura às 17:47–17:49 UTC de 2026-11-04: Render
  continua apontando `srv-d8rtuv9o3t8c73ehav5g` para
  `codex/personal-readiness-20261103`, com auto-deploy desligado. O deploy mais
  recente continua `dep-dbl0g5rncjis73fhe8dg`, commit
  `598c4d4505c3aec6d4de9a6b762cc1576f604374`, estado `live`. No GitHub, a
  comparação da branch candidata `codex/personal-readiness-release-20261104`
  com o HEAD local `29b505b8da9b64e92ca82f9c5c9cd1b261cb5c3b` retornou
  `identical` (0 commits à frente/atrás). Isso confirma que o commit candidato
  já está publicado na branch candidata, mas o Render ainda não consome essa
  branch. A integração GitHub não permitiu confirmar as regras de proteção da
  branch candidata (endpoint de proteção rejeitado pelo conector); isso não
  prova que a branch seja desprotegida. Não foi feito push/merge por essa via.
  Nenhuma variável de ambiente foi lida nem alterada.
- Em `trade_registry.py`, `_lock` é um `threading.RLock`. A função
  `_trpsf_v1_registry_lock()` em `main.py` retorna esse mesmo lock. Os caminhos
  de escrita do Registry revisados usam esse lock local. Os locks `flock` de
  `acquire_runtime_file_lock()` elegem líderes de loops de runtime; não são,
  por si, uma transação compartilhada entre processos para todos os writers.
- A montagem atual de `C3_CLOSED_REPAIR_WRITER_COORDINATOR_DORMANT_V1` usa
  `enabled=False`; o startup normal não ativa C3.
- Uma busca estática em `main.py`, `broker.py`, `trade_registry.py` e `bots/`
  encontrou inicialização de `threading.Thread`, mas nenhuma ocorrência de
  `multiprocessing`, `subprocess`, `Popen` ou `os.fork`. Isso é consistente com
  concorrência por threads no processo iniciado pelo Render; é uma busca
  textual limitada, não prova ausência de processos iniciados dinamicamente ou
  por infraestrutura externa.
- A auditoria estática existente enumera 8 writers em `trade_registry.py` e 11
  em `main.py` (19 no total), mas declara que não prova exclusão física entre
  processos nem que todo writer externo ao inventário use o mesmo domínio de
  lock/lease. O arquivo de auditoria é uma fotografia datada e avisa que partes
  da tabela histórica estão desatualizadas.
- Uma nova inspeção AST somente-leitura, sem importar ou executar `main.py`,
  confirmou estruturalmente os 8/8 writers listados de `trade_registry.py` com
  o lock `_lock` e os 11/11 writers listados de `main.py` com o wrapper de
  mutação C3 antes de `registry_lock`. O bootstrap do coordenador em `main.py`
  usa `enabled=False`; nesse estado, `mutation()` retorna
  `COORDINATOR_DEFAULT_OFF_PASSTHROUGH` com `shared_lock_acquired=False`. Isso
  confirma a estrutura dos 19 pontos inventariados, não a completude global do
  inventário nem exclusão contra processo/serviço externo. As três falhas do
  teste de âncoras C3 decorrem das linhas fixas antigas não acompanharem as
  funções atuais; não atualizei as âncoras automaticamente.
- A execução local dos testes de startup C3 dormente e concorrência do Registry
  (`test_c3_dormant_startup_same_coordinator_v2.py`,
  `test_registry_two_writers_atomic_rmw_v1.py` e
  `test_registry_remaining_writers_atomic_rmw_v1.py`) terminou com 100 aprovados
  em 384,40 s. Separadamente, os três testes de
  `test_c3_main_writer_source_anchors_offline.py` falham por divergência de
  escopo/âncoras de linha e porque o erro de deslocamento antecede o teste de
  drift. A inspeção AST atual confirmou os contextos estruturais dos 19 pontos
  listados, mas não prove exclusão contra writers externos. Não atualizar
  âncoras mecanicamente; C3 continua desativado e sem necessidade demonstrada
  para a topologia pessoal observada.
- Revalidação nesta worktree em 2026-11-04: a seleção offline
  `--personal-safety-no-ccxt` terminou com 265 aprovados em 523,25 s. A seleção
  `--persistence-locks` terminou com 30 aprovados em 169,95 s após um primeiro
  intento com 29 aprovados e 1 falha causada pelo metadado Versioneer do CCXT,
  que tentou iniciar `git` e foi corretamente bloqueado pelo runner offline.
  Na repetição, foi fornecida somente uma versão neutra em memória para esse
  metadado; nenhum subprocesso ou acesso à rede foi liberado, e os arquivos do
  projeto não foram alterados para contornar a barreira.

## Comparação com a alternativa simples

Com uma única instância e um único processo, o lock reentrante do módulo
Registry serializa os writers que o adquirem, inclusive chamadas concorrentes
por threads. Essa alternativa evita adicionar serviço signer, identidade OIDC,
armazenamento de checkpoint, lease distribuída e custos/risco operacional sem
requisito demonstrado para o uso de uma pessoa e uma conta.

O `RLock` é local ao processo: não coordena dois processos independentes que
escrevam o mesmo arquivo. Portanto a conclusão depende da topologia observada e
não se estende a escala horizontal, workers/processos extras ou outro serviço
que escreva o Registry. Esses cenários exigiriam nova medição e prova antes de
qualquer mudança. O disco persistente também não demonstra, sozinho, durabilidade
física ou recuperação após falha.

## Gatilhos para reavaliar C3

Reabrir a avaliação apenas se evidência atual mostrar mais de um processo ou
instância escrevendo simultaneamente, outro serviço escritor, corrida/perda de
atualização não resolvida pelo lock local, ou requisito concreto de recuperação
que não possa ser atendido pela solução single-process. Se isso ocorrer,
primeiro corrigir e testar contratos/âncoras dos writers em laboratório; depois
reavaliar a arquitetura mínima. Não criar HEAD sem confiança verificada, não
migrar/bootstrap o Registry e não reescrever dados históricos em massa.

## Limites e próximos gates

- No início desta revalidação, a worktree estava na branch
  `codex/personal-readiness-release-20261104`, HEAD
  `29b505b8da9b64e92ca82f9c5c9cd1b261cb5c3b`; o upstream local está em
  `0ddc28a70e36136fafd4e8ba316aaecc734e481c`. O release Render `598c4d4` é
  ancestral do HEAD, mas o código local difere dele em 17 arquivos (2.543
  inserções e 139 remoções). Portanto, testes locais não validam o release
  atualmente servido; equivalência de release continua pendente.
- As seleções de regressão executadas nesta worktree terminaram com 265 testes
  pessoais/offline, 30 testes de persistência/locks, 60 testes de escritores
  atômicos do Registry e 32 testes de sincronização/ownership aprovados. O
  runner bloqueou rede, subprocessos e leitura de `.env`, usando diretório de
  dados temporário. A falha inicial de import do CCXT foi reproduzida e
  atribuída à consulta de versão pelo pacote; a repetição passou com metadado
  neutro em memória, sem liberar subprocesso ou rede.
- A seleção ampliada `--extra`, executada com o wheel local fixado
  `ccxt==4.5.88` (`--no-index --no-deps`, fora do `.venv` compartilhado),
  terminou com 918 aprovados, 1 falha, 1 ignorado e 1 desmarcado em 1.463,33 s.
  A falha foi um `PermissionError` transitório ao abrir `bots/falcon.py` em um
  teste; a leitura direta do arquivo funcionou. Depois, o módulo completo
  `test_falcon_terminal_disaster_stop_emergency_recovery_v1.py` foi repetido no
  mesmo runner offline e terminou com 93 aprovados, incluindo aquele teste.
  Isso é consistente com uma falha transitória de acesso, mas a execução ampla
  ainda deve ser registrada literalmente como 918/1/1/1, não totalmente verde.
- Reexecução focada em 2026-11-04 do runner offline `--personal-http-auth`
  terminou com 235 aprovados em 81,49 s. O runner bloqueou rede externa,
  subprocessos e leitura de `.env`; permitiu somente os sockets locais exigidos
  pelos testes Flask. A tentativa anterior usando o alias `python` do Windows
  falhou antes de iniciar os testes; a execução aprovada usou o interpretador
  existente `.offline-envs/cq-ccxt-4.5.88/Scripts/python.exe`.
- Reexecução focada em 2026-11-04 do runner offline
  `--personal-execution-safety` terminou com 400 aprovados em 545,50 s. Essa
  seleção cobre preflight de execução pessoal, contenção de falha do stop
  inicial, cancelamento de entrada, sizing de stop após fill, gestão, contrato
  de escrita por cliente, leitura de stop, fechamento, validação numérica,
  posição, risco e rotas de autorização. O runner bloqueou rede, subprocessos
  e leitura de `.env`, com diretório temporário de dados.
- Testes locais não provam comportamento do release em Render, durabilidade do
  `/data`, integração de permissões nem prontidão de produção.
- O release validado ainda não é o release implantado. Deploy permanece
  condicionado à confirmação de custo incremental zero e a um plano para a
  interrupção possível do serviço com disco persistente.
- Plano para eventual promoção (nenhuma escrita executada): alvo único
  `srv-d8rtuv9o3t8c73ehav5g` (`central-robos-bingx`), branch Render
  `codex/personal-readiness-20261103`, atualmente em `598c4d4`. A candidata
  `29b505b` está publicada em `codex/personal-readiness-release-20261104`; para
  promovê-la seria necessário alterar a branch do serviço ou integrar a
  candidata à branch atualmente ligada e fazer deploy manual, pois auto-deploy
  está desligado. Antes disso verificar alvo/release, controles PAPER/DRY_RUN,
  configuração de rollback para `dep-dbl0g5rncjis73fhe8dg` e custo. O serviço
  usa plano Standard,
  uma instância e disco `/data` de 2 GB; segundo a documentação do Render, esse
  disco faz o deploy parar a instância atual antes de iniciar a nova, causando
  alguns segundos de indisponibilidade. O build consome minutos de pipeline;
  minutos suplementares podem ser comprados automaticamente após a franquia.
  Fontes: [Build Pipeline](https://render.com/docs/build-pipeline),
  [Persistent Disks](https://render.com/docs/disks) e
  [Render FAQ](https://render.com/docs/faq). A captura de uso compartilhada
  anteriormente é de 03/11 e não prova o saldo atual; não existe leitura de
  cobrança disponível na integração Render. Portanto o custo incremental zero
  permanece não confirmado, e push/deploy não serão feitos nesta etapa.
- Manter `ENABLE_REAL_TRADING=false`, `BROKER_DRY_RUN=true` e
  `FALCON_MODE=PAPER`. Nada nesta avaliação permite ativar LIVE ou enviar
  ordens reais.
