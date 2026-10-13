"""API endpoints for Persistent Semantic Memory store."""

from typing import List, Optional
from fastapi import APIRouter, Query, status
from pydantic import BaseModel

from app.models.memory import MemoryCategory, MemoryItem
from app.services.memory import memory_store

router = APIRouter(prefix="/api/memory", tags=["memory"])


class MemoryCreateRequest(BaseModel):
    category: MemoryCategory = MemoryCategory.REUSABLE_KNOWLEDGE
    content: str
    metadata: Optional[dict] = None
    task_id: Optional[str] = None


@router.post("", status_code=status.HTTP_201_CREATED)
async def store_memory(request: MemoryCreateRequest):
    """Store a semantic memory item."""
    item = MemoryItem(
        id="",
        category=request.category,
        content=request.content,
        metadata=request.metadata or {},
        task_id=request.task_id,
    )
    mem_id = memory_store.store(item)
    return {"id": mem_id, "status": "stored", "category": request.category}


@router.get("/search", response_model=List[MemoryItem])
async def search_memory(
    query: str = Query(..., min_length=1, description="Semantic search query"),
    category: Optional[MemoryCategory] = Query(None, description="Optional category filter"),
    limit: int = Query(5, ge=1, le=50, description="Max memories to return"),
):
    """Retrieve relevant memories ranked by the active store's scoring method."""
    return memory_store.retrieve(query=query, category=category, limit=limit)


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str):
    """Delete a memory item by ID."""
    success = memory_store.delete(memory_id)
    return {"id": memory_id, "deleted": success}
