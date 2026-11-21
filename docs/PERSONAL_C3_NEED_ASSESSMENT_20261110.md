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
