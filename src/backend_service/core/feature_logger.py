"""
Feature Capture Logger — non-blocking capture of inference payloads
to daily ``.jsonl`` files.

Purpose
-------
* Record every ``/predict`` request + response for offline analysis,
  model-quality monitoring, and future retraining.
* Capture **intermediate pipeline state** (macro baseline, micro
  forecast) that is invisible in the public API contract — this is
  the most valuable data for model debugging.
* Provide an audit trail for dispatch decisions.

File format
-----------
* JSON Lines (``.jsonl``): one JSON object per line, append-only.
* Files are rotated daily: ``features_YYYY-MM-DD.jsonl``.
* Default directory: ``<project_root>/data/feature_logs/``.
* Override via ``FEATURE_LOG_DIR`` environment variable.

Integration
-----------
* Called from ``routers.py`` via FastAPI ``BackgroundTasks``.
* Uses **sync** I/O — ``BackgroundTasks`` runs sync callables in the
  default thread-pool executor, so the event loop is never blocked.
* Thread-safe via ``threading.Lock`` (concurrent requests produce
  concurrent background tasks).
* Failures are logged at WARNING level but **never** propagate to the
  API response — the inference pipeline must not break because of
  logging issues.

Configuration (env vars)
------------------------
``FEATURE_LOG_DIR``          — directory path  (default: ``data/feature_logs/``)
``FEATURE_LOGGING_ENABLED``  — ``true`` | ``false``  (default: ``true``)
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Defaults ────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_LOG_DIR = _PROJECT_ROOT / "data" / "feature_logs"

ENV_LOG_DIR = "FEATURE_LOG_DIR"
ENV_LOGGING_ENABLED = "FEATURE_LOGGING_ENABLED"


# ── Core class ──────────────────────────────────────────────────────


class FeatureLogger:
    """Captures inference payloads to daily ``.jsonl`` files.

    Instances are thread-safe and intended to be used as singletons
    (see :func:`get_feature_logger`).
    """

    def __init__(
        self,
        log_dir: Path | None = None,
        enabled: bool = True,
    ) -> None:
        self.enabled = enabled
        self.log_dir = log_dir or _resolve_log_dir()
        self._lock = threading.Lock()

        if self.enabled:
            try:
                self.log_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                logger.exception(
                    "Cannot create feature-log directory %s — "
                    "disabling feature logging",
                    self.log_dir,
                )
                self.enabled = False
                return
            logger.info("FeatureLogger active → %s", self.log_dir)
        else:
            logger.info("FeatureLogger disabled via config")

    # ── public API ──────────────────────────────────────────────

    def log_inference(
        self,
        *,
        request_data: dict[str, Any],
        response_data: dict[str, Any],
        pipeline_state: dict[str, Any] | None = None,
        inference_duration_ms: float | None = None,
    ) -> None:
        """Append one inference record to today's log file.

        Parameters
        ----------
        request_data:
            Serialised ``ForecastRequest`` (camelCase keys via
            ``model_dump(by_alias=True)``).
        response_data:
            Serialised ``PredictResponse`` (camelCase keys).
        pipeline_state:
            Internal values **not** exposed in the API response:
            ``macro_daily_baseline``, ``daily_forecast``,
            ``micro_forecast``.  Invaluable for offline analysis.
        inference_duration_ms:
            Wall-clock time of the full pipeline, in milliseconds.
        """
        if not self.enabled:
            return

        now = datetime.now(timezone.utc)

        record: dict[str, Any] = {
            "logged_at": now.isoformat(),
            "inference_duration_ms": inference_duration_ms,
            "request": request_data,
            "pipeline_state": pipeline_state or {},
            "response": response_data,
        }

        log_path = self._log_path_for(now)
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"

        try:
            with self._lock:
                with open(log_path, "a", encoding="utf-8") as fh:
                    fh.write(line)
        except Exception:
            # Intentionally broad — logging must never crash the
            # service, no matter what (disk full, permissions, …).
            logger.warning(
                "Failed to write feature log to %s", log_path,
                exc_info=True,
            )

    # ── internals ───────────────────────────────────────────────

    def _log_path_for(self, dt: datetime) -> Path:
        """Return the file path for *dt*'s date."""
        date_str = dt.strftime("%Y-%m-%d")
        return self.log_dir / f"features_{date_str}.jsonl"


# ── Environment helpers ─────────────────────────────────────────────


def _resolve_log_dir() -> Path:
    """Read ``FEATURE_LOG_DIR`` or fall back to the project default."""
    env_val = os.environ.get(ENV_LOG_DIR)
    if env_val:
        return Path(env_val)
    return _DEFAULT_LOG_DIR


def _resolve_enabled() -> bool:
    """Read ``FEATURE_LOGGING_ENABLED`` or default to ``True``."""
    env_val = os.environ.get(ENV_LOGGING_ENABLED, "true")
    return env_val.lower() in ("true", "1", "yes", "on")


# ── Singleton access ────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_feature_logger() -> FeatureLogger:
    """Return the cached singleton :class:`FeatureLogger`.

    Mirrors the ``get_settings()`` pattern from
    ``backend_service.core.config``.
    """
    return FeatureLogger(
        log_dir=_resolve_log_dir(),
        enabled=_resolve_enabled(),
    )