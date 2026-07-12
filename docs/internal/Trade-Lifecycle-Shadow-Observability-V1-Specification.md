# Trade Lifecycle Shadow Observability V1 — Especificação Arquitetural

Status: DRAFT PARA AUDITORIA DO CTO  
Versão: 1.0.0-SHADOW  
Data: 12/07/2026  
Implementação: não iniciada

## 1. Objetivo

A Trade Lifecycle Shadow Observability V1 apresenta evidências produzidas pelo Trade Lifecycle Shadow Runtime Adapter V1 sobre a convergência entre o Trade Registry, autoridade operacional vigente, e o Trade Lifecycle Manager V3, projeção Shadow.

É uma camada pura, passiva, fail-open e somente leitura. Ela transforma arquivos e contratos públicos já existentes em respostas serializáveis, limitadas, sanitizadas e auditáveis. Não participa do lifecycle nem do caminho de decisão ou execução.

Declarações invariantes:

```text
operational_authority = False
broker_access = False
registry_write_access = False
lifecycle_write_access = False
execution_control = False
automatic_repair = False
```

A Observability nunca abre ou fecha trades, altera ordens, risco, TP50, break-even ou trailing, altera Registry ou Lifecycle, corrige divergências, executa replay, chama Broker ou BingX, bloqueia execução, participa de ALLOW/DENY ou atribui posições externas a robôs.

## 2. Escopo

- health composto da própria camada, Adapter, Lifecycle e persistência;
- métricas persistidas e métricas deriváveis com proveniência explícita;
- últimos eventos, com filtros e paginação somente leitura;
- divergências agrupadas por identidade estrutural;
- última reconciliação conhecida e seu resumo;
- estado, atualidade e integridade da persistência;
- evidência de atividade anterior e posterior a restart;
- filtros validados sobre campos permitidos;
- segregação de posições externas das estatísticas operacionais.

## 3. Fora de escopo

- reparo, replay ou qualquer escrita;
- promoção de autoridade;
- dashboard gráfico;
- Telegram e alertas automáticos;
- alteração do Lifecycle ou do Registry;
- integração direta com BingX, Broker, exchange ou rede;
- reconciliação operacional sob demanda;
- compactação, rotação, truncamento ou correção dos journals;
- criação de um novo ledger de deduplicação.

## 4. Arquitetura

Arquivos futuros esperados:

```text
trade_lifecycle_shadow_observability.py
tests/test_trade_lifecycle_shadow_observability.py
main.py  # somente na fase HTTP posterior
```

Fluxo e separação:

```text
Trade Registry (autoridade operacional)
    -> Shadow Runtime Adapter (produz evidência)
        -> runtime events JSONL
        -> runtime divergences JSONL
        -> runtime state JSON
            -> Shadow Observability (lê, valida, sanitiza e agrega)
                -> main.py (somente adapta HTTP e expõe o resultado)
```

O Adapter produz evidência. A Observability lê e agrega. `main.py` apenas valida parâmetros HTTP simples, chama uma função pública do módulo e serializa seu retorno.

`main.py` não deverá ler JSONL, agregar métricas, interpretar divergências, acessar atributos privados do Adapter nem implementar sanitização de domínio. A integração deverá receber uma instância/fachada somente leitura do módulo, sem Broker e sem Registry como dependências.

### 4.1 API pública futura do módulo

```python
get_health() -> dict
get_metrics() -> dict
list_events(filters=None, limit=50, cursor=None) -> dict
list_divergences(filters=None, limit=50, cursor=None) -> dict
get_reconciliation_summary() -> dict
```

Construtores poderão receber apenas caminhos resolvidos internamente/configurados no startup e providers públicos de health. Nenhuma função aceita path fornecido pelo request.

## 5. Inspeção e fontes de dados reais

### 5.1 Artefatos do Runtime Adapter

Diretório resolvido pelo Adapter, em ordem: argumento `data_dir`, `TRADE_LIFECYCLE_SHADOW_DATA_DIR`, `CENTRAL_DATA_DIR`, `<repo>/data`.

