# Manifesto de Configuração Render: Piloto LIVE C3 (08/10/2026)

Este documento atesta a política de risco aprovada pelo usuário para o Piloto LIVE e descreve as exatas variáveis de ambiente que devem ser aplicadas no painel do Render para habilitar o modo real com "Fail-Closed" seguro.

## 1. Variáveis de Risco do Piloto (Aprovadas)
As seguintes variáveis devem ser adicionadas/modificadas no Render Environment:

```env
# Ativação do modo real de negociação
ENABLE_REAL_TRADING=true
BROKER_DRY_RUN=false
FALCON_MODE=LIVE

# Limites Operacionais do Piloto
PILOT_MAX_CAPITAL_USD=50
PILOT_MAX_POSITION_SIZE_CONTRACTS=1
PILOT_MAX_CONCURRENT_POSITIONS=1
PILOT_MAX_RISK_PER_TRADE_PERCENT=1.0

# Kill Switch (Se "TRUE", o sistema rejeita ordens novas e foca em fechar/proteger as antigas)
PILOT_KILL_SWITCH=FALSE
```

## 2. Ações que precedem o Deploy
De acordo com o plano C3 de segurança:
1. Este manifesto de limites é submetido à branch.
2. A branch é enviada (`git push`) para atualizar a PR.
3. O administrador da conta insere as variáveis acima no painel de ambiente do serviço do Render.
4. O Render puxa a versão da branch de release e o "Preflight de Produção" avalia se os gates estão abertos.

## 3. Comportamento Esperado do "Fail-Closed"
Qualquer tentativa de burlar o `PILOT_MAX_CONCURRENT_POSITIONS` falhará localmente (coordenador). Se o `PILOT_KILL_SWITCH` for alterado para `TRUE` via dashboard do Render, o serviço reiniciará e acordará no modo `DORMANT`, preservando os *disaster stops* das posições na corretora mas estritamente impedindo qualquer nova abertura.
