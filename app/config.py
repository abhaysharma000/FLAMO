"""Application configuration for FLAMO Autonomous AI Operations Agent."""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables from .env file
load_dotenv()


class Settings(BaseModel):
    """Configuration settings for Flamo agent platform."""

    gemini_api_key: str = Field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", "").strip()
    )
    gemini_model: str = Field(
        default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
    )
    database_url: str = Field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./flamo.db").strip()
    )
    log_level: str = Field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").strip().upper()
    )
    max_retries: int = Field(
        default_factory=lambda: int(os.getenv("MAX_RETRIES", "3"))
    )
    workspace_dir: str = Field(
        default_factory=lambda: os.getenv("WORKSPACE_DIR", "./workspace").strip()
    )
    tool_timeout_seconds: int = Field(
        default_factory=lambda: int(os.getenv("TOOL_TIMEOUT_SECONDS", "30"))
    )

    # Phase 5: Semantic Memory & Vector Storage Configuration
    memory_backend: str = Field(
        default_factory=lambda: os.getenv("MEMORY_BACKEND", "sqlite").strip().lower()
    )
    embedding_model: str = Field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "gemini-embedding-001").strip()
    )
    chroma_persist_directory: str = Field(
        default_factory=lambda: os.getenv("CHROMA_PERSIST_DIRECTORY", "./workspace/chroma_memory").strip()
    )

    # Phase 7: Deployment, Server & Authentication Configuration
    host: str = Field(
        default_factory=lambda: os.getenv("HOST", "127.0.0.1").strip()
    )
    port: int = Field(
        default_factory=lambda: int(os.getenv("PORT", "8000"))
    )
    auth_enabled: bool = Field(
        default_factory=lambda: os.getenv("AUTH_ENABLED", "false").strip().lower() in ("true", "1", "yes")
    )
    operator_username: str = Field(
        default_factory=lambda: os.getenv("OPERATOR_USERNAME", "admin").strip()
    )
    operator_password: str = Field(
        default_factory=lambda: os.getenv("OPERATOR_PASSWORD", "").strip()
    )
    operator_password_hash: str = Field(
        default_factory=lambda: os.getenv("OPERATOR_PASSWORD_HASH", "").strip()
    )
    secret_key: str = Field(
        default_factory=lambda: os.getenv("SECRET_KEY", "").strip()
    )
    session_expire_minutes: int = Field(
        default_factory=lambda: int(os.getenv("SESSION_EXPIRE_MINUTES", "720"))
    )
    cookie_secure: bool = Field(
        default_factory=lambda: os.getenv("COOKIE_SECURE", "false").strip().lower() in ("true", "1", "yes")
    )
    cookie_samesite: str = Field(
        default_factory=lambda: os.getenv("COOKIE_SAMESITE", "lax").strip().lower()
    )
    cors_allowed_origins: str = Field(
        default_factory=lambda: os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
    )
    rate_limit_login_attempts: int = Field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_LOGIN_ATTEMPTS", "5"))
    )
    rate_limit_window_seconds: int = Field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "300"))
    )

    @property
    def effective_gemini_api_key(self) -> str:
        """Returns active Gemini API key. GEMINI_API_KEY takes precedence over GOOGLE_API_KEY."""
        gemini_env = os.getenv("GEMINI_API_KEY", "").strip()
        if gemini_env:
            return gemini_env
        google_env = os.getenv("GOOGLE_API_KEY", "").strip()
        if google_env:
            return google_env
        return self.gemini_api_key.strip()

    @property
    def resolved_workspace_path(self) -> Path:
        """Returns the absolute, resolved path to the safe workspace directory."""
        path = Path(self.workspace_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def resolved_chroma_persist_path(self) -> Path:
        """Returns the absolute, resolved path to the ChromaDB persistence directory."""
        path = Path(self.chroma_persist_directory).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def sqlite_db_path(self) -> str:
        """Extract local file path from sqlite:/// URL."""
        if self.database_url.startswith("sqlite:///"):
            return self.database_url.replace("sqlite:///", "")
        return "flamo.db"

    def validate_llm_config(self) -> None:
        """Validates that LLM requirements are met, raising a clear exception if not."""
        if not self.effective_gemini_api_key:
            raise ValueError(
                "CRITICAL CONFIGURATION ERROR: GEMINI_API_KEY (or GOOGLE_API_KEY) is missing or empty in .env. "
                "Please configure a valid GEMINI_API_KEY to run Flamo."
            )
        if not self.gemini_model:
            raise ValueError(
                "CRITICAL CONFIGURATION ERROR: GEMINI_MODEL is missing in .env. "
                "Specify a model such as 'gemini-3.8-flash'."
            )

    def validate_chroma_config(self) -> None:
        """Validates that requirements for ChromaDB backend are met."""
        if self.memory_backend == "chroma":
            if not self.effective_gemini_api_key:
                raise ValueError(
                    "CRITICAL CONFIGURATION ERROR: ChromaDB memory backend is enabled (MEMORY_BACKEND=chroma), "
                    "but neither GEMINI_API_KEY nor GOOGLE_API_KEY is configured in .env. "
                    "Please provide a Gemini API key or set MEMORY_BACKEND=sqlite."
                )

    @property
    def parsed_cors_origins(self) -> list[str]:
        """Returns list of allowed CORS origins, forbidding wildcard origins with credentials."""
        default_origins = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
        if not self.cors_allowed_origins:
            return default_origins

        origins = [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]
        if "*" in origins:
            raise ValueError(
                "CRITICAL SECURITY CONFIGURATION ERROR: Wildcard origin '*' is not allowed when credentials and authentication are enabled. Specify exact origins."
            )
        return origins

    def validate_deployment_security(self) -> bool:
        """Validate security boundaries for remote/public network exposure. Fail closed if insecure."""
        is_loopback = self.host in ("127.0.0.1", "localhost", "::1")
        if not is_loopback:
            # Bound to 0.0.0.0 or a non-loopback public interface
            if not self.auth_enabled:
                raise ValueError(
                    f"CRITICAL SECURITY CONFIGURATION ERROR: Application is configured to bind to public/remote interface '{self.host}' "
                    "without authentication enabled. To bind to public interfaces, set AUTH_ENABLED=true and configure "
                    "OPERATOR_PASSWORD or OPERATOR_PASSWORD_HASH in .env."
                )
            if not (self.operator_password or self.operator_password_hash):
                raise ValueError(
                    "CRITICAL SECURITY CONFIGURATION ERROR: AUTH_ENABLED=true but neither OPERATOR_PASSWORD nor "
                    "OPERATOR_PASSWORD_HASH is provided. Please set a secure operator password in .env."
                )
            if not self.secret_key:
                raise ValueError(
                    "CRITICAL SECURITY CONFIGURATION ERROR: SECRET_KEY is required for non-loopback deployment to secure session cookies. "
                    "Generate a 32+ character random secret in .env."
                )
        return True


# Global settings singleton
settings = Settings()


def get_settings() -> Settings:
    """Return the global application settings singleton."""
    return settings

