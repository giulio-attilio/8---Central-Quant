# Avaliação de startup e necessidade de C3 distribuído — 2026-11-07

## Escopo e conclusão provisória

O alvo é uso pessoal por um operador e uma conta. A evidência disponível não demonstra que um coordenador C3 distribuído precise estar no caminho crítico. Manter o C3 existente preservado, default-off e separado de ordens; não ativar nem ampliar neste estágio. Reavaliar se a topologia passar a ter mais de um processo/instância escrevendo o mesmo Registry ou se uma falha concreta mostrar que as travas locais não bastam.

Esta é uma conclusão provisória baseada no código local e em inspeções de leitura do Render. Ela não comprova durabilidade física do disco, comportamento de todas as rotas de escrita, nem configuração operacional completa.

## Evidência de topologia

- Render workspace `tea-d8gnnuojo6nc73ep3lg0`: a listagem de serviços retornou somente `central-robos-bingx` (`srv-d8rtuv9o3t8c73ehav5g`). A configuração lida em 2026-11-07 indica uma instância, comando `python main.py` e disco persistente único de 2 GB em `/data`.
- Logs recentes registram boots em um processo (`pid=44` ou `45`, `ppid=1`) e uma thread imediatamente antes de `start_enabled_bots()`. Isso é uma observação pontual por boot, não uma prova de ausência de concorrência em todo o runtime.
- O código do serviço inicia bots em threads dentro de um processo; há chamadas de inicialização no import de alguns módulos de bot (por exemplo `bots/trendpro.py`, `bots/donkey.py`, `bots/cobra.py`, `bots/meme.py`, `bots/predator.py` e `bots/turtle.py`). Quais bots estão habilitados em produção não foi lido, portanto o conjunto efetivamente ativo permanece desconhecido.

## Locks e writers

- `trade_registry.py` cria um `threading.RLock` para sincronização do Registry no processo.
- `main.py` também usa `fcntl.flock` para eleger um líder para loops/pollers específicos, mantendo o file handle aberto em `CENTRAL_PROCESS_LOCK_HANDLES`. Essa trava cobre somente os trabalhos que a chamam; não deve ser tratada como trava universal de todos os writers.
- O coordenador C3 define um inventário canônico de 19 writers, mas esse número é um contrato de código, não evidência de que os 19 estejam ativos ou registrados no runtime.
- O inventário canônico distribui 7 superfícies em `trade_registry.py` e 12 em `main.py`; todos descrevem o escopo atual como `PROCESS_LOCAL_FULL_RMW` ou `PROCESS_LOCAL_SAVE_ONLY`, enquanto o alvo futuro é `SHARED_INTERPROCESS_FULL_RMW`.
- O contrato declara explicitamente os bloqueios `RUNTIME_WRITER_REGISTRATION_ABSENT`, `REAL_MAINTENANCE_LEASE_NOT_ISSUED`, `REAL_NEW_WRITES_NOT_FENCED`, `REAL_INFLIGHT_MUTATIONS_NOT_DRAINED` e `REAL_SHARED_LOCK_NOT_ACQUIRED`. Portanto, a contagem 19 não é uma confirmação de 19 writers ativos: o próprio contrato informa que a instalação/coordenação real está ausente.
- O coordenador e o seam C3 são default-off, com `_DenyLockBackend` e `_DenyLeaseStore` quando não configurados. A documentação do seam declara que o módulo não lê variáveis de ambiente, toca o Registry, inicia workers ou faz chamadas de rede. Não encontrei evidência de ativação C3 na inspeção atual.

## Bloqueio de startup observado

