# -*- coding: utf-8 -*-
"""
Memory Profiler V1 — Central Quant
Versão: 2026-07-05-MEMORY-PROFILER-V1

Objetivo:
- Monitorar uso de memória da Central Quant sem aumentar muito o consumo.
- Gerar snapshots leves em JSONL.
- Expor funções para comando /memory, health e diagnóstico.
- Usar psutil quando disponível; fallback para resource.
- Usar tracemalloc opcional e limitado.

Arquivo sugerido:
    memory_profiler_v1.py

Uso básico no main.py:
    import memory_profiler_v1 as memory_profiler

    memory_profiler.start_memory_profiler(interval_seconds=300)

    # comando /memory:
    texto = memory_profiler.build_memory_report()
"""

import os
import gc
import json
import time
import threading
import traceback
from collections import Counter
from datetime import datetime

VERSION = "2026-07-05-MEMORY-PROFILER-V1"

DATA_DIR = os.environ.get("CENTRAL_DATA_DIR", "/opt/render/project/src/data")
SNAPSHOT_FILE = os.path.join(DATA_DIR, "memory_profiler_snapshots.jsonl")
STATE_FILE = os.path.join(DATA_DIR, "memory_profiler_state.json")

DEFAULT_LIMIT_MB = float(os.environ.get("RENDER_MEMORY_LIMIT_MB", "512"))
DEFAULT_INTERVAL_SECONDS = int(os.environ.get("MEMORY_PROFILER_INTERVAL_SECONDS", "300"))

# tracemalloc é útil, mas pode gerar overhead. Mantemos desligado por padrão.
TRACEMALLOC_ENABLED = os.environ.get("MEMORY_PROFILER_TRACEMALLOC", "0") == "1"
TRACEMALLOC_TOP_N = int(os.environ.get("MEMORY_PROFILER_TRACEMALLOC_TOP_N", "8"))

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


def _get_process_memory():
    """
    Retorna memória do processo atual.
    Preferência: psutil.
    Fallback: resource.
    """
    pid = os.getpid()

    try:
        import psutil  # type: ignore

        process = psutil.Process(pid)
        info = process.memory_info()
        rss_mb = info.rss / 1024 / 1024
        vms_mb = getattr(info, "vms", 0) / 1024 / 1024

        try:
            mem_percent_system = process.memory_percent()
        except Exception:
            mem_percent_system = None

        try:
            num_threads = process.num_threads()
        except Exception:
            num_threads = threading.active_count()

        return {
            "ok": True,
            "source": "psutil",
            "pid": pid,
            "rss_mb": _safe_round(rss_mb),
            "vms_mb": _safe_round(vms_mb),
            "usage_pct_render_limit": _safe_round((rss_mb / DEFAULT_LIMIT_MB) * 100),
            "memory_limit_mb": DEFAULT_LIMIT_MB,
            "memory_percent_system": _safe_round(mem_percent_system) if mem_percent_system is not None else None,
            "threads": num_threads,
        }
    except Exception as e:
        try:
            import resource

            usage = resource.getrusage(resource.RUSAGE_SELF)
            # Linux: ru_maxrss em KB.
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


def _get_gc_summary():
    """
    Conta objetos vivos por tipo.
    Para evitar overhead alto, retorna apenas top tipos.
    """
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

        return {
            "ok": True,
            "total_objects": total,
            "top_types": top_types,
            "gc_counts": list(gc.get_count()),
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "total_objects": None,
            "top_types": [],
            "gc_counts": list(gc.get_count()) if hasattr(gc, "get_count") else [],
        }


