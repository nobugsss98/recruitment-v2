from typing import Any


class DatabaseOperationError(RuntimeError):
    """A database request failed without exposing provider payload details."""

    def __init__(self, operation: str) -> None:
        super().__init__(f"Database operation failed: {operation}")
        self.operation = operation


class AmbiguousCandidateMatchError(ValueError):
    """Identity keys matched multiple different candidate profiles."""


def execute_query(query: Any, *, operation: str) -> list[dict[str, Any]]:
    try:
        response = query.execute()
    except Exception:
        raise DatabaseOperationError(operation) from None

    data = getattr(response, "data", None)
    if data is None:
        return []
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list) and all(isinstance(row, dict) for row in data):
        return data
    raise DatabaseOperationError(f"{operation} returned an invalid response")