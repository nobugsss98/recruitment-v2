from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class AuditLogCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: UUID | None = None
    actor_email: str | None = Field(default=None, max_length=320)
    action: str = Field(min_length=1, max_length=100)
    entity: str = Field(min_length=1, max_length=100)
    entity_id: str | None = Field(default=None, max_length=255)
    metadata: dict[str, object] = Field(default_factory=dict)


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    actor_id: UUID | None
    actor_email: str | None
    action: str
    entity: str
    entity_id: str | None
    timestamp: AwareDatetime
    metadata: dict[str, object]
