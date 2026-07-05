# -*- coding: utf-8 -*-
"""
Memory Profiler V1.3.1.1 — Central Quant
Versão: 2026-07-05-MEMORY-PROFILER-V1.3.1.1

Correção V1.3.1:
- /memory Telegram: texto leve, 1 snapshot.
- /memory HTTP/JSON: JSON leve, 1 snapshot.
- build_memory_json() NÃO chama build_memory_report().
- legacy_memory removido do JSON padrão.
- /memorylegacy deve ficar separado no main.py, se quiser comparar.
- /memorydeep continua disponível apenas sob demanda.

Arquivo:
    memory_profiler_v1.py
"""

import os
import gc
import json
import time
import threading
import traceback
from datetime import datetime
from collections import Counter

VERSION = "2026-07-05-MEMORY-PROFILER-V1.3.1.1"

DATA_DIR = os.environ.get("CENTRAL_DATA_DIR", "/opt/render/project/src/data")
SNAPSHOT_FILE = os.path.join(DATA_DIR, "memory_profiler_snapshots.jsonl")
STATE_FILE = os.path.join(DATA_DIR, "memory_profiler_state.json")
ERROR_FILE = os.path.join(DATA_DIR, "memory_profiler_error.log")

DEFAULT_LIMIT_MB = float(os.environ.get("RENDER_MEMORY_LIMIT_MB", os.environ.get("MEMORY_LIMIT_MB", "512")))
DEFAULT_INTERVAL_SECONDS = int(os.environ.get("MEMORY_PROFILER_INTERVAL_SECONDS", "300"))
GC_THRESHOLD_MB = float(os.environ.get("MEMORY_PROFILER_GC_THRESHOLD_MB", os.environ.get("MEMORY_GC_THRESHOLD_MB", "380")))

TRACEMALLOC_ENABLED = os.environ.get("MEMORY_PROFILER_TRACEMALLOC", "0").strip().lower() in {"1", "true", "yes", "sim", "on"}
TRACEMALLOC_TOP_N = int(os.environ.get("MEMORY_PROFILER_TRACEMALLOC_TOP_N", "8"))
SNAPSHOT_MAX_BYTES = int(os.environ.get("MEMORY_PROFILER_SNAPSHOT_MAX_BYTES", str(2 * 1024 * 1024)))

_snapshot_lock = threading.Lock()
_profiler_thread = None
_profiler_stop = False
_last_snapshot = None


def _now():
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


def _ensure_data_dir():
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except Exception:
        pass


def _safe_round(value, digits=2):
    try:
        return round(float(value), digits)
    except Exception:
        return value


