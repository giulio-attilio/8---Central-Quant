# Trade Lifecycle Shadow Runtime Adapter V1 — Especificação

Status: DRAFT
Versão: 1.0
Responsável: CTO
Implementação: Codex

---

## Objetivo

Conectar fatos confirmados do runtime atual ao Trade Lifecycle Manager V3 em Shadow Mode, preservando o Trade Registry como autoridade operacional vigente.

## Autoridade

O Adapter observa, normaliza, encaminha, compara e registra evidências. Não autoriza, nega, bloqueia ou modifica execução, risco, bots, Broker, ordens, proteção ou Trade Registry.

## Contratos obrigatórios

- Feature flag `TRADE_LIFECYCLE_SHADOW_RUNTIME_ADAPTER_ENABLED`, desligada por padrão.
- APIs públicas fail-open com `production_blocked=False`.
- Identidade priorizada por trade ID, identidade persistida, registry ID, execution ID, decision ID e signal ID.
- Fallback somente determinístico e nunca baseado apenas em símbolo e lado.
- Event ID factual preservado; na ausência, ID Central determinístico sem `observed_at`, UUID aleatório ou memória do processo.
- Deduplicação thread-safe.
- Evidências append-only e estado por substituição atômica.
- Reconciliação somente leitura, sem reparo automático.
- Posições externas permanecem sem ownership de bot.

## Isolamento operacional

O Adapter não acessa Broker, exchange, rede, Redis, Telegram ou Render. Seu retorno nunca participa de ALLOW/DENY nem altera o resultado oficial. Qualquer falha interna é registrada e devolvida como resultado estruturado sem interromper produção.

## Interface

`TradeLifecycleShadowRuntimeAdapter` oferece `observe_event`, `reconcile_trade`, `reconcile_all`, `get_health` e `get_metrics`.

## Persistência

Os journals Shadow são lazy, append-only e separados do Registry. O estado de métricas usa escrita atômica. Toda escrita é protegida pelo lock do Adapter e falhas de I/O permanecem isoladas.

## Critérios de aceitação

Import seguro; flag desligada; zero autoridade operacional; identidade independente por robô; posição externa segregada; event ID determinístico; idempotência concorrente; reconciliação somente leitura; ausência de Broker/rede/Registry write; persistência lazy; falha Shadow sem impacto operacional.
