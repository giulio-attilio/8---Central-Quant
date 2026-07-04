def portfolio_manager(capital=10000):
    try:
        import analytics_engine

        weights_payload = analytics_engine.portfolio_weights()
        decision_payload = analytics_engine.decision_engine_observation()

        weights = weights_payload.get("weights", [])
        decisions = decision_payload.get("decisions", [])

        decision_map = {
            item.get("name"): item
            for item in decisions
        }

        risk_policy = {
            "CORE": {
                "max_risk_per_trade_pct": 1.00,
                "max_open_risk_pct": 4.00,
                "description": "Robô principal, pode receber maior risco controlado.",
            },
            "DEVELOPING": {
                "max_risk_per_trade_pct": 0.50,
                "max_open_risk_pct": 2.00,
                "description": "Robô em evolução, risco reduzido até ganhar amostra.",
            },
            "DEFENSIVE": {
                "max_risk_per_trade_pct": 0.25,
                "max_open_risk_pct": 1.00,
                "description": "Robô defensivo ou fraco, exposição mínima.",
            },
            "OBSERVATION": {
                "max_risk_per_trade_pct": 0.35,
                "max_open_risk_pct": 1.50,
                "description": "Robô em observação neutra.",
            },
        }

        allocations = []

        for item in weights:
            name = item.get("name")
            weight = item.get("suggested_weight_pct", 0) or 0
            category = item.get("category") or "OBSERVATION"

            allocated_capital = capital * weight / 100

            policy = risk_policy.get(category, risk_policy["OBSERVATION"])

            max_risk_per_trade_pct = policy.get("max_risk_per_trade_pct", 0)
            max_open_risk_pct = policy.get("max_open_risk_pct", 0)

            max_risk_per_trade_usdt = allocated_capital * max_risk_per_trade_pct / 100
            max_open_risk_usdt = allocated_capital * max_open_risk_pct / 100

            decision = decision_map.get(name, {})

            allocations.append({
                "name": name,
                "weight_pct": weight,
                "capital_allocated": round(allocated_capital, 2),
                "category": category,
                "decision": decision.get("decision"),
                "reason": decision.get("reason"),
                "score": item.get("score"),
                "confidence": item.get("confidence"),
                "pnl_total_pct": item.get("pnl_total_pct"),
                "trades": item.get("trades"),
                "risk_policy": {
                    "max_risk_per_trade_pct": max_risk_per_trade_pct,
                    "max_risk_per_trade_usdt": round(max_risk_per_trade_usdt, 2),
                    "max_open_risk_pct": max_open_risk_pct,
                    "max_open_risk_usdt": round(max_open_risk_usdt, 2),
                    "description": policy.get("description"),
                },
            })

        total_allocated = sum(item.get("capital_allocated", 0) for item in allocations)
        total_max_open_risk = sum(
            item.get("risk_policy", {}).get("max_open_risk_usdt", 0)
            for item in allocations
        )

        return {
            "ok": True,
            "version": "2026-07-03-PORTFOLIO-MANAGER-V2-RISK-LIMITS",
            "generated_at": weights_payload.get("generated_at"),
            "mode": "OBSERVATION_ONLY",
            "capital": capital,
            "total_allocated": round(total_allocated, 2),
            "total_max_open_risk_usdt": round(total_max_open_risk, 2),
            "total_max_open_risk_pct": round((total_max_open_risk / capital * 100), 2) if capital else 0,
            "portfolio_health": weights_payload.get("portfolio_health", {}),
            "risk_policy": risk_policy,
            "allocations": allocations,
            "notes": [
                "Portfolio Manager V2 apenas observa e calcula alocação e risco teórico.",
                "Ainda não altera lote, execução ou risco real.",
                "Limites de risco são definidos por categoria do robô.",
                "CORE recebe maior risco; DEVELOPING e DEFENSIVE recebem risco reduzido.",
            ],
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }