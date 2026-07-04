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

        allocations = []

        for item in weights:
            name = item.get("name")
            weight = item.get("suggested_weight_pct", 0) or 0
            allocated_capital = capital * weight / 100

            decision = decision_map.get(name, {})

            allocations.append({
                "name": name,
                "weight_pct": weight,
                "capital_allocated": round(allocated_capital, 2),
                "category": item.get("category"),
                "decision": decision.get("decision"),
                "reason": decision.get("reason"),
                "score": item.get("score"),
                "confidence": item.get("confidence"),
                "pnl_total_pct": item.get("pnl_total_pct"),
                "trades": item.get("trades"),
            })

        return {
            "ok": True,
            "version": "2026-07-03-PORTFOLIO-MANAGER-V1",
            "generated_at": weights_payload.get("generated_at"),
            "mode": "OBSERVATION_ONLY",
            "capital": capital,
            "portfolio_health": weights_payload.get("portfolio_health", {}),
            "allocations": allocations,
            "notes": [
                "Portfolio Manager V1 apenas observa e calcula alocação teórica.",
                "Ainda não altera lote, execução ou risco real.",
                "Usa pesos do Portfolio Weights e decisões do Decision Engine.",
            ],
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }