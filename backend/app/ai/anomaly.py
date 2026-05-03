"""Anomaly scorer — loads the IsolationForest pickle trained in `ml/`.

`is_ready` reflects whether the model loaded successfully. If unavailable, the
scorer becomes a no-op and signals receive `anomaly_score=None, is_anomalous=False`.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import joblib
import numpy as np

log = logging.getLogger("ims.anomaly")

_DEFAULTS = {
    "latency_ms": 80.0,
    "error_rate": 0.02,
    "signal_freq_10s": 5.0,
    "payload_size": 2048.0,
    "hour_of_day": 12.0,
}


class AnomalyScorer:
    def __init__(self, model_path: str, threshold: float) -> None:
        self.model_path = model_path
        self.threshold = threshold
        self._model = None
        self._features: list[str] = []

    def _candidate_paths(self) -> list[str]:
        """Try the configured path first, then a couple of repo-relative fallbacks.

        Lets the same `.env` value (e.g. `ml/model.pkl`) work whether the
        backend is launched from the repo root or from `backend/`.
        """
        from pathlib import Path

        cands = [self.model_path]
        here = Path(__file__).resolve()
        # Walk up until we find a `ml/model.pkl` next to a sibling `backend/`.
        for parent in here.parents:
            cand = parent / "ml" / "model.pkl"
            if cand.exists():
                cands.append(str(cand))
                break
        return cands

    def load(self) -> None:
        for path in self._candidate_paths():
            if os.path.exists(path):
                try:
                    bundle = joblib.load(path)
                    self._model = bundle["model"]
                    self._features = bundle["features"]
                    self.threshold = bundle.get("threshold", self.threshold)
                    self.model_path = path
                    log.info("anomaly model loaded from %s (features=%s, threshold=%s)", path, self._features, self.threshold)
                    return
                except Exception as e:  # noqa: BLE001
                    log.exception("failed to load anomaly model from %s: %s", path, e)
        log.warning("anomaly model not found (tried %s) — scoring disabled", self._candidate_paths())

    @property
    def is_ready(self) -> bool:
        return self._model is not None

    def _row(self, signal: dict[str, Any], freq_10s: float) -> list[float]:
        ts = signal.get("created_at")
        hour = ts.hour if ts is not None else 12
        feat_map = {
            "latency_ms": float(signal.get("latency_ms") or _DEFAULTS["latency_ms"]),
            "error_rate": float(signal.get("error_rate") or _DEFAULTS["error_rate"]),
            "signal_freq_10s": float(freq_10s),
            "payload_size": float(signal.get("payload_size") or len(str(signal.get("payload") or "")) or _DEFAULTS["payload_size"]),
            "hour_of_day": float(hour),
        }
        return [feat_map[k] for k in self._features]

    def score_batch(self, signals: list[dict[str, Any]], freq_lookup: dict[str, float]) -> None:
        """Mutates each signal in-place, adding `anomaly_score` + `is_anomalous`."""
        if not self.is_ready or not signals:
            for s in signals:
                s["anomaly_score"] = None
                s["is_anomalous"] = False
            return
        rows = np.array([self._row(s, freq_lookup.get(s["component_id"], 0)) for s in signals])
        scores = self._model.decision_function(rows)  # type: ignore[union-attr]
        for s, sc in zip(signals, scores):
            s["anomaly_score"] = float(sc)
            s["is_anomalous"] = bool(sc < self.threshold)
