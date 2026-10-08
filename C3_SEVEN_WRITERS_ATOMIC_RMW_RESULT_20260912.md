# Sete writers — correção offline concluída

## Resultado e autorização

O «Siga» do usuário autorizou especificamente corrigir os seis caminhos restantes
de leitura–modificação–gravação e exigir o lock na sincronização automática.
Essa autorização foi atendida; não voltar a pedi-la.

**264 testes aprovados, zero falhas, em 113,89 s.** Código somente local, não
publicado. Isso reproduz e corrige cenários sintéticos; não comprova ocorrência
histórica do defeito nem readiness de produção.

## Alteração em main.py

Somente os corpos destas sete funções foram alterados nesta etapa:

| Função | Linha atual | Proteção implementada |
| --- | ---: | --- |
| `_trs_v1_manual_register_open_trade` | 4489 | Lock obrigatório desde a leitura até o save. |
| `registry_persistence_v12_recover_closed_trade_from_params` | 10197 | Commit sob lock; coleta de live state e auditoria fora dele; preview preservado. |
| `registry_mode_segregation_v1_analyze` | 11741 | Classificação e gravação do mesmo snapshot sob lock no commit. |
| `mark_registry_missing_trades` | 14822 | Leitura, marcação por trade_id e gravação sob lock. |
| `predator_paper_registry_sync_fix_v1_status` | 49490 | Coleta externa antes do lock; releitura, índices, plano e gravação dentro dele. |
| `predator_registry_orphan_open_fix_v1_status` | 49943 | Releitura protegida e revalidação do plano e dos registros completos antes de modificar. |
| `predator_auto_closed_sync_v1_status` | 67818 | Lock obrigatório; preservada a revalidação de identidades; recontagem externa após liberação. |

Usado o mesmo lock process-local existente, resolvido por
`_trpsf_v1_registry_lock`; nenhum novo coordenador, wrapper ou monkey patch.
Ausência de lock impede o commit. Funções com preview continuam aceitando
`commit=False` sem exigir lock. As coletas de preview existentes não foram
transformadas em operações sem I/O; nos testes são exclusivamente fakes.

Trecho central, com variações de resposta próprias de cada função:

```python
registry_lock = _trpsf_v1_registry_lock()
if registry_lock is None:
    raise RuntimeError("REGISTRY_LOCK_UNAVAILABLE")
with registry_lock:
    fresh_registry, fresh_error = _pprsf_v1_load_registry()
    # Revalidar, modificar e salvar o documento fresco neste mesmo contexto.
```

Na sincronização automática, falha na recontagem posterior gera
`POST_COMMIT_RECOUNT_FAILED` em warnings e não apaga a confirmação de uma gravação
já realizada. Essa recontagem coleta posições/eventos e não deve segurar o lock.

Comparação AST com a fonte congelada antes da correção comprovou que todos os
outros nós de topo, assinaturas e decoradores de admissão são iguais. Logo, os
gates e as alterações preexistentes foram preservados. SHA-256 de main.py:
`6e2f5718282f553ae089a301faa6d1488a0b8ef883455aebc6dca426dd2efdf2`.

## Arquivos de teste e evidências

- Novo `tests/test_registry_remaining_writers_atomic_rmw_v1.py`: 55 casos de
  concorrência determinística, lock ausente/inválido, leitura sob lock, falha no
  save, liberação em exceção, rejeição C3, preview, releitura falha, preservação de
  alteração concorrente e troca de lifecycle no plano de orphan.
- `tests/test_main_traderegistry_sync_v2_ownership.py`: fake com RLock e resolução
  do lock real da fixture.
- `tests/test_predator_orphan_open_fix.py`: mesmo ajuste e admissão C3 injetada.
- `tests/test_predator_auto_closed_registry_sync.py`: resolução do lock da fixture,
  admissão C3 injetada e limite correto da seção verificada pelo teste estático.
- `tests/test_predator_daily_summary_registry_sync.py`: lock da fixture e admissão
  C3 injetados; executados os cinco testes específicos de reparo/sincronização.
