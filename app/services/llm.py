"""LLM Service initialization and abstraction for Flamo."""

import logging
from typing import Any, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from app.config import settings

logger = logging.getLogger("flamo.services.llm")


def get_llm(temperature: float = 0.0, model_override: Optional[str] = None) -> ChatGoogleGenerativeAI:
    """Instantiate and return a configured Gemini Chat model instance.
    
    Ensures API keys are safely retrieved and never logged or leaked.
    """
    settings.validate_llm_config()
    model_name = model_override or settings.gemini_model
    
    logger.debug("Instantiating ChatGoogleGenerativeAI with model=%s", model_name)
    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=settings.gemini_api_key,
        temperature=temperature,
    )


def extract_text_content(content: Any) -> str:
    """Safely convert LLM message content (str, list of dicts/parts, etc.) into clean text."""
    if not content:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if "text" in item and item["text"]:
                    parts.append(str(item["text"]))
            elif hasattr(item, "text") and item.text:
                parts.append(str(item.text))
            elif isinstance(item, str):
                parts.append(item)
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


# Standard LLM instance for workflow nodes
try:
    llm = get_llm(temperature=0.0)
except Exception as e:
    logger.warning("LLM initialization deferred: %s", e)
    llm = None  # Will be lazily initialized or caught when invoked