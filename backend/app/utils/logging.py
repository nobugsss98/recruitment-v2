"""Structured JSON logging with per-request IDs.

Never log secrets (passwords, API keys, tokens) or raw resume/candidate text.
Log only identifiers, counts, model names, and latencies.
"""

import logging
import time
import uuid

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


REQUEST_ID_HEADER = "X-Request-ID"


def configure_logging() -> None:
    """Configure structlog to emit JSON through the standard logging pipeline."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a request ID to every response and log request lifecycle events."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid4_hex()
        request.state.request_id = request_id
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        logger = get_logger("app.http")
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "request failed",
                method=request.method,
                path=request.url.path,
                duration_ms=round(duration_ms, 2),
            )
            raise
        finally:
            structlog.contextvars.clear_contextvars()
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )
        return response


def uuid4_hex() -> str:
    return uuid.uuid4().hex
