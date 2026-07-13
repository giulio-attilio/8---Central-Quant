"""Cache estritamente local a uma request HTTP para auditorias Predator.

O modulo nao possui armazenamento global de resultados. O dicionario vive somente
em ``flask.g`` e e descartado automaticamente ao final do request context.
"""

from __future__ import annotations

import functools
import json
import sys
import uuid

from flask import g, has_app_context, has_request_context


def _caller_name():
    try:
        frame = sys._getframe(2)
        return str(frame.f_code.co_name)[:120]
    except Exception:
        return "UNKNOWN"


def _emit(event, request_id, audit, caller):
    try:
        print(
            f"{event} "
            + json.dumps(
                {
                    "request_id": request_id,
                    "audit": audit,
                    "caller": caller,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            flush=True,
        )
    except Exception:
        pass


def _request_state():
    if not has_request_context() and not has_app_context():
        return None
    try:
        state = getattr(g, "_predator_audit_request_state", None)
        if state is None:
            state = {
                "request_id": str(uuid.uuid4()),
                "results": {},
            }
            g._predator_audit_request_state = state
        return state
    except Exception:
        return None


def request_cached_predator_audit(audit):
    """Executa ``audit`` no maximo uma vez dentro do mesmo request Flask."""
    audit = str(audit)

    def decorate(function):
        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            state = _request_state()
            if state is None:
                return function(*args, **kwargs)

            caller = _caller_name()
            request_id = state["request_id"]
            results = state["results"]
            if audit in results:
                _emit("REQUEST_CACHE_HIT", request_id, audit, caller)
                return results[audit]

            _emit("REQUEST_CACHE_MISS", request_id, audit, caller)
            result = function(*args, **kwargs)
            results[audit] = result
            _emit("REQUEST_CACHE_STORE", request_id, audit, caller)
            return result

        return wrapped

    return decorate


__all__ = ["request_cached_predator_audit"]