| Fonte | Nome real | Papel |
|---|---|---|
| Events journal | `trade_lifecycle_shadow_runtime_events.jsonl` | resultado de cada observação que chegou ao ponto de journalização |
| Divergences journal | `trade_lifecycle_shadow_runtime_divergences.jsonl` | primeira ocorrência em memória de cada chave de divergência |
| State snapshot | `trade_lifecycle_shadow_runtime_state.json` | versão, atualização e métricas cumulativas da instância |
| Adapter health | `TradeLifecycleShadowRuntimeAdapter.get_health()` | flag, versão, erro, métricas e health do Manager |
| Lifecycle health | `trade_lifecycle_health()` | estado público do Lifecycle V3 |

Na inspeção de 12/07/2026, nenhum dos três arquivos `trade_lifecycle_shadow_runtime_*` existia no diretório `data/`. Isso é um estado válido de "sem evidência persistida", não corrupção.

Existem também arquivos próprios do Lifecycle Manager — `trade_lifecycle_shadow_snapshot.json`, `trade_lifecycle_shadow_events.jsonl` e `trade_lifecycle_shadow_divergences.jsonl`. Eles não substituem os artefatos Runtime e não são fonte primária da Observability V1. O health público do Lifecycle pode ser consultado; seus internals e locks privados não.

### 5.2 Schema real do runtime state

```json
{
  "version": "1.0.0-SHADOW",
  "updated_at": "ISO-8601 UTC",
  "metrics": {
    "observed": 0,
    "applied": 0,
    "duplicate": 0,
    "blocked": 0,
    "errors": 0,
    "reconciled": 0,
    "divergences": 0
  }
}
```

O state real não contém schema version independente, boot ID, startup time, cursor, último evento, última reconciliação, `_seen`, `_divergence_keys`, ocorrências, resoluções ou posições externas.

### 5.3 Schema real do runtime event journal

```json
{
  "timestamp": "ISO-8601 UTC",
  "event_id": "string",
  "event_type": "string",
  "lifecycle_id": "string",
  "identity": {"value": "string", "source": "string"},
  "status": "APPLIED|DUPLICATE|BLOCKED",
  "manager_result": {}
}
```

O `manager_result` é o retorno serializado do Lifecycle V3 e pode conter snapshot, warnings, reasons e divergences. O journal Runtime não persiste diretamente `trade_id`, `bot`, `setup`, `symbol`, `side` nem o payload original em campos de topo; filtros nesses campos dependem de extração segura do resultado aninhado e podem ser indisponíveis em registros antigos/incompletos.

Eventos inválidos antes da região persistida, Adapter desabilitado e exceções podem não gerar linha. `TRADE_UPDATED` atualmente resulta `BLOCKED` no Adapter, embora o resultado interno seja `NOOP`; portanto a métrica futura `noop` deve ser derivada semanticamente de `manager_result.status == "NOOP"`, sem reclassificar a evidência original.

### 5.4 Schema real do runtime divergence journal

```json
{
  "timestamp": "ISO-8601 UTC",
  "key": "SHA-256",
  "lifecycle_id": "string",
  "trade_id": "string",
  "field": "string",
  "shadow_value": null,
  "registry_value": null,
  "severity": "CRITICAL|WARNING",
  "reason": "string"
}
```

O `timestamp` efetivo é o timestamp da diferença produzida pelo Lifecycle. O arquivo não contém `resolved`, `resolved_at`, contagem de ocorrências, evento de match, resumo de rodada ou identificador de reconciliação.

### 5.5 Funções públicas reais

Adapter, na classe: `observe_event`, `reconcile_trade`, `reconcile_all`, `get_metrics`, `get_health`. Entrypoints exportados de runtime: `safe_observe_shadow_event` e `safe_reconcile_shadow_trade`. `reconcile_all` é público na classe, mas não está exportado como wrapper em `__all__`.

Lifecycle V3: `create_lifecycle`, `apply_event`, `get_lifecycle`, `get_trade_lifecycles`, `get_open_lifecycles`, `validate_transition`, `compare_with_registry`, `mark_reconciliation_required`, `mark_recovery_required`, `record_outcome`, `get_lifecycle_history`, `read_shadow_divergences`, `trade_lifecycle_health` e `reset_shadow_storage`.

A Observability só pode usar `get_health`/`get_metrics` do Adapter e `trade_lifecycle_health` como providers públicos. Não deve chamar operações mutáveis do Lifecycle nem `reconcile_*`.

### 5.6 Padrão HTTP real observado

`main.py` usa rotas Flask `GET`, lê filtros por `request.args`, chama builders/status functions e devolve `dict, status_code`; falhas são convertidas em payload estruturado. Há helpers locais que leem JSON/JSONL, mas alguns usam `read_text().splitlines()`, inadequado para journals grandes. O padrão a preservar é rota fina; os readers limitados e a interpretação ficarão no novo módulo.

### 5.7 Precedência e falhas de fonte

1. Journals append-only são evidência histórica para itens e reconstrução possível.
2. State é snapshot rápido para contadores da instância, nunca verdade superior ao journal.
3. Health público é evidência volátil da instância atual.
4. Cache é apenas otimização descartável.

Comportamento obrigatório:

- arquivo ausente: coleção vazia, warning `FILE_NOT_FOUND`, persistence status `MISSING`; não criar arquivo;
- arquivo vazio: coleção vazia, status `EMPTY`, sem erro fatal;
- state JSON inválido: ignorar como fonte de métricas, status `INVALID`, tentar derivação limitada dos journals;
- linha JSONL inválida: isolar a linha, incrementar métrica interna e `persistence.invalid_lines`, continuar;
- última linha sem newline ou JSON incompleto: tratar como escrita parcial, ignorar temporariamente e contar separadamente; não classificá-la como corrupção permanente na primeira leitura;
- linha válida acima do limite de bytes: não materializar conteúdo integral, marcar `truncated_lines`/`LINE_TOO_LARGE` e omitir o item;
- state antigo: apresentar `stale=true`, usar journals para dados posteriores quando possível e retornar DEGRADED;
- journal e state divergentes: expor ambas as proveniências, nunca ajustar arquivos; journal vence para existência/ordem dos itens, state vence apenas como contador declarado da instância quando não houver reconstrução equivalente.

## 6. Persistência e restart

V1 não cria nem modifica arquivos. JSONL permanece evidência append-only produzida pelo Adapter e o JSON permanece snapshot rápido produzido pelo Adapter. A Observability realiza startup validation lazy ou explícita, mantém apenas cache descartável em memória e jamais modifica journals.

### 6.1 Estratégia de reconstrução

- validar state e metadados dos journals no startup/primeira leitura;
- identificar o último registro completo de cada journal por leitura limitada reversa;
- para métricas históricas solicitadas, executar streaming controlado, com orçamento de bytes/tempo e resultado `partial=true` quando o orçamento terminar;
- não persistir checkpoint na V1; cursor HTTP é opaco, assinado e vinculado ao arquivo observado, mas não é gravado;
- reconstrução integral só ocorre por operação interna explicitamente limitada ou durante preparação de cache, nunca em todo request;
- nenhuma reconstrução chama Adapter, Registry, Lifecycle ou reconcile.

Preservação/reconstrução possível:

| Dado | Estratégia V1 | Limitação atual |
|---|---|---|
| contadores | state + contagem derivada do event journal | erros e tentativas não journalizados não são reconstruíveis integralmente |
| último evento | última linha válida completa do events journal | pode não representar evento rejeitado antes do journal |
| última reconciliação | melhor evidência: divergence timestamp ou `reconciled` do state | matches/rodadas não têm journal próprio; horário exato pode ser desconhecido |
| divergências | agrupar divergence journal | só primeiras ocorrências por boot/chave em memória são persistidas |
| ocorrências | contar linhas por identidade estrutural | dedup em memória impede persistir repetições no mesmo processo |
| resoluções | inferir apenas diante de evidência posterior suficiente | hoje não há evento de resolução/match persistido; normalmente `unknown` |
| external positions | classificar events cujo lifecycle/evento indique external | payload de topo não está no runtime journal; cobertura pode ser parcial |
| erros recentes | state/health e linhas com resultado de erro quando existirem | exceções do Adapter não são journalizadas no caminho atual |

### 6.2 Evidência de atividade após restart

O contrato deve expor `process_started_at` quando o provider puder fornecê-lo, `state_updated_at`, `last_event_at`, mtimes e `activity_after_restart` com valores `CONFIRMED`, `NOT_OBSERVED` ou `UNKNOWN`. Só será `CONFIRMED` se uma evidência persistida completa tiver timestamp posterior ao startup conhecido. Mtime isolado não prova evento de negócio.

