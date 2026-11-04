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
- Revalidação somente de leitura às 18:18–18:20 UTC de 2026-11-04: Render
  continua apontando `srv-d8rtuv9o3t8c73ehav5g` para
  `codex/personal-readiness-20261103`, com auto-deploy desligado. O deploy mais
  recente continua `dep-dbl0g5rncjis73fhe8dg`, commit
  `598c4d4505c3aec6d4de9a6b762cc1576f604374`, estado `live`. No GitHub, a
  branch acompanhada pelo Render avançou para `20ed76bdaab8f2efe9a18fa72dc6207875d8f6c1`,
  merge "Merge personal execution and Registry safety". A comparação dessa
  branch com a candidata `codex/personal-readiness-release-20261104`
  (`50eb62e6781b3c872caa83851988b6b0abbc39c8`) mostra a candidata 2 commits à
  frente e 1 atrás do merge base `29b505b`; os únicos arquivos diferentes são
  este relatório e um ajuste no harness de teste. Portanto, os arquivos de
  aplicação da correção de segurança já estão integrados à branch que o Render
  acompanha, mas ainda não estão no deploy ativo. A branch candidata está sem
  proteção, o endpoint de rulesets do repositório retornou lista vazia, e o
  fast-forward para `50eb62e` foi publicado e confirmado. Nenhuma variável de
  ambiente foi lida ou alterada.
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
- Repetição da seleção completa `--extra` no HEAD
  `ee0a53cb985e9e48a0547f01bb63084b6f47a2f5` terminou em 2026-11-04 com 919
  aprovados, 1 ignorado e 1 desmarcado em
  1.157,70 s. A falha transitória de leitura de `bots/falcon.py` não se repetiu.
  A execução usou `ccxt==4.5.88`, bloqueou rede externa, subprocessos e leitura
  de `.env`, permitiu somente os sockets locais exigidos pelos testes e usou
  diretório temporário de dados.
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
- Revalidação posterior, no mesmo código-fonte (HEAD `cc8b674` só acrescentou
  documentação depois do commit de testes `ee0a53c`): `--personal-http-auth`
  terminou com 235 aprovados em 95,14 s e `--personal-execution-safety` com
  400 aprovados em 599,73 s. O runner manteve rede externa, subprocessos e
  leitura de `.env` bloqueados, usando dados temporários. `git diff --check`
  permaneceu limpo.
- Consulta GitHub somente-leitura ao commit `20ed76b` não encontrou status de
  CI publicados. Isso não foi contado como aprovação de CI.
- Reconsulta Render somente-leitura confirmou novamente auto-deploy desligado,
  branch `codex/personal-readiness-20261103` e deploy `598c4d4` em `live`.
  A sessão do navegador não pôde ser ativada pela ferramenta e o conector não
  oferece leitura de billing; portanto franquia/custo incremental continuam
  sem confirmação e nenhum deploy foi disparado.
- Testes locais não provam comportamento do release em Render, durabilidade do
  `/data`, integração de permissões nem prontidão de produção.
- O código de segurança validado está integrado na branch seguida pelo Render
  (`20ed76b`), mas o release ativo continua em `598c4d4`. Deploy permanece
  condicionado à confirmação de custo incremental zero e a um plano para a
  interrupção possível do serviço com disco persistente.
- Plano para eventual promoção (nenhuma escrita de produção executada): alvo
  único `srv-d8rtuv9o3t8c73ehav5g` (`central-robos-bingx`), mantendo a branch
  Render `codex/personal-readiness-20261103`. O deploy manual usaria o HEAD
  integrado `20ed76b`; auto-deploy está desligado. Antes disso verificar
  novamente branch/commit, controles PAPER/DRY_RUN, configuração de rollback
  para `dep-dbl0g5rncjis73fhe8dg` e custo incremental zero. O serviço
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

## Revalidação local da conciliação de propriedade — 2026-11-04

- Revalidado antes da edição: branch `codex/personal-readiness-release-20261104`,
  HEAD `f33dae8404dbbd07287717b670148c9bd870ed8d`; a worktree estava limpa.
- Encontrado risco no `_mpa_v1_build_payload`: uma posição da corretora era
  classificada como `CENTRAL_LIVE_MATCHED` somente porque símbolo e lado
  coincidiam com alguma posição LIVE da Central. A resposta normalizada de
  posições do broker contém contrato/lado e quantidade, mas não inclui
  identidade de lifecycle/ordem que prove a origem; além disso, a exposição
  pode estar agregada. Igualdade de quantidade também não prova propriedade.
