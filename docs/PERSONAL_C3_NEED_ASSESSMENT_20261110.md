# Avaliação da necessidade de C3 distribuído — uso pessoal (2026-11-10)

## Decisão

As evidências atuais **não justificam ativar nem ampliar o C3 distribuído no
caminho crítico** para a operação pessoal de uma pessoa e uma conta. Manter o
C3 existente preservado e dormente. A decisão é proporcional à topologia
observada e deve ser revista se a topologia mudar; não é uma aprovação de
prontidão de trading.

## Evidências observadas

- Render `central-robos-bingx`: um serviço web, uma instância Standard, comando
  de startup `python main.py`, disco persistente de 4 GB em `/data`,
  `autoDeploy=off`. Consulta somente de leitura em 2026-11-10 06:04 UTC.
- Reconsulta Render somente de leitura em 2026-11-10: deploy Live mais recente
  `4c2ff20db31584ab23f74a2f76073a02881fb90d` (`dep-dbphh9ff3r2c73865ebg`),
  uma instância, disco persistente de 4 GB em `/data`, `autoDeploy=off`.
  O branch configurado no serviço (`codex/personal-readiness-20261103`) difere
  do branch do release validado (`codex/personal-readiness-runtime-fix-20261110`);
  não muda o deploy atual com auto-deploy desligado, mas deve ser reconciliado
  antes de futuras publicações. `healthCheckPath` permanece vazio.
- Em produção, watchdogs continuavam marcando Trend PRO Elite, Donkey H4 e
  Meme Hunter como parados desde 2026-11-09 20:04 BRT. Portanto, o serviço não
  está operacionalmente pronto; disponibilidade HTTP e baixa CPU não explicam
  nem resolvem essa paralisação.
- `trade_registry.py` aponta o Registry para o diretório configurado, `/data`
  quando disponível, e declara um `threading.RLock` compartilhado (`_lock`). Os
  caminhos de leitura/gravação do módulo usam esse lock. O inventário estático
  documenta 8 writers nesse módulo e 11 em `main.py`; são callsites, não prova
  de 19 writers simultaneamente ativos.
- `main.py` usa `fcntl.flock` com arquivos de lock em `CENTRAL_DATA_DIR` para
  eleger líderes de loops/pollers quando há duplicação de processos. O comando
  configurado é um único `python main.py`, não um servidor configurado com
  múltiplos workers. A API de serviço reporta uma instância; inspeção manual
  anterior encontrou um processo Python com várias threads.
- Revalidação offline no HEAD `4c2ff20`: `--registry-writers` aprovou 60 testes;
  essa seleção verifica callsites de save/RMW, falhas, reload e concorrência
  sintética, não mede simultaneidade real em produção. `--c3-dormant-startup`
  aprovou 24 testes e 3 subtestes em 610,20 s, cobrindo atribuições/startup sem
  I/O e mantendo a instalação/gate C3 inativos nos cenários testados.
- A inicialização de coordenação C3 na fonte fica default-off/dormente. A
  verificação do preflight classifica a indisponibilidade do C3 como informativa
  para uma instância com disco persistente e lock local, e sugere reavaliar se
  houver múltiplos processos/instâncias ou outro backend.

## Comparação com a alternativa pessoal simples

Para a topologia atual, uma instância/um processo com Registry persistido em
`/data`, `RLock` no Registry e locks locais de processo nos loops fornece a
coordenação proporcional necessária, sem signer, autoridade remota, checkpoint
distribuído ou dependência adicional de cloud. O C3 acrescentaria componentes,
custos potenciais e modos de falha, sem evidência observada de segundo processo,
instância, serviço ou conta escrevendo o mesmo Registry.

Os 19 writers existentes justificam manter serialização local e testes de
concorrência; sozinhos não demonstram que um signer/lease distribuído seja
necessário. Os caminhos C3 existentes permanecem preservados e dormentes.

## Condições para reabrir a decisão

Reavaliar C3 se houver qualquer uma destas mudanças comprovadas: mais de uma
instância; mais de um processo/worker que escreva o Registry; um segundo serviço
ou operador com acesso de escrita ao mesmo armazenamento; migração do Registry
para backend compartilhado; ou evidência de que os locks locais não abrangem
todos os writers efetivamente ativos. Antes de ativar, cumprir integralmente os
gates de backup/restauração, âncora/assinatura, hashes, integração fail-closed,
writers inventariados, zero operações, lease/interlocks, kill switch,
recuperação, rollback e preflight recente.

## Limitações e estado

Esta é uma avaliação de arquitetura e configuração, não um ensaio de contenção
física em produção. As consultas Render foram somente leitura; nenhum secret foi
consultado; não houve mudança de controles de trading, restart, deploy ou ordem.
Os logs consultados após o deploy `4c2ff20` registraram tarefas bloqueadas por
`STATIC_OPERATIONAL_RUNTIME`, como relatório histórico, snapshot Redis grande e
auditoria pesada do Predator. Isso confirma suspensão deliberada, não a causa
raiz de scanners anteriormente observados como parados. Não desligar o gate sem
medir carga, latência, locks e impacto de escrita. Custo de futuras publicações
não está confirmado como zero; não publicar sem verificar custo e condições
operacionais atuais.

## Atualização local — reconciliação de signal_id (2026-11-21)

- No worktree candidato `cq-falcon-paper-missing-key-hotfix-20261121`, branch
  `codex/falcon-paper-missing-key-hotfix-20261121`, HEAD base `784a570`, o
  preview de reconciliação agora compara também `signal_id`, classificado
  explicitamente como `SIGNAL_ID_REVIEW_ONLY`. Sinal identifica o evento que
  originou a análise; não prova ordem, fill nem ciclo de vida de posição.
- Para identificadores de revisão, o matcher cruza os campos presentes nos
  dois snapshots; todos os campos em comum precisam concordar. Campos que só
  aparecem de um lado não são tratados como prova nem como conflito. A
  correspondência por signal continua estritamente review-only.
- Correspondência por `signal_id` nunca torna linha elegível para importação.
  IDs duplicados resultam em `AMBIGUOUS_SIGNAL_ID`; o relatório continua
  sanitizado e `all_rows_ineligible_for_import=true`.
- Evidência fornecida pelo operador antes desta alteração: duas linhas de
  origem tinham `signal_id`; os resultados sanitizados anteriores mostraram
  dois candidatos lógicos ambíguos. Não houve nova leitura de Upstash ou
  Registry nesta atualização, portanto não há resultado de match por
  `signal_id` para produção.
- Validação após a alteração: runner offline `--paper-registry-source-preview`
  aprovou 43 testes; `--paper-registry-source-capture` aprovou 20; `git diff
  --check` passou. A primeira tentativa da seleção ampliada
  `--personal-lifecycle-completeness` falhou na coleta porque o Python global
  não tinha `ccxt`. Foi reutilizado o ambiente offline já existente
  `cq-offline-ccxt-py314-20261106` (`ccxt 4.5.88`, `pytest 9.1.1`): a seleção
  terminou com 892 aprovados e 1 ignorado em 568,20 s. Nenhuma dependência foi
  baixada/instalada e o runner aplicou os bloqueios de rede.
- O candidato ainda não foi enviado nem publicado; a instância Render não foi
  alterada por esta atualização de código. Consulta Render MCP somente leitura
  em 2026-11-21 confirmou `bbd9511ffb425c3df7415283d69ed35ec84a2657` como Live,
  uma instância, plano Standard, disco persistente de 4 GB montado em `/data`,
  auto-deploy desligado e `healthCheckPath` vazio. O candidato local continua
  fora de produção. Métricas consultadas mostraram CPU aproximadamente
  29–42%, memória 0,83–0,91 GiB e amostras p95 HTTP 0,21–0,46 s no intervalo
  retornado; isso não valida a lógica PAPER.
- Logs recentes consultados incluíram erros de timeout de 10 s do Risk Manager
  para o serviço MEME (19–20/11/2026) e respostas HTTP 502 de probes públicos.
  Buscas sanitizadas por `FALCON_PAPER_PERSISTENCE_RECONCILIATION_REQUIRED`,
  `PAPER_STATE_FILES_MISSING` e `SOURCE_SNAPSHOT_INVALID` desde 18/11 não
  retornaram linhas; ausência desses textos nos logs não valida o estado do
  ledger nem a saúde do executor.
  Não houve leitura de secrets nem chamada à corretora. O serviço não foi
  alterado; controles runtime PAPER/REAL, estado do ledger e posições/ordens
  BingX não foram verificados nesta consulta.
- O latch de reconciliação continua fail-closed. A inspeção local encontrou
  escrita persistente e leitura fail-closed entre reinícios, mas nenhuma rotina
  explícita de liberação. Não apagar o latch manualmente nem criar ledgers
  vazios: primeiro é necessário um procedimento auditável após reconciliação
  comprovada.
- Uma captura somente leitura anteriormente fornecida pelo operador retornou
  `SOURCE_SNAPSHOT_INVALID` / `SOURCE_BOT_KEY_CONFLICT` para Falcon. A checagem
  sanitizada indicou dois rótulos `bot` fora do nome canônico, do `BOT_NAME`
  efetivo e do nome padrão do código. `BOT_NAME` pode ser sobrescrito no
  ambiente; não é seguro inferir nem adicionar alias para o valor desconhecido.
  Enquanto esse conflito não for explicado, o novo matching por `signal_id`
  não poderá produzir evidência operacional de reconciliação.
- O patch isolado foi transplantado sem reescrever histórico para o branch
  `codex/signal-id-preview-20261121`, sobre o Live `bbd9511`; commit local
  `71ba7a3d789b25aa09605ff383d71b82203ac16a`. Nesse branch passaram 43 testes
  de preview, 20 de captura e 892 da seleção ampliada (1 ignorado, 604,80 s).
  Isso torna `bbd9511` o rollback de código conhecido para esse patch. O branch
  permanece local, sem push ou deploy.
- Revisão adicional da autenticação no Live `bbd9511`: o gate global retorna
  503 se o usuário/senha não estiverem configurados; credenciais ausentes ou
  incorretas não liberam rotas. Apenas GET sem query para `/healthz` é isento
  do Basic Auth, com resposta mínima de liveness. Runner offline
  `--personal-http-auth`: 243 testes passaram. Não foram lidos valores de
  credenciais; a presença atual das variáveis no Render continua sem
  verificação, então a evidência local não comprova a configuração de runtime.

## Revalidação Linux offline de persistência e C3 — 2026-11-21

- Worktree `codex/signal-id-preview-20261121`, HEAD `16a748800844f48e475e442a353b8f1bde9b76c3`, limpo antes da atualização deste relatório; o runner foi executado no Ubuntu WSL2 com Python 3.14.4 e pytest 9.0.2, sem instalar dependências e com `PYTHONDONTWRITEBYTECODE=1`.
- `--paper-integrated-disk-guard`: 102 testes passaram e 12 subtestes passaram em 15,27 s. Diferentemente da execução Windows, os casos POSIX anteriormente ignorados rodaram, incluindo rejeição de symlink raiz/intermediário/relativo, ancoragem `dir_fd` durante troca de caminho, detecção de mount/device e replace atômico no diretório verificado.
- `--registry-writers`: 60 passaram em 8,55 s; `--registry-lock-audit`: 1 passou, 59 foram selecionados fora, em 7,44 s.
- `--c3-dormant-startup`: 24 testes e 3 subtestes passaram em 43,40 s. A conclusão permanece manter C3 distribuído preservado e dormente: a topologia Render observada é uma instância/um processo de start `python main.py`, e os locks locais conhecidos cobrem o caminho inventariado; isso não exclui writers externos desconhecidos nem constitui evidência para ativar C3.
- `--paper-registry-source-preview`: 43 passaram; `--paper-registry-source-capture`: 20 passaram no WSL. São fixtures/offline; nenhum snapshot do Upstash nem Registry de produção foi acessado.
- `--broker-paper-disk-guard`: 47 testes passaram em 2,97 s no venv Windows offline existente. Isso cobre o contrato testado do broker/PAPER, mas não a integração com a BingX nem uma execução de ordens.
- Revalidação WSL2: `--falcon-lifecycle-projection` passou 18; `--personal-position-read-fail-closed` passou 44 (1 ignorado); `--trading-mode-defaults` passou 9. A seleção `--personal-lifecycle-no-ccxt` não coletou três módulos porque falta `flask` na distro; sem instalação de dependências e sem rede.
- A tentativa histórica de `--personal-lifecycle-completeness` no WSL foi interrompida na coleta: a distro não tem `ccxt`/`flask`, e reutilizar o `site-packages` do venv Windows falha ao importar a extensão Windows de `cryptography` em Python Linux. Nenhum pacote foi instalado e a rede permaneceu bloqueada pelo runner. A reexecução Windows completa de 21/11 está registrada na seção posterior; não se afirma aprovação da seleção ampla em Linux.
- Esta validação é offline e usa filesystem temporário/sintético; não verifica o mount real `/data` no Render, estado ou latch PAPER de produção, variáveis de autenticação no runtime, fonte Upstash, nem posições/ordens atuais da BingX. Nesta rodada, só se consultou metadado/configuração do serviço Render em modo somente leitura; nenhum arquivo/registro do disco de produção, segredo ou estado da corretora foi lido ou escrito.

## Matriz de prontidão operacional — 2026-11-21