O state atual é insuficiente para restart completo. O Adapter não carrega seu state, não persiste seen event IDs e não persiste divergence keys. Ao reiniciar, métricas voltam a zero e uma persistência posterior pode sobrescrever o state; deduplicação do Lifecycle pode ainda proteger eventos que estejam em seu snapshot, mas isso não restaura a deduplicação própria do Adapter.

A Observability não deve reconstruir nem alimentar deduplicação. Ela apenas exibe evidências e sinaliza a lacuna.

## 7. Limite de memória e paginação

É proibido usar `Path.read_text()`, `readlines()` ou equivalente sobre um journal inteiro em request.

Parâmetros V1:

- `limit` default: 50 itens;
- `limit` máximo: 200 itens;
- tamanho máximo por linha: 256 KiB;
- resposta JSON máxima estimada: 2 MiB;
- string sanitizada: no máximo 4 KiB; valores maiores recebem marcador de truncamento;
- profundidade máxima: 8; coleção aninhada máxima: 100 elementos;
- orçamento default de leitura por request: 8 MiB e 250 ms de CPU/IO cooperativo, configurável apenas no startup dentro de teto seguro.

Eventos recentes usam tail binário em blocos e parsing reverso de linhas completas. Filtros que exigem busca histórica usam streaming binário por páginas, sem carregar o arquivo. Arquivos grandes retornam `partial=true` e cursor continuável quando atingem orçamento.

### 7.1 Cursor compatível com JSONL

Cursor opaco codifica, no mínimo: versão do cursor, source lógico, identidade estável do arquivo obtida no startup, offset byte da próxima busca, direção, tamanho/mtime observado e hash dos filtros normalizados. Deve ser autenticado com segredo efêmero do processo ou integridade equivalente sem expor path.

Se o arquivo encolher, for substituído, o filtro mudar ou o offset ficar inválido, retornar `409 CURSOR_STALE` com orientação para reiniciar a paginação. Crescimento append-only após o offset é permitido. O cursor nunca contém path arbitrário e nunca autoriza escolher arquivo.

Ordenação de resposta: mais recente primeiro. `next_cursor` continua em direção ao passado. Não usar número de linha como identidade estável, pois o custo de localizar linhas cresce e rotação futura o invalida.

## 8. Contrato de health

```json
{
  "ok": true,
  "status": "OK",
  "module": "trade_lifecycle_shadow_observability",
  "version": "1.0.0-SHADOW",
  "mode": "SHADOW",
  "enabled": true,
  "operational_authority": false,
  "broker_access": false,
  "registry_write_access": false,
  "lifecycle_write_access": false,
  "execution_control": false,
  "automatic_repair": false,
  "adapter": {},
  "lifecycle": {},
  "persistence": {},
  "last_event_at": null,
  "last_reconciliation_at": null,
  "restart": {"activity_after_restart": "UNKNOWN"},
  "warnings": [],
  "errors": []
}
```

Estados:

- `OK`: habilitada, readers operacionais, state válido e fontes existentes/consistentes dentro da tolerância; ausência legítima antes da primeira atividade pode ser OK com warning quando Adapter também não produziu evidência;
- `DEGRADED`: uma fonte inválida/stale, linhas inválidas, última linha parcial persistente, divergência state/journal, Lifecycle indisponível ou rebuild parcial, mas ao menos uma fonte útil permanece;
- `UNAVAILABLE`: módulo não consegue ler nenhuma fonte necessária, configuração de paths é inválida ou erro interno impede resposta útil;
- `DISABLED`: feature flag da Observability ou Adapter desabilitada; `ok=true` para funcionamento técnico, `enabled=false`, sem implicar saúde operacional.

Falha da Observability nunca derruba runtime, muda health global de execução ou bloqueia ordens. O endpoint continua estruturado; o HTTP comunica disponibilidade da consulta, não autoridade de trading.

## 9. Contrato de metrics

```json
{
  "ok": true,
  "status": "OK|PARTIAL|DISABLED|UNAVAILABLE",
  "module": "trade_lifecycle_shadow_observability",
  "version": "1.0.0-SHADOW",
  "mode": "SHADOW",
  "as_of": "ISO-8601 UTC",
  "partial": false,
  "events": {"observed": 0, "applied": 0, "noop": 0, "duplicate": 0, "blocked": 0, "errors": 0, "invalid": 0},
  "reconciliation": {"attempted": 0, "matches": 0, "divergences": 0, "missing_in_registry": 0, "missing_in_lifecycle": 0},
  "divergences": {"open": 0, "resolved": 0, "high": 0, "medium": 0, "low": 0, "unknown_resolution": 0},
  "external_positions": {"observed": 0, "currently_known": 0},
  "persistence": {"invalid_lines": 0, "truncated_lines": 0, "last_state_load": null, "rebuild_count": 0},
  "provenance": {},
  "warnings": [],
  "errors": []
}
```

