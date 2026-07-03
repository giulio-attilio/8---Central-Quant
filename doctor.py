#!/usr/bin/env python3
# ==============================================================================
# CENTRAL QUANT DOCTOR V2
# Versão: 2026-07-03-CENTRAL-DOCTOR-V2-TRADE-REGISTRY
#
# Uso:
#   python doctor.py
#
# Objetivo:
# - Reduzir falsos positivos da V1.
# - Validar sintaxe, estrutura, arquitetura e integração básica da Central Quant.
# - Diferenciar ambiente LOCAL de RENDER.
# - Não reprovar deploy por variáveis de ambiente ausentes localmente.
# - Marcar Turtle sem Risk obrigatório como principal pendência real.
# ==============================================================================

import ast
import os
import py_compile
import sys
from pathlib import Path
from datetime import datetime


ROOT = Path(__file__).resolve().parent

CORE_FILES = [
    "main.py",
    "history_manager.py",
    "event_bus.py",
    "trade_registry.py",
]

BOT_FILES = [
    "bots/trendpro.py",
    "bots/donkey.py",
    "bots/cobra.py",
    "bots/meme.py",
    "bots/predator.py",
    "bots/turtle.py",
    "bots/falcon.py",
]

OPTIONAL_FILES = [
    "broker.py",
    "context_manager.py",
    "exchange_manager.py",
    "telegram_utils.py",
]

RISK_CRITICAL_BOTS = [
    "bots/donkey.py",
    "bots/turtle.py",
    "bots/predator.py",
    "bots/falcon.py",
]

ENV_RENDER_HINTS = [
    "RENDER",
    "RENDER_SERVICE_ID",
    "RENDER_EXTERNAL_URL",
]

LOCAL_OPTIONAL_ENVS = [
    "UPSTASH_REDIS_REST_URL",
    "UPSTASH_REDIS_REST_TOKEN",
    "CENTRAL_TELEGRAM_BOT_TOKEN",
    "CENTRAL_TELEGRAM_CHAT_ID",
    "ENABLE_REAL_TRADING",
    "EXECUTION_MODE",
]


def now():
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def is_render_env():
    return any(os.environ.get(k) for k in ENV_RENDER_HINTS)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")
    except Exception:
        return ""


def exists(rel_path: str) -> bool:
    return (ROOT / rel_path).exists()


def check_syntax(rel_path: str):
    path = ROOT / rel_path
    if not path.exists():
        return False, "arquivo ausente"
    try:
        py_compile.compile(str(path), doraise=True)
        return True, "OK"
    except py_compile.PyCompileError as exc:
        return False, str(exc)


def parse_ast(rel_path: str):
    path = ROOT / rel_path
    if not path.exists():
        return None
    try:
        return ast.parse(read_text(path))
    except Exception:
        return None


def ast_function_names(rel_path: str):
    tree = parse_ast(rel_path)
    if tree is None:
        return set()
    funcs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.add(node.name)
    return funcs


def ast_route_paths(rel_path: str):
    tree = parse_ast(rel_path)
    if tree is None:
        return set()

    routes = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call):
                func = dec.func
                is_route = isinstance(func, ast.Attribute) and func.attr == "route"
                if is_route and dec.args:
                    arg = dec.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        routes.add(arg.value)
    return routes


def contains_any(rel_path: str, terms):
    text = read_text(ROOT / rel_path)
    return any(term in text for term in terms)


def ok_line(label, detail=""):
    return f"✅ {label}" + (f": {detail}" if detail else "")


def fail_line(label, detail=""):
    return f"❌ {label}" + (f": {detail}" if detail else "")


def warn_line(label, detail=""):
    return f"⚠️ {label}" + (f": {detail}" if detail else "")


def info_line(label, detail=""):
    return f"ℹ️ {label}" + (f": {detail}" if detail else "")


