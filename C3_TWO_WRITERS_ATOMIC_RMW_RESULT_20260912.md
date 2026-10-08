# Correção local de dois writers — resultado de 12/09/2026

## Resultado

Escopo autorizado pelo «siga» após a revisão arquitetural: reproduzir e corrigir
offline a perda de atualizações em `_rtlm_v1_update_open_trade_snapshot` e
`trade_close_outcome_v1_commit`, sem remover gates ou atuar em produção.

Antes: 8 falhas esperadas e 77 testes aprovados. Quatro falhas reproduziram uma
gravação obsoleta que recolocava um lifecycle OPEN após fechamento concorrente;
quatro demonstraram ausência de bloqueio antecipado quando o lock era inválido.
Isso reproduz um defeito sintético, não comprova ocorrência histórica real.

Depois: **85 testes aprovados, zero falhas, em 44,20 segundos**.

## Diff desta etapa

- `main.py`: o lock existente retornado por `_trpsf_v1_registry_lock` agora envolve
  todo o read-modify-write das duas funções. Sem lock, retorna
  `REGISTRY_LOCK_UNAVAILABLE` antes de ler ou gravar. A admissão C3 continua externa
  ao lock local; `commit=False` continua sem leitura. Nenhum novo lock, wrapper,
  coordenador ou monkey patch foi criado.
- `tests/test_registry_two_writers_atomic_rmw_v1.py`: 15 novos testes sintéticos,
  com extração AST das funções e injeção de dependências, sem importar `main`.
- `tests/test_trade_close_outcome_semantic_recurrence_v1.py`: fixture passa a
  fornecer um RLock sintético ao commit.
- `tests/test_trade_registry_closed_identity_residual_guards_v1.py`: fixture passa
  a fornecer o lock do módulo Registry isolado.
- `.offline_validation/two_writers_rmw_20260912/run.py`: launcher local para o
  laboratório já existente, sem downloads. Não é componente de release/runtime.
- `.offline_validation/two_writers_rmw_20260912/red-evidence/` e `green-evidence/`:
  cada diretório contém `tests.txt`, `results.xml` e `location.json` desta rodada.
- Este relatório e `C3_OFFLINE_CONTINUITY_20260911.md`: resultado e continuidade.

Trecho central adicionado, seguido do corpo anterior sob o contexto:

```python
lock_resolver = globals().get("_trpsf_v1_registry_lock")
registry_lock = lock_resolver() if callable(lock_resolver) else None
if registry_lock is None:
    return {"attempted": True, "committed": False, "status": "REGISTRY_LOCK_UNAVAILABLE"}
with registry_lock:
    # corpo anterior da operação, incluindo a leitura e a gravação
    ...
```

## Verificações realizadas

Suíte dirigida de cinco arquivos: os três testes acima mais
`tests/test_falcon_real_pilot_preflight_fail_closed_v1.py` e
`tests/test_trade_registry_live_entry_storage_readiness_v1.py`.

Cobertura nova: concorrência determinística para ambos os writers com CLOSED em
lista/dicionário; ausência/invalidade do lock; save rejeitado ou com exceção sem
perda de dados e com liberação do lock; rejeição C3 anterior ao acesso local;
preview sem commit. Os testes existentes cobrem identidade conflitante, causa STOP,
PnL líquido e R bruto separados, gates de preflight e storage.

Ambiente: Python 3.11.9 já instalado, Linux isolado, uid 999, fonte somente leitura,
scratch ext4 dedicado, nenhuma rota de rede e nenhum mount Windows visível aos
testes. Hook bloqueia rede, subprocessos e importações operacionais antes da
coleta. Foram exportados apenas 19 arquivos Python da dependência explícita.

Comparação AST entre as fontes congeladas antes/depois confirmou: somente as duas
funções mudaram; removendo o novo guard/contexto, seus corpos, assinaturas e
decoradores são iguais aos anteriores. Todos os demais nós de topo são iguais.
O `main.py` atual é byte a byte igual ao testado; SHA-256:
`6d3e26c9e628c6b48b4d82535527534889e2987975b2d27063411c9926715dfd`.

Verificação de whitespace do diff dos três arquivos rastreados alterados passou
com `core.longpaths=true`; apenas avisos LF/CRLF. Uma tentativa de verificar todo
o worktree sem essa opção encontrou caminhos antigos longos; não é uma validação
global. Alterações preexistentes do usuário foram preservadas.

## Limites, riscos e próximo passo

O lock é process-local: não prova exclusão entre processos/hosts, proteção de todos
os writers, recuperação WAL, readiness atual ou segurança de uma ativação Live.
O fechamento mantém também as gravações de auditoria existentes sob o lock, o que
pode aumentar contenção; não foi feito benchmark. Callers sem o lock passam a
falhar fechado. Não foram executados a suíte completa, runtime real, preflight
operacional, testes de broker, restart real ou homologação de produção.

Próximo passo seguro: inventário somente leitura dos demais caminhos de gravação,
reutilizando o inventário existente e indicando quais ainda deixam leitura fora
do lock. Não corrigir automaticamente os demais writers, remover gate, preparar
deploy ou reabrir estudos concluídos. Esta correção dos dois writers terminou.
Percentual restante para Live: indeterminado; teste offline não mede prontidão real.

Nenhum secret, Registry real ou dado operacional foi acessado. Nenhuma chamada
externa foi feita pelo código ou testes; houve apenas consulta à documentação
pública OpenAI para a manutenção do automatismo do Codex. Nenhum commit, push,
deploy, alteração de configuração de trading real ou ordem foi executado.

Automatismo existente mantido ativo, com resultado atualizado, sem esperar outro
OK para a revisão somente leitura. Configuração ativa não significa execução
técnica contínua após esta rodada. OpenAI Docs orientou somente essa atualização
administrativa, não a correção do código. Referência pública:
[tarefas agendadas](https://learn.chatgpt.com/docs/automations?surface=app).

Modelo recomendado para a revisão: GPT-6 Astra; esforço Alto. Nenhuma troca de
modelo foi executada.