- Alteração local: posições do broker com candidato da Central agora são
  `POSITION_OWNERSHIP_UNVERIFIED`; nenhuma posição é anexada automaticamente.
  Elas permanecem no conjunto de divergências consumido pelo gate LIVE, de
  modo que novas entradas ficam bloqueadas até existir sinal de propriedade
  confiável. O relatório preserva o candidato da Central para investigação.
- Regressões adicionadas para coincidência exata de símbolo/lado/quantidade e
  para quantidade agregada diferente. Resultado no runner offline
  `--personal-execution-safety`: **402 passed in 601.78s**. O runner bloqueou
  rede externa, subprocessos e leitura de `.env`, usando persistência temporária.
  `git diff --check` passou. Esta evidência é local/sintética, não valida a
  resposta da conta nem a integração de produção.
- A alteração foi commitada localmente em `4b5c1c0`, mas não foi enviada nem
  implantada. A consequência conservadora é intencional: sem prova de origem,
  a conciliação não libera novas entradas LIVE, mesmo que símbolo, lado e
  quantidade coincidam.
- Reexecução em 2026-11-04 de `--personal-execution-safety`: **402 passed em
  845,40 s**, Python Windows 3.14.5, wheel local `ccxt==4.5.88` instalado
  somente em pasta temporária com `pip --no-index --no-deps`; SHA-256 do wheel:
  `3e37d626cf3245c547b76751a26a9119df9da28f1f80fbdb751586bfebf5f791`. O runner
  bloqueou rede externa, subprocessos e leitura de `.env`, usando persistência
  temporária. A coleta sem o wheel não passou porque `ccxt` estava ausente; a
  tentativa no WSL também parou antes dos testes por falta de Flask/pip. Não
  houve download nem alteração de dependências compartilhadas.
- Reexecução dedicada `--stop-readback` em 2026-11-04, com o mesmo wheel local
  temporário: **12 passed em 37,31 s**. A seleção isolada manteve a rede e os
  subprocessos bloqueados; nenhum acesso externo ou alteração persistente fora
  do temporário ocorreu.

## Regressão expandida e estado de publicação — 2026-11-04

- Após o commit local `4b5c1c0`, a suíte offline expandida
  `tests/run_falcon_pilot_minimal_offline.py --extra` terminou com **921 passed,
  1 skipped e 1 deselected em 979,22 s**. O runner bloqueou rede externa,
  subprocessos e leitura de `.env`, e usou persistência temporária. O caso
  marcado `deselected` não é contado como aprovado.
- Estado Render relido em 2026-11-04: serviço `central-robos-bingx`, ID
  `srv-d8rtuv9o3t8c73ehav5g`, segue a branch
  `codex/personal-readiness-20261103`, `autoDeploy=no`, plano Standard, uma
  instância e disco persistente `/data` de 2 GB. O deploy ativo permanece
  `dep-dbl0g5rncjis73fhe8dg`, commit `598c4d4505c3aec6d4de9a6b762cc1576f604374`.
  Nenhum deploy ou alteração no serviço ocorreu.
- GitHub, somente leitura, confirmou a branch candidata
  `codex/personal-readiness-release-20261104` no SHA
  `cc8b674e6d3597ccdfac96a15559773c42b99598`; esse SHA é ancestral direto do
  HEAD local `4b5c1c0`. Há três commits locais posteriores. Não existe diretório
  `.github/workflows` nessa branch. O push fast-forward foi tentado, mas o SSH
  empacotado no sandbox falhou ao iniciar (`NtCreateDirectoryObject ...
  0xC0000022`) antes de autenticar. Não foi usado force push, chave alternativa,
  nem ocorreu escrita remota. Publicação permanece pendente de um caminho de
  autenticação GitHub que funcione nesse ambiente ou ação manual do usuário.
- A ferramenta Render disponível não expõe billing. A captura compartilhada
  mostra o uso no momento da captura, mas não confirma o saldo/custo incremental
  atual de um build/deploy. Mesmo após publicar na branch candidata, o serviço
  Render não implanta automaticamente; eventual deploy continua condicionado
  à confirmação de custo zero e verificação de rollback.
- Verificação de produção estritamente read-only em 2026-11-04, sem enviar
  credenciais: `GET /healthz` respondeu **200** e `GET /healthz?detail=true`
  respondeu **401**. Isso confirma o health check público exato e que a variante
  com query não amplia a exceção de autenticação no deploy ativo. Nenhuma rota
  de trading foi chamada; não é uma validação completa de todas as rotas nem
  prova de configuração dos controles de execução.
- Reexecução da suíte dedicada `--personal-http-auth` no código local após a
  correção e documentação: **235 passed in 87,66s**. O runner bloqueou rede,
  subprocessos e leitura de `.env`, permitiu apenas os sockets locais Flask e
  redirecionou persistência para temporário. O resultado não substitui o GET
  read-only no serviço ativo e não prova todas as configurações de produção.