Mapeamento:

- state fornece diretamente `observed`, `applied`, `duplicate`, `blocked`, `errors`, `reconciled`/`attempted` e `divergences`, sempre marcado `source=adapter_state`;
- event journal reconstrói `observed` journalizado, `applied`, `duplicate`, `blocked`, `noop` e invalid lines; não reconstrói erros não journalizados;
- divergence journal reconstrói grupos, severidades e categorias missing quando presentes;
- `matches`, missing, external atualmente podem ser `null`/`unknown` se a evidência real não os suportar;
- `invalid` representa contratos/linhas inválidos observáveis, não deve ser inventado a partir de `blocked`;
- severidade real `CRITICAL` mapeia para `high`, `WARNING` para `medium`; `low` só com evidência explícita futura;
- métricas internas da Observability ficam em namespace separado, conforme seção 17.

Contadores com cobertura diferente nunca são somados cegamente. O payload expõe proveniência, cobertura temporal e discrepância.

## 10. Contrato de events

Filtros permitidos: `lifecycle_id`, `trade_id`, `event_id`, `bot`, `setup`, `symbol`, `side`, `event_type`, `status`, `date_from`, `date_to`, `limit`, `cursor`.

```json
{
  "ok": true,
  "status": "OK",
  "items": [{
    "timestamp": "ISO-8601 UTC",
    "event_id": "string",
    "event_type": "string",
    "lifecycle_id": "string",
    "trade_id": null,
    "bot": null,
    "setup": null,
    "symbol": null,
    "side": null,
    "identity_source": "string",
    "status": "string",
    "summary": {},
    "external_position": false
  }],
  "page": {"limit": 50, "returned": 0, "next_cursor": null, "partial": false},
  "warnings": [],
  "errors": []
}
```

Datas são ISO-8601 com timezone; `date_from <= date_to`; strings de filtro têm tamanho máximo 128 e enumerações são allowlist. Campos ausentes permanecem `null`, sem inferência por símbolo/lado. Cada item passa por projeção allowlist e sanitização recursiva.

Nunca expor secrets, tokens, headers, credenciais, autenticação, payload integral, `manager_result` integral, paths internos ou dados brutos desnecessários da conta BingX.

## 11. Contrato de divergences

Campos mínimos normalizados:

```json
{
  "divergence_id": "string",
  "lifecycle_id": "string",
  "trade_id": "string|null",
  "field": "string",
  "registry_value": null,
  "lifecycle_value": null,
  "severity": "HIGH|MEDIUM|LOW",
  "first_seen_at": "ISO-8601 UTC",
  "last_seen_at": "ISO-8601 UTC",
  "occurrences": 1,
  "resolved": null,
  "resolved_at": null,
  "source": "SHADOW_RUNTIME_ADAPTER",
  "category": "FIELD_MISMATCH"
}
```

Identidade estrutural é SHA-256 canônico de `lifecycle_id + trade_id + field + canonical(registry_value) + canonical(lifecycle_value) + category`, sem timestamps. O `key` real do Adapter pode ser preservado internamente como evidência, mas não substitui a regra versionada futura. Valores são normalizados de forma determinística e sanitizados antes da resposta.

Repetições com a mesma identidade incrementam `occurrences`, atualizam `last_seen_at` apenas na projeção em memória e preservam `first_seen_at`. Como o Adapter suprime repetições pela chave durante o processo, `occurrences` significa ocorrências persistidas, não número real de reconciliations.

Resolução é somente observada. Só pode ser `resolved=true` quando uma evidência persistida posterior, da mesma identidade e rodada completa, declarar match/ausência da diferença. Evidência parcial, desaparecimento da janela, restart, ausência de nova linha ou health OK não resolve divergência. Com schema atual, a regra normal é `resolved=null` e `resolved_at=null`.

