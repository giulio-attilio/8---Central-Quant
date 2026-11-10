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
