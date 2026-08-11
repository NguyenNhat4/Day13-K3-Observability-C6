from __future__ import annotations

from contextlib import contextmanager
import os
from typing import Any, Iterator

try:
    from langfuse import get_client, observe

    LANGFUSE_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover
    LANGFUSE_SDK_AVAILABLE = False

    def observe(*args: Any, **kwargs: Any):
        def decorator(func):
            return func

        return decorator

    class _DummyClient:
        def update_current_trace(self, **kwargs: Any) -> None:
            return None

        def update_current_generation(self, **kwargs: Any) -> None:
            return None

        def update_current_span(self, **kwargs: Any) -> None:
            return None

        def start_as_current_span(self, **kwargs: Any) -> "_NoopObservation":
            return _NoopObservation()

        def start_as_current_generation(self, **kwargs: Any) -> "_NoopObservation":
            return _NoopObservation()

        def flush(self) -> None:
            return None

    def get_client():
        return _DummyClient()


class _NoopObservation:
    def __enter__(self) -> "_NoopObservation":
        return self

    def __exit__(self, *_: Any) -> bool:
        return False

    def update(self, **kwargs: Any) -> None:
        return None


def get_langfuse_client():
    return get_client()


def tracing_enabled() -> bool:
    return LANGFUSE_SDK_AVAILABLE and bool(
        os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
    )


@contextmanager
def start_span(client: Any, **kwargs: Any) -> Iterator[Any]:
    if not tracing_enabled() or not hasattr(client, "start_as_current_span"):
        yield _NoopObservation()
        return

    with client.start_as_current_span(**kwargs) as span:
        yield span


@contextmanager
def start_generation(client: Any, **kwargs: Any) -> Iterator[Any]:
    if not tracing_enabled() or not hasattr(client, "start_as_current_generation"):
        yield _NoopObservation()
        return

    with client.start_as_current_generation(**kwargs) as generation:
        yield generation


def flush_langfuse() -> None:
    client = get_langfuse_client()
    if tracing_enabled() and hasattr(client, "flush"):
        client.flush()