- `MISSING_IN_REGISTRY`: lifecycle identificado existe na evidência Shadow e uma rodada completa, identificada, declara ausência no snapshot Registry;
- `MISSING_IN_LIFECYCLE`: trade Registry identificado por IDs fortes e uma rodada completa declara ausência no Lifecycle;
- nunca inferir missing por não aparecer numa página limitada;
- external positions usam categoria `EXTERNAL_POSITION`, coleção/contadores separados e não entram em matches ou divergências operacionais;
- Observability não grava resolução no Lifecycle, Registry ou journal.

Filtros adicionais: `field`, `severity`, `resolved`, `category`, além dos filtros identitários, datas, limit e cursor. Paginação e limites são os da seção 7.

## 12. Contrato de reconciliation

Na V1, reconciliation é GET e apresenta apenas o último resultado conhecido persistido:

```json
{
  "ok": true,
  "status": "MATCH|DIVERGENCE|PARTIAL|UNKNOWN|NO_EVIDENCE",
  "known_at": null,
  "reconciliation_id": null,
  "compared": null,
  "matches": null,
  "divergences": 0,
  "errors": 0,
  "missing_in_registry": 0,
  "missing_in_lifecycle": 0,
  "sample": [],
  "sample_truncated": false,
  "evidence_quality": "INSUFFICIENT",
  "warnings": []
}
```

O schema atual não persiste rodada, matches, quantidade comparada nem horário de reconciliação sem divergência. Portanto esses campos devem permanecer `null`/`UNKNOWN`, e o endpoint não pode alegar um resumo completo. Uma amostra contém no máximo 20 divergências sanitizadas.

Não é seguro executar `reconcile_all` em request HTTP: ele percorre o snapshot, chama comparações que persistem divergências/snapshot no Lifecycle e persiste state/journal no Adapter. Isso viola GET sem efeitos colaterais, pode custar O(n) e disputa locks. A V1 somente apresenta resultado persistido; uma futura reconciliação ativa exigirá sprint e contrato próprios fora do request.

## 13. Endpoints futuros

Todos são GET, sem escrita, sem rede e fail-open em relação ao runtime.

| Endpoint | Função | Parâmetros | Sucesso | Falhas de consulta |
|---|---|---|---|---|
| `GET /shadowhealth` | `get_health()` | nenhum | 200 | 200 DISABLED/DEGRADED; 503 UNAVAILABLE |
| `GET /shadowmetrics` | `get_metrics()` | nenhum na V1 | 200 | 200 PARTIAL/DISABLED; 503 sem fonte útil |
| `GET /shadowevents` | `list_events(...)` | filtros da seção 10 | 200 | 400 filtro; 409 cursor stale; 413 limite/payload; 503 reader indisponível |
| `GET /shadowdivergences` | `list_divergences(...)` | filtros da seção 11 | 200 | 400/409/413/503 equivalentes |
| `GET /shadowreconciliation` | `get_reconciliation_summary()` | nenhum | 200 | 200 NO_EVIDENCE/DISABLED; 503 reader indisponível |

Arquivo inexistente retorna 200, lista vazia ou `NO_EVIDENCE`, warning e persistence `MISSING`; não retorna 404 e não cria arquivo. Desabilitado retorna 200 com `enabled=false`, `status=DISABLED` e coleções vazias. Exceções são sanitizadas; 500 fica reservado a defeito inesperado da integração HTTP, ainda sem propagação ao runtime.

`POST`, `PUT`, `PATCH` e `DELETE` não terão rotas; Flask responderá 405. Não haverá parâmetros `repair`, `replay`, `reconcile`, `refresh`, `path`, `file`, `persist` ou `commit`.

## 14. Concorrência

- Adapter escrevendo JSONL: reader considera apenas linhas terminadas por newline; última linha incompleta é ignorada e reavaliada depois;
- append concorrente: capturar tamanho inicial e nunca ler além dele na página atual;
- state substituído por `os.replace`: abrir pelo nome e ler uma cópia; se metadados mudarem durante parse, repetir uma vez; nunca abrir `.tmp`;
- múltiplas requests: readers não mutam fonte; cache usa lock próprio curto ou snapshots imutáveis, sem lock do Adapter;
- restart durante leitura: descritor aberto pode apontar para arquivo anterior; concluir página com identidade capturada ou devolver cursor stale, sem combinar duas versões;
- JSON válido porém semanticamente incompleto é isolado como invalid record;
- não depender de `_lock`, `_seen`, `_divergence_keys`, `_metrics` ou qualquer estrutura privada do Adapter.