- `.offline_validation/seven_writers_rmw_20260912/run.py`: launcher do laboratório
  existente; não incluir no runtime/release operacional.
- `.offline_validation/seven_writers_rmw_20260912/verify_scope.py`: comparação AST
  exclusivamente de código com a cópia congelada; gera `scope-evidence.json`.
- Este relatório e `C3_OFFLINE_CONTINUITY_20260911.md`: resultado/continuidade.

Rodadas preservadas, sem sobrescrever evidência anterior:

1. `red-evidence`: 43 falhas / 96 aprovações; também revelou duas dependências
   faltantes na nova fixture automática, corrigidas antes da fase RED válida.
2. `red2-evidence`: 37 falhas / 102 aprovações, antes de alterar main.py.
3. `green-evidence`: 139 aprovações após a correção.
4. `green2-evidence`: 263 aprovações / uma falha no teste estático antigo: seu
   recorte incluía `_c3_closed_identity_repair_trading_controls_v1`, fora da seção
   de auto-sync. Ajustado o recorte até a última rota auto-sync, sem excluir a
   função sob teste ou afrouxar a lista de chamadas proibidas. Nenhuma nova mudança
   em main.py foi necessária.
5. `green3-evidence`: **264 aprovações**. Cada rodada contém `tests.txt`,
   `results.xml` e `location.json`.

A suíte ampliada reúne 11 arquivos (um deles com cinco testes selecionados),
incluindo os 85 testes anteriores, identidade CLOSED, ownership V2, PAPER,
idempotência, preflight fail-closed e storage readiness. Hashes de main.py e dos
cinco arquivos de teste modificados/criados conferidos com o manifesto exportado
da rodada final: todos idênticos. Verificação de whitespace passou; somente avisos
Git sobre LF/CRLF, sem mutação Git.

Laboratório: Python 3.11.9 já instalado, Linux uid999, fonte read-only, scratch
ext4 sintético, zero rotas de rede e sem mounts Windows visíveis aos testes.
Hook anterior à coleta bloqueia rede, subprocessos e imports operacionais. Foram
exportados somente 28 arquivos Python de dependências explícitas, sem .env,
Registry real, histórico operacional ou diretório Git.

## Limites e próximo passo

O lock é local ao processo: não homologa exclusão entre processos/hosts,
startup/WAL, relógio/lease, estado persistente de produção ou Live. Não torna a
coleta de posições dos módulos uma transação atômica com o Registry. Segurar o
lock durante planejamento pode aumentar contenção; não houve benchmark ou teste
de carga operacional. Callers sem lock passam a falhar fechado.

Não foram executados a suíte completa, servidor, bots/broker, preflight real,
restart real, deploy, bootstrap ou reparo real. Comportamentos preexistentes fora
da correção, como a resposta da recuperação manual em falha de auditoria posterior
ao save, não foram redesenhados. Não alegar cobertura de todo writer possível.

Próximo passo seguro e finito: preparar a revisão do diff/pacote exclusivamente
local destas correções, ligado à fonte congelada e ao manifesto testado, sem
incluir alterações alheias, laboratórios, dados, segredos ou runtime Python.
Não executar commit/push/deploy, mudar flags, remover gates ou ativar Live.
Não repetir inventário ou testes idênticos sem achado novo. Percentual restante
para Live: **indeterminado**, pois os testes offline não medem prontidão real.

Nenhum secret ou dado real foi acessado; nenhuma chamada operacional externa foi
feita; nenhum commit, push, deploy, configuração de trading real ou ordem foi
executado. Rede somente para documentação pública OpenAI sobre automatismo.

Automatismo existente mantido ACTIVE, com autorização e resultado atualizados;
o usuário não precisa enviar OK para essa revisão local. OpenAI Docs orientou
somente a atualização administrativa, não a alteração de código. Execuções locais
agendadas dependem de computador ligado e aplicativo em execução, conforme a
[documentação oficial](https://learn.chatgpt.com/docs/automations?surface=app).
Modelo recomendado: GPT-6 Astra — Alto; nenhuma troca foi executada.
