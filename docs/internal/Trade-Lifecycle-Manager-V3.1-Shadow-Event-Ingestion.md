# Trade Lifecycle Manager V3.1 — Shadow Event Ingestion Bridge

Status: DRAFT
Versão: 3.1.0
Última revisão: 11/07/2026
Responsável: CTO
Implementação: Codex
Aprovado: Não

---

## 1. Objetivo

O Shadow Event Ingestion Bridge recebe eventos explicitamente fornecidos por componentes da Central Quant e os encaminha ao Trade Lifecycle Manager V3 em Shadow Mode. Ele oferece uma fronteira única de validação, observabilidade e isolamento para uma integração futura, sem participar do runtime atual.

A versão é `3.1.0-SHADOW-BRIDGE`. Ela nasce desligada e não possui autoridade operacional.

## 2. Contexto arquitetural auditado

Os fatos de um lifecycle estão atualmente distribuídos. O Execution Orchestrator cria plano, identidade e chave idempotente, mas não produz todos os fatos de execução. O Execution Engine aplica gates e pode encaminhar execução. Broker produz evidências de submissão, fills, proteção e fechamento. Trade Registry mantém evidência lógica persistida. Falcon possui caminho direto ao Broker. `main.py` contém wrappers, awareness e reconciliação adicionais.

Consequentemente, nenhum desses pontos foi escolhido como produtor único nesta fase. O Bridge permanece isolado até que a instrumentação dos produtores seja especificada.

## 3. Responsabilidade dominante

Receber envelopes explícitos, validar seu contrato mínimo, preservar identidade e evidência, encaminhá-los ao Lifecycle Manager e traduzir o resultado sem impacto operacional.

Também registra tentativas, dead letters, métricas e falhas internas. A criação de lifecycle somente ocorre pela interface explícita destinada a essa finalidade.

## 4. Autoridade proibida

O Bridge não gera signal, não decide estratégia, não aprova ou nega trade, não calcula score, risco ou quantidade e não executa recovery. Não envia, cancela ou fecha ordens; não cria ou altera stops; não consulta Broker, BingX, exchange, Redis ou mensageria.

Ele não altera Registry ou bots, não infere ownership, não inventa `lifecycle_id` ou `trade_id` operacional e não pode bloquear Engine, Broker, Falcon ou runtime.

## 5. Interfaces públicas

- `emit_shadow_event(...)`: encaminha um evento canônico explicitamente fornecido.
- `emit_shadow_lifecycle_created(...)`: solicita explicitamente a criação de lifecycle Shadow.
- `shadow_bridge_health()`: expõe flags, contadores, erros, paths e health defensivo do Manager.
- `read_shadow_ingestion_log(limit=100)`: lê tentativas válidas do journal.
- `read_shadow_dead_letters(limit=100)`: lê dead letters.
- `reset_shadow_bridge_storage(confirm=False)`: remove somente os arquivos do Bridge após confirmação.

Nenhuma interface é chamada automaticamente.

## 6. Envelope canônico

Cada tentativa normaliza `schema_version`, versão do Bridge, Shadow Mode, correlation ID, tipo e ID externo do evento, IDs de lifecycle e trade, componente de origem, timestamps, evidência, payload, intenção de persistência e `operational_impact=false`.

O dict do chamador é preservado por cópia defensiva. `event_id`, `trade_id` e `occurred_at` externos são preservados quando fornecidos. O correlation ID local possui prefixo `CENTRAL-SHADOW-BRIDGE-`, não representa ownership e nunca substitui IDs operacionais.

## 7. Feature flags

- `TRADE_LIFECYCLE_SHADOW_INGESTION_ENABLED`: default `false`.
- `TRADE_LIFECYCLE_SHADOW_INGESTION_PERSIST`: default `true`.
- `TRADE_LIFECYCLE_SHADOW_DEAD_LETTER_ENABLED`: default `true`.

São reconhecidos `true`, `false`, `1`, `0`, `yes`, `no`, `on` e `off`. As flags são avaliadas em uso para permitir testes isolados. Quando a ingestão está desligada, o Bridge retorna `DISABLED`, não encaminha, não conta forwarding e não cria storage.

