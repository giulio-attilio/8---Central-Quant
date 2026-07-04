def capital_check(capital=10000, bot=None, required=0, risk=0):
    try:
        import bot_exposure_manager

        exposure_payload = bot_exposure_manager.bot_exposure_manager(capital=capital)
        exposures = exposure_payload.get("exposures", [])

        target = None
        for item in exposures:
            if str(item.get("name", "")).upper() == str(bot or "").upper():
                target = item
                break

        if not target:
            return {
                "ok": False,
                "error": f"Bot não encontrado: {bot}",
            }

        capital_free = target.get("capital_free", 0) or 0
        risk_free = target.get("risk_free_usdt", 0) or 0

        required = float(required or 0)
        risk = float(risk or 0)

        capital_excess = max(0, required - capital_free)
        risk_excess = max(0, risk - risk_free)

        if required <= capital_free and risk <= risk_free:
            decision = "ALLOW"
            reason = "Capital livre e risco livre suficientes."
            suggested_required = required
            reduction_pct = 0.0

        elif risk <= risk_free and capital_free > 0:
            decision = "REDUCE_SIZE"
            reason = "Risco suficiente, mas capital solicitado excede o capital livre."
            suggested_required = capital_free
            reduction_pct = round((1 - capital_free / required) * 100, 2) if required else 0

        elif required <= capital_free and risk_free > 0:
            decision = "REDUCE_RISK"
            reason = "Capital suficiente, mas risco solicitado excede o risco livre."
            suggested_required = required
            reduction_pct = round((1 - risk_free / risk) * 100, 2) if risk else 0

        else:
            decision = "BLOCK"
            reason = "Capital e/ou risco insuficientes para abrir nova posição."
            suggested_required = min(required, capital_free)
            reduction_pct = 100.0

        return {
            "ok": True,
            "version": "2026-07-03-CAPITAL-ALLOCATOR-V1",
            "generated_at": exposure_payload.get("generated_at"),
            "mode": "OBSERVATION_ONLY",
            "bot": target.get("name"),
            "category": target.get("category"),
            "base_decision": target.get("decision"),
            "capital": capital,
            "capital_allocated": target.get("capital_allocated"),
            "capital_used": target.get("capital_used"),
            "capital_free": capital_free,
            "required_capital": required,
            "capital_excess": round(capital_excess, 2),
            "risk_free_usdt": risk_free,
            "required_risk_usdt": risk,
            "risk_excess_usdt": round(risk_excess, 2),
            "decision": decision,
            "reason": reason,
            "suggested_required_capital": round(suggested_required, 2),
            "suggested_reduction_pct": reduction_pct,
            "notes": [
                "Capital Allocator V1 apenas observa.",
                "Ainda não altera lote, execução ou risco real.",
                "Usa exposição por robô para decidir se um trade hipotético cabe.",
            ],
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }