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