| Requisito | Evidência mais recente disponível | Estado |
|---|---|---|
| C3 distribuído | Render: uma instância e `python main.py`; `RLock`/`flock` locais conhecidos; suites offline writers, lock e startup dormente passaram no WSL. Writers fora do inventário continuam possíveis. | Não há necessidade concreta demonstrada; manter C3 dormente. |
| Persistência `/data` e estado PAPER | Guard local passou testes POSIX/WSL de symlink, mount/device, troca de caminho e replace ancorado. Último `paper_integrated_health` do operador, em 17/11, reportou `PAPER_STATE_FILES_MISSING`; não houve leitura posterior do Shell. | Código testado localmente; runtime/ledgers atuais não verificados. Não criar ledgers vazios. |
| Origem e identidade PAPER | Captura Upstash anterior retornou `SOURCE_SNAPSHOT_INVALID`/`SOURCE_BOT_KEY_CONFLICT`; dois rótulos Falcon eram desconhecidos. `signal_id` no candidato local é apenas identificador de revisão, nunca elegível para importação. | Reconciliação bloqueada; nenhuma importação ou descarte autorizado. |
| Autenticação HTTP | SHA Live `bbd9511` contém gate global e tem 243 testes offline aprovados. Os testes mostram fail-closed quando credenciais ausentes/incorretas; presença das variáveis no Render não foi confirmada recentemente. | Implementação presente; configuração/runtime não comprovados. |
| Controles de trading | Defaults e suíte offline validam comportamento fail-closed. Valores `ENABLE_REAL_TRADING=false`, `BROKER_DRY_RUN=true`, `FALCON_MODE=paper` foram reportados pelo operador em 17/11, não nesta rodada. | Manter esses valores; confirmação runtime atual pendente. |
| Conta BingX | Não foi feita conferência agregada atual de posições/ordens nesta rodada. | Estado desconhecido; não usar confirmações antigas para autorizar operação. |
| Fluxo entrada→fill→stop→gestão→fechamento→reconciliação | Suites offline cobrem contratos e falhas com mocks. Nenhuma evidência recente de ciclo integrado de produção ou teste de corretora foi obtida. | Não comprovado; não enviar ordens reais. |
| Release | Render continua Live no SHA `bbd9511`; branch local `codex/signal-id-preview-20261121` está em `16a7488`, sem push/deploy; auto-deploy desligado. | Release não corresponde ao candidato validado; não publicar sem decisão financeira específica se custo não for zero. |

Não repetir ainda o capture em Live: ele falha em `SOURCE_BOT_KEY_CONFLICT` antes de alcançar matching por `signal_id`, então a MGET autorizada provavelmente repetiria a falha conhecida. A ação manual útil é inspecionar privadamente, em Upstash Data Browser, somente os dois campos `bot` dos registros em `falcon:positions`, sem editar nem copiar os registros: comparar com o nome efetivo do Falcon configurado no serviço (o default no código local é `Falcon Strike ORB PRO`) e identificar se a divergência veio de versão/producer conhecido. Não envie os rótulos nem payloads aqui. Se a origem continuar desconhecida, mantenha ambos em quarentena; a autorização de uma MGET até US$ 0,01 permanece não consumida.

## Revalidação Windows offline e metadados Render — 2026-11-21

- Revalidei branch `codex/signal-id-preview-20261121` no HEAD `16a748800844f48e475e442a353b8f1bde9b76c3`; no início daquela etapa, o status já mostrava este relatório, `paper_registry_source_preview.py` e `tests/test_paper_registry_source_preview.py` modificados. As alterações de captura e seu teste foram acrescentadas depois, preservando os três arquivos existentes. `git diff --check` passou.
- Com Python 3.14.5 e `tests/run_falcon_pilot_minimal_offline.py` em modo isolado/rede bloqueada: PAPER disk guard 92 passaram, 10 foram pulados por dependência POSIX e 12 subtestes passaram; writers Registry 60 passaram; lock audit 1 passou (59 selecionados fora); C3 dormant startup 24 e 3 subtestes passaram; trading mode defaults 9 passaram; Falcon lifecycle projection 18 passaram. A seleção de startup C3 levou 356,98 s no Windows. Os resultados POSIX completos estão registrados na seção WSL acima; estes resultados Windows não os substituem.
- Render foi consultado apenas por metadados: serviço `central-robos-bingx`, Live em `bbd9511ffb425c3df7415283d69ed35ec84a2657`, uma instância, disco `/data` de 4 GB, auto-deploy desligado e health check vazio. Nenhuma consulta a Shell, disco, segredo, Upstash ou BingX foi feita por esta rodada.
- O diff local de `paper_registry_source_preview.py` contra o SHA Live confirma que o suporte de matching review-only por `signal_id` e aliases fixos de nomes de exibição são candidatos locais, não código atualmente publicado. O source capture já existente no Live pode produzir um snapshot agregado sanitizado, mas não inclui essas alterações; no erro observado, a validação de bot ocorre antes do matching.
- Nenhuma chamada de escrita externa, instalação, commit, push, deploy ou mudança de controles de trading ocorreu. A única ação manual pendente desta etapa é o operador executar uma vez o source capture no Render Shell com o token temporário Read-Only no prompt oculto e compartilhar somente o JSON sanitizado; a autorização de até US$ 0,01 permanece não consumida.

## Reauditoria estática do caminho C3 — 2026-11-21

- A composição em `main.py` constrói o coordenador com `enabled=False` e instala a fronteira de recuperação também default-off. Na implementação do coordenador, `mutation()` com `enabled=False` emite `COORDINATOR_DEFAULT_OFF_PASSTHROUGH` sem adquirir backend de lock compartilhado ou lease; portanto os contextos C3 não são proteção ativa de escrita no runtime atual.
- A serialização efetiva inventariada é local: `trade_registry.py` define um `threading.RLock` e os writers o usam; `_trpsf_v1_registry_lock()` em `main.py` retorna precisamente esse mesmo objeto, que os 11 callsites registrados adquirem junto dos contextos C3. `acquire_runtime_file_lock()` usa `flock` em `/data` para eleição de loops/processos, não substitui o lock do Registry.
- Evidência de necessidade: o Render observado tem uma instância e inicia `python main.py`; a arquitetura declarada é uma conta/operador e um disco persistente. Os 19 itens são callsites canônicos e sua cobertura estrutural passa os testes, não evidência de 19 processos concorrentes. Não apareceu evidência concreta de segundo processo/serviço writer ou backend Registry compartilhado.
- Decisão: preservar os componentes C3, mas não habilitá-los nem tratá-los como caminho crítico necessário para este escopo pessoal. Os locks locais são proporcionais à topologia observada. Limite: sessões de Shell, processos auxiliares ou writers fora do inventário podem alterar o Registry; isso não foi medido em produção. Se surgir tal writer concorrente, reabrir o inventário e verificar primeiro se um lock local compartilhado entre processos basta antes de considerar coordenação distribuída.

## Revalidação lifecycle offline — 2026-11-21

- No mesmo worktree/HEAD, `python -I tests/run_falcon_pilot_minimal_offline.py --personal-lifecycle-no-ccxt` completou com 766 testes aprovados e 1 ignorado em 628,50 s. A rede permaneceu bloqueada pelo runner. `ccxt` não está instalado neste Python 3.14.5; nenhum pacote foi instalado.
- Em seguida, reutilizei a cópia local compatível de `ccxt` já existente em `cq-lifecycle-offline-1324a6b316044c7f89eaffdce58d1610\Lib\site-packages`, sem instalação, e executei `--personal-lifecycle-completeness` pelo mesmo runner isolado: 892 passaram e 1 foi ignorado em 565,98 s. Portanto, a suíte ampla local está agora aprovada no Windows; a rede permaneceu bloqueada.
- O êxito completo melhora cobertura de regressão com mocks, mas não verifica deploy, `/data` de produção, credenciais, Upstash real, execução/fill/stop na BingX ou operação contínua. A prontidão de integração em produção continua sem comprovação.

## Revalidação fail-closed de leitura pessoal — 2026-11-21

- `python -I tests/run_falcon_pilot_minimal_offline.py --personal-position-read-fail-closed`: 44 passaram e 1 foi ignorado; runner isolado/rede bloqueada.
- A execução inicial de `--broker-paper-disk-guard` com o Python base não coletou porque `ccxt` não está instalado nele. Em seguida, reutilizei sem alterações a cópia completa já existente em `cq-lifecycle-offline-1324a6b316044c7f89eaffdce58d1610\Lib\site-packages`, adicionando essa pasta somente ao `sys.path` do processo isolado; `47` testes passaram em `2,42 s`. Não houve instalação nem rede.
- `python -I tests/run_falcon_pilot_minimal_offline.py --personal-http-auth`: 243 passaram em 73,98 s. É evidência da lógica local; não verifica se os segredos necessários estão configurados no serviço Live, e nenhum valor de credencial foi lido.
- Cobertura adversarial adicional em `tests/test_paper_registry_source_preview.py`: (a) `signal_id` único com `execution_mode` divergente continua `SIGNAL_ID_REVIEW_ONLY`, reporta `MODE_CONFLICT`, não é importável nem expõe IDs; (b) nomes de exibição fixos de Falcon/Turtle normalizam para as chaves corretas, continuando review-only. `--paper-registry-source-preview`: 46 passaram em 0,31 s; `--paper-registry-source-capture`: 20 passaram em 0,26 s. Rótulos desconhecidos continuam rejeitados.
- Limite crítico: a nova normalização resolve apenas nomes de exibição fixos presentes no código. Os dois rótulos Falcon classificados anteriormente como desconhecidos seguem sem explicação; nenhum alias foi criado para eles, e `signal_id` não prova lifecycle, fill ou ownership executado.

## Inspeção estática do loop de comandos Falcon — 2026-11-21

- `rg` no repositório encontrou apenas a definição de `commands_loop()` em `bots/falcon.py`; não há chamador Python ativo. O startup inicia scanner, management, summary e watchdog, e mantém a thread de comandos comentada para evitar conflito `getUpdates` (próximo ao bloco de inicialização Falcon).
- A função, se chamada futuramente, não valida `chat_id` contra `FALCON_CHAT_ID`/lista autorizada antes de responder a `/health`, `/posicoes` e outros comandos. Além disso, `/reset_falcon_all` apaga posições, sinais, trades, eventos e funil no Redis, embora não apareça na resposta de `/comandos`. Isso é um risco latente de autorização/destruição, não um caminho atualmente alcançável pelo startup inventariado.
- Não foi enviada mensagem Telegram, consultado token nem alterado Redis. Ações futuras para reativar esse loop devem primeiro adicionar autorização de chat fail-closed e exigir confirmação explícita para reset destrutivo; testar chat ausente/errado/autorizado, comando oculto e ausência de qualquer escrita em chamadas não autorizadas.

## Diagnóstico sanitizado de snapshot PAPER inválido — 2026-11-21

- No worktree `codex/signal-id-preview-20261121`, o capturador recebeu uma melhoria local para incluir contagens estruturais fixas por bot quando o preview estrito falha: registros totais, campos `bot` presentes/ausentes, correspondência canônica/nome de exibição conhecido/label não reconhecido, aliases de bot conflitantes e presença de campos de identidade permitidos. Nenhum valor de bot, identificador, locator, status arbitrário ou payload é retornado.
- Isso é diagnóstico somente: o resultado continua `ok=false`, `SOURCE_SNAPSHOT_INVALID`, `all_rows_ineligible_for_import=true` e `writes_performed=false`; não altera critérios de matching nem torna `signal_id` elegível para importação.
- `--paper-registry-source-capture`: 21 passaram; `--paper-registry-source-preview`: 46 passaram; a suíte de persistência executada nesta rodada no Windows: 92 passaram, 10 POSIX ignorados e 12 subtestes aprovados. O runner bloqueia rede. `git diff --check` passou.
- O capturador e os aliases adicionais continuam somente locais, no HEAD `16a748800844f48e475e442a353b8f1bde9b76c3`; não foram enviados ao GitHub nem publicados no Render. O diagnóstico não resolve a origem real dos dois registros Falcon nem prova identidade de posição/fill/lifecycle.

## Confirmação de metadados do serviço — 2026-11-21

- Render MCP, workspace Central Quant `tea-d8gnnuojo6nc73ep3lg0`: `central-robos-bingx` (`srv-d8rtuv9o3t8c73ehav5g`) segue Live no deploy `dep-dbuha6oae00c73ei09kg`, commit `bbd9511ffb425c3df7415283d69ed35ec84a2657`; branch configurada `codex/personal-readiness-20261103`, auto-deploy `off`, uma instância, plano Standard, disco persistente `/data` 4 GB, `healthCheckPath` vazio, allowlist pública `0.0.0.0/0`.
- Foi consultada somente configuração/metadado; nenhum log, ambiente, Shell, disco, credencial, Upstash ou BingX foi acessado. O código local mantém autenticação HTTP Basic global, exceto a rota mínima `/healthz`; a validação local não prova que os segredos estejam configurados no runtime.
- A documentação oficial atual confirma que `healthCheckPath` vazio usa probe TCP; configurar caminho HTTP num web service é configuração separada. Um deploy específico com disco persistente não tem garantia de zero downtime, e o build consome minutos de pipeline. Como saldo/custo zero não foi verificado e o candidato local está sujo e difere do SHA Live, nenhuma publicação foi tentada.
- Não há ferramenta Shell no Render MCP desta sessão. Para verificar os valores atuais de PAPER e a saúde real dos ledgers será necessária leitura manual sanitizada do usuário; a última evidência manual de `PAPER_STATE_FILES_MISSING` é de 17/11 e está desatualizada.

