"""Data models for Semantic Memory abstraction."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MemoryCategory(str, Enum):
    """Categories of persistent semantic memory."""
    TASK_MEMORY = "task_memory"
    USER_PREFERENCES = "user_preferences"
    PREVIOUS_FINDINGS = "previous_findings"
    REUSABLE_KNOWLEDGE = "reusable_knowledge"


class MemoryItem(BaseModel):
    """An individual unit of stored memory."""
    id: str
    category: MemoryCategory = MemoryCategory.REUSABLE_KNOWLEDGE
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    task_id: Optional[str] = None
    relevance_score: Optional[float] = None
    scoring_method: Optional[str] = None


class MemoryQuery(BaseModel):
    """Query model for retrieving relevant memories."""
    query: str
    category: Optional[MemoryCategory] = None
    limit: int = Field(default=5, ge=1, le=50)
