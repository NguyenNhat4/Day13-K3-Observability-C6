# Báo cáo Day 13 Observability

## 1. Thông tin nhóm

- Tên nhóm:
- Repository URL: `https://github.com/NguyenNhat4/Day13-K3-Observability-C6`
- Commit SHA cuối: `4ea98c9`
- Thành viên và vai trò:
  - Nguyễn Minh Phú - CP1 / Logging & PII
  - Nguyễn Minh Nhật - CP2 / Metrics, tracing, dashboard, prompt observability
  - Nguyễn Tiến Thành - CP3 / Điều tra challenge

## 2. Kết quả kỹ thuật

- Điểm `validate_logs.py`: `80/100`
- Tổng số traces: tối thiểu 10 traces đã xuất hiện trong Langfuse; CP3 có 5 traces challenge trong `submission/evidence/cp3_traces.json`.
- Số PII leak còn lại: `0`
- Link/đường dẫn dashboard: `submission/evidence/dashboard.png`
- Evidence chính:
  - `submission/evidence/cp3_validate_logs.txt`
  - `submission/evidence/cp3_validate_dashboard.txt`
  - `submission/evidence/cp3_traces.json`
  - `submission/evidence/cp3_log_excerpt.jsonl`
  - `submission/evidence/cp3_investigation.md`

## 3. Logging và tracing

- Evidence correlation ID: `submission/evidence/cp3_log_excerpt.jsonl`
  - Primary CP3 correlation ID: `req-0be80050`
  - Log `request_received`: feature `refund`, session `k3-challenge-s02`, user hash `867738e76862`
  - Log `response_sent`: `latency_ms=5572`, `tokens_in=31`, `tokens_out=97`, `cost_usd=0.001548`, `quality_score=0.9`
- Evidence PII redaction: `submission/evidence/cp3_validate_logs.txt`
  - `Potential PII leaks detected: 0`
- Evidence trace waterfall: `submission/evidence/cp3_traces.json`
  - Primary trace ID: `0020b19653db5d9897fec83d1b0fe762`
  - Trace URL: `https://cloud.langfuse.com/project/cmso2lzdo03pzad0fbogsbjhs/traces/0020b19653db5d9897fec83d1b0fe762`
- Giải thích một span đáng chú ý:
  - `retrieve-context` mất khoảng `2501ms` trong trace chính.
  - `generate-response` chỉ khoảng `151ms`.
  - Vì vậy latency chủ yếu đến từ RAG retrieval, không phải LLM generation.

## 4. Prompt versioning

- Prompt name: `day13-chat`
- Version/label baseline: `production`
- Version/label candidate:
- Trace ID của mỗi version:
- Bằng chứng đổi label hoặc rollback: `submission/evidence/prompt_v1.png`
- Ghi chú: CP3 traces hiện ghi `prompt_source=local-fallback`, `prompt_version=local-v1`, nghĩa là app có bật Langfuse nhưng prompt `day13-chat` label `production` chưa được fetch thành công từ Langfuse project tại thời điểm chạy challenge. Cần bổ sung prompt v1/v2 + ảnh rollback nếu nộp đủ CP2 prompt versioning.

## 5. Dashboard, SLO và alerts

- Kết quả `validate_dashboard.py`: `HỢP LỆ: 6/6 panel có trong dashboard contract.`
- Evidence dashboard: `submission/evidence/dashboard.png`
- SLO đã chọn và lý do:
  - SLO latency: `p95 <= 2000ms` cho feature quan trọng như `refund`.
  - Lý do: challenge threshold là `2000ms`; khi `rag_slow` bật, `latency_p95=5572ms`, vượt xa SLO.
- Alert rules và runbook:
  - Alert khi `latency_p95 > 2000ms` trong 5 phút.
  - Khi alert xảy ra: mở dashboard metrics, lọc trace có latency cao, xem waterfall để xác định span chậm, rồi tìm log cùng `correlation_id`.

## 6. Điều tra challenge

- Challenge ID: `day13-k3-observability-v1`
- Incident chính thức: `rag_slow`
- Affected feature: `refund`
- Latency threshold: `2000ms`
- Evidence chạy incident:
  - Enable: `submission/evidence/cp3_incident_enable.txt`
  - Load test: `submission/evidence/cp3_challenge_load_test.txt`
  - Disable: `submission/evidence/cp3_incident_disable.txt`