def bot_runtime_pattern(rel_path: str):
    text = read_text(ROOT / rel_path)
    funcs = ast_function_names(rel_path)

    has_threading = "threading.Thread" in text
    has_while_true = "while True" in text
    has_scanner_words = any(x in text.lower() for x in ["scanner", "scan", "varrer"])
    has_management_words = any(x in text.lower() for x in ["management", "gest", "manage", "posição", "posicao"])

    scanner_functions = [
        fn for fn in funcs
        if any(key in fn.lower() for key in ["scanner", "scan"])
    ]

    management_functions = [
        fn for fn in funcs
        if any(key in fn.lower() for key in ["management", "gest", "manage", "monitor"])
    ]

    return {
        "has_threading": has_threading,
        "has_while_true": has_while_true,
        "has_scanner_words": has_scanner_words,
        "has_management_words": has_management_words,
        "scanner_functions": scanner_functions,
        "management_functions": management_functions,
        "runtime_ok": has_threading and has_while_true and has_scanner_words,
    }


def risk_pattern(rel_path: str):
    text = read_text(ROOT / rel_path)

    has_route = "/can_open_trade" in text or "can_open_trade" in text
    has_http = "requests.post" in text or "requests.get" in text
    has_allow_deny = any(x in text for x in ["ALLOW", "DENY", "allowed", "denied", "bloque"])
    has_return_block = any(x in text for x in ["return False", "return None", "return {", "return decision"])
    has_symbol_side = "symbol" in text and "side" in text

    score = 0
    for item in [has_route, has_http, has_allow_deny, has_return_block, has_symbol_side]:
        if item:
            score += 20

    return {
        "has_route": has_route,
        "has_http": has_http,
        "has_allow_deny": has_allow_deny,
        "has_return_block": has_return_block,
        "has_symbol_side": has_symbol_side,
        "score": score,
        "ok": score >= 80,
    }


