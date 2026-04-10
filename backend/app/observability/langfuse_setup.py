import os
from typing import Optional
from app.observability.logging_config import get_logger

logger = get_logger(__name__)

_langfuse_client = None


def get_langfuse():
    global _langfuse_client
    if _langfuse_client is not None:
        return _langfuse_client

    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    host = os.getenv("LANGFUSE_HOST", "http://localhost:3000")

    if not secret_key or not public_key or secret_key.startswith("sk-lf-your"):
        logger.warning("Langfuse keys not configured - tracing disabled")
        return None

    try:
        from langfuse import Langfuse
        _langfuse_client = Langfuse(
            secret_key=secret_key,
            public_key=public_key,
            host=host,
        )
        logger.info("Langfuse tracing initialized", extra={"stage": "startup"})
        return _langfuse_client
    except Exception as e:
        logger.warning(f"Failed to initialize Langfuse: {e}")
        return None


class TraceContext:
    """Context manager for a Langfuse trace spanning a full incident pipeline."""

    def __init__(self, incident_id: str, name: str = "incident-pipeline"):
        self.incident_id = incident_id
        self.name = name
        self._trace = None
        self._lf = get_langfuse()

    def start(self):
        if self._lf:
            try:
                self._trace = self._lf.trace(
                    name=self.name,
                    metadata={"incident_id": self.incident_id},
                )
            except Exception as e:
                logger.debug(f"Langfuse trace start failed: {e}")
        return self

    def span(self, name: str, input_data: Optional[dict] = None, output_data: Optional[dict] = None):
        if self._trace:
            try:
                return self._trace.span(
                    name=name,
                    input=input_data,
                    output=output_data,
                )
            except Exception as e:
                logger.debug(f"Langfuse span failed: {e}")
        return None

    def generation(self, name: str, model: str, prompt: str, completion: str, usage: Optional[dict] = None):
        if self._trace:
            try:
                return self._trace.generation(
                    name=name,
                    model=model,
                    prompt=prompt,
                    completion=completion,
                    usage=usage,
                )
            except Exception as e:
                logger.debug(f"Langfuse generation failed: {e}")
        return None

    def end(self):
        if self._lf:
            try:
                self._lf.flush()
            except Exception:
                pass