## Revalidação read-only e offline — 2026-11-21 (continuação)

- Worktree revalidado antes da documentação: branch `codex/signal-id-preview-20261121`, HEAD `579e3e15655ff453f15281afbc4c4eb26852db8c`, sem alterações locais. Nenhum arquivo de produção, credencial, segredo, corretora ou Upstash foi acessado por comando nesta rodada.
- Render MCP somente leitura confirmou `central-robos-bingx` Live em `bbd9511ffb425c3df7415283d69ed35ec84a2657` (`dep-dbuha6oae00c73ei09kg`), uma instância Standard, start command `python main.py`, disco persistente de 4 GB em `/data`, `autoDeploy=off`, `healthCheckPath` vazio e allowlist `0.0.0.0/0`. O candidato local `579e3e1` não é o release Live. Nenhum deploy, push, alteração de ambiente ou custo externo foi iniciado.
- Inventário estático atual mantém os 8 writers de `trade_registry.py` e 11 callsites de `main.py`. A composição C3 em `main.py` continua com `enabled=False`; os instaladores informam `runtime_activation_allowed=False`. O serviço observado tem uma instância e executa um processo Python de entrada; os 19 callsites não demonstram concorrência distribuída. Decisão: preservar C3, mantê-lo dormente e usar os locks locais existentes; reavaliar apenas se aparecer writer concorrente comprovado fora desse domínio.
- Runner `tests/run_falcon_pilot_minimal_offline.py` executado com Python isolado, sem instalar dependências e com a rede bloqueada pelo runner: `--registry-writers` 60 passou; `--paper-integrated-disk-guard` no Windows 92 passou, 10 foram ignorados por dependerem de POSIX, 12 subtestes passaram; `--paper-registry-source-preview` 46 passou; `--paper-registry-source-capture` 21 passou; `--c3-dormant-startup` 24 passou e 3 subtestes passaram. O startup C3 levou 469,22 s sob execução paralela. Na mesma versão/HEAD, a seleção PAPER de disco foi repetida em WSL2/Linux: 102 passou, 12 subtestes passaram em 19,22 s, incluindo a cobertura POSIX de symlinks, troca de diretório ancorado e replace atômico. Esses resultados são offline/sintéticos e não validam o mount `/data` real nem estado de produção.
- Nova evidência visual fornecida pelo operador no Upstash Data Browser mostra `falcon:positions` como string JSON de 2 caracteres com valor `{}` na captura de 21/11/2026. Isso prova apenas que essa chave estava vazia naquele instante. O arquivo colado anteriormente continha quatro linhas `OPEN`/`PAPER` com label `Falcon Strike`; a captura vazia não estabelece quando nem de qual chave vieram aquelas linhas. A origem permanece desconhecida; não importar, descartar, recriar nem tratar essas linhas como posições atuais.
- Estado de prontidão continua incompleto: não houve nesta rodada Shell/health atual do Render, leitura dos arquivos/latch PAPER em `/data`, verificação atual dos controles runtime, nem conferência agregada atual de posições e ordens BingX. Não se conclui segurança operacional contínua a partir do Live, dos testes locais ou do snapshot Redis vazio. Não criar ledgers vazios nem liberar latch; manter `ENABLE_REAL_TRADING=false`, `BROKER_DRY_RUN=true` e `FALCON_MODE=PAPER`.

## Revalidação de autenticação e defaults — 2026-11-21 (continuação)

- Revisão do objeto Git do SHA Live `bbd9511ffb425c3df7415283d69ed35ec84a2657`, sem buscar a rede ou ler configuração/secrets: `main.py` aplica autenticação antes das rotas; só `GET /healthz` sem query pode ser isento, e apenas para liveness. O runtime-readiness hook responde 503 até `CENTRAL_RUNTIME_READY`; outro hook recusa métodos GET com parâmetros de mutação. Isso valida a lógica versionada, não comprova que usuário/senha estejam configurados no ambiente Render atual nem que o serviço esteja pronto para trading.
- No HEAD local `579e3e1`, o runner offline passou `--personal-http-auth` (243), `--personal-position-read-fail-closed` (44; 1 ignorado) e `--trading-mode-defaults` (9). Não houve chamada à corretora, consulta de credenciais, instalação ou acesso à rede.

## Auditoria adicional do I/O PAPER e leitor JSONL — 2026-11-21

- No worktree `codex/signal-id-preview-20261121`, HEAD-base `579e3e15655ff453f15281afbc4c4eb26852db8c`, a revisão local encontrou acessos diretos não guardados em `main.py`: Outcome Evaluator V1, Adaptive Weight Engine V1/V2, Learning Engine V1 e a criação inicial de `CENTRAL_DATA_DIR`. Nesta continuação também foram migrados os helpers genéricos de decisão/timeline/snapshot-sombra, runtime stability, Strategy Evolution, Trade Lifecycle Manager, armazenamento PRG da console, disaster-stop fallback e snapshot/eventos de Registry Persistence. Os JSONL revisados usam cauda limitada a 6 MiB, descriptor-anchored em `/data` no POSIX, descartando linha final incompleta.
- A leitura foi adicionada sem alterar o contrato de “arquivo PAPER integrado ausente”: `paper_integrated_health` segue reportando arquivos ausentes até evidência nova; esta mudança não cria nem importa posições/ledgers. A criação do diretório central agora usa `ensure_paper_data_dir`, que valida mount e symlinks no caminho Render.
- Testes reproduzíveis, runner offline/rede bloqueada: `--paper-integrated-disk-guard` no Windows: 96 passou, 10 ignorados por exigir POSIX e 12 subtestes passaram; WSL2: 106 passou e 12 subtestes passaram. `--registry-writers`: 60 passou; `--personal-http-auth`: 243 passou; `--personal-position-read-fail-closed`: 44 passou e 1 ignorado. `git diff --check` passou.
- Após acrescentar a asserção estática do bootstrap e revisar o leitor, os dois módulos diretamente afetados passaram juntos: 15 testes, 8 ignorados por requerer POSIX, em 67,86 s; essa chamada direcionada não usa rede nem fixture de produção.
- Limites: isso é evidência local/sintética; não foi feito deploy nem leitura de `/data`, Shell, Upstash, segredo ou BingX. O SHA Live conhecido continua sendo `bbd9511` conforme a consulta somente de metadados anterior; não se comprovou que estas alterações estejam em produção. A varredura de `main.py` ainda mostra acessos diretos a arquivos centrais em componentes como TrendPro Daily Summary, auto-execution bridge/watchdog, pilot cooldown, auditorias de fechamento/piloto, execution-attempt audit, memory snapshot, Falcon Live audit e preflight/auditoria de stop. Essas rotas precisam de análise/guard próprio; a cobertura completa de todo I/O do processo permanece incompleta e não se deve inferir prontidão.
- Próximo avanço de reconciliação continua manual e somente leitura: a captura anterior do Upstash falhou com `SOURCE_BOT_KEY_CONFLICT`; o screenshot de 21/11 mostra `falcon:positions` como `{}` naquele instante, o que não estabelece a origem/horário do anexo com registros. Manter os registros fora de importação e não inicializar ledgers até a origem e identidade de execução serem comprovadas.

## Proveniência do anexo de registros Falcon — 2026-11-21

- Inspecionei o arquivo anexado somente para metadados e campos de origem/tempo, sem exibir payloads ou IDs: são 2 registros, ambos com `bot=Falcon Strike` e `created_at` `16/11/2026 12:17` e `16/11/2026 12:45`; não há fuso declarado. Não há campo `source`, `writer`, `module`, `process` nem literal de chave Redis no arquivo.
- A cópia local do anexo tem 7.263 bytes e timestamps NTFS de criação/modificação `2026-11-18 22:18:41 UTC`; isso data a cópia/anexo, não o evento de origem. O screenshot do Data Browser mostra o valor atual de `falcon:positions` como `{}`; não apresenta histórico nem horário da última escrita. Portanto, não está provado que os dois registros vieram dessa chave, nem qual processo os gravou.
- O código local de `bots/falcon.py` define `POSITIONS_KEY = "falcon:positions"`; `save_positions()` escreve esse dicionário via `redis_set_json`. Chamadas de persistência aparecem na aceitação de sinal, nos loops de gestão e na reconciliação/remoção. Há também `/reset_falcon_all` escrevendo `{}` diretamente, mas a auditoria estática anterior não encontrou chamador ativo de `commands_loop()` no startup. Isso prova que a versão local conhece escritores compatíveis, não que o deploy que gerou o anexo os usou.
- A única verificação manual que ainda pode ajudar é consultar Render Logs em torno de 16/11 às 12:17 e 12:45 (fuso local do serviço e janela equivalente em UTC) e procurar mensagens de startup/persistência Falcon. Se os logs não registrarem a chave ou o writer, a proveniência histórica não é recuperável apenas pelo valor atual do Redis; manter os registros sem importação/inicialização.

## Continuação: sidecars adicionais sob o guard `/data` — 2026-11-21

- A revisão do diff confirmou que o patch anterior já havia migrado os sidecars do Auto Real Execution Bridge e do Real Position Watchdog; nesta etapa também foram migrados os leitores/escritores de Pilot Cooldown, Real Close Auto Evaluator e Real Pilot Dashboard para as primitivas guardadas. Escritas JSON mantêm a serialização compatível (`default=str`); eventos JSONL usam append guardado e leituras de cauda limitadas a 6 MiB.
- Acrescentei teste AST para exigir leitores e escritores guardados nesses cinco grupos e impedir I/O direto nos helpers auditados. Runner offline/rede bloqueada `--paper-integrated-disk-guard`: Windows, 97 passaram, 10 ignorados por depender de POSIX e 12 subtestes passaram em 15,34 s; WSL2, 107 passaram e 12 subtestes passaram em 20,31 s. `git diff --check` passou nesta revisão.
- A varredura estática ainda mostra I/O direto em componentes adicionais de `/data`, incluindo TrendPro Daily Summary, Telegram Notifier, Execution Attempt Audit, Memory Diet snapshots, Falcon Live Audit, Broker Disaster Stop Payload Preview e Falcon Real Pilot Preflight Checklist. Alguns são apenas telemetria/auditoria, mas não os considero cobertos; precisam de triagem individual antes de alegar cobertura completa. A lista não inclui operações genéricas de `/proc`, histórico diário ou locks, que têm finalidade distinta.
- As mudanças continuam apenas no worktree local sujo; não houve commit, push, deploy, acesso a segredo, alteração de ambiente, Upstash, BingX ou `/data` de produção. O SHA Live conhecido é histórico e não foi revalidado nesta etapa. Os testes demonstram as primitivas em fixtures, não a situação runtime do serviço.
- A ação manual para a proveniência do anexo permanece a mesma: em Render → `central-robos-bingx` → Logs, selecionar 16/11/2026 ao redor de 12:17 e 12:45 no fuso exibido e buscar termos Falcon/persistência. Se o painel estiver em UTC, converter as janelas pelo fuso mostrado; o horário do arquivo não informa timezone. Não copiar linhas com segredos nem payloads. Se não houver logs que registrem produtor/chave, a origem não poderá ser concluída pelos dados atuais; manter os dois registros em quarentena e não inicializar o ledger.

## Continuação: checks de existência do Registry e regressão — 2026-11-21

- Removi consultas diretas `.exists()`/`.resolve()` dos checks do Registry ativo, prontidão Falcon, preview de bootstrap e seleção de fontes legadas; as verificações de arquivo usam `paper_file_exists`, e a deduplicação de candidatos usa caminho absoluto lexical sem seguir symlinks. Isso não executa bootstrap nem altera/importa dados.
- Acrescentei uma asserção AST para manter esses checks sob o guard. Validação final neste checkout, runner offline que bloqueia rede e usa dados temporários: `--paper-integrated-disk-guard` **98 passed, 10 skipped (POSIX-only), 12 subtests passed**; `--registry-writers` **60 passed**; `--personal-position-read-fail-closed` **44 passed, 1 skipped**; `--personal-http-auth` **243 passed**; `git diff --check` passou.
- Os testes de filesystem POSIX (symlink, device/mount e `dir_fd`) continuam sem execução nesta máquina Windows nesta rodada; o resultado Linux/WSL anterior não foi repetido depois das últimas alterações. A cobertura do I/O total também não está completa e o runtime de produção não foi revalidado.
- Nenhum deploy, push, leitura de produção, Upstash, credencial, BingX ou alteração de controles ocorreu. O último screenshot disponível mostra somente `falcon:positions={}` no instante capturado; a ação manual opcional para origem histórica continua sendo buscar no Render Logs em 16/11 perto de 12:17 e 12:45 (confirmando fuso), e compartilhar apenas linhas sanitizadas que identifiquem writer/chave. Se não houver esse log, a origem segue não comprovada.

## Continuação: sidecars e Registry pelo guard central — 2026-11-21