- Reexecução adicional em 2026-11-04 do mesmo comando, com Python Windows
  3.14.5: **235 passed in 99,91s**. O runner manteve rede, subprocessos e
  leitura de `.env` bloqueados, permitindo apenas sockets locais Flask e
  persistência temporária. Uma tentativa no Python do WSL (3.14.4) não chegou
  aos testes porque Flask não está instalado; não foi usado `pip` nem rede e
  nenhuma dependência foi alterada.
- A seleção específica de startup dormente C3, ausente de `--extra`, foi
  executada separadamente: `--c3-dormant-startup` terminou com **24 passed e
  3 subtests passed em 389,32s**. O runner isolado bloqueou rede e subprocessos.
  Isso confirma os contratos locais de não ativação no startup cobertos por
  esses testes; não demonstra que C3 distribuído seja necessário nem valida
  integração AWS/Render. Nenhuma escrita externa ocorreu.
- Com permissão de rede deste turno, um GET sem credenciais para a rota pública
  de leitura `/livestatus` respondeu **401**. O cliente descartou o corpo e
  imprimiu apenas o status. Isso é evidência read-only de que uma rota real de
  relatório está protegida no deploy ativo; não foi chamada nenhuma rota de
  ordem.
- Capturas do usuário em 2026-11-04, às 16:41–16:42 BRT, mostram uso de
  pipeline **0/1.000 min**, Starter selecionado com 1.000 minutos incluídos,
  limite de gasto de **US$ 5/mês**, e tráfego de saída 14,05/25 GB. Isso sustenta
  custo incremental zero para um build que permaneça na franquia disponível no
  momento da captura, sem upgrade ou compra de minutos; não garante custo zero
  se o saldo mudar ou o build exceder a franquia. O serviço web existente segue
  no plano Standard. Não houve deploy nem alteração de configuração.
- Revalidação Render somente de leitura em 2026-11-04: o alvo segue
  `srv-d8rtuv9o3t8c73ehav5g`, ligado à branch `codex/personal-readiness-20261103`,
  com auto-deploy desligado, uma instância e disco persistente `/data` de 2 GB.
  `healthCheckPath` está vazio; Render está usando a checagem TCP padrão, embora
  `GET /healthz` responda 200 no release ativo. Antes de um futuro deploy, é
  recomendável configurar `/healthz` como health check HTTP no serviço e
  confirmar que a rota permanece rápida e sem efeitos colaterais. Isso mede
  apenas liveness/readiness do processo, não prontidão de trading. O disco
  persistente implica interrupção durante a substituição da instância; não
  iniciar o deploy sem janela segura e confirmação de que não há operação em
  andamento. A integração Render disponível não expõe atualização desse campo.
- Estado de publicação na mesma revalidação: HEAD local
  `db009554f2ce4efaa92d7c39c833286bca23c9fc` está 11 commits à frente da branch
  remota, que continua em `cc8b674e6d3597ccdfac96a15559773c42b99598`. O push
  por HTTPS não conseguiu conectar ao GitHub mesmo após a concessão de rede ao
  ambiente; nenhum objeto/ref remoto foi alterado. Depois da publicação, o
  release pretendido deve ser escolhido por SHA em `Manual Deploy > Deploy a
  specific commit`, não `Deploy latest commit`, porque o serviço aponta para
  outra branch. Nenhum deploy foi iniciado.

## Revalidação adicional local e estado atual — 2026-11-04

- Revalidei branch, HEAD e status antes de qualquer edição: branch
  `codex/personal-readiness-release-20261104`, HEAD
  `2f3f7e79e75dd9e9794259a54cca906b9a2645db`, sem alterações locais; 13 commits
  à frente da referência remota observada.
- O `--personal-http-auth` foi reexecutado com o Python isolado já existente,
  overlay local do wheel CCXT 4.5.88 e o runner de isolamento do repositório:
  **235 passed em 148,92 s**. O runner bloqueou rede, subprocessos e leitura de
  `.env`, permitiu apenas os sockets locais necessários ao Flask e redirecionou
  persistência para temporário. Nenhuma dependência foi instalada ou alterada.
- A tentativa de checagem Linux atual não iniciou: `wsl -d Ubuntu` retornou
  `Wsl/E_ACCESSDENIED` antes de executar comandos. Portanto, esta rodada não
  acrescenta evidência Linux/WSL.
- GitHub somente leitura ainda mostra a branch remota em
  `cc8b674e6d3597ccdfac96a15559773c42b99598`; Render somente leitura ainda
  mostra o serviço na branch `codex/personal-readiness-20261103` e deploy ativo
  `598c4d4505c3aec6d4de9a6b762cc1576f604374`. Não houve push, deploy ou escrita
  em AWS/Render/produção.