## 15. Performance

Metas conservadoras em disco local, p95, sem rebuild integral:

| Operação | Meta p95 | Trabalho máximo normal |
|---|---:|---|
| health | 50 ms | stat + state pequeno + health providers |
| metrics | 100 ms | state/cache; sem scan integral |
| eventos recentes | 150 ms | tail até 50 itens/8 MiB |
| divergências | 200 ms | cache/tail agrupado limitado |
| reconciliation | 100 ms | snapshot derivado/cache |

Cache somente leitura e descartável:

- state: chave por versão lógica, mtime, tamanho e conteúdo validado; TTL máximo 2 s;
- tail de journals: chave por identidade, tamanho, mtime, cursor e hash de filtros; TTL máximo 5 s;
- agregados: chave por identidade/tamanho/mtime e versão do agregador; TTL máximo 10 s;
- invalidar se tamanho diminuir, mtime regredir/mudar inesperadamente, schema/versão mudar, cursor não corresponder ou startup mudar;
- limitar cache por entradas e bytes (sugestão: 128 entradas/16 MiB), com LRU;
- cache nunca é persistido, nunca é autoridade e resposta informa `as_of`/`cached`.

## 16. Segurança

- allowlist de campos de saída e denylist recursiva case-insensitive para chaves como `password`, `secret`, `token`, `authorization`, `cookie`, `api_key`, `apikey`, `private_key`, `credential`, `headers`;
- máximo de string 4 KiB, profundidade 8, 100 elementos por coleção e linha 256 KiB;
- valores excedentes são substituídos por marcador e tamanho original, nunca cortados em meio de UTF-8;
- erros expõem código e mensagem segura, não traceback nem path absoluto;
- paths são resolvidos uma vez no startup a partir da configuração existente, canonicalizados e verificados dentro do diretório Shadow permitido;
- requests nunca fornecem path, glob, nome de arquivo ou offset cru;
- filtros têm allowlist, tipos, enumerações, timezone, tamanho e cardinalidade validados;
- cursor é opaco, íntegro, limitado em tamanho e vinculado a source/filtros;
- resposta é interrompida antes de 2 MiB com `partial=true` e cursor;
- nenhuma importação de Broker, exchange, HTTP client, Registry mutável ou `main` no módulo;
- sanitização ocorre antes de cachear itens públicos, evitando guardar payload sensível desnecessário.

## 17. Observabilidade da própria Observability

Namespace separado `observability_internal`:

```json
{
  "requests": 0,
  "request_errors": 0,
  "journal_read_errors": 0,
  "invalid_json_lines": 0,
  "cache_hits": 0,
  "cache_misses": 0,
  "last_successful_read": null,
  "last_error": null
}
```

Esses contadores são de processo, não persistidos na V1, e nunca são somados ou confundidos com trading, Adapter ou Lifecycle. Mensagens são sanitizadas e `last_error` não contém path ou conteúdo bruto.

## 18. Testes obrigatórios futuros

- arquivos ausentes e vazios;
- state JSON inválido, schema inesperado e state válido;
- JSONL parcialmente inválido e última linha incompleta;
- linha acima de 256 KiB e truncamento UTF-8 seguro;
- arquivos grandes sem leitura irrestrita;
- limit default 50, máximo 200 e rejeição acima do máximo;
- todos os filtros, combinações, datas e normalização;
- paginação sem duplicar/omitir dentro de snapshot estável;
- cursor adulterado, stale, arquivo crescido, truncado e substituído;
- sanitização por chave, profundidade, strings, coleções e payload;
- external positions segregadas;
- divergências repetidas agrupadas;
- divergência resolvida com evidência suficiente e resolução unknown sem ela;
- MISSING_IN_REGISTRY e MISSING_IN_LIFECYCLE apenas com rodada completa;
- rebuild limitado após restart e resultado partial por orçamento;
- concorrência de leitura/escrita e `os.replace` do state;
- múltiplos readers simultâneos;
- health OK, DEGRADED, UNAVAILABLE e DISABLED;
- Adapter desabilitado e Lifecycle indisponível;
- ausência de Broker/import de Broker;
- ausência de escrita em todos os arquivos e ausência de rede;
- endpoints GET, contratos/status HTTP e 405 para métodos de escrita;
- arquivo inexistente retornando coleção vazia/NO_EVIDENCE;
- fail-open sem alterar health ou execução do runtime;
- cache hit/miss/invalidação e teto de memória;
- regressão da suíte completa, sempre com rede bloqueada antes dos imports.

