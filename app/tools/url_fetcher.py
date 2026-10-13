"""URL content fetcher tool for extracting readable webpage text."""

import ipaddress
import logging
import socket
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger("flamo.tools.url_fetcher")


def is_forbidden_or_private_host(hostname: str) -> bool:
    """Validate that hostname does not target loopback, private, or link-local network."""
    clean_host = hostname.strip().lower()
    if clean_host in ("localhost", "0.0.0.0", "::1", "metadata.google.internal"):
        return True
    try:
        ip = ipaddress.ip_address(clean_host)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        pass

    try:
        addrinfo = socket.getaddrinfo(clean_host, None)
        for _, _, _, _, sockaddr in addrinfo:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True
    except Exception:
        pass
    return False


class UrlFetcherInput(BaseModel):
    """Input parameters for URL content fetcher."""

    url: str = Field(description="The full HTTP/HTTPS URL of the webpage to retrieve")
    max_length: int = Field(default=4000, ge=500, le=15000, description="Maximum characters of extracted text to return")


@tool(args_schema=UrlFetcherInput)
def url_fetcher(url: str, max_length: int = 4000) -> str:
    """Fetch and parse readable text content from a web page URL.
    
    Automatically validates against private/loopback SSRF, strips HTML formatting,
    and returns clean article/page text with HTTP metadata.
    """
    clean_url = url.strip()
    if not (clean_url.startswith("http://") or clean_url.startswith("https://")):
        raise ValueError(f"Invalid URL protocol. URL must start with http:// or https://: '{clean_url}'")

    parsed = urlparse(clean_url)
    hostname = parsed.hostname or ""
    if not hostname or is_forbidden_or_private_host(hostname):
        raise PermissionError(
            f"Security Violation: Access to loopback/private host '{hostname}' is strictly forbidden."
        )

    logger.info("Fetching URL content from: %s", clean_url)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 FlamoAgent/1.0"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        with httpx.Client(timeout=12.0, follow_redirects=True, headers=headers) as client:
            response = client.get(clean_url)

            if response.status_code >= 400:
                raise ValueError(
                    f"HTTP Error {response.status_code} ({response.reason_phrase}) while fetching {clean_url}"
                )

            final_url = str(response.url)
            content_type = response.headers.get("content-type", "").lower()
            page_title = parsed.netloc

            if "text/html" in content_type or "xml" in content_type:
                soup = BeautifulSoup(response.text, "html.parser")
                title_tag = soup.find("title")
                if title_tag and title_tag.string:
                    page_title = title_tag.string.strip()

                # Remove non-content elements
                for element in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "button", "form"]):
                    element.decompose()

                text = soup.get_text(separator="\n\n")
            else:
                text = response.text

            # Clean whitespace, filter boilerplate lines and preserve distinct paragraphs
            boilerplate_patterns = [
                "skip to content", "signed in", "reload to refresh", "to refresh your session",
                "signed out", "switched account", "dismiss alert", "jump to",
                "toggle navigation", "all rights reserved", "terms of service", "privacy statement"
            ]
            raw_blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
            cleaned_blocks = []
            for b in raw_blocks:
                b_lines = [l.strip() for l in b.splitlines() if l.strip()]
                b_text = " ".join(b_lines)
                if len(b_text) < 20:
                    continue
                if any(bp in b_text.lower() for bp in boilerplate_patterns):
                    continue
                cleaned_blocks.append(b_text)

            cleaned_text = "\n\n".join(cleaned_blocks)

            if not cleaned_text:
                return f"[Source URL: {final_url} | HTTP Status: {response.status_code} | Title: {page_title}]\n\nNotice: Webpage at {clean_url} was retrieved successfully, but contained no readable text."

            if len(cleaned_text) > max_length:
                cleaned_text = cleaned_text[:max_length] + f"\n\n[... Truncated at {max_length} characters of {len(cleaned_text)} total ...]"

            return f"[Source URL: {final_url} | HTTP Status: {response.status_code} | Title: {page_title}]\n\n{cleaned_text}"

    except httpx.TimeoutException:
        raise TimeoutError(f"Connection timed out while fetching URL: {clean_url}")
    except httpx.RequestError as e:
        raise ValueError(f"Network error accessing {clean_url}: {str(e)}")
