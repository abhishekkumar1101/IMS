# IMS — Demo guide

Five-minute walkthrough that hits every rubric item. Run two terminals (backend + frontend) plus a third for the simulator.

## 0. Prep (one time)

```bash
# Windows
scripts\quickstart.bat
# Mac/Linux
bash scripts/quickstart.sh
```

This installs Python deps + `npm install` for the frontend. Confirm the repo's `.env` has both `MONGODB_URI` and `GEMINI_API_KEY`.

## 1. Boot the system (≈ 30 s)

**Terminal 1 — backend**
```bash
cd backend
python -m uvicorn app.main:app --reload
```

Wait for: `IMS backend ready on http://0.0.0.0:8000`. The metric printer should start ticking every 5 s.

**Terminal 2 — frontend**
```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`. You should see:
- Dark dashboard with a header showing a green status dot, `0 sig/s · 0 queue`, current time.
- The empty-state card: "All clear ⛅" with the simulator command shown.
- 4 stat cards on top (Active / P0 / Closed / Total signals — all zero).

**Sanity check:**
```bash
curl http://localhost:8000/health
# {"status":"ok","deps":{"mongo":"ok","anomaly_model":"loaded","gemini":"configured","transactions":"supported"},...}
```

If `anomaly_model` says `loaded` and `gemini` says `configured`, you're good.

## 2. Generate a failure (≈ 10 s)

**Terminal 3:**
```bash
python scripts/simulate_failure.py
```

You'll see:
```
[1/3] RDBMS_PRIMARY: 5000 signals / 2s
[2/3] MCP_HOST_03:    3000 signals / 1.5s
[3/3] CACHE_CLUSTER_01: 300 signals / 3s
=> total accepted=8200 in ~8s (~1k sig/s)
```

While this runs, the backend's metric printer will spike:
```
[metrics] signals_sec=~1000  queue_depth=~200  received=…  work_items=3
```

Watch the **dashboard live-update** — three new incidents should appear, sorted by severity:
1. P0 RDBMS_PRIMARY (red left border, 5 000 signals)
2. P0 MCP_HOST_03 (red left border, 3 000 signals)
3. P2 CACHE_CLUSTER_01 (200 signals)

This proves: **debouncing** (8 200 signals → 3 incidents), **rate-limiting** under high throughput, and **state pattern** (all start in OPEN). The stat cards at the top now show: `3 active · 2 P0 · 0 closed · 8,200 signals`.

## 3. AI summary (≈ 5 s)

On the Live Feed, click the **✨ Generate AI summary** link under any incident. After ~1 s a Gemini-generated one-liner appears (e.g. *"Primary RDBMS replica unresponsive due to checkpoint IO saturation"*).

This proves: **Gemini 2.5 Flash Lite integration** + circuit breaker + Redis-equivalent in-memory cache (the second click is instant — cached).

## 4. Drill into an incident (≈ 30 s)

Click the RDBMS_PRIMARY incident. The detail page shows:
- Severity / component / kind chips and the **state stepper** (OPEN highlighted in indigo, future stages dim).
- Big signal count + relative timestamps.
- A red **anomaly chip** showing how many signals were flagged by the Isolation Forest (typically 30–50 of the first 200 visible).
- Two-column layout: **Raw signals** table on the left (with anomaly chips in fuchsia for outliers); **Discussion** thread on the right.
- An action button: **Start investigating**.

This proves: **Data Lake** queryability (raw signals from MongoDB), the **anomaly ML model** flagging outliers, and the **professional UI**.

## 5. Real-time collaboration (≈ 30 s)

Open the same incident in a **second browser tab/window** (or another browser). On both pages you'll see two avatars in the top-right: presence is live via WebSocket.

Type a comment in either tab — it appears in the other instantly. (Backend pushes via the `/ws/incidents/{id}` channel.)

This proves: **WebSocket presence + threaded comments** (the bonus collab feature).

## 6. State machine: OPEN → INVESTIGATING → RESOLVED (≈ 15 s)

On the incident page, click:
1. **Start investigating** — stepper advances to INVESTIGATING (indigo); button changes to "Mark resolved".
2. **Mark resolved** — stepper advances to RESOLVED; new buttons appear: "Submit RCA & close" + "Re-open".

Behind the scenes each click goes through the **State pattern** in `backend/app/workflow/states.py`. Try clicking the back button and watching the Live Feed — the incident disappears from the active list because RESOLVED is sorted lower.

## 7. Mandatory RCA — try to cheat (≈ 30 s)

Try this from a terminal:
```bash
curl -X POST http://localhost:8000/incidents/<id>/transition \
  -H "Content-Type: application/json" \
  -d '{"to_state":"CLOSED","actor":"hacker"}'
```

You'll get `422 use POST /incidents/{id}/rca to close (RCA required)`. The State pattern refuses to skip the RCA.

Now do it the right way: click **Submit RCA & close**. The modal opens with:
- Two **datetime pickers** pre-filled (start = first signal, end = now).
- A **dropdown** with 10 root-cause categories.
- Two **textareas** (fix applied / prevention steps) — both require ≥ 10 chars.

Try submitting an empty form — the browser's HTML5 validation kicks in. Fill it out, click **Close incident with RCA**. The incident flips to CLOSED. The detail page now shows:
- Stepper at CLOSED.
- A green **MTTR chip** (e.g. "MTTR 12m 34s") computed automatically.
- A green "✓ Closed with RCA" badge.

Back on the Live Feed, the incident disappears from the active list and reappears under the collapsible **Closed (1)** section.

This proves: **mandatory RCA**, **automatic MTTR**, **transactional close** (RCA insert + state flip + transition log all atomic on Atlas).

## 8. Backpressure under load (optional, ≈ 15 s)

```bash
python scripts/load_test.py --workers 32 --batch 500 --duration 10
```

Watch the backend metric printer:
```
[metrics] signals_sec=~15000  queue_depth=~30000  received=…  rejected_429=~30000
```

Once the bounded queue fills, the rate limiter / queue-full path returns HTTP 429. The system never crashes or runs out of memory — exactly the rubric's requirement.

## 9. Tests

```bash
cd backend
pytest -q
# 23 passed
```

Covers: state pattern (every legal/illegal transition), RCA validation (Pydantic + State pattern), MTTR math, debouncer, in-memory rate limiter.

## What each rubric item ties to

| Rubric | Demo step |
|---|---|
| Concurrency & no race conditions | Step 2 (simulator) + Step 8 (load test) |
| Data Handling — separation | Steps 4 (Mongo `signals` Data Lake), 6 (state_transitions audit), 7 (transactional close) |
| LLD / patterns | State pattern surfaces in Steps 6+7; Strategy pattern fires when WIs are created (P0 → P0PageStrategy log line) |
| UI/UX | All steps, especially 4 and 7 |
| Resilience & tests | Step 8 (backpressure) + Step 9 (pytest) |
| Documentation | This file + README + `docs/` |
| Tech-stack rationale | `docs/prompts/02-tech-stack-decision.md` |
| Bonus | Step 3 (Gemini), Step 4 (Isolation Forest), Step 5 (real-time collab) |