- Ampliei a migração do I/O central para TrendPro Daily Summary, Real Execution Telegram Notifier, Execution Attempt Audit, Broker Disaster Stop Payload Preview, Falcon Real Pilot Preflight, Falcon Live Execution Audit, Falcon Live Order snapshots, reconciliação central-only, Predator Auto Closed Sync, Registry Closed Reconciliation, Memory Diet snapshots e leitor do Executive Alert log. JSON preserva `default=str` quando já usado; JSONL fica limitado a caudas de 6 MiB ou ao limite anterior mais estrito.
- O writer do adaptador de Registry (`_trpsf_v1_atomic_write_json`) agora delega ao writer descriptor-anchored em `/data`; o leitor usa o guard para caminhos centrais e recusa fallback efêmero no Render. Não executei bootstrap/merge/importação. A composição no startup ainda chama o status de persistência com `read_only=True, no_io=True`; a rota explícita com `force` não foi acionada.
- Testes offline e sem rede após essas mudanças: `--registry-writers` 60 passaram; `--paper-integrated-disk-guard` no Windows 98 passaram, 10 ignorados por exigir POSIX e 12 subtestes passaram; WSL2 108 passaram e 12 subtestes passaram; `--personal-http-auth` 243 passaram; `--personal-position-read-fail-closed` 45 passaram; `git diff --check` passou.
- Ainda não é auditoria exaustiva de todo I/O de `main.py`/`trade_registry.py`. Permanecem caminhos de histórico diário, leitura de código-fonte de bots, `/proc`/flock, indicadores `exists` em diagnósticos de auditoria do broker e I/O próprio do módulo `trade_registry.py`; a segurança deste último depende do adaptador ser instalado antes de qualquer caller de load/save. A ordem de import/startup e callers anteriores ao patch continuam como itens de revisão. Não substituir chamadas por regex sem mapear semântica.
- Tudo permanece local e não commitado; não houve push/deploy, leitura de produção, Upstash, credenciais, segredos ou BingX. A proveniência dos registros anexados continua sem evidência histórica; o ledger PAPER integrado permanece ausente conforme a última leitura manual. Não mudar controles PAPER/LIVE nem inicializar ledgers.

## Continuação da auditoria de I/O de histórico — 2026-11-21

- `history_manager.py` agora escolhe `CENTRAL_DATA_DIR` antes de `DATA_DIR`; a inicialização básica valida o diretório via guard; criação de arquivos de histórico, append JSONL, contagem/leitura JSONL e leitura/escrita JSON passam pelos helpers de `paper_state_storage`. O JSON usa replace atômico no mesmo diretório. Isso não inicializa os ledgers específicos do executor PAPER (`paper_integrated_positions.json` / `paper_integrated_seen.json`) e não reconcilia registros.
- Testes offline com rede bloqueada: `--history-memory-state-io`: 53 passaram, 2 ignorados, 1 deselecionado; `--paper-integrated-disk-guard`: 100 passaram, 11 ignorados e 12 subtestes; `py_compile` nos módulos alterados e `git diff --check` passaram.
- A cobertura do `history_manager.py` segue incompleta: scanners/rotinas de rotação, índice de trades fechados, backup/reparo e alguns acessos diretos permanecem fora deste guard. Não executei rotação, reparo ou qualquer escrita de histórico de produção. O restante do repositório ainda contém outros callsites diretos que exigem inventário antes de qualquer alegação de cobertura total.
- Nenhum acesso a Render/Upstash/BingX, segredo, deploy ou push ocorreu. O screenshot de `falcon:positions={}` só demonstra o valor observado naquele instante; não prova quem gravou os dois registros anexados nem quando. A origem segue sem comprovação e a reconciliação/importação continua bloqueada.

## Continuação: guard do Registry-base e revalidação C3 — 2026-11-21

- O próprio `trade_registry.py` agora usa `paper_state_storage` para verificar diretórios/arquivos, ler e gravar atomicamente, sem depender do adaptador instalado por `main.py`. `load_registry`, `load_registry_read_only` e `load_registry_raw_read_only` falham fechados se falta o arquivo no caminho classificado persistente; os leitores read-only não criam Registry vazio nesse caso. A normalização `default=str` e o lock local foram preservados. Não houve bootstrap nem execução com Registry de produção.
- Em `history_manager.py`, o índice de trades fechados passou a usar stat/open/write guardados; os previews de rotação agora validam e leem arquivos pelo guard. A serialização JSON mantém `default=str`. Isso ainda não cobre as rotinas explícitas de commit/rotação/rebuild/backfill: elas contêm escritas diretas e podem reescrever arquivos em massa; não foram executadas e continuam bloqueadas para uma auditoria transacional separada.

### Continuação — bloqueio fail-closed das reescritas de histórico no Render

- Como a rotação/rebuild ainda usavam temporários e `os.replace` por pathname (sem transação ancorada em `dir_fd`), acrescentei um bloqueio antecipado em `history_manager.py` para as rotinas de rotação normal/emergencial, rebuild completo de `closed_trades` e backfill forçado. Em `RENDER=true`, elas retornam `BLOCKED_STORAGE_GUARD_REQUIRED` antes de preview/leitura/escrita; caminhos que resolvem para `/data` também são bloqueados sem depender da variável de plataforma.
- O backfill incremental (`force=False`) continua permitido: não trunca nem substitui o arquivo e seu append segue pelo writer guardado. O teste registra essa distinção.
- Novo teste `tests/test_history_rewrite_render_block_v1.py` verifica bloqueio antes de I/O, preservação byte-a-byte dos arquivos e que o backfill incremental não fica indevidamente bloqueado. Nenhuma rotina de manutenção foi executada contra `/data` ou produção.
- Limite: isto desabilita as operações de reescrita no Render em vez de afirmar que já estão seguras; a alternativa futura é implementar e testar transação streaming ancorada por descritor. Também não resolve o ledger integrado ausente nem a proveniência dos registros Upstash.
- Na mesma revisão do inventário de `main.py`, corrigi mais dois callsites concretos do Registry Storage Fix: o append de evento de bootstrap agora usa `_append_central_paper_audit_event`, e o fsync de diretório delega a `fsync_paper_directory`. O teste AST exige que o bootstrap use o append guardado e não tenha `open()` direto; o teste de durabilidade verifica a delegação. Não executei bootstrap.
- Validação local após essas mudanças: runner offline com rede/subprocesso bloqueados, `--history-memory-state-io`: 110 passou, 2 ignorados, 1 desmarcado em 156,49 s; `--history-render-rewrite-guard`: 5 passou; `--central-runtime-lock-guard`: 8 passou; `--paper-main-storage-guard`: 7 passou em 138,15 s. `tests/test_trade_registry_atomic_durable_write_v1.py`: 13 passou em 95,82 s. A seleção offline mais ampla `--paper-integrated-disk-guard`, executada antes da última alteração do lock, marcou 100 passou, 11 ignorados, 12 subtestes passou; o modo focado de lock valida a alteração posterior. `py_compile` e `git diff --check` passaram depois das alterações de código.
- Ainda há trabalho: inventário de I/O central completo e cobertura de entrada/fill/posição/stop/fechamento/reconciliação não foram concluídos; o código não foi publicado; origem dos registros Upstash e ledger PAPER integrado continuam sem evidência; nenhum estado da BingX foi consultado nesta rodada. C3 segue dormente e não foi ativado.
- O leitor de eventos do Auto Real Execution Bridge também fazia `os.open(path)` direto no seu arquivo central. Agora ele abre via `_open_guarded_paper_binary` quando o destino está dentro de `CENTRAL_DATA_DIR` e falha fechado em Render se o caminho centralizado não estiver disponível; o algoritmo de tail/count e sua semântica foram preservados. O teste offline `--arb-tail-storage-guard` passou 23 testes, incluindo comprovação de que o ramo central não chama `os.open` por pathname. Essa mudança local não ativa execução real.
- O gate offline `--paper-main-storage-guard` foi repetido após adicionar a asserção AST para esse leitor: 7 passou em 190,15 s. `py_compile` e `git diff --check` passaram após o patch. O inventário do processo ainda não está completo; os parsers de tail por pathname restantes foram classificados como fallback não-Render/local ou seguem pendentes de triagem por callsite.
- Regressões offline com rede bloqueada: `--registry-writers`: 73 passaram; `--registry-atomic-storage`: 13 passaram; `--history-memory-state-io`: 110 passaram, 2 ignorados e 1 deselecionado antes do último ajuste de serialização; após esse ajuste, o teste focado `--history-storage-serialization`: 1 passou e 45 foram deselecionados; `--c3-dormant-startup-verbose`: 24 passaram e 3 subtestes passaram. `--paper-integrated-disk-guard` no Windows: 100 passaram, 11 ignorados e 12 subtestes; `py_compile` e `git diff --check` passaram.
- A auditoria de todo o repositório ainda não está completa: manutenção destrutiva de histórico, outros módulos legados e alguns arquivos de código-fonte/locks permanecem fora do guard central; cada caminho precisa ser classificado antes de uma conclusão global. O conjunto C3 continua default-off e sem evidência de concorrência distribuída que justifique ativação.
- Alterações permanecem locais no branch `codex/signal-id-preview-20261121`, HEAD `579e3e15655ff453f15281afbc4c4eb26852db8c`, com trabalho não commitado preservado. Nenhum push/deploy, custo externo, leitura de produção, segredo, Upstash ou BingX ocorreu. Não foi verificado se logs históricos atribuem o writer dos dois registros Falcon; `{}` na chave atual não prova proveniência. PAPER integrado segue sem ledger e sem reconciliação comprovada.

## Revalidação offline e evidência manual de Logs — 2026-11-21

- No mesmo worktree/HEAD, reexecutei com Python isolado: `--paper-main-storage-guard` (8 passou em 200,26 s), `--data-status-lock-guard` (1 passou, 7 deselecionados em 24,54 s), `--paper-integrated-disk-guard` (109 passou, 11 ignorados, 12 subtestes em 280,58 s), `--registry-writers` (73 passou em 182,13 s) e `--c3-dormant-startup` (24 passou, 3 subtestes em 405,56 s). `py_compile` dos módulos críticos e `git diff --check` passaram. São testes locais/offline; não validam runtime de produção.
- As novas capturas do Render Logs usam filtro `FALCON`, intervalo 15–17/11/2026 e fuso GMT-3. Elas mostram inicialização/carregamento do Falcon em 15/11 e notificações bloqueadas `SIGNAL_PAPER` em 16/11 às 12:20:34 e 12:50:34, além de `PAPER_TRADE_CLOSED` às 06:15:31. O anexo tem horários `created_at` 12:17 e 12:45 sem fuso. A proximidade temporal é apenas correlação: as linhas são notificações de sinal/fechamento, não registram `SET` da chave Redis nem identificam a rotina que persistiu o conteúdo.
- `bots/falcon.py` no checkout local define `POSITIONS_KEY="falcon:positions"`; `save_positions()` persiste por `redis_set_json` e é chamada na sincronização de sinal, gestão e reconciliação/remoção. O snapshot Upstash `{}` não contém timestamp/histórico. Logo, a chave é compatível com um writer local, mas origem e horário exatos dos registros do anexo continuam sem prova; não importar, inicializar ou descartar registros.
- C3 permanece dormente: o teste de startup passou offline e a inspeção local não prova necessidade de coordenação distribuída. A topologia/configuração atual do Render, estado atual de `/data`, variáveis runtime, conta BingX e paridade do release continuam sem revalidação nesta rodada.

## Busca adicional de logs e guard de módulos de política — 2026-11-21

- A nova captura do Render Logs usa o filtro literal `FALCON15` no intervalo visível de 15–17/11/2026 (GMT-3) e retorna “No matching logs”. Isso é evidência negativa limitada à consulta e retenção/intervalo exibidos; não identifica a chave Redis, processo escritor ou horário da criação do anexo. O filtro anterior `FALCON` mostrou inicialização e notificações PAPER, mas nenhuma linha de gravação Redis. Proveniência segue inconclusiva.
- Migrei oito módulos locais de alerta, EventBus e políticas para resolver armazenamento por `paper_state_storage` e usar helpers guardados para checagem, leitura, append e escrita JSON. Adicionei `tests/test_policy_persistent_storage_guard_v1.py` e a seleção offline `--policy-storage-guard`. Os testes não inicializam nem alteram ledgers de produção.
- A primeira execução combinada encontrou três respostas HTTP 503 porque o novo gate de prontidão global estava falso nos testes de rotas. Corrigi apenas o fixture local de `tests/test_history_eventbus_smoke.py` para simular runtime já pronto; produção mantém o gate fail-closed. A seleção final passou: `27 passed in 2.02s`. `py_compile` dos oito módulos e testes alterados, mais `git diff --check`, passaram.
- Limites: validação local sintética, sem deploy, push, chamada externa ou leitura de estado atual. A auditoria estática não prova por si só cobertura global de I/O PAPER; outros callsites diretos de `main.py` e componentes legados permanecem pendentes. Não criar ledgers vazios nem importar os registros sem identidade/proveniência forte. O estado de `/data`, flags atuais e posições/ordens da BingX não foram revalidados nesta rodada.

## Guard adicional para Journal, Learning e Context — 2026-11-21