- Auditoria do grafo local confirmou que o HEAD candidato descende do deploy
  ativo `598c4d4` e do ancestral `0ddc28a` da branch acompanhada pelo Render;
  portanto não é uma base de código alheia ao release atual. O delta candidato
  contém 20 arquivos (2.957 inserções, 145 remoções), incluindo autenticação e
  gates de segurança cobertos pelos testes locais. A implementação
  `trade_registry.py` não foi alterada; a mudança de `main.py` endurece a
  sincronização explícita do Registry e foi revisada sem executar a rota.
  Essa análise de ancestralidade e diff não substitui validação do runtime,
  configuração ou dados de produção.

## Autenticação pessoal sem segredo estático — 2026-11-04

- Antes de editar, revalidei branch `codex/personal-readiness-release-20261104`,
  HEAD `1f79896ed7221eb9d94ad2b53928f6760d5d4281` e worktree limpa. As únicas
  mudanças desta rodada são a autenticação local, os testes correspondentes e
  este registro; nenhuma alteração existente foi descartada.
- A autenticação candidata deixou de depender de
  `CENTRAL_PERSONAL_HTTP_USER`/`CENTRAL_PERSONAL_HTTP_PASSWORD`. O módulo gera
  uma chave aleatória apenas em memória no início do processo; deriva senhas
  Basic rotativas de dois minutos, aceita a janela anterior só para tolerar uma
  requisição que cruza a virada e nunca persiste ou imprime os valores. Os sete
  clientes internos continuam limitados ao hostname HTTPS exato do Render ou
  ao loopback/porta configurados. A validação global de rotas, rejeição
  cross-site e bloqueio de mutação via GET continuam em vigor.
- Limite residual: Basic ainda pode ser repetido por quem obtiver a senha
  durante sua curta janela de validade; TLS, escopo de host e ausência de
  exposição/log são necessários. O desenho presume o processo único atualmente
  descrito pela configuração Render (1 instância, `python main.py`); não prova
  comportamento após restart/execução real em produção. Rotas privadas não
  ficam utilizáveis diretamente pelo navegador sem uma sessão de operador; a
  rota pública `/healthz` permanece apenas liveness. Não foi criada uma sessão
  de navegador nem um serviço adicional.
- Validação isolada da autenticação: `python.exe -I
  tests/run_falcon_pilot_minimal_offline.py --personal-http-auth` — **238
  passed em 112,02 s** na execução final após remover a função redundante. O
  runner bloqueou rede/DNS, subprocessos e leitura de `.env`, permitiu apenas
  os sockets locais do Flask e usou diretório temporário para dados. Cobriu
  rotação/expiração, aceitação na virada, rejeição após expirar, hosts não
  confiáveis, gate real Flask e os sete chamadores.
- Regressões adjacentes: `python.exe -m unittest discover -s tests -p
  test_history_eventbus_smoke.py -v` — **13/13 passed**, com bloqueio de rede
  instalado por cada teste e persistência temporária; `python.exe -m pytest -q
  tests/test_trade_lifecycle_shadow_observability_http.py` — **25 passed em
  2,49 s**, com os patches de rede próprios desse módulo e `CENTRAL_AUTO_START_RUNTIME=false`.
  `py_compile` dos arquivos tocados e `git diff --check` também passaram.
- Uma tentativa de incluir a suíte `unittest` no runner pytest foi descartada:
  o pytest isolado falhou antes de executar aqueles testes por não ter a opção
  `trace` (plugin de depuração desativado). Os mesmos 13 testes foram então
  executados diretamente por `unittest` e passaram. Essa falha do harness não é
  contada como teste do produto.
- As capturas de Billing de 2026-11-04 mostram 0/1.000 minutos de pipeline
  consumidos, Starter, US$ 5/1.000 min com 1.000 min incluídos, limite mensal de
  US$ 5 e banda 14,05/25 GB. Isso não garante custo zero de um deploy específico.
  Esta ressalva substitui qualquer inferência anterior de que a franquia, por si
  só, comprovaria custo zero para o próximo deploy.
  O serviço Render segue com auto-deploy desligado, 1 instância e start command
  `python main.py`; nenhum ambiente foi alterado e nenhum deploy foi iniciado.
- O código validado foi salvo no commit local `5317daa`
  (`fix(auth): rotate personal runtime HTTP credentials`); o HEAD da worktree
  ficou `5317daa744e9240e385fc0768377c79992ddcc64`, 16 commits à frente da
  referência de rastreamento local. Não houve push nem deploy. A autenticação
  ainda não está integrada no Render. Os testes não demonstram configuração,
  disponibilidade ou comportamento no processo ativo, nem prontidão de trading.