def _maybe_trim_snapshot_file():
    try:
        if not os.path.exists(SNAPSHOT_FILE):
            return
        size = os.path.getsize(SNAPSHOT_FILE)
        if size <= SNAPSHOT_MAX_BYTES:
            return

        keep_bytes = max(128 * 1024, SNAPSHOT_MAX_BYTES // 2)
        with open(SNAPSHOT_FILE, "rb") as f:
            f.seek(max(0, size - keep_bytes))
            data = f.read()

        if b"\n" in data:
            data = data.split(b"\n", 1)[1]

        with open(SNAPSHOT_FILE, "wb") as f:
            f.write(data)
    except Exception:
        pass


def _get_process_memory():
    """
    RSS real do processo.
    Preferência: /proc/self/status no Render/Linux.
    """
    pid = os.getpid()

    try:
        with open("/proc/self/status", "r", encoding="utf-8") as f:
            rss_mb = None
            vms_mb = None
            for line in f:
                if line.startswith("VmRSS:"):
                    rss_mb = float(line.split()[1]) / 1024.0
                elif line.startswith("VmSize:"):
                    vms_mb = float(line.split()[1]) / 1024.0

            if rss_mb is not None:
                return {
                    "ok": True,
                    "source": "procfs",
                    "pid": pid,
                    "rss_mb": _safe_round(rss_mb),
                    "vms_mb": _safe_round(vms_mb) if vms_mb is not None else None,
                    "usage_pct_render_limit": _safe_round((rss_mb / DEFAULT_LIMIT_MB) * 100),
                    "memory_limit_mb": DEFAULT_LIMIT_MB,
                    "memory_percent_system": None,
                    "threads": threading.active_count(),
                }
    except Exception:
        pass

    try:
        import psutil  # type: ignore

        process = psutil.Process(pid)
        info = process.memory_info()
        rss_mb = info.rss / 1024 / 1024
        vms_mb = getattr(info, "vms", 0) / 1024 / 1024

        return {
            "ok": True,
            "source": "psutil",
            "pid": pid,
            "rss_mb": _safe_round(rss_mb),
            "vms_mb": _safe_round(vms_mb),
            "usage_pct_render_limit": _safe_round((rss_mb / DEFAULT_LIMIT_MB) * 100),
            "memory_limit_mb": DEFAULT_LIMIT_MB,
            "memory_percent_system": None,
            "threads": process.num_threads() if hasattr(process, "num_threads") else threading.active_count(),
        }
    except Exception as e:
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            rss_mb = usage.ru_maxrss / 1024
            return {
                "ok": True,
                "source": "resource",
                "pid": pid,
                "rss_mb": _safe_round(rss_mb),
                "vms_mb": None,
                "usage_pct_render_limit": _safe_round((rss_mb / DEFAULT_LIMIT_MB) * 100),
                "memory_limit_mb": DEFAULT_LIMIT_MB,
                "memory_percent_system": None,
                "threads": threading.active_count(),
            }
        except Exception as e2:
            return {
                "ok": False,
                "source": "none",
                "pid": pid,
                "error": str(e),
                "fallback_error": str(e2),
                "rss_mb": None,
                "usage_pct_render_limit": None,
                "memory_limit_mb": DEFAULT_LIMIT_MB,
                "threads": threading.active_count(),
            }


def _light_gc_summary():
    return {
        "ok": True,
        "mode": "light",
        "gc_counts": list(gc.get_count()),
        "total_objects": None,
        "top_types": [],
        "note": "Resumo leve: gc.get_objects() não foi executado.",
    }


def _deep_gc_summary():
    try:
        objects = gc.get_objects()
        total = len(objects)
        counter = Counter()

        for obj in objects:
            try:
                counter[type(obj).__name__] += 1
            except Exception:
                counter["unknown"] += 1

        top_types = [{"type": k, "count": v} for k, v in counter.most_common(15)]
        del objects

        return {
            "ok": True,
            "mode": "deep",
            "total_objects": total,
            "top_types": top_types,
            "gc_counts": list(gc.get_count()),
        }
    except Exception as e:
        return {
            "ok": False,
            "mode": "deep",
            "error": str(e),
            "total_objects": None,
            "top_types": [],
            "gc_counts": list(gc.get_count()),
        }


def _get_tracemalloc_summary(force=False):
    if not (force or TRACEMALLOC_ENABLED):
        return {
            "enabled": False,
            "top": [],
            "note": "Tracemalloc desligado para reduzir overhead.",
        }

    try:
        import tracemalloc

        if not tracemalloc.is_tracing():
            tracemalloc.start(25)

        snapshot = tracemalloc.take_snapshot()
        stats = snapshot.statistics("filename")[:TRACEMALLOC_TOP_N]

        top = []
        for stat in stats:
            try:
                top.append({
                    "file": str(stat.traceback[0].filename),
                    "size_mb": _safe_round(stat.size / 1024 / 1024),
                    "count": stat.count,
                })
            except Exception:
                pass

        current, peak = tracemalloc.get_traced_memory()

        return {
            "enabled": True,
            "current_mb": _safe_round(current / 1024 / 1024),
            "peak_mb": _safe_round(peak / 1024 / 1024),
            "top": top,
        }
    except Exception as e:
        return {
            "enabled": True,
            "ok": False,
            "error": str(e),
            "top": [],
        }


def _read_last_snapshots(limit=8):
    if not os.path.exists(SNAPSHOT_FILE):
        return []

    try:
        with open(SNAPSHOT_FILE, "rb") as f:
            f.seek(0, os.SEEK_END)
            end = f.tell()
            block_size = 4096
            data = b""
            pos = end

            while pos > 0 and data.count(b"\n") <= limit:
                read_size = min(block_size, pos)
                pos -= read_size
                f.seek(pos)
                data = f.read(read_size) + data

            lines = data.splitlines()[-limit:]

        out = []
        for line in lines:
            try:
                out.append(json.loads(line.decode("utf-8")))
            except Exception:
                pass
        return out
    except Exception:
        return []


def _append_snapshot(snapshot):
    _ensure_data_dir()
    _maybe_trim_snapshot_file()
    with open(SNAPSHOT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, ensure_ascii=False, sort_keys=True) + "\n")


