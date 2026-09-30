FROM python:3.12.14-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY signals-requirements.txt /app/
RUN pip install --no-cache-dir -r signals-requirements.txt
COPY bingx_public_signal_source.py donkey_advisory_offline.py falcon_advisory_offline.py falcon_advisory_preview.py falcon_signal_identity.py signal_only_workflow.py signal_only_service.py telegram_signal_delivery.py signal_only_runner.py /app/
COPY signals_sources/ /app/signals_sources/
COPY signals-config.validation.json /app/signals-config.validation.json
ENTRYPOINT ["python", "-I", "-B", "/app/signal_only_runner.py"]
# Validated nonsecret configuration only; no activation or credentials by default.
CMD ["--check-config", "--config", "/app/signals-config.validation.json"]
