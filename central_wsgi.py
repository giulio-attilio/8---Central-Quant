"""Production WSGI entry point for the single-process Central runtime."""

import os


# Gunicorn imports the WSGI module after creating its worker. Runtime startup is
# started by gunicorn.conf.py in a background thread so the HTTP listener can
# come up before bot modules finish loading, as it does in the local launcher.
os.environ["CENTRAL_AUTO_START_RUNTIME"] = "false"

import main as central_main  # noqa: E402

app = central_main.app