def _save_state(snapshot):
    _ensure_data_dir()
    state = {
        "ok": True,
        "version": VERSION,
        "updated_at": _now(),
        "snapshot_file": SNAPSHOT_FILE,
        "state_file": STATE_FILE,
        "last_snapshot": snapshot,
    }
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)


def _run_gc_if_needed(mem, force=False):
    rss = (mem or {}).get("rss_mb")
    should_gc = bool(force)

    try:
        if rss is not None and float(rss) >= GC_THRESHOLD_MB:
            should_gc = True
    except Exception:
        pass

    if not should_gc:
        return {
            "executed": False,
            "collected": None,
            "threshold_mb": GC_THRESHOLD_MB,
        }

    try:
        collected = gc.collect()
        try:
            import ctypes
            libc = ctypes.CDLL("libc.so.6")
            libc.malloc_trim(0)
        except Exception:
            pass

        return {
            "executed": True,
            "collected": collected,
            "threshold_mb": GC_THRESHOLD_MB,
        }
    except Exception as e:
        return {
            "executed": False,
            "error": str(e),
            "threshold_mb": GC_THRESHOLD_MB,
        }


def collect_memory_snapshot(reason="manual", include_gc=False, include_tracemalloc=False, deep=False, force_gc=False, persist=True):
    """
    Uma chamada = um snapshot.
    V1.3.1 não chama relatório dentro do JSON e não chama JSON dentro do relatório.
    """
    global _last_snapshot

    with _snapshot_lock:
        mem_before = _get_process_memory()
        gc_action = _run_gc_if_needed(mem_before, force=force_gc)
        mem = _get_process_memory() if gc_action.get("executed") else mem_before

        if include_gc:
            gc_info = _deep_gc_summary() if deep else _light_gc_summary()
        else:
            gc_info = {"enabled": False, "mode": "none"}

        snapshot = {
            "ok": True,
            "version": VERSION,
            "generated_at": _now(),
            "generated_at_iso": _now_iso(),
            "reason": reason,
            "mode": "deep" if deep else "light",
            "memory": mem,
            "gc": gc_info,
            "gc_action": gc_action,
            "tracemalloc": _get_tracemalloc_summary(force=include_tracemalloc),
        }

        try:
            previous = _last_snapshot
            if previous is None:
                last = _read_last_snapshots(limit=1)
                previous = last[-1] if last else None

            if previous:
                prev_rss = (((previous or {}).get("memory") or {}).get("rss_mb"))
                curr_rss = (mem or {}).get("rss_mb")
                if prev_rss is not None and curr_rss is not None:
                    snapshot["delta_rss_mb"] = _safe_round(float(curr_rss) - float(prev_rss))
                else:
                    snapshot["delta_rss_mb"] = None
            else:
                snapshot["delta_rss_mb"] = None
        except Exception:
            snapshot["delta_rss_mb"] = None

        if persist:
            try:
                _append_snapshot(snapshot)
                _save_state(snapshot)
            except Exception as e:
                snapshot["persist_error"] = str(e)

            _last_snapshot = snapshot

        return snapshot


def _status_from_pct(pct):
    status = "OK"
    emoji = "✅"
    severity = "NORMAL"

    try:
        pct_f = float(pct)
        if pct_f >= 92:
            return "CRÍTICO", "🔴", "CRITICAL"
        if pct_f >= 85:
            return "ALTO", "🟠", "HIGH"
        if pct_f >= 75:
            return "ATENÇÃO", "🟡", "MEDIUM"
    except Exception:
        pass

    return status, emoji, severity