## 19. Critérios de aceitação

- somente leitura comprovada por testes de filesystem;
- `operational_authority`, `broker_access`, `registry_write_access`, `lifecycle_write_access`, `execution_control` e `automatic_repair` sempre false;
- nenhuma importação de Broker, Registry mutável ou cliente de rede;
- nenhuma escrita no Registry, Lifecycle, Adapter state ou journals;
- nenhuma chamada BingX ou efeito em execução;
- memória, linha, resposta, tempo e cache limitados;
- restart coerente com proveniência e lacunas explícitas;
- JSON/linha inválidos isolados;
- dados sensíveis sanitizados e paths não expostos;
- external positions fora das estatísticas operacionais;
- testes completos verdes e rede bloqueada;
- auditoria do CTO;
- nenhum commit antes da aprovação.

## 20. Sequência de implementação futura

### Fase A — módulo puro

- readers limitados;
- sanitização e validação;
- agregação e proveniência;
- contratos públicos;
- cache descartável;
- testes unitários sem rede/escrita.

### Fase B — auditoria do CTO

- auditar autoridade, schemas, limites, restart e exposição de dados;
- decidir se o Adapter ganhará, em sprint separada, boot ID e journal de reconciliação.

### Fase C — HTTP

- endpoints GET finos em `main.py`;
- testes HTTP, 405 e fail-open.

### Fase D — encerramento

- auditoria final;
- suíte completa segura;
- commit, push e deploy apenas com autorizações explícitas e separadas.

## 21. Respostas às questões arquiteturais

1. **O state atual é suficiente para restart?** Não. Só contém versão, atualização e sete contadores; não é carregado pelo Adapter e pode ser sobrescrito após restart.
2. **O Adapter persiste seen event IDs?** Não. `_seen` existe somente em memória.
3. **O Adapter persiste divergence keys?** Não. `_divergence_keys` existe somente em memória; o journal contém `key`, mas o Adapter não o recarrega.
4. **Como evitar duplicidade após restart?** Hoje, apenas a idempotência persistida do Lifecycle (`event_keys`/`blocked_event_keys`) pode impedir parte das reaplicações. A lacuna do Adapter deve ser corrigida em sprint própria; Observability apenas a evidencia.
5. **A Observability reconstrói deduplicação?** Não. Agrupa evidências para exibição, mas nunca alimenta o Adapter nem decide aplicação.
6. **Como identificar resolução?** Somente por evidência persistida posterior, completa e correlacionada à mesma identidade/rodada. O schema atual geralmente não permite; usar `resolved=null`.
7. **É seguro executar `reconcile_all` no HTTP?** Não. Além do custo, o caminho atual persiste divergências e snapshots, portanto tem efeitos colaterais.
8. **Limites de eventos?** Default 50; máximo 200.
9. **Paginação JSONL?** Cursor opaco por offset byte, direção reversa, identidade/tamanho/mtime e hash dos filtros; invalidar em substituição/truncamento.
10. **Como impedir leitura arbitrária?** Paths resolvidos/canonicalizados apenas no startup dentro do diretório permitido; nenhuma função HTTP aceita path; cursor não expõe nem seleciona arquivo.
11. **Como separar external positions?** Classificação explícita por evento/lifecycle external, namespace e contadores próprios; nunca atribuir bot/setup/trade ownership nem incluí-las em convergência operacional.

## 22. Limitações e decisões que exigem sprint futura

Para que reconciliation e restart sejam completos, o produtor de evidência precisaria futuramente, após aprovação específica, persistir boot ID, seen keys ou cursor, início/fim de rodada de reconciliação, matches, missing dos dois lados, ocorrências e resoluções. Esta especificação não autoriza tais mudanças e não altera o Trade Lifecycle Shadow Runtime Adapter V1.

Até lá, toda resposta deve preferir `unknown`, `null`, `partial=true` e warnings a fabricar precisão. Ausência de evidência não é evidência de convergência, resolução ou ausência de posição.

