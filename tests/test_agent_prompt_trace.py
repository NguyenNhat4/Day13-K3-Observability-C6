from __future__ import annotations

from app import agent as agent_module


class ManagedPrompt:
    version = 3

    def compile(self, **variables: str) -> str:
        return (
            f"Feature={variables['feature']}\n"
            f"Docs={variables['docs']}\n"
            f"Question={variables['message']}"
        )


class RecordingObservation:
    def __init__(self, start_kwargs: dict) -> None:
        self.start_kwargs = start_kwargs
        self.updates: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def update(self, **kwargs) -> None:
        self.updates.append(kwargs)


class RecordingLangfuseClient:
    def __init__(self) -> None:
        self.prompt = ManagedPrompt()
        self.trace_updates: list[dict] = []
        self.spans: list[RecordingObservation] = []
        self.generations: list[RecordingObservation] = []

    def get_prompt(self, name: str, **kwargs):
        return self.prompt

    def update_current_trace(self, **kwargs) -> None:
        self.trace_updates.append(kwargs)

    def start_as_current_span(self, **kwargs):
        span = RecordingObservation(kwargs)
        self.spans.append(span)
        return span

    def start_as_current_generation(self, **kwargs):
        generation = RecordingObservation(kwargs)
        self.generations.append(generation)
        return generation


def test_agent_links_prompt_version_to_trace_and_generation(monkeypatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "test-public-key")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("LANGFUSE_PROMPT_NAME", "day13-chat")
    monkeypatch.setenv("LANGFUSE_PROMPT_LABEL", "production")
    client = RecordingLangfuseClient()
    monkeypatch.setattr(agent_module, "get_langfuse_client", lambda: client)

    agent = agent_module.LabAgent()
    agent.run(
        user_id="student-01",
        feature="qa",
        session_id="session-01",
        message="Explain traces",
        correlation_id="req-test",
    )

    assert [span.start_kwargs["name"] for span in client.spans] == [
        "chat-response",
        "retrieve-context",
        "resolve-prompt",
    ]
    generation = client.generations[-1]
    assert generation.start_kwargs["name"] == "generate-response"
    assert generation.start_kwargs["model"] == agent.model
    assert generation.start_kwargs["prompt"] is client.prompt

    trace_metadata = client.trace_updates[-1]["metadata"]
    assert trace_metadata["prompt_name"] == "day13-chat"
    assert trace_metadata["prompt_label"] == "production"
    assert trace_metadata["prompt_version"] == "3"
    assert trace_metadata["prompt_source"] == "langfuse"
    assert trace_metadata["correlation_id"] == "req-test"
    assert client.trace_updates[0]["input"] == {
        "message": "Explain traces",
        "feature": "qa",
    }
    assert client.trace_updates[-1]["output"]["answer"].startswith("Starter answer.")
    assert generation.updates[-1]["metadata"]["prompt_version"] == "3"
    assert generation.updates[-1]["usage_details"]["prompt_tokens"] > 0
