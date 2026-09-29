FROM python:3.12.14-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY signals-requirements.txt /app/
RUN pip install --no-cache-dir -r signals-requirements.txt
COPY bingx_public_signal_source.py donkey_advisory_offline.py falcon_advisory_offline.py falcon_advisory_preview.py falcon_signal_identity.py signal_only_workflow.py signal_only_service.py telegram_signal_delivery.py signal_only_runner.py /app/
COPY signals_sources/ /app/signals_sources/
ENTRYPOINT ["python", "-I", "-B", "/app/signal_only_runner.py"]
# Intentionally no activation by default, nor embedded credentials/configuration.
CMD ["--check-config", "--config", "/var/data/signals/config.json"]