- Triệu chứng từ metrics:
  - Trước challenge: `traffic=0` trong `submission/evidence/cp3_metrics_before.json`
  - Sau challenge: `traffic=5`, `latency_p50=5216ms`, `latency_p95=5572ms`, `latency_p99=5572ms`, `error_breakdown={}` trong `submission/evidence/cp3_metrics_after.json`
  - Tất cả request trả HTTP 200, nên đây là latency incident, không phải error incident.

- Trace ID liên quan:
  - Primary trace: `0020b19653db5d9897fec83d1b0fe762`
  - URL: `https://cloud.langfuse.com/project/cmso2lzdo03pzad0fbogsbjhs/traces/0020b19653db5d9897fec83d1b0fe762`
  - Session: `k3-challenge-s02`
  - Correlation ID: `req-0be80050`
  - Root `chat-response`: `5573ms`
  - Span `retrieve-context`: `2501ms`
  - Span `resolve-prompt`: `2920ms`
  - Generation `generate-response`: `151ms`

- Log line/correlation ID liên quan:
  - File: `submission/evidence/cp3_log_excerpt.jsonl`
  - Correlation ID: `req-0be80050`
  - `request_received`: `feature=refund`, `session_id=k3-challenge-s02`
  - `response_sent`: `latency_ms=5572`, `tokens_in=31`, `tokens_out=97`, `cost_usd=0.001548`, `quality_score=0.9`

- Root cause:
  - Root cause là incident `rag_slow` làm tầng RAG retrieval chậm.
  - Trong `app/mock_rag.py`, khi `STATE["rag_slow"]` bật, `retrieve()` chạy `time.sleep(2.5)`.
  - Trace xác nhận `retrieve-context` mất khoảng `2500ms` trên các request `refund`, còn `generate-response` chỉ khoảng `151-152ms`.

- Fix action:
  - Immediate fix: tắt incident bằng `python scripts/inject_incident.py --disable`.
  - Code/architecture fix: bỏ slow path hoặc khôi phục hiệu năng vector-store/RAG cho feature `refund`.
  - Giữ span `retrieve-context` để debug các lỗi RAG latency về sau.

- Preventive measure:
  - Alert khi `latency_p95 > 2000ms` cho feature `refund`.
  - Theo dõi riêng latency của span `retrieve-context`, cảnh báo khi retrieval > `1000ms`.
  - Thêm timeout/cache/fallback cho RAG để vector-store chậm không kéo sập latency end-to-end.

## 7. Đóng góp cá nhân

| Thành viên | Phần việc | Commit/PR | Điều đã học |
|---|---|---|---|
| Nguyễn Minh Phú | CP1 - Logging & PII: hoàn thiện correlation ID, log enrichment, PII redaction và chạy validate log. | `c66b5d7` (`Checkpoint1`), `7a57bfb` (`fix: detect and redact Vietnamese phone PII`) | Log phải có context đầy đủ trước khi debug incident; PII cần được scrub trước khi render JSON log; correlation ID là khóa để nối request, response và evidence. |
| Nguyễn Minh Nhật | CP2 - Metrics, traces, dashboard và prompt observability: tạo trace trên Langfuse, bổ sung metadata tracing, chuẩn bị dashboard/evidence và prompt observability workflow. | `f1a02e5` (`feat: add dashboard and prompt observability workflow`), `da1ad4b` (`feat: enhance observability with response tracing and add new evidence images`) | Trace cần metadata `prompt_name`, `prompt_label`, `prompt_version`; dashboard phải bám đúng 6 panel trong contract; metrics giúp phát hiện triệu chứng trước khi mở trace. |
| Nguyễn Tiến Thành | CP3 - Chạy challenge chính thức, bật/tắt incident `rag_slow`, thu metrics/log/trace evidence, xác định root cause và viết phần điều tra trong report. | CP3 evidence trong `submission/evidence/cp3_*`; trace chính `0020b19653db5d9897fec83d1b0fe762`; report cập nhật tại `submission/REPORT.md`. | Biết cách điều tra theo luồng Metrics → Traces → Logs → Root cause; dùng `correlation_id` để nối log với trace; phân biệt latency do RAG retrieval với latency do LLM generation. |