- Render está em status operacional instável: eventos `server_available` seguidos de `server_failed` por timeout de conexão na porta 10000. O deploy `4eb9f66` consta como `live`, mas isso não significa que o runtime esteja pronto.
- Nos boots recentes, o último marcador de aplicação observado é `MEMORY before_start_bots`; não aparece `MEMORY after_start_bots` antes do restart. A release atualmente publicada (`4eb9f66`) chama `start_central_runtime_once()` antes de `serve_forever()`, e `start_enabled_bots()` importa cada bot habilitado e aplica o history wrapper sincronicamente. A branch de prontidão inclui o diagnóstico de `789882c`, que inicia o servidor HTTP em thread antes do runtime, mas ainda executa o boot dos bots no thread principal.
- Confirmação de leitura em 2026-11-07 14:00 UTC: o deploy `4eb9f66` ainda estava ativo. Logs de requisição mostraram chamadas GET a `/healthz` encerradas pelo cliente após ~29 s (HTTP 499), além de respostas 502 durante reinícios. Isso é consistente com a ordem de inicialização publicada, sem provar qual import/rotina específica está bloqueando.
- O serviço tem `healthCheckPath` vazio; conforme a [documentação de health checks do Render](https://render.com/docs/health-checks), o padrão é um probe TCP, não HTTP. Portanto os 499 do cron em `/healthz` são observação externa da aplicação, e não falha de um HTTP health check configurado no Render.
- Logs de forense registram o disco em 96.06% de uso, 62.08 MB livres e `trade_lifecycle.jsonl` com 481.453 MB. Isso é risco operacional adicional, mas não prova que esse arquivo seja a causa do bloqueio.
- O módulo específico e a etapa exata ainda não são conhecidos: a release publicada não tem marcadores por bot. O candidato local inclui os marcadores sanitizados, inicia o servidor HTTP antes do runtime e mantém `CENTRAL_RUNTIME_READY` falso até terminar a carga dos bots e dos roteadores. Enquanto isso, `/healthz` e as demais rotas retornam 503, inclusive chamadas autenticadas; depois do boot, `/healthz` retorna 200. Isso evita que o cron registre falso sucesso durante um boot travado, mas ainda não prova que os bots carregaram nem resolve por si só a prontidão de trading.

## Alternativa simples e decisão sobre C3

Para a topologia observada de uma instância e um operador, a alternativa proporcional é manter um processo, serializar atualizações do Registry com a trava compartilhada em memória, manter os file locks apenas para loops explicitamente líderes e deixar C3 distribuído fora do caminho crítico. Antes de escalar para múltiplas instâncias/processos, a aplicação teria de demonstrar locks realmente compartilhados para cada writer, recuperação segura e teste de concorrência multi-processo; só então o C3 poderia ser reconsiderado.

## Validação e limites

- Commit local `789882c`: teste offline `python3.14.exe tests/run_falcon_pilot_minimal_offline.py --drain-only` passou, 28 testes; `py_compile` e `git diff --check` passaram.
- Revisão local anterior do gate HTTP, métodos e readiness pré-runtime: 173 testes em 457.67 s. Após a correção de `ac4d23c`, três testes direcionados de readiness/auth/persistência passaram em 154.60 s com conexões bloqueadas; `py_compile` e `git diff --check` também passaram. A sonda pública devolve 503 antes da prontidão e 200 após ela. Todos esses testes usam dados sintéticos e não substituem verificação de produção.
- O runner restringe rede e persistência a dados temporários nessa suíte. O resultado valida contratos locais, não o Render, chamadas reais da BingX/Telegram, fill, posição, stop, fechamento, reconciliação ou durabilidade física.
- O push foi concluído pelo GitHub Desktop; o GitHub confirmou os commits `47bb5f8` (readiness) e `54437f9` (registro da publicação), e o checkout ficou sincronizado com `origin/codex/personal-readiness-release-20261104`. O deploy ativo do Render continua sendo `4eb9f66`; o auto-deploy está desligado, então o push não publicou o candidato. A autorização recebida para `4eb9f66` não exige novo deploy, pois esse SHA já está ativo. Nenhuma alteração foi feita na AWS, Render, variáveis de ambiente ou dados de produção; os controles de trading não foram lidos nem alterados.

## Próximos critérios

1. Recuperar/estabilizar o serviço sem iniciar ordens e resolver o espaço em disco sem apagar nem reescrever históricos em massa.
2. Avaliar separadamente a publicação do candidato `47bb5f8` no Render para observar o último marcador e identificar o bot/fase exatos. Isso não foi feito: o SHA atualmente ativo é `4eb9f66`, e a confirmação de deploy recebida correspondia apenas a esse SHA já ativo. Antes de um deploy de outro SHA, conferir novamente custo, disco, risco de interrupção e ausência de operações abertas; não substituir o alvo autorizado.
3. Demonstrar, com inventário runtime sem segredos, os writers e processos realmente ativos e testar disputa de Registry entre threads/processos.
4. Manter PAPER/DRY_RUN e provar os controles de entrada, fill, posição, disaster stop, fechamento e reconciliação antes de qualquer alegação de prontidão.