- A varredura de I/O identificou `journal_manager.py` e `learning_engine.py` gravando/lendo seus sidecars via `Path.open`, além de criação de diretório no import; `context_manager.py` também criava o diretório no import. Migrei os três para resolver o diretório pelo `paper_state_storage`; Journal e Learning agora usam os helpers compartilhados para leitura, append e escrita atômica. O leitor limitado de lifecycle abre seu arquivo via `open_paper_binary`, preservando a leitura por blocos e o snapshot EOF.
- Os testes de lifecycle foram ajustados para fixar `CENTRAL_DATA_DIR` no `tmp_path` e interceptar a nova abstração `open_paper_binary`; isso impede que testes dependam do ambiente do host e mantém o teste de append concorrente.
- Runner offline com rede/subprocesso bloqueados: `--journal-learning-storage-guard` passou 71 testes em 214,89 s; `--policy-storage-guard` passou 28 em 4,93 s. `py_compile` dos módulos/testes alterados e `git diff --check` passaram.
- A busca estática confirma que esses três módulos não mantêm chamadas diretas a `open`, `Path.open/read_text/write_text/mkdir/touch` ou `os.open/replace` para estado. Isto não cobre todo o processo: continuam callsites de leitura de arquivos de estratégia/configuração em bots e rotinas de histórico/snapshot em `main.py` que exigem classificação específica. Sem estado atual de Render/BingX e sem reconciliação de identidade dos registros, a prontidão contínua permanece não comprovada. Nenhum deploy, push, secret, Upstash ou BingX foi acessado nesta etapa.

## Fallback do snapshot diário no Render — 2026-11-21

- A revisão dos callsites restantes em `main.py` mostrou que `save_daily_snapshot()` e `build_history_report()` mantinham ramos locais com `open`/`glob` quando o diretório não fosse reconhecido como centralizado. Embora a configuração Render escolha `CENTRAL_DATA_DIR / "daily_history"`, um caminho divergente poderia cair no fallback efêmero.
- Agora, em `RENDER=true`, `save_daily_snapshot()` falha antes de montar o payload se `DAILY_HISTORY_DIR` não estiver sob o diretório central verificado; o relatório retorna mensagem de indisponibilidade em vez de procurar dados locais. O comportamento local fora do Render permanece.
- `--paper-main-storage-guard` passou 9 testes em 196,88 s, incluindo prova de que o cenário Render com caminho não centralizado não cria arquivo; `py_compile` e `git diff --check` passaram. Isso cobre apenas os caminhos diários testados, não toda a I/O do processo.
- Nenhuma chamada externa, leitura de `/data` de produção, alteração de controles, push ou deploy foi feita. Permanecem pendentes os outros callsites, a reconciliação de origem/identidade PAPER e as evidências operacionais atuais de Render e BingX.

## Regressões offline de execução, stop e fechamento — 2026-11-21

- O Python padrão deste checkout não tem `ccxt`; localizei e reutilizei um venv já existente, sem instalar dependências nem acessar rede. O runner `tests/run_falcon_pilot_minimal_offline.py` impõe as barreiras offline antes da coleta.
- No venv Python 3.11.9 / `ccxt 4.5.90`, passaram `--initial-stop-cancel` (85 testes), `--close-reconciliation` (110) e `--stop-readback` (12). Essas seleções cobrem cenários sintéticos de preenchimento/tamanho e falha de stop inicial, reconciliação de fechamento e contrato de leitura do stop; não comprovam comportamento de produção.
- O `requirements.txt` deste checkout fixa `ccxt==4.5.88`, diferente do 4.5.90 disponível no venv. A validação com a versão exata fixada permanece pendente; não tentei instalar ou baixar pacote.
- A varredura das chamadas `open()` dos bots restantes aponta leitores de watchlists configuráveis (`*_WATCHLIST_FILE` / `watchlists/*.json`), não leitores/escritores dos ledgers de posição. Não alterei esses leitores nesta etapa; eles não comprovam persistência PAPER e têm cobertura operacional separada.
- Nenhuma chamada externa, segredo, alteração de controle, commit, push ou deploy ocorreu. Estado atual de conta, `/data` e paridade do release não foram consultados.

## Continuação: presença PAPER usando descriptor guard — 2026-11-21

- A revisão encontrou checks de presença com `Path.is_file()`/`.exists()` em `paper_state_storage.read_paper_positions_state()` e no relatório de `execution_pipeline_status.py`. O conteúdo já era lido pelos helpers guardados, mas os metadados de presença não usavam a mesma checagem ancorada e resistente a symlink. Substituí esses checks por `paper_file_exists()`; erros de presença no resumo de outcome agora retornam status fail-closed, e a presença de adaptive weights fica desconhecida se a guarda falhar.
- Acrescentei testes de regressão para presença ausente e erro de symlink no resumo do pipeline. Com venv local existente Python 3.11 / `ccxt 4.5.90`, `pytest` focado aprovou 18 testes com 9 ignorados por depender de POSIX e os testes adjacentes de executor/lifecycle/outcome aprovaram 68, 2 ignorados e 12 subtestes. O runner offline/rede/subprocesso bloqueados `--paper-main-storage-guard` passou 9 testes em 20,18 s. Não houve instalação nem chamada de rede.
- Render MCP somente leitura confirmou `central-robos-bingx` com `autoDeploy=no`; o deploy mais recente retornado continua Live em `bbd9511ffb425c3df7415283d69ed35ec84a2657`. Métrica de `instance_count` mostrou 1 por amostra ao longo das últimas 24 horas UTC. Isso reforça que não há necessidade observada de C3 distribuído para a topologia atual, mas não prova ausência de processos auxiliares, sessões Shell ou writers externos.
- As capturas fornecidas mostram ausência de correspondência para `FALCON15` apenas no intervalo 15–17/11 GMT-3; outra busca mostra sinais `BTCUSDT` bloqueados pelo limite Central/PAPER `3/3` e concentração `70,1%`. Isto prova bloqueio de sinal naquele log, não existência/ausência atual de ordens ou posições. O estado BingX e os arquivos `/data` não foram consultados nesta continuação.
- Em WSL2, os testes POSIX focados (`paper_state_storage`, resolução do executor, idempotência e outcome) passaram: 91 testes e 12 subtestes. O runner agregado `--paper-integrated-disk-guard` executou os casos de filesystem, mas terminou com 123 aprovados, 12 subtestes e 1 falha ambiental porque um teste de `main.py` importa Flask, ausente na distro; não instalei dependências. O gate `--paper-main-storage-guard` passou no Windows com o runner offline (9 testes). `py_compile` e `git diff --check` passaram.
- Branch `codex/signal-id-preview-20261121`, HEAD `579e3e15655ff453f15281afbc4c4eb26852db8c`; todas as alterações permanecem locais e não commitadas. A cobertura total de I/O de `main.py` e módulos legados, runtime `/data`, ledger/reconciliação PAPER e integração de corretora continuam incompletos; nenhum deploy/push, segredo, mudança de ambiente, Upstash ou BingX foi acessado.

## Continuação: revisão da autenticação HTTP pública — 2026-11-21

- Revisei o gate global em `main.py`: todas as rotas do app Central, inclusive paths inexistentes/aliases, passam por Basic Auth fail-closed; `/healthz` só fica isento em `GET` sem query e retorna liveness mínimo. O hook também bloqueia contexto cross-site/origin inválido; outro hook exige POST para intents mutáveis via GET, e um terceiro nega qualquer rota antes da prontidão completa do runtime.
- Os módulos dos bots definem apps Flask próprios, mas seu `app.run()` está sob `if __name__ == "__main__"`; o loader do Central importa com `CENTRAL_DEFER_BOT_STARTUP=1` e inicia workers pelo Central. Portanto as rotas dos apps dos bots não são listeners adicionais no caminho normal `python main.py` verificado no Render. Isso não substitui uma auditoria da configuração do servidor/processo em runtime.
- Runner offline/rede bloqueada `--personal-http-auth`: 243 testes passaram em 25,22 s. O módulo `personal_http_auth.py` e os trechos de auth de `main.py` não diferem do commit `bbd9511`, confirmado pelo Render MCP como Live; isso estabelece paridade do código de auth, não a presença atual das variáveis de ambiente.
- Nenhum valor de credencial foi lido. A presença de `CENTRAL_PERSONAL_HTTP_USER` e `CENTRAL_PERSONAL_HTTP_PASSWORD` no Render não foi revalidada nesta rodada; confirmação manual anterior é histórica. Sem essa confirmação atual, não concluo autenticação configurada em produção, embora o fallback aleatório por processo continue fail-closed para acesso externo.

## Continuação: fixture dos leitores protegidos e regressão completa — 2026-11-21

- A suíte `--personal-lifecycle-completeness` revelou que a fixture AST de forensics compilava leitores de `main.py` sem fornecer os aliases `_paper_file_exists` e `_read_guarded_paper_text` usados pelo módulo real. Corrigi a fixture para injetar as primitivas reais de `paper_state_storage`; não substituí nem contornei os guards.
- A leitura limitada de snapshot agora traduz `PAPER_FILE_SIZE_LIMIT_EXCEEDED` para o código sanitizado esperado `<SOURCE>_TOO_LARGE`, preservando limite e recusa de leitura excedente. Teste focado: `tests/test_falcon_disaster_stop_failure_forensics_v1.py` — 283 passaram. Suíte offline com rede bloqueada: `--personal-lifecycle-completeness` — 892 passaram, 1 ignorado em 232,20 s. `git diff --check` passou.
- Essa evidência é exclusivamente de regressão local/offline; não comprova execução de ordens/fills, reconciliação, runtime `/data`, estado BingX ou paridade do release completo. Nenhum deploy, push, acesso a segredo ou leitura/escrita de produção ocorreu nesta etapa.

## Continuação: revalidação C3 no checkout atual — 2026-11-21

- A implementação atual cria o coordenador com configuração padrão desabilitada; o wrapper dos writers retorna `COORDINATOR_DEFAULT_OFF_PASSTHROUGH` sem lock compartilhado. A ativação controlada não está conectada ao `main.py`, exige autoridade/interlock não instalados e falha fechada por padrão. C3 permanece preservado, mas fora do caminho crítico de coordenação distribuída.
- Runner offline/rede bloqueada no HEAD local `579e3e15655ff453f15281afbc4c4eb26852db8c`: `--c3-dormant-startup` — 24 passaram e 3 subtestes; `--registry-writers` — 73 passaram. Isso valida contratos e concorrência sintética, não a completude dos writers em produção.
- A observação Render somente leitura disponível nesta continuação reporta uma instância e o serviço `central-robos-bingx` em `bbd9511ffb425c3df7415283d69ed35ec84a2657`, com auto-deploy desligado. Não foram consultados Shell, Registry, `/data`, Upstash ou BingX; portanto não há prova de ausência de processo externo, estado atual de posições ou paridade das mudanças locais.

## Guard de leitura do shadow PAPER e evidência de logs — 2026-11-21

- A inspeção local encontrou mais dois leitores ativos do estado shadow: `trade_lifecycle_shadow_observability.py` (health/eventos/divergências) e `trade_timeline_validator.py` (rota de evidência da timeline). Ambos faziam abertura direta por `Path.open`; a observabilidade também ignorava `DATA_DIR` no fallback e resolvia o caminho antes do guard, o que podia apagar a evidência lexical de symlink intermediário.
- Alinhei a resolução com `CENTRAL_DATA_DIR`/`DATA_DIR`, preservei o path lexical até o guard, e passei metadados/leitura para `paper_file_stat`, `open_paper_binary` e `open_paper_text`. Fontes ausentes continuam distintas de arquivos inválidos; falhas de mount/path retornam indisponibilidade em vez de produzir uma leitura vazia confiável.
- Validação Windows: `pytest` dos módulos shadow, timeline, storage e manager — 411 passaram, 4 ignorados; `py_compile` e `git diff --check` passaram. Validação POSIX/WSL do núcleo sem Flask — 390 passaram; uma tentativa anterior incluindo o teste HTTP parou na coleta por `ModuleNotFoundError: flask`, sem instalar dependências. Runner offline `--paper-integrated-disk-guard` terminou com 116 passaram, 13 ignorados e 12 subtestes. Parte do runner terminou antes do último patch no validador; o conjunto focado Windows/WSL foi executado depois.
- Os anexos do Render mostram: filtro `FALCON15` sem resultados no intervalo exibido; notificações PAPER bloqueadas por política; e Smart Predator PAPER bloqueado por limite de exposição `3/3`/concentração. Isso não comprova criação ou fechamento de posição LIVE, gravação na chave Upstash, integridade dos ledgers, nem ausência atual de ordens.
- Limite restante importante: `trade_lifecycle_shadow_bridge.py` contém escritores/leitores/remoção diretos, mas não há referência de importação no `main.py` nem nos componentes ativos consultados; permanece classificado como caminho legado/dormente até auditoria de callers mais ampla. `startup_disk_forensics.py` coleta metadados de disco e nomes, sem ler conteúdo dos ledgers. O inventário global de todos os I/Os PAPER e a validação de execução Render permanecem incompletos.
- Mudanças somente locais no branch `codex/signal-id-preview-20261121`, HEAD `579e3e15655ff453f15281afbc4c4eb26852db8c`; arquivos não relacionados e alterações prévias foram preservados. Nenhum acesso a produção, credenciais, Upstash, BingX, push ou deploy ocorreu. Não inicializei/importei ledgers, não alterei controles REAL/PAPER e não ativei C3.

## Guard dos logs de execução do Broker — 2026-11-21

