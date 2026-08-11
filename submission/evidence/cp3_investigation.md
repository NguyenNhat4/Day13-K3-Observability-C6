# CP3 Challenge Investigation

## Challenge Run

- Challenge ID: `day13-k3-observability-v1`
- Incident: `rag_slow`
- Affected feature: `refund`
- Latency threshold: `2000ms`
- Incident enabled evidence: `submission/evidence/cp3_incident_enable.txt`
- Challenge load output: `submission/evidence/cp3_challenge_load_test.txt`
- Incident disabled evidence: `submission/evidence/cp3_incident_disable.txt`

## Metrics Symptom

Before challenge, `/metrics` showed `traffic=0`.

After the official challenge load test:

- `traffic`: 5
- `latency_p50`: 5216ms
- `latency_p95`: 5572ms
- `latency_p99`: 5572ms
- `error_breakdown`: empty
- `quality_avg`: 0.86

All challenge requests returned HTTP 200, so the incident is latency degradation, not request failure. P95 `5572ms` is above the challenge threshold `2000ms`.

## Trace Evidence

Primary trace:

- Trace ID: `0020b19653db5d9897fec83d1b0fe762`
- Trace URL: `https://cloud.langfuse.com/project/cmso2lzdo03pzad0fbogsbjhs/traces/0020b19653db5d9897fec83d1b0fe762`
- Session ID: `k3-challenge-s02`
- Correlation ID: `req-0be80050`
- Root span `chat-response`: 5573ms
- Span `retrieve-context`: 2501ms
- Span `resolve-prompt`: 2920ms
- Generation `generate-response`: 151ms

The trace narrows the challenge-specific slowdown to `retrieve-context`, which consistently takes about 2500ms across all five challenge traces. `generate-response` stays around 151-152ms, so the LLM generation is not the root cause.

Secondary finding: `resolve-prompt` also adds latency because prompt lookup falls back to `local-v1` with `prompt_source=local-fallback`. This is a setup issue for prompt management, but it is not the official incident root cause.

## Log Evidence

Relevant log excerpt is saved at `submission/evidence/cp3_log_excerpt.jsonl`.

For the primary trace correlation ID `req-0be80050`:

- `request_received`: feature `refund`, session `k3-challenge-s02`, user hash `867738e76862`
- `response_sent`: `latency_ms=5572`, `tokens_in=31`, `tokens_out=97`, `cost_usd=0.001548`, `quality_score=0.9`

The control log shows `incident_enabled` with payload `{"name": "rag_slow"}` before the challenge traffic and `incident_disabled` after the investigation.

## Root Cause

The official challenge incident is `rag_slow`. In `app/mock_rag.py`, when `STATE["rag_slow"]` is true, `retrieve()` sleeps for 2.5 seconds before returning documents. The trace confirms this with `retrieve-context` spans around 2500ms, and the logs confirm affected `refund` requests exceed the 2000ms threshold.

## Fix Action

- Immediate fix: disable the `rag_slow` incident with `python scripts/inject_incident.py --disable`.
- Code/architecture fix: remove the artificial slow path or restore vector-store/RAG retrieval performance for the `refund` feature.
- Add/keep dedicated `retrieve-context` tracing so future RAG latency issues are visible separately from generation latency.

## Preventive Measure

- Alert when `latency_p95 > 2000ms` for `feature=refund`.
- Track `retrieve-context` span latency separately and alert when retrieval exceeds 1000ms.
- Add retrieval timeout/caching/fallback for the RAG layer so slow vector-store calls do not dominate end-to-end latency.
