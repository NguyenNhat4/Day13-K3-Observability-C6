from __future__ import annotations

import os
import time
from dataclasses import dataclass

from . import metrics
from .mock_llm import FakeLLM
from .mock_rag import retrieve
from .pii import hash_user_id, scrub_text, summarize_text
from .prompt_management import resolve_prompt
from .tracing import get_langfuse_client, start_generation, start_span, tracing_enabled


@dataclass
class AgentResult:
    answer: str
    latency_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    quality_score: float


class LabAgent:
    def __init__(self, model: str = "claude-sonnet-4-5") -> None:
        self.model = model
        self.llm = FakeLLM(model=model)

    def run(
        self,
        user_id: str,
        feature: str,
        session_id: str,
        message: str,
        correlation_id: str | None = None,
    ) -> AgentResult:
        started = time.perf_counter()
        langfuse_client = get_langfuse_client()
        request_metadata = {
            "app": os.getenv("APP_NAME", "day13-observability-lab"),
            "feature": feature,
            "model": self.model,
        }
        if correlation_id:
            request_metadata["correlation_id"] = correlation_id

        with start_span(
            langfuse_client,
            name="chat-response",
            input={"message": scrub_text(message), "feature": feature},
            metadata=request_metadata,
        ) as root_span:
            langfuse_client.update_current_trace(
                name="chat-response",
                user_id=hash_user_id(user_id),
                session_id=session_id,
                tags=["lab", f"feature:{feature}", self.model],
                input={"message": summarize_text(message), "feature": feature},
                metadata=request_metadata,
            )

            with start_span(
                langfuse_client,
                name="retrieve-context",
                input={"query": scrub_text(message), "feature": feature},
            ) as retrieval_span:
                try:
                    docs = retrieve(message)
                except Exception as exc:
                    retrieval_span.update(
                        level="ERROR",
                        status_message=f"{type(exc).__name__}: {scrub_text(str(exc))}",
                    )
                    raise
                retrieval_span.update(
                    output={"documents": [scrub_text(doc) for doc in docs]},
                    metadata={"doc_count": len(docs)},
                )

            with start_span(
                langfuse_client,
                name="resolve-prompt",
                input={"prompt_name": os.getenv("LANGFUSE_PROMPT_NAME", "day13-chat")},
            ) as prompt_span:
                prompt = resolve_prompt(
                    langfuse_client,
                    feature=feature,
                    docs=docs,
                    message=message,
                    enabled=tracing_enabled(),
                )
                prompt_metadata = {
                    "prompt_name": prompt.name,
                    "prompt_label": prompt.label,
                    "prompt_version": prompt.version,
                    "prompt_source": prompt.source,
                    "prompt_fetch_error": prompt.fetch_error,
                }
                prompt_span.update(output=prompt_metadata, metadata=prompt_metadata)

            generation_metadata = {
                **prompt_metadata,
                "doc_count": len(docs),
                "query_preview": summarize_text(message),
            }
            with start_generation(
                langfuse_client,
                name="generate-response",
                input=[{"role": "user", "content": scrub_text(prompt.text)}],
                model=self.model,
                metadata=generation_metadata,
                prompt=prompt.managed_prompt,
            ) as generation:
                try:
                    response = self.llm.generate(prompt.text)
                except Exception as exc:
                    generation.update(
                        level="ERROR",
                        status_message=f"{type(exc).__name__}: {scrub_text(str(exc))}",
                    )
                    raise

                quality_score = self._heuristic_quality(message, response.text, docs)
                latency_ms = int((time.perf_counter() - started) * 1000)
                cost_usd = self._estimate_cost(response.usage.input_tokens, response.usage.output_tokens)
                generation.update(
                    output=scrub_text(response.text),
                    usage_details={
                        "prompt_tokens": response.usage.input_tokens,
                        "completion_tokens": response.usage.output_tokens,
                    },
                    cost_details={"total": cost_usd},
                    metadata=generation_metadata,
                    prompt=prompt.managed_prompt,
                )

            output = {
                "answer": summarize_text(response.text),
                "quality_score": quality_score,
            }
            trace_metadata = {
                **request_metadata,
                **prompt_metadata,
                "latency_ms": latency_ms,
                "tokens_in": response.usage.input_tokens,
                "tokens_out": response.usage.output_tokens,
                "cost_usd": cost_usd,
            }
            root_span.update(output=output, metadata=trace_metadata)
            langfuse_client.update_current_trace(output=output, metadata=trace_metadata)

        metrics.record_request(
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            quality_score=quality_score,
        )

        return AgentResult(
            answer=response.text,
            latency_ms=latency_ms,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            cost_usd=cost_usd,
            quality_score=quality_score,
        )

    def _estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        input_cost = (tokens_in / 1_000_000) * 3
        output_cost = (tokens_out / 1_000_000) * 15
        return round(input_cost + output_cost, 6)

    def _heuristic_quality(self, question: str, answer: str, docs: list[str]) -> float:
        score = 0.5
        if docs:
            score += 0.2
        if len(answer) > 40:
            score += 0.1
        if question.lower().split()[0:1] and any(token in answer.lower() for token in question.lower().split()[:3]):
            score += 0.1
        if "[REDACTED" in answer:
            score -= 0.2
        return round(max(0.0, min(1.0, score)), 2)
