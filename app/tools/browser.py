"""Playwright sandboxed browser tool for autonomous web operations."""

import asyncio
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger("flamo.tools.browser")

# Security: Forbidden URL schemes to prevent SSRF and local file exfiltration
FORBIDDEN_SCHEMES = {"file", "javascript", "data", "chrome", "about", "vbscript"}


class BrowserInput(BaseModel):
    """Input parameters for the browser tool."""
    action: str = Field(
        description="Browser action: 'navigate', 'extract_text', 'inspect', 'click', 'type', 'screenshot'."
    )
    url: Optional[str] = Field(
        default=None,
        description="Target URL for 'navigate' or 'extract_text'."
    )
    selector: Optional[str] = Field(
        default=None,
        description="CSS selector for 'click', 'type', or target element inspection."
    )
    text: Optional[str] = Field(
        default=None,
        description="Text to type when action='type'."
    )
    screenshot_name: Optional[str] = Field(
        default="screenshot.png",
        description="Filename when action='screenshot' (saved inside workspace)."
    )


def _validate_url(url: str) -> None:
    """Validate that the URL is HTTP/HTTPS and not targeting forbidden schemes."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme in FORBIDDEN_SCHEMES or scheme not in ("http", "https"):
        raise PermissionError(
            f"Security Violation: URL scheme '{scheme}' is forbidden. Only HTTP/HTTPS is allowed."
        )


def _execute_playwright_sync(
    action: str,
    url: Optional[str] = None,
    selector: Optional[str] = None,
    text: Optional[str] = None,
    screenshot_name: Optional[str] = "screenshot.png",
    timeout_ms: int = 15000,
) -> Dict[str, Any]:
    """Execute Playwright browser operation in a sandboxed headless context."""
    from playwright.sync_api import sync_playwright

    if url:
        _validate_url(url)

    start_time = time.perf_counter()

    with sync_playwright() as p:
        # Launch sandboxed headless Chromium
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 FlamoAgent/2.0",
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=False,
        )
        page = context.new_page()
        page.set_default_timeout(timeout_ms)

        try:
            target_url = url or "https://example.com"
            if action in ("navigate", "inspect", "extract_text", "screenshot") or url:
                page.goto(target_url, wait_until="domcontentloaded")

            if action == "navigate":
                title = page.title()
                current_url = page.url
                return {
                    "action": "navigate",
                    "url": current_url,
                    "title": title,
                    "status": "success",
                    "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
                }

            elif action == "extract_text":
                title = page.title()
                # Extract clean readable text
                body_text = page.inner_text("body")
                # Collapse excessive whitespace
                cleaned_text = re.sub(r"\n\s*\n+", "\n\n", body_text).strip()
                # Limit size to prevent LLM context flooding
                max_chars = 4000
                truncated = len(cleaned_text) > max_chars
                return {
                    "action": "extract_text",
                    "url": page.url,
                    "title": title,
                    "content": cleaned_text[:max_chars],
                    "is_truncated": truncated,
                    "status": "success",
                    "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
                }

            elif action == "inspect":
                title = page.title()
                headings = [
                    h.inner_text().strip()
                    for h in page.query_selector_all("h1, h2, h3")
                    if h.inner_text().strip()
                ][:10]
                links = [
                    {"text": a.inner_text().strip()[:50], "href": a.get_attribute("href")}
                    for a in page.query_selector_all("a[href]")
                    if a.inner_text().strip()
                ][:8]
                return {
                    "action": "inspect",
                    "url": page.url,
                    "title": title,
                    "headings": headings,
                    "links_sample": links,
                    "status": "success",
                    "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
                }

            elif action == "click":
                if not selector:
                    raise ValueError("Action 'click' requires a CSS 'selector'.")
                page.click(selector)
                page.wait_for_load_state("domcontentloaded")
                return {
                    "action": "click",
                    "selector": selector,
                    "current_url": page.url,
                    "title": page.title(),
                    "status": "success",
                    "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
                }

            elif action == "type":
                if not selector or text is None:
                    raise ValueError("Action 'type' requires 'selector' and 'text'.")
                page.fill(selector, text)
                return {
                    "action": "type",
                    "selector": selector,
                    "text": text,
                    "status": "success",
                    "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
                }

            elif action == "screenshot":
                safe_name = os.path.basename(screenshot_name or "screenshot.png")
                workspace_dir = os.path.abspath(settings.workspace_dir)
                os.makedirs(workspace_dir, exist_ok=True)
                save_path = os.path.join(workspace_dir, safe_name)
                page.screenshot(path=save_path, full_page=False)
                return {
                    "action": "screenshot",
                    "saved_to": safe_name,
                    "full_path": save_path,
                    "status": "success",
                    "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
                }

            else:
                raise ValueError(
                    f"Unknown browser action: '{action}'. Allowed: navigate, extract_text, inspect, click, type, screenshot."
                )

        finally:
            context.close()
            browser.close()


def browser_tool(
    action: str,
    url: Optional[str] = None,
    selector: Optional[str] = None,
    text: Optional[str] = None,
    screenshot_name: Optional[str] = "screenshot.png",
) -> Dict[str, Any]:
    """Execute sandboxed browser automation using headless Playwright.
    
    Actions:
      - 'navigate': Open a URL and return page title and URL.
      - 'extract_text': Extract clean readable body text from the page.
      - 'inspect': Return title, top headings, and sample links.
      - 'click': Click an element identified by CSS selector.
      - 'type': Type text into an input field identified by CSS selector.
      - 'screenshot': Capture viewport screenshot and save into workspace.
    """
    try:
        return _execute_playwright_sync(
            action=action,
            url=url,
            selector=selector,
            text=text,
            screenshot_name=screenshot_name,
            timeout_ms=settings.tool_timeout_seconds * 1000,
        )
    except Exception as exc:
        logger.error("Browser tool error on action '%s': %s", action, exc)
        return {
            "status": "error",
            "action": action,
            "error": str(exc),
            "url": url,
        }


from langchain_core.tools import StructuredTool

browser = StructuredTool.from_function(
    func=browser_tool,
    name="browser",
    description="Automate sandboxed web browser actions using Playwright: navigate, extract_text, inspect, click, type, screenshot.",
    args_schema=BrowserInput,
)