- A busca estática encontrou que os logs centrais de execução e auditoria do Broker ainda usavam `mkdir`/`Path.open`/`read_text` diretamente. Esses arquivos são consumidos pelas rotas de auditoria/reconciliação; um fallback para `daily_history` podia apontar para armazenamento efêmero local no Render.
- Os dois writers agora usam `append_paper_text`; o leitor de JSONL usa o tail reader limitado e guardado. Em Render, os fallbacks legados fora de `/data` são omitidos; caminhos primários inválidos falham fechados e o writer retorna `False`, sem tentar criar arquivo efêmero.
- Novo teste `tests/test_broker_execution_log_storage_guard_v1.py`; seleção offline dedicada `--broker-log-storage-guard`: Windows 4 passaram/1 ignorado e POSIX/WSL 5 passaram. O teste POSIX prova rejeição de caminho temporário com `RENDER=true`; o teste de AST impede I/O direto nesses três callsites. `py_compile` e `git diff --check` passaram.
- A auditoria restante continua ampla: `decision_identity_store.py` contém I/O direto, porém o store V2.7A.2 está explicitamente `None` no runtime e só é injetado em testes; `trade_lifecycle_shadow_bridge.py` não tem caller ativo encontrado. Há ainda I/O direto em `main.py`, `history_manager.py`, timeline index/maintenance e outros módulos que exigem classificação e correções individualizadas. Não alego cobertura global.
- Todas as mudanças seguem locais, sem produção/rede/credenciais, sem iniciar seeds, sem alterar `/data` e sem ativar C3/LIVE. Próxima validação ainda necessária: suíte mais ampla de regressão do Broker com dependências do projeto disponíveis; o Python global/WSL desta máquina não tem `ccxt`, e não instalei pacotes.

## Guard de leitura do Registry V2 PAPER — 2026-11-21

- A trilha adicional pelo Turtle encontrou que `registry_v2_wal.py` já usa os openers `paper_state_storage`, mas `registry_v2_reader.py` e o fallback de `_load_snapshot_or_empty` em `registry_v2_core.py` abriam o snapshot diretamente. O adaptador de runtime do Turtle valida storage, mas esse acesso ainda deixava a leitura final vulnerável a symlink/TOCTOU.
- O reader e o fallback core agora usam `open_paper_text`; a presença do snapshot passa por `paper_file_exists`. A seleção `--registry-v2-paper-storage-guard` executa reader/core/adapter/integration com os limites offline: Windows 280 passaram/1 ignorado, POSIX/WSL 281 passaram. A recusa de caminho fora de `/data` com `RENDER=true` foi exercitada em WSL; nenhum snapshot de produção foi lido ou escrito.
- Resta confirmar no runtime se `REGISTRY_V2_PAPER_WRITE_ENABLED` está realmente desligado e se o adaptador tem storage configurado; não consultei ambiente. As rotas Turtle podem estar carregadas, então “módulo dormant” não deve ser usado para dispensar auditoria do adapter. Os writers V2 continuam validados pelo WAL e por storage explícito; não houve bootstrap/migração de Registry.

## Revalidação de release, autenticação e guards — 2026-11-21

- Render MCP somente leitura: `central-robos-bingx` está Live em `bbd9511ffb425c3df7415283d69ed35ec84a2657` desde 18/11; plano Standard, uma instância, disco persistente de 4 GB em `/data`, auto-deploy desligado, branch configurada `codex/personal-readiness-20261103`, `healthCheckPath` vazio e allowlist de rede `0.0.0.0/0`. Não consultei variáveis/segredos, Shell, logs de aplicação, Registry, `/data`, Upstash ou BingX.
- O código de autenticação HTTP do commit Live contém os hooks `central_personal_http_auth_before_request` e `central_personal_http_runtime_readiness_before_request`; o teste offline dedicado no checkout passou (`243 passed`). Isso valida o código, não a presença atual das variáveis de autenticação nem uma requisição anônima ao serviço.
- O Live é ancestral do checkout local `579e3e15655ff453f15281afbc4c4eb26852db8c`. Há alterações rastreadas e arquivos novos não commitados; auto-deploy está desligado e a branch local diverge da branch configurada no Render. Logo, o Live não representa as mudanças locais ainda não publicadas.
- Regressão offline ampla do checkout atual: `--personal-lifecycle-completeness` terminou com `892 passed, 1 skipped` em 927,26 s; o runner bloqueia rede, subprocessos e `.env` antes de carregar pytest. O conjunto focado de storage terminou com `252 passed, 15 skipped`. `git diff --check` passou após os testes.
- Limite C3: a seleção combinada de source-anchor/startup/recovery teve `4 failed, 19 errors`; a comparação estática local encontrou divergência nos 19 spans hard-coded do contrato já no `HEAD` (11 em `main.py`, 8 em `trade_registry.py`). Não atualizei anchors nem autorizei runtime C3; isso exige identificar a fonte canônica e validar hashes/autoridade antes de mudar o contrato. Para uso pessoal, a topologia observada de uma instância, junto aos locks locais, não apresenta evidência concreta que justifique coordenação distribuída no caminho crítico; C3 permanece dormente.
- Não revalidei o estado atual do executor PAPER, `/data` ou BingX. As últimas evidências fornecidas pelo operador eram históricas e apontavam ledgers PAPER ausentes e snapshot Upstash de origem/identidade não comprovada. Não criar arquivos vazios, importar registros, publicar ou alterar controles com base nisso. Sem custo de deploy comprovado e com alterações locais não commitadas, nenhum push/deploy foi feito.

## Triagem dos callsites restantes — 2026-11-21

- Revisei os I/Os diretos encontrados por busca em `main.py`, `paper_executor_integrated.py`, `paper_lifecycle.py`, `outcome_evaluator.py`, `registry_v2_*`, `decision_identity_store.py`, `trade_lifecycle_shadow_bridge.py` e bots carregados. Os acessos do executor/lifecycle/outcome/Registry V2 passam pelos helpers centrais de `paper_state_storage`; nos caminhos genéricos de `main.py`, os leitores/escritores centrais escolhem o guard `/data` e recusam fallback para arquivo local quando `RENDER=true`.
- Os `open()` remanescentes em `bots/{falcon,turtle,donkey,cobra,meme,trendpro,predator}.py` localizados nessa busca são leitores de configuração/watchlist, não ledgers de posição. O `os.open()` no leitor de evidência física aplica `O_NOFOLLOW`; o ramo de arquivos centrais usa `_open_guarded_paper_binary` e falha fechado em Render quando o guard não está disponível.
- `decision_identity_store.py` é importado pelo código, mas o `DECISION_IDENTITY_RECORD_STORE` do `main.py` permanece `None`; a única setter observada está explicitamente limitada a testes. Portanto os métodos de disco do store não são um writer ativo do runtime configurado nesta fonte.
- `trade_lifecycle_shadow_bridge.py` mantém I/O direto, porém uma busca de referências em `main.py`, `execution_engine.py` e `trade_lifecycle_manager.py` não encontrou caller. Classificação: caminho aparentemente legado/dormente, ainda não prova que nenhum import indireto ou invocação operacional exista.
- Isto é triagem estática direcionada, não inventário exaustivo de todos os acessos do repositório nem validação de chamadas em produção. Os guards locais foram revalidados pelos `252 passed, 15 skipped` focados e pelos `892 passed, 1 skipped` do runner amplo offline; nenhum arquivo real de `/data` foi aberto por esses testes.

## Revalidação do startup C3 e writers — 2026-11-21

- Reexecutei no mesmo HEAD `579e3e15655ff453f15281afbc4c4eb26852db8c` pelo runner offline, com bloqueio de rede/subprocessos: `--c3-dormant-startup` terminou `24 passed, 3 subtests passed`; `--registry-writers` terminou `73 passed`. Isso confirma startup default-off e regressão sintética dos writers no checkout atual; não é evidência de coordenação distribuída em produção.
- A leitura Render do serviço continua apontando `bbd9511ffb425c3df7415283d69ed35ec84a2657` como Live (último deploy listado em 18/11), auto-deploy desligado e uma instância. Não houve mudança externa, leitura de dados de trading, push ou deploy nesta revalidação.
- C3 permanece dormente. A divergência dos 19 source spans no contrato permanece um bloqueio para qualquer trabalho de instalação/ativação C3, mas não é razão para ativar um coordenador distribuído sem necessidade demonstrada. Continuação de prontidão ainda depende de estado PAPER e reconciliação de origem/identidade atuais, além da verificação operacional da conta.

## Cobertura estática do gate HTTP público — 2026-11-21

- Comparei por blocos de função os hooks de autenticação/readiness e o helper de credenciais entre o checkout atual e o commit Live `bbd9511`; os oito blocos comparados são idênticos. O gate global `before_request` registra antes das rotas do app Central, exige Basic Auth configurado para as demais rotas e bloqueia métodos/flags GET de mutação.
- A única exceção sem Basic Auth observada é `GET /healthz` sem query string. A resposta é um JSON mínimo de liveness; verificações de `Origin`/`Referer` e `Sec-Fetch-Site` ocorrem antes da exceção, e o gate de readiness pode retornar 503 até o runtime estar pronto.
- As sete aplicações Flask internas dos bots têm `app.run()` apenas em blocos `if __name__ == "__main__"`; o loader Central define `CENTRAL_DEFER_BOT_STARTUP=1` antes do import. Não encontrei listeners alternativos no caminho normal de `python main.py` no código local.
- Limite: isto é equivalência estática dos hooks e inspeção de configuração/código. Não fiz requisição anônima ao serviço, não confirmei a presença atual das variáveis de autenticação, nem testei navegador, proxy ou configuração do Render em runtime. O serviço permanece em allowlist pública `0.0.0.0/0`, então a autenticação da aplicação é essencial.

## Reexecução focada e novas capturas — 2026-11-21

- No checkout `579e3e15655ff453f15281afbc4c4eb26852db8c`, reexecutei o runner offline: `--paper-main-storage-guard` terminou `9 passed` em 177,40 s; `--registry-writers`, `73 passed` em 136,87 s; `--c3-dormant-startup`, `24 passed, 3 subtests passed` em 468,45 s. `git diff --check` passou. São testes locais/sintéticos; não demonstram integração de produção nem justificam ativar C3.
- Reexecutei também, com Python isolado e rede bloqueada, `--paper-registry-source-preview` (`46 passed` em 0,30 s) e `--paper-registry-source-capture` (`21 passed` em 0,27 s). Os casos continuam classificando `signal_id` como review-only e rejeitando snapshot inválido; nenhuma leitura de produção foi feita.
- A captura Render com filtro literal `FALCON15` não encontra correspondências entre 15/11 00:00 e 17/11 12:24 GMT-3. As outras capturas mostram o Falcon carregado e notificações PAPER bloqueadas por `LIVE_ONLY_POLICY`; logs BTCUSDT mostram o Smart Predator bloqueado pelo limite Central/PAPER (3/3, concentração 70,1%). Isso não confirma posição/ordem, execução PAPER ou atividade atual; a janela é histórica.
- Recontagem estática do contrato canônico: 19 superfícies lógicas (8 em `trade_registry.py`, 11 em `main.py`). Não são 19 processos. As contagens textuais de `save_registry()` (10 ocorrências em cada arquivo) não substituem o inventário, pois parte dos writers usa APIs de abertura/fechamento do Registry. A topologia pessoal observada não apresentou necessidade concreta de coordenação C3 distribuída; o contrato C3 existente permanece preservado e dormente.
- Nenhuma configuração, segredo, ledger, conta BingX ou serviço Render foi alterado/consultado nesta reexecução. Estado PAPER e conta real continuam sem evidência atual nesta etapa; reconciliação e prontidão operacional seguem pendentes.

## I/O residual de histórico e busca estática ampliada — 2026-11-21

- Uma busca ampliada dos callsites encontrou escritas pathname-based restantes em `history_manager.py` (`rebuild_closed_trades_v4_from_events` e `backfill_closed_trades_from_events(force=True)`). Ambas verificam `_history_rewrite_blocked_on_render()` antes de ler/truncar; no Render, o retorno é fail-closed porque `RENDER=true` ou o alvo está/resolve sob `/data`. `--history-render-rewrite-guard` passou `5` testes: os casos de rebuild/force não alteram bytes nem criam backups/staging; o caminho incremental (`force=False`) permanece disponível e usa os helpers de I/O guardados.
- Os acessos genéricos restantes em `main.py` passam pelos adapters `_append_jsonl`, `_read_jsonl_tail`, `_read_json_file` e `_write_json_file`: para paths centrais, eles delegam ao guard ancorado; com `RENDER=true`, paths fora da raiz verificada falham fechados. Snapshot diário e os readers de Memory Diet/Registry Persistente também têm ramificações explícitas entre guard central e recusa de fallback no Render. `trade_timeline_validator.py` usa `paper_file_stat`/`open_paper_text` na leitura documental.
- `trade_lifecycle_shadow_bridge.py` ainda contém `Path.open/read_text` direto, mas a busca de referências no runtime Central não encontrou caller fora dos próprios testes; permanece legado aparentemente dormente, não certificado como impossível de invocar. `registry_v2_migration_audit.py` é uma ferramenta read-only de auditoria com path explícito, não um writer de estado runtime.
- Limite: a busca ampliada é estática por APIs e nomes de estado, não uma prova formal de todos os efeitos indiretos, imports dinâmicos ou callsites futuros. Nenhum arquivo de produção foi aberto. O bloqueio de rewrites por pathname foi testado localmente; integração do mount `/data` atual continua sem verificação.

## Proteção do bridge de lifecycle shadow — 2026-11-21