## 8. Journaling

O arquivo `trade_lifecycle_shadow_ingestion.jsonl` é append-only e criado somente na primeira escrita autorizada. Cada linha registra identidade da tentativa, origem, status, forwarding, deduplicação, bloqueio, dead letter, timestamps, duração, avisos, motivos e status do Manager.

O journal não é fonte de ownership nem substitui lifecycle ou Registry.

Falha ao persistir o journal de ingestão produz `status=ERROR`, atualiza o health e mantém `operational_impact=false`. O resultado do Manager é preservado: o fato pode já ter sido aplicado, deduplicado ou bloqueado mesmo quando o Bridge retorna erro por perda de observabilidade. O Bridge não reverte o Manager e não repete a chamada.

## 9. Dead letters

O arquivo `trade_lifecycle_shadow_dead_letters.jsonl` registra contratos inválidos, lifecycle inexistente, transição bloqueada, criação bloqueada e falhas internas. Cada registro possui motivo canônico, envelope, resultado do Manager, timestamp, `retry_scheduled=false` e `operational_impact=false`.

Não existe retry automático. Dead letter é evidência para auditoria e futura reconciliação, não autorização para nova ação.

Se a escrita do dead letter falhar, o resultado público passa a `ERROR`, preserva a classificação e o motivo original, mantém `dead_letter=true` e não agenda retry. A própria falha não cria outro dead letter recursivo.

A persistência do Bridge é observabilidade, não autoridade operacional. Sua falha é explicitamente visível, mas nunca altera o fluxo operacional já realizado.

## 10. Isolamento

O Bridge usa apenas biblioteca padrão e o Trade Lifecycle Manager V3. Não importa Broker, Exchange Manager, CCXT, `requests`, `main.py`, Trade Registry ou bots. Não cria thread, loop, worker ou servidor. Não acessa rede e não cria diretório durante import.

Toda falha normal retorna resultado estruturado. A barreira defensiva de exceções registra erro e mantém `operational_impact=false`.

## 11. Posições manuais

Uma posição externa somente pode ser apresentada pela criação explícita prevista pelo Manager. Ela permanece `MANUAL_POSITION_DETECTED`, sem `trade_id` operacional, bot, fill, outcome ou estatística. Símbolo e lado não comprovam ownership, e o Bridge não atribui posição externa ao Falcon.

## 12. Health

O health expõe estado da flag, contadores em memória, timestamps, último erro, paths lazy e notas de isolamento. O health do Lifecycle Manager é obtido defensivamente; sua falha não torna o Bridge indisponível.

Os contadores reiniciam com o processo e não possuem persistência própria nesta fase.

## 13. Rollout

O rollout da V3.1.0 limita-se a import e chamadas explícitas em testes. A flag permanece desligada por padrão. Nenhuma configuração de Render, rota, bot, Engine, Broker ou runtime é alterada.

Qualquer ativação futura exige definição dos produtores, mapeamento factual dos eventos, testes sem rede, auditoria de volume, estratégia de rollback e aprovação do CTO.

## 14. Limites da V3.1.0

A V3.1.0 não está integrada. Ela não observa automaticamente o sistema, não captura eventos do Broker, não reconstrói fatos ausentes, não agenda retry e não resolve divergências. Seus contadores são locais ao processo.

O Orchestrator não é fonte suficiente de todos os fatos. O Registry registra evidência lógica, mas não substitui fills. O Falcon ainda possui caminho direto ao Broker. `main.py` não é alterado nesta fase. Broker não será instrumentado diretamente sem desenho específico que preserve autoridade e segurança.

## 15. Plano da V3.1.1

A V3.1.1 escolherá e especificará os produtores de cada evento canônico. O trabalho deverá mapear intenção, submissão, fill, disaster stop, gestão, close e outcome às fontes factuais adequadas, incluindo o caminho próprio do Falcon.

Antes de integrar, deverá definir idempotência por produtor, ordenação, falhas, replay, compatibilidade com PAPER/VERIFY/LIVE, rollout por flag e critérios de desligamento. A integração não poderá transformar o Bridge em autoridade operacional nem fazer do Broker ou do Registry uma fonte única de todos os fatos.