def _get_tracemalloc_summary():
    """
    Snapshot opcional. Só roda se MEMORY_PROFILER_TRACEMALLOC=1.
    """
    if not TRACEMALLOC_ENABLED:
        return {
            "enabled": False,
            "top": [],
            "note": "Defina MEMORY_PROFILER_TRACEMALLOC=1 para habilitar.",
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
    """
    Lê apenas as últimas linhas do arquivo JSONL.
    Evita carregar histórico inteiro.
    """
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

        snapshots = []
        for line in lines:
            try:
                snapshots.append(json.loads(line.decode("utf-8")))
            except Exception:
                pass
        return snapshots
    except Exception:
        return []


def _append_snapshot(snapshot):
    _ensure_data_dir()
    with open(SNAPSHOT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, ensure_ascii=False, sort_keys=True) + "\n")


def _save_state(snapshot):
    _ensure_data_dir()
    state = {
        "ok": True,
        "version": VERSION,
        "updated_at": _now(),
        "snapshot_file": SNAPSHOT_FILE,
        "last_snapshot": snapshot,
    }
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)


def collect_memory_snapshot(reason="manual", include_gc=True, include_tracemalloc=False):
    """
    Coleta snapshot leve.
    """
    global _last_snapshot

    with _snapshot_lock:
        mem = _get_process_memory()

        snapshot = {
            "ok": True,
            "version": VERSION,
            "generated_at": _now(),
            "generated_at_iso": _now_iso(),
            "reason": reason,
            "memory": mem,
            "gc": _get_gc_summary() if include_gc else {"enabled": False},
            "tracemalloc": _get_tracemalloc_summary() if include_tracemalloc else {"enabled": False},
        }

        try:
            previous = _last_snapshot or (_read_last_snapshots(limit=1)[-1] if _read_last_snapshots(limit=1) else None)
            if previous:
                prev_rss = (((previous or {}).get("memory") or {}).get("rss_mb"))
                curr_rss = (mem or {}).get("rss_mb")
                if prev_rss is not None and curr_rss is not None:
                    snapshot["delta_rss_mb"] = _safe_round(float(curr_rss) - float(prev_rss))
        except Exception:
            snapshot["delta_rss_mb"] = None

        try:
            _append_snapshot(snapshot)
            _save_state(snapshot)
        except Exception as e:
            snapshot["persist_error"] = str(e)

        _last_snapshot = snapshot
        return snapshot


def _memory_loop(interval_seconds):
    global _profiler_stop

    # Primeiro snapshot logo ao iniciar.
    try:
        collect_memory_snapshot(reason="profiler_start", include_gc=True, include_tracemalloc=False)
    except Exception:
        pass

    while not _profiler_stop:
        try:
            time.sleep(max(30, int(interval_seconds)))
            collect_memory_snapshot(reason="scheduled", include_gc=True, include_tracemalloc=False)
        except Exception:
            try:
                _ensure_data_dir()
                with open(os.path.join(DATA_DIR, "memory_profiler_error.log"), "a", encoding="utf-8") as f:
                    f.write(_now() + " | " + traceback.format_exc() + "\n")
            except Exception:
                pass


def start_memory_profiler(interval_seconds=DEFAULT_INTERVAL_SECONDS):
    """
    Inicia thread daemon.
    Seguro para chamar mais de uma vez.
    """
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


def get_memory_health():
    """
    Retorna health simples para dashboard/health.
    """
    snapshot = collect_memory_snapshot(reason="health", include_gc=False, include_tracemalloc=False)
    mem = snapshot.get("memory") or {}
    pct = mem.get("usage_pct_render_limit")

    status = "OK"
    severity = "NORMAL"

    try:
        pct_f = float(pct)
        if pct_f >= 92:
            status = "CRITICAL"
            severity = "CRITICAL"
        elif pct_f >= 85:
            status = "WARNING"
            severity = "HIGH"
        elif pct_f >= 75:
            status = "ATTENTION"
            severity = "MEDIUM"
    except Exception:
        pass

    return {
        "ok": True,
        "version": VERSION,
        "status": status,
        "severity": severity,
        "rss_mb": mem.get("rss_mb"),
        "usage_pct_render_limit": pct,
        "memory_limit_mb": mem.get("memory_limit_mb"),
        "threads": mem.get("threads"),
        "generated_at": snapshot.get("generated_at"),
    }