def _format_memory_report_from_snapshot(snapshot, recent=None):
    mem = snapshot.get("memory") or {}
    gc_info = snapshot.get("gc") or {}
    gc_action = snapshot.get("gc_action") or {}
    trace = snapshot.get("tracemalloc") or {}
    deep = snapshot.get("mode") == "deep"

    rss = mem.get("rss_mb")
    pct = mem.get("usage_pct_render_limit")
    limit = mem.get("memory_limit_mb")
    threads = mem.get("threads")
    delta = snapshot.get("delta_rss_mb")

    status, emoji, _severity = _status_from_pct(pct)

    title = "🧠 MEMORY PROFILER DEEP — CENTRAL QUANT V1.3.1" if deep else "🧠 MEMORY PROFILER — CENTRAL QUANT V1.3.1"

    lines = [
        title,
        f"Data/hora: {snapshot.get('generated_at')}",
        "",
        f"Status: {emoji} {status}",
        f"RSS atual: {rss} MB",
        f"Uso Render: {pct}% de {limit} MB",
        f"Delta último snapshot: {delta} MB",
        f"Threads: {threads}",
        f"Fonte: {mem.get('source')}",
        f"Modo: {'DEEP/PESADO' if deep else 'LIGHT/LEVE'}",
        "",
        "GC:",
        f"- Counts: {gc_info.get('gc_counts')}",
        f"- GC automático executado: {gc_action.get('executed')}",
        f"- Objetos coletados: {gc_action.get('collected')}",
        f"- Threshold GC: {gc_action.get('threshold_mb')} MB",
    ]

    if deep:
        lines += [
            "",
            "Objetos Python:",
            f"- Total: {gc_info.get('total_objects')}",
        ]
        top_types = gc_info.get("top_types") or []
        if top_types:
            lines.append("")
            lines.append("Top tipos vivos:")
            for item in top_types[:12]:
                lines.append(f"- {item.get('type')}: {item.get('count')}")
    else:
        lines += [
            "",
            "Objetos Python:",
            "- Não contados no /memory para evitar overhead.",
            "- Use /memorydeep apenas quando precisar de diagnóstico pesado.",
        ]

    if recent:
        lines.append("")
        lines.append("Últimos snapshots:")
        for item in recent[-6:]:
            m = item.get("memory") or {}
            lines.append(
                f"- {item.get('generated_at')} | "
                f"{m.get('rss_mb')} MB | "
                f"{m.get('usage_pct_render_limit')}% | "
                f"{item.get('mode', 'light')}"
            )

    if trace.get("enabled"):
        lines += [
            "",
            "Tracemalloc:",
            f"- Atual: {trace.get('current_mb')} MB",
            f"- Pico: {trace.get('peak_mb')} MB",
        ]
        for item in (trace.get("top") or [])[:TRACEMALLOC_TOP_N]:
            file_name = item.get("file", "")
            if len(file_name) > 58:
                file_name = "..." + file_name[-55:]
            lines.append(f"- {item.get('size_mb')} MB | {item.get('count')} | {file_name}")
    else:
        lines += [
            "",
            "Tracemalloc: desligado no modo leve.",
        ]

    lines.append("")
    lines.append("Leitura:")
    try:
        pct_f = float(pct)
        if pct_f >= 92:
            lines.append("Memória em zona crítica. Alto risco de restart no Render.")
        elif pct_f >= 85:
            lines.append("Memória alta. Monitorar crescimento e evitar novos módulos pesados.")
        elif pct_f >= 75:
            lines.append("Memória em atenção. Central operável, mas sem folga grande.")
        else:
            lines.append("Memória controlada neste momento.")
    except Exception:
        lines.append("Não foi possível classificar a memória.")

    return "\n".join(lines)


