"""Health check and diagnostics API routes."""

from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status
from app.config import settings
from app.tools.registry import default_registry

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def get_health():
    """System health check endpoint verifying database, LLM settings, and tools."""
    tools_list = [t.name for t in default_registry.list_tool_metadata()]
    
    # Check LLM key status without revealing the key
    has_api_key = bool(settings.effective_gemini_api_key)
    
    is_chroma = (settings.memory_backend or "").strip().lower() == "chroma"
    db_type = "sqlite" if "sqlite" in settings.database_url.lower() else "postgresql"

    # Check database connectivity dynamically
    db_connected = True
    try:
        from app.services.database import repository
        with repository._connection() as conn:
            conn.execute("SELECT 1;").fetchone()
    except Exception:
        db_connected = False

    is_healthy = has_api_key and db_connected

    return {
        "status": "healthy" if is_healthy else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "2.0.0",
        "system": "FLAMO Autonomous AI Operations Agent",
        "llm": {
            "provider": "google-genai",
            "model": settings.gemini_model,
            "configured": has_api_key,
        },
        "database": {
            "type": db_type,
            "status": "connected" if db_connected else "disconnected",
        },
        "memory": {
            "backend": settings.memory_backend,
            "active_backend": settings.memory_backend,
            "search_method": "dense_vector" if is_chroma else "stemmed_token_match",
            "configured_embedding_model": settings.embedding_model,
            "active_embedding_model": settings.embedding_model if is_chroma else None,
            "embedding_model": settings.embedding_model if is_chroma else None,
            "vector_search_active": is_chroma,
        },
        "workspace": {
            "status": "ready" if settings.resolved_workspace_path.exists() else "unavailable",
            "sandbox_enabled": True,
            "exists": settings.resolved_workspace_path.exists(),
        },
        "tools_registered": {
            "count": len(tools_list),
            "tools": tools_list,
        },
    }


@router.get("/health/live")
def get_liveness():
    """Liveness probe: lightweight endpoint confirming application process is running."""
    return {
        "status": "alive",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/ready")
def get_readiness():
    """Readiness probe: validates critical dependencies before routing production traffic."""
    from fastapi import Response, status
    reasons = []

    # 1. Database check
    try:
        from app.services.database import repository
        with repository._connection() as conn:
            conn.execute("SELECT 1;").fetchone()
    except Exception as e:
        reasons.append(f"Database error: {type(e).__name__}")

    # 2. Workspace check
    try:
        if not settings.resolved_workspace_path.exists():
            reasons.append("Workspace directory inaccessible")
    except Exception as e:
        reasons.append(f"Workspace error: {type(e).__name__}")

    # 3. LLM key check
    if not settings.effective_gemini_api_key:
        reasons.append("Gemini API key unconfigured")

    # 4. Chroma check if enabled
    if (settings.memory_backend or "").strip().lower() == "chroma":
        try:
            if not settings.resolved_chroma_persist_path.exists():
                reasons.append("Chroma persistence directory inaccessible")
        except Exception as e:
            reasons.append(f"Chroma directory error: {type(e).__name__}")

    if reasons:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "reasons": reasons},
        )

    return {
        "status": "ready",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
