def bot_exposure_manager(capital=10000):
    try:
        import portfolio_manager

        pm_payload = portfolio_manager.portfolio_manager(capital=capital)
        allocations = pm_payload.get("allocations", [])

        exposures = []

        for item in allocations:
            allocated = item.get("capital_allocated", 0) or 0
            used_capital = 0.0
            used_risk = 0.0

            free_capital = allocated - used_capital

            risk_policy = item.get("risk_policy", {})
            max_open_risk_usdt = risk_policy.get("max_open_risk_usdt", 0) or 0
            free_risk = max_open_risk_usdt - used_risk

            exposures.append({
                "name": item.get("name"),
                "category": item.get("category"),
                "decision": item.get("decision"),
                "capital_allocated": round(allocated, 2),
                "capital_used": round(used_capital, 2),
                "capital_free": round(free_capital, 2),
                "max_open_risk_usdt": round(max_open_risk_usdt, 2),
                "risk_used_usdt": round(used_risk, 2),
                "risk_free_usdt": round(free_risk, 2),
                "usage_pct": round((used_capital / allocated * 100), 2) if allocated else 0,
                "risk_usage_pct": round((used_risk / max_open_risk_usdt * 100), 2) if max_open_risk_usdt else 0,
            })

        return {
            "ok": True,
            "version": "2026-07-03-BOT-EXPOSURE-MANAGER-V1",
            "generated_at": pm_payload.get("generated_at"),
            "mode": "OBSERVATION_ONLY",
            "capital": capital,
            "portfolio_health": pm_payload.get("portfolio_health", {}),
            "exposures": exposures,
            "notes": [
                "V1 assume capital utilizado e risco utilizado como zero.",
                "Próxima versão deve ler posições abertas reais da Central.",
                "Este módulo prepara o Capital Allocator.",
            ],
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }