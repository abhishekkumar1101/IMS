# Prompt 1 — Initial spec ingestion

The full spec lives in `Engineering_Assignment__Incident_Management_System.pdf`
at the repo root. Key bullets distilled from the PDF (per submission rule #4
that prompts/specs/plans must be checked in):

- IMS that monitors APIs, MCP hosts, distributed caches, async queues, RDBMS,
  NoSQL stores.
- Bursts up to 10 000 signals/sec; cannot crash if persistence is slow.
- Debounce 100 signals / 10 s for the same Component ID into one Work Item.
- Four storage roles: raw audit Data Lake, transactional Source of Truth,
  hot-path Cache, time-series sink.
- Strategy pattern for alerting (P0 RDBMS, P2 Cache, ...).
- State pattern for `OPEN → INVESTIGATING → RESOLVED → CLOSED`.
- Mandatory RCA before CLOSED. Auto-compute MTTR.
- Async processing, rate limiter, `/health`, throughput printer every 5 s.
- React/Vue/HTMX dashboard: live feed (severity-sorted), incident detail
  with raw signals + state controls, RCA form (datetime pickers, dropdown,
  textareas).
- Submit: `/backend` + `/frontend`, README with arch diagram + Docker compose
  setup + backpressure section, sample failure simulator, all
  prompts/specs/plans checked in. Bonus for creative additions.

User-supplied additions (free / no-cost):

- Use Gemini API key (`gemini-2.5-flash-lite`) for AI features.
- Add anomaly detection ML built in Jupyter, persisted as `.pkl`.
- Real-time collaboration (presence + comments).
- Live-feed Gemini incident summarizer.
- Professional UI.