- Mesmo sem caller no runtime Central e com ingestão default-off, mantive o módulo existente e substituí seu append/leitor pathname-based por `ensure_paper_data_dir`, `append_paper_text`, `paper_file_exists` e `read_paper_text`. A resolução agora também honra `DATA_DIR` via `resolve_paper_data_dir`; override customizado permanece sujeito ao guard e falha fechado fora da raiz no Render.
- O reset do bridge apaga apenas storage local descartável; bloqueia em Render e para qualquer alvo lexicalmente/resolvido sob `/data`, pois ainda não existe helper de unlink ancorado. Isso evita tratar observabilidade shadow como autorização para limpar estado persistente.
- `--lifecycle-shadow-bridge-storage-guard` passou `84` testes no Windows (1,83 s) e `84` no WSL/Linux (4,51 s), com runner offline e rede bloqueada. Os casos cobrem resolução de `DATA_DIR`, recusa de paths externos para I/O, preservação dos arquivos quando reset é bloqueado e compatibilidade funcional do bridge.
- A implementação permanece sem caller/runtime integration e sem autoridade operacional. Os testes não provam comportamento do mount `/data` no Render nem habilitam o bridge.

## Concorrência efetiva local e limite da conclusão C3 — 2026-11-21

- A fonte local permite concorrência **entre threads**: o servidor Werkzeug inicia com `threaded=True`, e os bots Central iniciam workers daemon. Os oito writers canônicos de `trade_registry.py` entram no `threading.RLock` global; os writers de `main.py` que fazem RMW consultam e usam esse mesmo lock. `acquire_runtime_file_lock()` usa `flock` para impedir duplicação de loops de runtime entre processos no container, mas isso não é um lock universal para todo caller de `save_registry()`.
- Portanto a alternativa simples para a topologia observada — um processo Central com múltiplas threads — é manter o `RLock` compartilhado para o Registry, escrita atômica e os file locks de liderança já existentes. Não é correto dizer que não há simultaneidade; ela existe no processo e está coberta pelo lock local conhecido nos writers testados.
- O código do checkout não contém `render.yaml`, `Procfile` ou outro manifesto local que fixe o comando de serviço. O último dado Render lido anteriormente indicava uma instância e `python main.py`, mas não foi revalidado nesta etapa. Não concluí que múltiplos processos sejam impossíveis; concluí apenas que não há evidência atual de dois processos gravando simultaneamente o mesmo Registry que justifique C3 distribuído. Se a implantação mudar para vários processos/serviços compartilhando `/data`, essa conclusão precisa ser revista antes da mudança.
- O C3 permanece preservado e dormente; não atualizei anchors divergentes, não alterei writer contracts e não tentei ativação. Os testes recentes cobrem writers e startup default-off localmente, não a exclusão multi-processo em produção.

## Revalidação de entrada, fill e stops — 2026-11-21

- Reexecutei com `tests/run_falcon_pilot_minimal_offline.py`, Python isolado (`-I`) e o `ccxt` já existente no cache local, sem instalação ou rede: `--entry-fill-stop` passou 37 testes; `--close-reconciliation` passou 110; `--initial-stop-containment` passou 79. Total: 226 testes, sem falhas.
- Um runner iniciado anteriormente em outro terminal terminou sem que sua saída pudesse ser recuperada; não foi contado como evidência. Os três resultados acima vieram de sessões controladas nesta rodada.
- `git diff --check` passou. O checkout continua sujo com alterações pré-existentes e recentes; não houve commit, push, deploy ou modificação da produção. Esses testes locais não validam corretora, fills reais, disco `/data` do Render, posições/ordens atuais nem prontidão para uso contínuo.
- A captura de logs com filtro `FALCON15` fornecida pelo operador não mostra correspondências na janela 15–17/11. Isso é apenas ausência de linhas que correspondam ao filtro histórico, não prova ausência de posições ou atividade atual.

## Revalidação integrada de guards e preflight — 2026-11-21

- Com runner offline/rede bloqueada e `ccxt` já presente no cache local (sem instalação), seleções passaram: `--paper-integrated-disk-guard` 116 passed, 13 skipped, 12 subtests; `--registry-writers` 73; `--broker-paper-disk-guard` 47; `--broker-log-storage-guard` 4 passed, 1 skipped; `--policy-storage-guard` 28; `--history-render-rewrite-guard` 5; `--arb-tail-storage-guard` 23; `--central-runtime-lock-guard` 8; `--paper-main-storage-guard` 9; `--journal-learning-storage-guard` 71; `--data-status-lock-guard` 1 passed, 8 deselected; `--registry-v2-paper-storage-guard` 280 passed, 1 skipped; source preview/capture 46/21.
- A primeira execução ampla `--personal-execution-safety` encontrou 406 passed e 2 falhas de fixture AST no teste de readiness: o namespace sintético não injetava o alias `_paper_file_exists`, embora o módulo real o importe do guard de storage. A fixture foi corrigida para injetar `lambda path: path.exists()`; a implementação de produção não foi relaxada. Foi adicionado o seletor focado `--preflight-storage-readiness`, que passou 3 testes (53 deselected). Reexecução ampla posterior terminou `408 passed` em 790,33 s.
- Outras seleções offline atuais passaram: `--personal-http-auth` 243; `--can-open-risk` 10 selecionados (67 deselected); `--trading-mode-defaults` 9. Em conjunto com as seleções de execução/fill/stop documentadas acima, isso melhora cobertura sintética local de auth, gates, identidade de storage e reconciliação.
- `git diff --check` passou após as mudanças. Os resultados são do checkout sujo local; não houve acesso a Render/BingX/Upstash, mudanças externas, push, deploy, ou alteração de controles LIVE. Permanecem sem prova atual o health e os ledgers em `/data`, a origem/identidade dos registros PAPER e o estado agregado da conta BingX. Portanto não se conclui prontidão operacional contínua.

## Regressão integrada de ciclo pessoal — 2026-11-21

- Após a correção exclusiva da fixture AST de readiness acima, reexecutei `--personal-lifecycle-completeness` no runner offline com Python isolado e pacote `ccxt` já presente no cache: `892 passed, 1 skipped` em 617,78 s. A seleção inclui cenários sintéticos de lifecycle, reconciliação e contenção; não acessa corretora nem dados de produção.
- O resultado não equivale a integração live: entrada/fill reais, posição e ordem protetiva na BingX, disaster stop em runtime, fechamento e reconciliação end-to-end permanecem sem evidência atual. O SHA local validado continua diferente do release Live conhecido, e a árvore permanece suja; não houve push/deploy.

## Revalidação de metadados Render — 2026-11-21 19:28 UTC

- Consulta somente de metadados ao serviço `central-robos-bingx`: service `srv-d8rtuv9o3t8c73ehav5g`, branch configurada `codex/personal-readiness-20261103`, `autoDeploy=off`, uma instância Standard, start `python main.py`, disco persistente de 4 GB em `/data`, `healthCheckPath` vazio e allowlist `0.0.0.0/0`.
- `list_deploys` confirmou Live em `bbd9511ffb425c3df7415283d69ed35ec84a2657` (`dep-dbuha6oae00c73ei09kg`, concluído 18/11 03:03 UTC). O checkout local continua em `579e3e15655ff453f15281afbc4c4eb26852db8c`, branch `codex/signal-id-preview-20261121`, com alterações locais não commitadas; portanto a release testada localmente não está publicada.
- As leituras foram apenas de metadados; não consultaram Shell, variáveis/segredos, ledgers, BingX, Upstash ou URL pública. Nenhum deploy, configuração ou gasto de build foi iniciado. O custo de publicar o worktree atual não foi consultado e permanece incerto; sem isso não avançar para push/deploy.
- A documentação oficial atual confirma que `healthCheckPath` vazio usa probe TCP e que serviços com disco persistente não têm garantia de deploy sem downtime. No SHA Live, `/healthz` é uma verificação pública mínima de runtime-start/readiness e está explicitamente documentada no código como não sendo trading-readiness. Não alterei a configuração: com uma instância e disco, o probe HTTP teria impacto de roteamento/restart se falhasse, e não há evidência operacional atual suficiente para escolher um health check de trading.

## Inventário direcionado dos sidecars PAPER — 2026-11-21

- Busca literal por `paper_integrated_positions.json`, `paper_integrated_seen.json`, `paper_integrated_executor_log.jsonl` e `paper_lifecycle_log.jsonl` nos fontes Python não encontrou um novo leitor/escritor direto fora dos módulos de estado esperados. Executor, lifecycle e outcome usam `paper_file_exists`/`read_paper_text`/`append_paper_text` e wrappers JSON guardados; `execution_pipeline_status` só consome a saúde agregada e usa os helpers para seus próprios stats; o leitor de learning valida `paper_data_mount_verified` e abre JSONL via `open_paper_binary`.
- Esse inventário é por nomes/callsites e complementa os testes `--paper-integrated-disk-guard`, `--paper-main-storage-guard`, `--journal-learning-storage-guard` e `--registry-v2-paper-storage-guard`; não é uma prova formal de imports dinâmicos ou de código futuro. Não leu arquivos de produção, não cria ledgers e não muda o bloqueio `PAPER_STATE_FILES_MISSING`.
- O `BOT_NAME` não precisa existir no Environment para o Falcon iniciar: tanto o SHA Live como o `HEAD` local definem o default `Falcon Strike ORB PRO`. A captura sanitizada anterior classificou os 2 registros da chave Falcon como `OTHER`; não configurar `BOT_NAME` para um valor presumido nem converter esse conflito em match, pois isso mudaria a regra de aceitação sem provar a origem dos registros.
- A descoberta das ferramentas Render nesta sessão não encontrou execução de Shell/SSH via MCP. Por isso não é possível obter o health PAPER/runtime do container por este conector; não usar token/credenciais nem contornar por chamada pública. A etapa fica dependente de saída manual sanitizada do Render Shell e contagem atual de posições/ordens na BingX Real.

## Atualização operacional — 2026-11-21

- Nova leitura Render MCP, somente de metadados: `central-robos-bingx` continua Live no SHA `bbd9511ffb425c3df7415283d69ed35ec84a2657`, com uma instância, auto-deploy desligado, disco persistente de 4 GB em `/data` e `healthCheckPath` vazio. Não foram consultados Shell, arquivos/segredos, Upstash nem API pública.
- O operador forneceu nesta conversa uma saída de `paper_integrated_health` com `ok=False`, `PAPER_STATE_FILES_MISSING`, arquivos ausentes/inválidos e contagens `None`. Isso é evidência manual fornecida pelo operador, não leitura independente atual do container.
- O operador reportou 1 posição LIVE e 2 ordens abertas na BingX, sob acompanhamento manual. Não houve verificação independente da conta; não houve cancelamento, fechamento, ordem, restart ou deploy.
- O operador confirmou que consegue acompanhar manualmente a exposição mesmo se houver interrupção do serviço. Isso esclarece a tolerância operacional à janela, mas não comprova custo zero nem especifica um novo SHA para publicação. O checkout local permanece sujo e o trabalho validado nele não é a release Live; sem custo zero comprovado, não fazer push/deploy.
- Estado de prontidão permanece bloqueado: ledger PAPER ausente, reconciliação de origem/identidade inconclusiva, estado da conta não verificado independentemente e release local diferente da produção. Não criar ledgers vazios, importar/descarregar os registros nem alterar controles de trading.

## Guard de armazenamento do Memory Profiler — 2026-11-21

- Auditoria estática ampliada encontrou que `memory_profiler_v1.py` usava apenas `CENTRAL_DATA_DIR`, com fallback fixo para `/opt/render/project/src/data`; portanto, no ambiente previamente reportado com `DATA_DIR=/data` e `CENTRAL_DATA_DIR` ausente, snapshots/estado/erros podiam ir para armazenamento efêmero. A configuração de ambiente atual não foi lida independentemente.
- Ajuste local: o módulo agora resolve o diretório pelo helper compartilhado (`CENTRAL_DATA_DIR`/`DATA_DIR`/`/data`), valida a persistência antes de gravar, usa helpers guardados para leitura/append e replace atômico e registra erro de persistência em vez de cair para um caminho efêmero. O trim do snapshot também usa leitura e replace guardados.
- Runner offline `--memory-profiler-storage-guard`: 15 testes passaram em 24,99 s (5 novos de storage e 10 existentes de coordenação GC); rede e subprocessos permaneceram bloqueados. `git diff --check` passou.
- Repetição no Ubuntu WSL2 com Python 3.14.4/pytest 9.0.2: os mesmos 15 testes passaram em 5,05 s, incluindo os helpers POSIX do guard; sem instalar dependências ou liberar rede. O checkout/HEAD `579e3e1` e a árvore suja foram rechecados antes da execução.
- Suíte mais ampla `--paper-integrated-disk-guard-no-flask` no WSL: 128 testes e 12 subtestes passaram, 1 teste foi excluído em 38,46 s. A exclusão é apenas `test_daily_history_blocks_ephemeral_render_fallback`, que importa `main.py` e não pode ser coletado sem Flask; o WSL não tem Flask, e nenhuma dependência foi instalada. A primeira tentativa sem exclusão teve 128 aprovados e falhou somente nesse import ausente.
- Alteração e testes permanecem somente no checkout local sujo; não houve push, deploy, acesso a secrets ou alteração de produção. Assim, a release Live ainda pode manter o comportamento antigo; isso precisa ser corrigido em uma publicação futura apenas após validação e custo zero confirmado.

