"""Pydantic schemas for trace submission and response."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TraceCreate(BaseModel):
    """Request schema for submitting a new trace."""

    title: str = Field(min_length=1, max_length=500)
    context_text: str = Field(min_length=1)
    solution_text: str = Field(min_length=1)
    # max_length on list applies to the list length (number of elements), capped at 20 tags
    tags: list[str] = Field(default_factory=list, max_length=20)
    agent_model: Optional[str] = Field(None, max_length=100)
    agent_version: Optional[str] = Field(None, max_length=50)
    metadata_json: Optional[dict] = None
    supersedes_trace_id: Optional[uuid.UUID] = None
    review_after: Optional[datetime] = None
    watch_condition: Optional[str] = Field(None, max_length=500)


class TraceResponse(BaseModel):
    """Response schema for a trace, suitable for ORM serialization."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    title: str
    context_text: str
    solution_text: str
    trust_score: float
    confirmation_count: int
    tags: list[str] = Field(default_factory=list)
    depth_score: int = 0
    somatic_intensity: float = 0.0
    impact_level: str = "normal"
    retrieval_count: int = 0
    half_life_days: Optional[int] = None
    trace_type: str = "episodic"
    is_stale: bool = False
    is_flagged: bool = False
    context_fingerprint: Optional[dict] = None
    convergence_level: Optional[int] = None
    memory_temperature: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    contributor_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class TraceAccepted(BaseModel):
    """Immediate response after a trace is accepted for async processing."""

    id: uuid.UUID
    status: str = "pending"
    message: str = "Trace accepted for processing"