def build_memory_report(include_tracemalloc=False, deep=False):
    """
    Telegram/texto.
    V1.3.1: exatamente 1 snapshot.
    """
    if include_tracemalloc and not deep:
        deep = True

    snapshot = collect_memory_snapshot(
        reason="command_deep" if deep else "command",
        include_gc=True,
        include_tracemalloc=include_tracemalloc,
        deep=deep,
        force_gc=False,
        persist=True,
    )
    recent = _read_last_snapshots(limit=6)
    return _format_memory_report_from_snapshot(snapshot, recent=recent)


def build_memory_json(deep=False, include_text=False):
    """
    HTTP/JSON.
    V1.3.1: exatamente 1 snapshot.
    Por padrão NÃO inclui text para evitar gerar relatório duplicado.
    """
    snapshot = collect_memory_snapshot(
        reason="json_deep" if deep else "json",
        include_gc=True,
        include_tracemalloc=deep,
        deep=deep,
        force_gc=False,
        persist=True,
    )

    if include_text:
        recent = _read_last_snapshots(limit=6)
        snapshot["text"] = _format_memory_report_from_snapshot(snapshot, recent=recent)

    return snapshot


def get_memory_health():
    snapshot = collect_memory_snapshot(
        reason="health",
        include_gc=False,
        include_tracemalloc=False,
        deep=False,
        force_gc=False,
        persist=True,
    )
    mem = snapshot.get("memory") or {}
    status, _emoji, severity = _status_from_pct(mem.get("usage_pct_render_limit"))

    return {
        "ok": True,
        "version": VERSION,
        "status": status,
        "severity": severity,
        "rss_mb": mem.get("rss_mb"),
        "usage_pct_render_limit": mem.get("usage_pct_render_limit"),
        "memory_limit_mb": mem.get("memory_limit_mb"),
        "threads": mem.get("threads"),
        "delta_rss_mb": snapshot.get("delta_rss_mb"),
        "generated_at": snapshot.get("generated_at"),
    }


def memory_profiler_health_text():
    health = get_memory_health()
    return (
        "🧠 MEMORY PROFILER\n"
        f"Status: {health.get('status')}\n"
        f"RSS: {health.get('rss_mb')} MB\n"
        f"Uso Render: {health.get('usage_pct_render_limit')}%\n"
        f"Delta: {health.get('delta_rss_mb')} MB\n"
        f"Threads: {health.get('threads')}\n"
        f"Versão: {VERSION}"
    )


def start_memory_profiler(interval_seconds=DEFAULT_INTERVAL_SECONDS):
    global _profiler_thread, _profiler_stop

    if _profiler_thread and _profiler_thread.is_alive():
        return {
            "ok": True,
            "already_running": True,
            "version": VERSION,
            "interval_seconds": interval_seconds,
        }

    _profiler_stop = False
    _profiler_thread = threading.Thread(
        target=_memory_loop,
        args=(interval_seconds,),
        name="central-memory-profiler",
        daemon=True,
    )
    _profiler_thread.start()

    return {
        "ok": True,
        "started": True,
        "version": VERSION,
        "interval_seconds": interval_seconds,
        "snapshot_file": SNAPSHOT_FILE,
        "state_file": STATE_FILE,
    }


def stop_memory_profiler():
    global _profiler_stop
    _profiler_stop = True
    return {"ok": True, "stopping": True, "version": VERSION}


def _memory_loop(interval_seconds):
    global _profiler_stop

    try:
        collect_memory_snapshot(
            reason="profiler_start",
            include_gc=False,
            include_tracemalloc=False,
            deep=False,
            persist=True,
        )
    except Exception:
        pass

    while not _profiler_stop:
        try:
            time.sleep(max(30, int(interval_seconds)))
            collect_memory_snapshot(
                reason="scheduled",
                include_gc=False,
                include_tracemalloc=False,
                deep=False,
                persist=True,
            )
        except Exception:
            try:
                _ensure_data_dir()
                with open(ERROR_FILE, "a", encoding="utf-8") as f:
                    f.write(_now() + " | " + traceback.format_exc() + "\n")
            except Exception:
                pass


if __name__ == "__main__":
    print(build_memory_report(include_tracemalloc=TRACEMALLOC_ENABLED, deep=TRACEMALLOC_ENABLED))