def build_memory_report(include_tracemalloc=False):
    """
    Texto pronto para Telegram.
    """
    snapshot = collect_memory_snapshot(
        reason="command",
        include_gc=True,
        include_tracemalloc=include_tracemalloc,
    )

    mem = snapshot.get("memory") or {}
    gc_info = snapshot.get("gc") or {}
    trace = snapshot.get("tracemalloc") or {}
    recent = _read_last_snapshots(limit=6)

    rss = mem.get("rss_mb")
    pct = mem.get("usage_pct_render_limit")
    limit = mem.get("memory_limit_mb")
    threads = mem.get("threads")
    delta = snapshot.get("delta_rss_mb")

    status = "OK"
    emoji = "✅"
    try:
        pct_f = float(pct)
        if pct_f >= 92:
            status = "CRÍTICO"
            emoji = "🔴"
        elif pct_f >= 85:
            status = "ALTO"
            emoji = "🟠"
        elif pct_f >= 75:
            status = "ATENÇÃO"
            emoji = "🟡"
    except Exception:
        pass

    lines = []
    lines.append("🧠 MEMORY PROFILER — CENTRAL QUANT V1")
    lines.append(f"Data/hora: {snapshot.get('generated_at')}")
    lines.append("")
    lines.append(f"Status: {emoji} {status}")
    lines.append(f"RSS atual: {rss} MB")
    lines.append(f"Uso Render: {pct}% de {limit} MB")
    lines.append(f"Delta último snapshot: {delta} MB")
    lines.append(f"Threads: {threads}")
    lines.append(f"Fonte: {mem.get('source')}")
    lines.append("")
    lines.append("Objetos Python:")
    lines.append(f"- Total: {gc_info.get('total_objects')}")
    lines.append(f"- GC counts: {gc_info.get('gc_counts')}")

    top_types = gc_info.get("top_types") or []
    if top_types:
        lines.append("")
        lines.append("Top tipos vivos:")
        for item in top_types[:10]:
            lines.append(f"- {item.get('type')}: {item.get('count')}")

    if recent:
        lines.append("")
        lines.append("Últimos snapshots:")
        for item in recent[-6:]:
            m = item.get("memory") or {}
            lines.append(
                f"- {item.get('generated_at')} | "
                f"{m.get('rss_mb')} MB | "
                f"{m.get('usage_pct_render_limit')}%"
            )

    if trace.get("enabled"):
        lines.append("")
        lines.append("Tracemalloc:")
        lines.append(f"- Atual: {trace.get('current_mb')} MB")
        lines.append(f"- Pico: {trace.get('peak_mb')} MB")
        for item in (trace.get("top") or [])[:TRACEMALLOC_TOP_N]:
            file_name = item.get("file", "")
            if len(file_name) > 58:
                file_name = "..." + file_name[-55:]
            lines.append(f"- {item.get('size_mb')} MB | {item.get('count')} | {file_name}")
    else:
        lines.append("")
        lines.append("Tracemalloc: desligado por padrão para reduzir overhead.")

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


def build_memory_json():
    """
    Útil para endpoint HTTP.
    """
    return collect_memory_snapshot(reason="json", include_gc=True, include_tracemalloc=False)


def memory_profiler_health_text():
    health = get_memory_health()
    return (
        "🧠 MEMORY PROFILER\n"
        f"Status: {health.get('status')}\n"
        f"RSS: {health.get('rss_mb')} MB\n"
        f"Uso Render: {health.get('usage_pct_render_limit')}%\n"
        f"Threads: {health.get('threads')}\n"
        f"Versão: {VERSION}"
    )


if __name__ == "__main__":
    print(build_memory_report(include_tracemalloc=TRACEMALLOC_ENABLED))
