# Diagnóstico — Resumo diário automático desabilitado

Data: 16/07/2026  
Status: pendente de correção

## Sintoma

O resumo diário automático das 23:55 não está mais chegando.

## Evidência

O /health mostrou:

- auto_ceo_daily_enabled=false
- auto_daily_summaries_enabled=false
- daily_summary_manual_commands_available=true

## Leitura

O problema não parece ser Falcon, Telegram manual ou falha geral da Central.

O resumo automático está desligado por configuração/policy.

Automático: desligado.  
Manual: disponível.

## Correção planejada

Daily Summary Scheduler Restore V1

Objetivos:
1. Descobrir por que auto_daily_summaries_enabled está false.
2. Restaurar envio automático do resumo CEO às 23:55.
3. Manter política LIVE_ONLY para sinais/trades PAPER.
4. Permitir resumo diário informativo sem liberar spam de PAPER.
5. Adicionar health claro mostrando próximo horário do resumo.

## Regra operacional

Não implementar hoje.
Não fazer deploy hoje.
Planejar patch pequeno amanhã.

---

## Inspeção read-only — Daily Summary Scheduler Restore Inspection V1

Conclusão: o resumo automático das 23:55 está desativado por configuração intencional e também seria bloqueado pela política Telegram atual.

Causas encontradas:

1. CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED tem default false.
2. CENTRAL_AUTO_CEO_DAILY_ENABLED tem default false.
3. Mesmo ligando as flags, o CEO Daily atual usa:
   - bot=CENTRAL
   - event_type=AUTOMATIC_DAILY_SUMMARY
   - mode=PAPER
4. Essa combinação é bloqueada pelo LIVE_ONLY_POLICY.
5. O scheduler marca o resumo como enviado mesmo se o Telegram/policy bloquear o envio.
6. O horário usa igualdade exata 23:55, frágil após delay ou restart.

Correção planejada amanhã:

Daily Summary Scheduler Restore V1

Patch mínimo:
1. Manter CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED=false.
2. Tornar CENTRAL_AUTO_CEO_DAILY_ENABLED=true suficiente apenas para o CEO Central.
3. Criar evento específico CENTRAL_CEO_DAILY_SUMMARY.
4. Permitir no Telegram somente bot=CENTRAL + event_type=CENTRAL_CEO_DAILY_SUMMARY.
5. Não liberar AUTOMATIC_DAILY_SUMMARY PAPER dos bots.
6. Só marcar como enviado se o envio realmente retornar sucesso.
7. Tornar o horário tolerante: >= 23:55 e ainda não enviado hoje.
8. Expor no /health:
   - daily_summary_scheduler_enabled
   - daily_summary_next_run_at
   - daily_summary_last_run_at
   - daily_summary_last_error
   - daily_summary_policy_reason

Regra:
Não implementar em 16/07/2026.
Implementar em patch pequeno no próximo ciclo operacional.
