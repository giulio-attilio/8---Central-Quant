# Manifesto de Configuração Render: Piloto LIVE C3 (08/10/2026)

Este documento atesta a política de risco aprovada pelo usuário para o Piloto LIVE e descreve as exatas variáveis de ambiente que devem ser aplicadas no painel do Render para habilitar o modo real com "Fail-Closed" seguro.

## 1. Variáveis de Risco do Piloto (Aprovadas)
As variáveis abaixo são as nativas da Central Quant e devem ser inseridas no Environment do Render:

```env
# Ativação do modo real de negociação (Flags OBRIGATÓRIAS)
ENABLE_REAL_TRADING=true
BROKER_DRY_RUN=false
FALCON_MODE=LIVE
CENTRAL_REAL_PILOT_ENABLED=true
CENTRAL_REAL_PILOT_GUARD_ENABLED=true
BROKER_REAL_PILOT_GUARD_ENABLED=true

# Limites Operacionais do Piloto (Risco e Capital)
FALCON_REAL_NOTIONAL_USDT=50
FALCON_REAL_MAX_POSITIONS=1

# Opcional para restringir o ambiente:
CENTRAL_REAL_PILOT_ALLOWED_BOTS=FALCON
```

## 2. Ações que precedem o Deploy
1. O administrador da conta insere as variáveis acima no painel de ambiente do serviço do Render.
2. O Render puxa a versão da branch de release e o "Preflight de Produção" (FALCON_REAL_PILOT_PREFLIGHT_CHECKLIST_V1) avalia se os gates estão abertos.

## 3. Comportamento Esperado do "Fail-Closed"
Qualquer tentativa de burlar o `FALCON_REAL_MAX_POSITIONS` falhará localmente no coordenador `trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1`. Se ocorrer falha de confirmação na BingX (Timeouts), o sistema entra em modo Recovery, bloqueando a abertura de novas ordens e mantendo exclusividade sobre o Stop Físico já confirmado.
