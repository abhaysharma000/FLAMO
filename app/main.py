import logging
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_auth import require_operator, router as auth_router
from app.api.routes_health import router as health_router
from app.api.routes_tasks import router as tasks_router
from app.api.routes_stream import router as stream_router
from app.api.routes_memory import router as memory_router
from app.api.routes_reports import router as reports_router
from app.config import settings
from app.services.task_service import task_service

# Structured Logging & Sensitive Secret Redaction Filter
class SensitiveDataFilter(logging.Filter):
    """Redacts API keys, credentials, and session tokens from log records."""
    REDACTION_PATTERNS = [
        (re.compile(r"AIzaSy[A-Za-z0-9_-]{30,40}"), "[REDACTED_GEMINI_KEY]"),
        (re.compile(r"(api[-_]?key\s*[:=]\s*)['\"]?([A-Za-z0-9_\-\.]{8,})['\"]?", re.IGNORECASE), r"\1[REDACTED]"),
        (re.compile(r"(password\s*[:=]\s*)['\"]?([^\s&'\"]+)['\"]?", re.IGNORECASE), r"\1[REDACTED]"),
        (re.compile(r"(bearer\s+)([a-zA-Z0-9_\-\.]{10,})", re.IGNORECASE), r"\1[REDACTED]"),
        (re.compile(r"(flamo_session=)([a-zA-Z0-9_\-]{10,})", re.IGNORECASE), r"\1[REDACTED]"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern, repl in self.REDACTION_PATTERNS:
                record.msg = pattern.sub(repl, record.msg)
        if record.args:
            new_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    for pattern, repl in self.REDACTION_PATTERNS:
                        arg = pattern.sub(repl, arg)
                new_args.append(arg)
            record.args = tuple(new_args)
        return True


# Configure root logging with secret redaction
logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
root_logger = logging.getLogger()
root_logger.addFilter(SensitiveDataFilter())
logger = logging.getLogger("flamo")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verify security configuration, sandbox workspace, and operational readiness on startup."""
    # Enforce fail-closed deployment validation
    settings.validate_deployment_security()

    workspace_path = settings.resolved_workspace_path
    logger.info(
        "Flamo platform initialized. Workspace sandbox: %s, Auth enabled: %s, Bind: %s:%s",
        workspace_path,
        settings.auth_enabled,
        settings.host,
        settings.port,
    )
    yield
    logger.info("Flamo platform shutting down gracefully.")


# Initialize FastAPI application
app = FastAPI(
    title="FLAMO — Autonomous AI Operations Agent",
    description="A production-grade autonomous agent platform featuring planning, tool execution loops, verification, and inspectable traces.",
    version="2.0.0",
    lifespan=lifespan,
)

# Correlation ID Middleware
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID") or f"req-{uuid.uuid4().hex[:12]}"
    request.state.correlation_id = correlation_id
    response: Response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response

# CORS Middleware with validated allowed origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.parsed_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(tasks_router, dependencies=[Depends(require_operator)])
app.include_router(stream_router)
app.include_router(memory_router, dependencies=[Depends(require_operator)])
app.include_router(reports_router, dependencies=[Depends(require_operator)])

# Resolve frontend assets directory
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
dist_dir = frontend_dir / "dist"

if dist_dir.exists() and (dist_dir / "index.html").exists():
    if (dist_dir / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(dist_dir / "assets")), name="assets")
    if (dist_dir / "static").exists():
        app.mount("/static", StaticFiles(directory=str(dist_dir / "static")), name="static")

    @app.get("/", include_in_schema=False)
    def serve_dist_index():
        return FileResponse(dist_dir / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_dist_spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("ws/"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not Found")
        try:
            resolved_dist = dist_dir.resolve()
            target_file = (dist_dir / full_path).resolve()
            target_file.relative_to(resolved_dist)
            if target_file.is_file():
                return FileResponse(target_file)
        except (ValueError, PermissionError):
            pass
        return FileResponse(dist_dir / "index.html")
elif frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

    @app.get("/", include_in_schema=False)
    def serve_index():
        return FileResponse(frontend_dir / "index.html")



def run_cli_task(goal: str):
    """Run an autonomous task synchronously via CLI and print inspectable results."""
    print("=" * 65)
    print(" FLAMO -- Autonomous AI Operations Agent (CLI Mode)")
    print("=" * 65)
    print(f"Goal: {goal}\n")

    task = task_service.execute_task_sync(goal)

    print("\n" + "=" * 65)
    print(f"TASK EXECUTION SUMMARY [ID: {task.id}]")
    print("=" * 65)
    print(f"Status:       {task.status.value.upper()}")
    print(f"Duration:     {task.duration_seconds}s")
    print(f"Tool Calls:   {task.total_tool_calls}")
    print(f"Retries:      {task.retry_count}")

    if task.plan:
        print("\nEXECUTION PLAN:")
        for step in task.plan.steps:
            mark = "[DONE]" if step.status.value == "completed" else "[    ]"
            print(f"  {mark} Step {step.id}: {step.title} ({step.description})")
            if step.output:
                print(f"         Output: {step.output}")

    if task.verification_result:
        vr = task.verification_result
        verdict = "PASSED" if vr.is_valid else "FAILED"
        print(f"\nVERIFICATION [{verdict} - Score: {vr.score*100:.0f}%]:")
        for cp in vr.checks_passed:
            print(f"  [PASS] {cp}")
        for cf in vr.checks_failed:
            print(f"  [FAIL] {cf}")

    print("\nFINAL ANSWER:")
    print("-" * 65)
    print(task.final_answer or "No answer formulated.")
    print("-" * 65)


def main():
    """Entry point when executing `python -m app.main`."""
    parser = argparse.ArgumentParser(description="FLAMO Autonomous AI Operations Agent")
    parser.add_argument("goal", nargs="?", default="What is 125 multiplied by 48?", help="Goal for the agent to execute")
    parser.add_argument("--serve", action="store_true", help="Start the FastAPI web server")
    parser.add_argument("--host", default="0.0.0.0", help="Host address for web server")
    parser.add_argument("--port", type=int, default=8000, help="Port for web server")
    args = parser.parse_args()

    if args.serve:
        import uvicorn
        print(f"Starting Flamo Control Center at http://{args.host}:{args.port}")
        uvicorn.run("app.main:app", host=args.host, port=args.port, reload=False)
    else:
        run_cli_task(args.goal)


if __name__ == "__main__":
    main()