## Fail-safe de ticker e stale alert do Donkey — 2026-11-21

- Releitura local confirmou que o scanner executa `_manage_donkey_open_positions_cycle`; `safe_fetch_ticker` retorna `None` após falha/retry, `_donkey_ticker_last_price` exige preço finito e positivo, e ciclo sem preço mantém a posição sem MFE/gestão/escrita. Falhas são marcadas por símbolo; preço válido as limpa. `montar_watchdog_status` eleva alerta quando a falha de gestão excede `DONKEY_TICKER_STALE_ALERT_SECONDS` (padrão 900 s).
- A seleção offline `--market-data-throttle` passou 160 testes no Ubuntu WSL2 (21,79 s), incluindo ticker intermitente `None → preço válido → None → recuperação`, preservação de estado durante falha e alerta/recuperação do watchdog. O runner bloqueou rede e subprocessos.
- Evidência limitada a fixtures/mocks e leitura de código do checkout local; não comprova latência, resposta da BingX, notificação externa nem que o SHA Live contenha a mesma implementação. Nenhuma alteração de código Donkey foi feita nesta verificação.

## Revalidação offline de gates PAPER e C3 — 2026-11-21

- Reexecutei no checkout sujo `579e3e15655f` via WSL/Ubuntu Python 3.14, com o runner offline: `--paper-integrated-disk-guard-no-flask` 128 passed, 1 deselected e 12 subtests; `--memory-profiler-storage-guard` 15 passed; `--lifecycle-shadow-bridge-storage-guard` 84 passed; `--history-render-rewrite-guard` 5 passed; `--c3-dormant-startup` 24 passed e 3 subtests; `--registry-v2-paper-storage-guard` 281 passed; `--registry-startup-admission` 1 passed. Não houve instalação de dependências nem acesso de rede.
- A tentativa de `--personal-lifecycle-completeness` não coletou testes: o ambiente WSL não tem `ccxt` nem Flask, resultando em seis erros de import durante coleta. `--policy-storage-guard` também não coletou por falta de Flask em `tests/test_history_eventbus_smoke.py`. Isso é limitação do ambiente, não aprovação nem falha funcional do código; não instalei pacotes.
- A validação local de C3 sustenta manter a integração dormente; não demonstra necessidade ou operação distribuída em produção. Todos os resultados são do checkout local, ainda diferente do SHA Live `bbd9511ffb425c3df7415283d69ed35ec84a2657`; não houve push, deploy, alteração de dados, controles LIVE ou conta BingX.
- A prontidão contínua permanece não comprovada: `/data` PAPER continua reportado ausente, a reconciliação de origem/identidade não foi concluída e a conta BingX não foi consultada independentemente nesta sessão. A suíte ampla offline foi viabilizada com o cache local indicado acima; o Python/WSL base continua sem `ccxt`/Flask.
- Com o Python local 3.14.5 (Flask e pytest presentes, `ccxt` ausente), `--personal-safety-no-ccxt` passou 273 testes em 1.698,28 s, sem instalar dependências. Uma tentativa inicial de `--personal-lifecycle-no-ccxt` a partir da pasta-pai mostrou falhas porque os testes resolvem `main.py` relativamente ao diretório atual; foi interrompida sem resumo. Reexecutada no diretório do checkout, a seleção completa passou 766 testes, 1 skip, em 924,03 s. A seleção `--personal-http-auth`, também no diretório correto, passou 243 testes em 114,31 s. Assim, as falhas aparentes não se reproduziram quando o runner foi iniciado no cwd exigido.
- Para completar a cobertura dos módulos dependentes de `ccxt`, usei somente `PYTHONPATH` apontando para o `site-packages` já existente em `cq-paper-fulltest-20261118-01` (ccxt 4.5.88, Flask 3.1.3, pytest 9.1.1); os executáveis do venv não existiam, mas os pacotes estavam intactos. No cwd do checkout, `--personal-lifecycle-completeness` passou 892 testes, 1 skip, em 971,17 s. O runner bloqueou rede/subprocessos; nenhuma instalação, alteração de serviço ou chamada de corretora ocorreu.
- Com o mesmo runtime local/cache offline e o cwd correto, `--personal-execution-safety` passou 408 testes em 997,60 s. A seleção cobre contratos sintéticos de preflight, entrada/fill, stop protetor, leitura de posições, risco agregado e reconciliação/fechamento; não comprova execução live, estado da conta ou corretora.
- Fechamento das seleções antes limitadas pela falta de Flask: `--paper-integrated-disk-guard` passou 116 testes, 13 skips e 12 subtests em 262,44 s; incluiu o teste de fallback diário excluído anteriormente. `--policy-storage-guard` passou 28 testes em 2,61 s. `--paper-main-storage-guard` passou 9 testes em 206,30 s. Todas foram executadas no cwd do checkout, com rede bloqueada pelo runner e `PYTHONPATH` apontando ao cache local já existente; sem instalar dependências.
- Revalidação específica de C3 e inventário do código corrente `579e3e15655f`: `--registry-writers` passou 73 testes em 175,25 s; `--registry-lock-audit` passou 1 (72 foram selecionados fora) em 75,16 s; `--c3-dormant-startup` passou 24 testes e 3 subtests em 538,96 s. O código atual preserva os anchors de writers e define `enabled=False`; isso sustenta manter C3 dormente e locks locais para a instância pessoal observada. Esses testes não medem processos auxiliares/writers de produção não inventariados e não demonstram segurança para ativar C3.
- Os testes offline do reconstrutor PAPER também foram repetidos no cwd correto: `--paper-registry-source-preview` passou 46 testes e `--paper-registry-source-capture` passou 21. A inspeção confirma que a captura executa apenas MGET de origem, emite somente métricas/status sanitizados e define `all_rows_ineligible_for_import=true`/`writes_performed=false`. Isso valida o contrato local; não valida a resposta atual do Upstash nem resolve conflitos de bot, identidade ou snapshot da produção.
- Os gates offline complementares do Registry passaram no checkout atual: `--registry-v2-migration-audit` 83 testes em 0,58 s; `--registry-stop-evidence` 97 em 36,86 s. Cobrem auditoria/classificação e evidência de fechamento com fixtures; não leem o Registry real e não transformam identificadores lógicos em identidade forte.

## Auditoria de I/O dos ledgers PAPER — 2026-11-21

- Busca estática pelos quatro caminhos canônicos (`paper_integrated_positions.json`, `paper_integrated_seen.json`, `paper_integrated_executor_log.jsonl`, `paper_lifecycle_log.jsonl`) encontrou constantes/callers em `paper_executor_integrated.py`, `paper_lifecycle.py`, `outcome_evaluator.py`, `execution_pipeline_status.py` e `executive_policy_learning.py`. Os acessos de execução/saúde encontrados passam por `paper_state_storage` (`read_paper_text`, `open_paper_binary`, `paper_file_exists`, `append_paper_text`, `write_json_atomically`) ou por wrappers que os chamam; a busca não encontrou `open/read_text/write_text` direto nesses quatro arquivos fora do guard. `execution_pipeline_status.py` lê posições via health dos módulos e usa helpers guardados para stats.
- No POSIX/Render, `paper_data_mount_verified` exige `/data` como mountpoint, rejeita symlink no root/subcaminhos e compara device; as operações concretas reabrem a cadeia com `dir_fd`, `O_NOFOLLOW`, `st_dev` e mount ID. O replace JSON cria temporário exclusivo no diretório do destino, faz `fsync` do arquivo e diretório e renomeia relativamente ao mesmo descritor. Isso reduz o risco TOCTOU pathname-based; não é uma prova de segurança contra alteração privilegiada do mount ou kernel.
- Ausência dos ledgers permanece explícita (`PAPER_STATE_FILES_MISSING`); leituras exigidas não a convertem em lista vazia. Não inicializei/criei arquivos. `executive_policy_learning.py` pode criar seus próprios arquivos de aprendizagem sob a mesma resolução/guard, mas não os quatro ledgers do executor.
- Confirmação local: `python -m pytest -q tests/test_paper_state_storage_render_paths_v1.py tests/test_paper_executor_data_dir_resolution_v1.py tests/test_paper_executor_integrated_idempotency_v1.py` terminou `67 passed, 9 skipped, 12 subtests passed` em 1,38 s. Os casos são unitários/sintéticos; a validação POSIX usa mocks onde necessário e não comprova o mount atual do Render.
- Limite: inventário textual/estático focado nos nomes canônicos e leitura dos módulos listados, não análise formal de todos os fluxos dinâmicos/futuros. A reconciliação Upstash/Registry e a razão histórica para ledgers ausentes continuam pendentes; não se deve importar, descartar nem inicializar os 68/69 registros sem prova de identidade. Sem deploy, sem mudanças de produção e sem consulta da conta BingX nesta etapa.

## Revalidação de autenticação HTTP — 2026-11-21

- No checkout sujo `579e3e15655ff453f15281afbc4c4eb26852db8c`, a comparação local confirmou `personal_http_auth.py` idêntico ao arquivo do último SHA Live conhecido `bbd9511ffb425c3df7415283d69ed35ec84a2657`. O hook global em `main.py` é aplicado antes dos handlers; a exceção sem credencial é somente `GET /healthz` sem query, que informa liveness/runtime e não estado de trading. Os hooks também bloqueiam intenção mutável por GET e recusam acesso até runtime pronto.
- Reexecutei `python -I tests/run_falcon_pilot_minimal_offline.py --personal-http-auth`: `243 passed` em 116,77 s. O runner offline bloqueia rede/subprocessos. Um teste direto da mesma seleção retornou ainda `161 passed` em 31,34 s; ambos são testes locais sobre fixtures/dispatcher Flask, não uma prova da configuração de secrets ou do serviço em runtime.
- A saída manual anterior `CENTRAL_PERSONAL_HTTP_USER_SET=True` e `...PASSWORD_SET=True` é antiga e não foi revalidada; nenhum valor de segredo foi lido. Não houve requisição pública, mudança de credenciais, commit, push ou deploy. A mudança ampla e suja em `main.py` continua não publicada; autenticação validada localmente não atesta a release corrente.
- Reexecutei em Ubuntu/WSL os mesmos testes de storage que no Windows incluem casos POSIX: `76 passed, 12 subtests passed` em 11,14 s, sem skips. Isso exercitou os caminhos POSIX sintéticos do guard/symlink/replace; não acessou nem representa o mount `/data` do Render.

## Estado Render atual, somente leitura — 2026-11-21

- Render MCP confirmou `central-robos-bingx` como serviço web no workspace Central Quant: último deploy `bbd9511ffb425c3df7415283d69ed35ec84a2657` (`live`, manual, 18/11/2026 03:03 UTC). Configuração: branch `codex/personal-readiness-20261103`, auto-deploy off, uma instância, plano `standard`, disco persistente 4 GB em `/data`, `healthCheckPath` vazio e allowlist `0.0.0.0/0`. O checkout local desta rodada é `codex/signal-id-preview-20261121` / `579e3e15655f`; suas modificações não estão publicadas nessa release/branch.
- A relação Git atual foi verificada localmente: `bbd9511` é o merge-base e o HEAD está quatro commits à frente. O `git status` reportou 50 caminhos modificados/não rastreados no checkout; os testes anteriores exercitaram esse worktree, não necessariamente um snapshot limpo apenas do HEAD. Não trate os resultados como certificação de release limpa.
- A autenticação global é portanto uma proteção crítica no serviço público; o helper `personal_http_auth.py` local é idêntico ao do SHA Live, mas não revalidei as variáveis de ambiente nem fiz chamada HTTP externa. O caminho de health check continua sem probe de aplicação configurado.
- A consulta foi somente de metadados e não alterou serviço. Plano Standard não demonstra que um novo build/deploy custaria zero; nenhum custo atual foi consultado/confirmado. Sem publicação, restart, leitura de secrets, logs, `/data`, Upstash ou conta BingX.
- Eventos Render filtrados desde 18/11 retornaram apenas os dois deploys dessa data: `bbd9511` terminou com sucesso; não vieram eventos de restart/falha nesse filtro e janela. Isso não é um health check funcional e não cobre operações do bot nem a conta BingX.

## Validação isolada do HEAD comprometido — 2026-11-21

- Criei um worktree temporário limpo em detached HEAD `579e3e15655ff453f15281afbc4c4eb26852db8c`, sem alterar o checkout principal; executei `--paper-registry-source-preview` (46 passed), `--paper-registry-source-capture` (21 passed) e `--personal-http-auth` (243 passed), todos via runner offline com `python -I`. O worktree temporário permaneceu limpo e foi removido após os testes.
- Escopo: isso valida esses três seletores no HEAD committed atual. Não valida as dezenas de mudanças de storage/Registry ainda não commitadas no checkout principal, nem completa os testes de integração de produção. O serviço continua no `bbd9511`; não publiquei os quatro commits nem consultei billing para confirmar custo incremental zero.
- No mesmo snapshot limpo, os gates C3 passaram: `--registry-writers` 60; `--registry-lock-audit` 1 passed/59 deselected; `--c3-dormant-startup` 24 passed e 3 subtests em 567,27 s. Evidência local reforça manter C3 dormente; não mede writers/processos externos em produção nem prova necessidade distribuída. O worktree temporário foi removido após confirmar status limpo; os 50 caminhos do checkout principal foram preservados.
