FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    FEATURE_LOGGING_ENABLED=true \
    FEATURE_LOG_DIR=/app/data/feature_logs \
    SETTINGS_PATH=/app/config/settings.yaml

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        "fastapi>=0.110.0" \
        "uvicorn[standard]>=0.29.0" \
        "pydantic>=2.6.0" \
        "pydantic-settings>=2.2.0" \
        "pyyaml>=6.0.1" \
        "polars>=1.0.0" \
        "numpy>=1.26.0" \
        "catboost>=1.2.0" \
        "lightgbm>=4.1.0" \
        "scikit-learn>=1.4.0" \
        "joblib>=1.3.0"


COPY src /app/src
COPY config /app/config
COPY models /app/models

RUN mkdir -p /app/data/feature_logs

EXPOSE 8000

CMD ["uvicorn", "backend_service.main:app", "--host", "0.0.0.0", "--port", "8000"]