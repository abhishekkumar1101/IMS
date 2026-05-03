# Anomaly Detection Model

`train_anomaly.ipynb` → `model.pkl`

## What it does

A scikit-learn `IsolationForest` trained on **5,000 synthetic signals** (per assignment instruction to keep the sample small). It scores incoming signals on five features and flags those scoring below the configured threshold (`ANOMALY_SCORE_THRESHOLD`, default `-0.05`).

## Features

| Feature | Source |
|---|---|
| `latency_ms`        | `signal.latency_ms` (caller-supplied) |
| `error_rate`        | `signal.error_rate` |
| `signal_freq_10s`   | live count from Redis ZSET (debouncer window) |
| `payload_size`      | `signal.payload_size` or `len(json(payload))` |
| `hour_of_day`       | from `signal.occurred_at` |

Missing features default to median values so partial signals still score (graceful).

## Re-training

```bash
cd ml
python -c "..."        # see notebook
# or:
jupyter nbconvert --to notebook --execute train_anomaly.ipynb
```

The backend lazy-loads `model.pkl` at startup (`app/ai/anomaly.py`); if the file is missing, scoring is skipped and signals get `is_anomalous=false`.