def main():
    errors = []
    warnings = []
    lines = []

    render = is_render_env()
    env_label = "RENDER" if render else "LOCAL"

    lines.append("🩺 CENTRAL DOCTOR V2 — CENTRAL QUANT")
    lines.append(f"Gerado em: {now()}")
    lines.append(f"Raiz: {ROOT}")
    lines.append(f"Ambiente detectado: {env_label}")
    lines.append("")

    lines.append("==============================")
    lines.append("1. ARQUIVOS PRINCIPAIS")
    lines.append("==============================")

    for rel in CORE_FILES:
        if exists(rel):
            lines.append(ok_line(rel))
        else:
            lines.append(fail_line(rel, "ausente"))
            errors.append(f"Arquivo principal ausente: {rel}")

    lines.append("")
    lines.append("==============================")
    lines.append("2. BOTS")
    lines.append("==============================")

    for rel in BOT_FILES:
        if exists(rel):
            lines.append(ok_line(rel))
        else:
            lines.append(warn_line(rel, "ausente"))
            warnings.append(f"Bot ausente: {rel}")

    lines.append("")
    lines.append("==============================")
    lines.append("3. SINTAXE PYTHON")
    lines.append("==============================")

    py_files = [rel for rel in CORE_FILES + BOT_FILES + OPTIONAL_FILES if exists(rel)]
    syntax_ok = 0

    for rel in py_files:
        ok, detail = check_syntax(rel)
        if ok:
            syntax_ok += 1
            lines.append(ok_line(rel, "OK"))
        else:
            short = detail.splitlines()[-1] if detail else "erro"
            lines.append(fail_line(rel, short))
            errors.append(f"Erro de sintaxe em {rel}: {detail}")

    lines.append("")
    lines.append("==============================")
    lines.append("4. MAIN / CENTRAL")
    lines.append("==============================")

    main_critical = [
        "BOT_CONFIGS",
        "central_exposure_snapshot",
        "GLOBAL_RISK_MAX_POSITIONS",
        "can_open_trade",
    ]

    main_expected = [
        "build_executive_report_daily",
        "build_executive_report_monthly",
        "central_daily_report_loop",
        "auditrisk",
        "central_watchdog_status",
    ]

    if exists("main.py"):
        for term in main_critical:
            ok = contains_any("main.py", [term])
            lines.append(ok_line(f"main.py contém {term}") if ok else fail_line(f"main.py contém {term}"))
            if not ok:
                errors.append(f"main.py não contém item crítico: {term}")

        for term in main_expected:
            ok = contains_any("main.py", [term])
            lines.append(ok_line(f"main.py contém {term}") if ok else warn_line(f"main.py contém {term}"))
            if not ok:
                warnings.append(f"main.py não contém item esperado: {term}")

        routes = ast_route_paths("main.py")
        expected_routes = ["/risk", "/bots", "/health", "/central"]
        for route in expected_routes:
            ok = route in routes
            lines.append(ok_line(f"rota {route}") if ok else warn_line(f"rota {route} não confirmada"))
            if not ok:
                warnings.append(f"Rota não confirmada no main.py: {route}")

        audit_routes = [r for r in routes if "audit" in r.lower() or "auditrisk" in r.lower()]
        if audit_routes:
            lines.append(ok_line("rota de auditoria", ", ".join(sorted(audit_routes))))
        else:
            lines.append(warn_line("rota /auditrisk não confirmada"))
            warnings.append("Rota /auditrisk não confirmada")

    lines.append("")
    lines.append("==============================")
    lines.append("5. HISTORY / EVENT BUS")
    lines.append("==============================")

    history_expected = [
        "HISTORY_EVENTS_FILE",
        "DECISION_LOG_FILE",
        "build_history_report",
        "build_export_payload",
        "log_event",
    ]

    if exists("history_manager.py"):
        for term in history_expected:
            ok = contains_any("history_manager.py", [term])
            lines.append(ok_line(f"history_manager.py contém {term}") if ok else warn_line(f"history_manager.py contém {term}"))
            if not ok:
                warnings.append(f"History sem item esperado: {term}")

    if exists("event_bus.py"):
        for term in ["emit_from_http", "history_manager"]:
            ok = contains_any("event_bus.py", [term])
            lines.append(ok_line(f"event_bus.py contém {term}") if ok else warn_line(f"event_bus.py contém {term}"))
            if not ok:
                warnings.append(f"Event Bus sem item esperado: {term}")

    lines.append("")
    lines.append("==============================")
    lines.append("5B. TRADE REGISTRY")
    lines.append("==============================")

    trade_registry_expected = [
        "TRADE_REGISTRY_FILE",
        "load_registry",
        "save_registry",
        "make_trade_id",
        "register_open_trade",
        "update_trade",
        "close_trade",
        "get_open_trades",
        "get_trade_registry_snapshot",
        "reset_trade_registry",
    ]

    if exists("trade_registry.py"):
        funcs = ast_function_names("trade_registry.py")

        for term in trade_registry_expected:
            if term == "TRADE_REGISTRY_FILE":
                ok = contains_any("trade_registry.py", [term])
            else:
                ok = term in funcs

            lines.append(ok_line(f"trade_registry.py contém {term}") if ok else fail_line(f"trade_registry.py contém {term}"))

            if not ok:
                errors.append(f"trade_registry.py não contém item obrigatório: {term}")

        registry_text = read_text(ROOT / "trade_registry.py")
        registry_safety_checks = [
            ("data/trade_registry.json", ["trade_registry.json"]),
            ("lock/thread-safe", ["threading.Lock", "_lock"]),
            ("gravação atômica", ["os.replace", ".tmp"]),
            ("open_trades", ["open_trades"]),
            ("closed_trades", ["closed_trades"]),
        ]

        for label, terms in registry_safety_checks:
            ok = any(term in registry_text for term in terms)
            lines.append(ok_line(f"trade_registry.py segurança {label}") if ok else warn_line(f"trade_registry.py segurança {label} não confirmada"))
            if not ok:
                warnings.append(f"Trade Registry: segurança não confirmada: {label}")

    else:
        lines.append(fail_line("trade_registry.py", "ausente"))
        errors.append("Arquivo principal ausente: trade_registry.py")

    lines.append("")
    lines.append("==============================")
    lines.append("6. RISK MANAGER NOS BOTS")
    lines.append("==============================")

    for rel in RISK_CRITICAL_BOTS:
        if not exists(rel):
            lines.append(warn_line(rel, "arquivo ausente"))
            warnings.append(f"{rel}: arquivo ausente")
            continue

        rp = risk_pattern(rel)

        if rp["ok"]:
            lines.append(ok_line(rel, f"Risk obrigatório confirmado ({rp['score']}/100)"))
        else:
            lines.append(fail_line(rel, f"Risk obrigatório NÃO confirmado ({rp['score']}/100)"))
            if "turtle" in rel:
                warnings.append(f"{rel}: integração obrigatória com /can_open_trade pendente")
            else:
                errors.append(f"{rel}: integração obrigatória com /can_open_trade não confirmada")

        detail = (
            f"rota={rp['has_route']} http={rp['has_http']} "
            f"allow/deny={rp['has_allow_deny']} block={rp['has_return_block']} "
            f"symbol/side={rp['has_symbol_side']}"
        )
        lines.append(info_line(f"detalhe {rel}", detail))

    lines.append("")
    lines.append("==============================")
    lines.append("7. RUNTIME DOS BOTS")
    lines.append("==============================")

    for rel in BOT_FILES:
        if not exists(rel):
            continue

        pattern = bot_runtime_pattern(rel)

        if pattern["runtime_ok"]:
            lines.append(ok_line(rel, "runtime/threads/scanner confirmados"))
        else:
            lines.append(info_line(rel, "runtime não totalmente confirmado por análise estática"))

        if pattern["scanner_functions"]:
            lines.append(info_line(f"{rel} scanners", ", ".join(pattern["scanner_functions"][:8])))
        if pattern["management_functions"]:
            lines.append(info_line(f"{rel} gestão", ", ".join(pattern["management_functions"][:8])))

    lines.append("")
    lines.append("==============================")
    lines.append("8. AMBIENTE")
    lines.append("==============================")

    if render:
        lines.append(ok_line("Ambiente Render detectado"))
        for name in LOCAL_OPTIONAL_ENVS:
            configured = bool(os.environ.get(name))
            if configured:
                lines.append(ok_line(name, "configurada"))
            else:
                lines.append(warn_line(name, "não configurada no Render"))
                warnings.append(f"Variável ausente no Render: {name}")
    else:
        lines.append(ok_line("Ambiente local detectado"))
        lines.append(info_line("Variáveis Render", "ignoradas localmente; serão validadas no Render"))
        for name in LOCAL_OPTIONAL_ENVS:
            configured = bool(os.environ.get(name))
            lines.append(("✅" if configured else "ℹ️") + f" {name}: " + ("configurada localmente" if configured else "não configurada localmente"))

    lines.append("")
    lines.append("==============================")
    lines.append("9. DIAGNÓSTICO FINAL")
    lines.append("==============================")

    score = 100
    score -= len(errors) * 20
    score -= len(warnings) * 2
    score = max(0, min(100, score))

    lines.append(f"Sintaxe OK: {syntax_ok}/{len(py_files)} arquivos")
    lines.append(f"Erros críticos: {len(errors)}")
    lines.append(f"Warnings: {len(warnings)}")
    lines.append(f"Score: {score}/100")
    lines.append("")

    if errors:
        status = "❌ STATUS: PROJETO NÃO APTO PARA DEPLOY"
    elif any("turtle.py" in w and "can_open_trade" in w for w in warnings):
        status = "🟡 STATUS: APTO PARA DEPLOY COM TURTLE DESABILITADO"
    elif score >= 90:
        status = "🟢 STATUS: PROJETO APTO PARA DEPLOY"
    else:
        status = "🟡 STATUS: APTO PARA TESTE, REVISAR WARNINGS"

    lines.append(status)

    if errors:
        lines.append("")
        lines.append("ERROS CRÍTICOS:")
        for item in errors:
            lines.append(f"- {item}")

    if warnings:
        lines.append("")
        lines.append("WARNINGS:")
        for item in warnings[:60]:
            lines.append(f"- {item}")

    lines.append("")
    lines.append("RECOMENDAÇÃO OPERACIONAL:")
    if any("turtle.py" in w and "can_open_trade" in w for w in warnings):
        lines.append("- Manter ENABLE_TURTLE=false até corrigir Risk obrigatório no Turtle.")
    if not errors:
        lines.append("- Deploy permitido se o objetivo não envolver reativar módulos pendentes.")
    else:
        lines.append("- Corrigir erros críticos antes de qualquer deploy.")

    output = "\n".join(lines)
    print(output)

    report_path = ROOT / "doctor_report.txt"
    try:
        report_path.write_text(output, encoding="utf-8")
        print(f"\nRelatório salvo em: {report_path}")
    except Exception:
        pass

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
