"""Evidence pipeline and Claim Verification service."""

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from app.models.evidence import (
    Claim,
    Evidence,
    EvidencePipelineResult,
    EvidenceStatus,
    Source,
    SourceType,
)

logger = logging.getLogger("flamo.services.evidence")

# Known authoritative domain patterns
PRIMARY_DOMAINS = {
    "python.org",
    "docs.python.org",
    "pypi.org",
    "langchain.com",
    "langchain-ai.github.io",
    "fastapi.tiangolo.com",
    "docs.anthropic.com",
    "ai.google.dev",
    "openai.com",
    "w3.org",
    "ietf.org",
    "microsoft.com",
    "docs.microsoft.com",
    "learn.microsoft.com",
    "microsoft.github.io",
    "llamaindex.ai",
    "docs.llamaindex.ai",
    "crewai.com",
    "docs.crewai.com",
}

# Verified official GitHub organization namespaces
OFFICIAL_GITHUB_ORGS = {
    "langchain-ai",
    "crewaiinc",
    "microsoft",
    "run-llama",
    "tiangolo",
    "pydantic",
    "python",
    "google",
    "meta",
    "openai",
    "anthropics",
}

# English stop words to filter out when assessing core semantic tokens
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "of",
    "with", "by", "from", "as", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "can", "could", "should", "would",
    "will", "shall", "may", "might", "must", "it", "its", "this", "that", "these",
    "those", "there", "their", "they", "we", "our", "you", "your", "which", "what",
    "who", "whom", "how", "when", "where", "why", "all", "any", "both", "each",
    "few", "more", "most", "other", "some", "such", "than", "too", "very", "also",
    "just", "about", "into", "through", "during", "before", "after", "above", "below",
}

NEGATION_WORDS = {
    "not", "no", "never", "cannot", "neither", "nor", "without", "lacks",
    "unsupported", "false", "refuted", "non", "deprecated", "obsolete", "abandoned",
}

RELATIONAL_ACTION_WORDS = {
    "transition", "transitioning", "transitioned", "transitions",
    "migrate", "migrating", "migrated", "migration", "migrates",
    "replace", "replacing", "replaced", "replaces", "replacement",
    "supersede", "superseded", "supersedes",
    "evolve", "evolving", "evolved", "evolution",
    "shift", "shifting", "shifted",
    "merge", "merging", "merged",
    "deprecated", "deprecating", "deprecation",
}


def classify_source_type(url: str) -> SourceType:
    """Classify source authority based on URL domain, subdomain, and organization path."""
    if not url or not isinstance(url, str):
        return SourceType.WEB_SEARCH
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]

        # Secure domain comparison: must match exact domain or valid subdomain
        is_primary_domain = any(
            domain == auth_d or domain.endswith("." + auth_d)
            for auth_d in PRIMARY_DOMAINS
        )

        if is_primary_domain:
            if "docs" in domain or "/docs" in url or "/doc" in url:
                return SourceType.PRIMARY
            return SourceType.PRIMARY

        # GitHub validation: do not trust arbitrary user repos as official
        if domain == "github.com" or domain.endswith(".github.com"):
            path_parts = [p for p in parsed.path.lower().strip("/").split("/") if p]
            if path_parts and path_parts[0] in OFFICIAL_GITHUB_ORGS:
                return SourceType.OFFICIAL_REPO
            return SourceType.SECONDARY

        if "docs." in domain or "/docs" in url or "/doc" in url or "documentation" in domain:
            return SourceType.DOCUMENTATION

        if any(blog in domain for blog in ["medium.com", "dev.to", "substack.com", "reddit.com", "blogspot.com"]):
            return SourceType.SECONDARY

        return SourceType.WEB_SEARCH
    except Exception:
        return SourceType.WEB_SEARCH


class EvidenceService:
    """Service to process research outputs, extract claims, and verify evidence."""

    def create_source(
        self,
        url: str,
        title: Optional[str] = None,
        http_status: Optional[int] = None,
        final_url: Optional[str] = None,
        retrieval_status: str = "retrieved",
    ) -> Source:
        """Create a typed Source object with auto-classified authority and retrieval status."""
        try:
            domain = urlparse(url).netloc.lower()
        except Exception:
            domain = ""
        stype = classify_source_type(url)
        return Source(
            url=url,
            title=title or domain or "Web Source",
            source_type=stype,
            domain=domain,
            retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
            http_status=http_status,
            final_url=final_url or url,
            retrieval_status=retrieval_status,
        )

    def extract_evidence_from_tool_results(
        self,
        tool_results: List[Any],
    ) -> List[Evidence]:
        """Parse observations from web_search, url_fetcher, and browser tools into Evidence."""
        evidence_list: List[Evidence] = []

        for record in tool_results:
            tool_name = getattr(record, "tool_name", "")
            result = getattr(record, "result", None)
            is_error = getattr(record, "is_error", False)
            if is_error or not result:
                continue

            # 1. Parsing web_search results
            if tool_name == "web_search":
                if isinstance(result, list):
                    for item in result:
                        if isinstance(item, dict):
                            url = str(item.get("url", "")).strip()
                            title = str(item.get("title", "")).strip()
                            snippet = str(item.get("snippet", "")).strip()
                            if not snippet or not url or len(snippet) < 25:
                                continue

                            source = self.create_source(url=url, title=title, retrieval_status="search_snippet")
                            ev_id = f"ev-{uuid.uuid4().hex[:8]}"
                            evidence = Evidence(
                                id=ev_id,
                                source=source,
                                claim_text=snippet[:200],
                                supporting_snippet=snippet,
                                confidence=0.85 if source.source_type in (SourceType.PRIMARY, SourceType.OFFICIAL_REPO) else 0.65,
                                status=EvidenceStatus.UNVERIFIED,
                                explanation=f"Search snippet from {source.title} ({source.source_type.value})",
                                retrieval_status="search_snippet",
                                final_url=url,
                            )
                            evidence_list.append(evidence)

                elif isinstance(result, str):
                    pattern = r"(?:^|\n)\s*\d+\.\s*(?P<title>[^\n]+)\n\s*URL:\s*(?P<url>https?://[^\s\n]+)\n\s*Summary:\s*(?P<snippet>[^\n]+(?:\n(?!\s*\d+\.|\Z)[^\n]+)*)"
                    for m in re.finditer(pattern, result):
                        url = m.group("url").strip()
                        title = m.group("title").strip()
                        snippet = m.group("snippet").strip()
                        if snippet and url and len(snippet) >= 25:
                            source = self.create_source(url=url, title=title, retrieval_status="search_snippet")
                            ev_id = f"ev-{uuid.uuid4().hex[:8]}"
                            evidence = Evidence(
                                id=ev_id,
                                source=source,
                                claim_text=snippet[:200],
                                supporting_snippet=snippet,
                                confidence=0.85 if source.source_type in (SourceType.PRIMARY, SourceType.OFFICIAL_REPO) else 0.65,
                                status=EvidenceStatus.UNVERIFIED,
                                explanation=f"Search snippet from {source.title} ({source.source_type.value})",
                                retrieval_status="search_snippet",
                                final_url=url,
                            )
                            evidence_list.append(evidence)

            # 2. Parsing url_fetcher results (full page text)
            elif tool_name == "url_fetcher":
                url = ""
                title = ""
                content = ""
                status_code: Optional[int] = 200
                final_url = ""

                if isinstance(result, str):
                    header_m = re.match(
                        r"^\[Source URL:\s*(?P<final_url>[^\s|]+)\s*\|\s*HTTP Status:\s*(?P<status>\d+)\s*\|\s*Title:\s*(?P<title>[^\]]+)\]\n\n(?P<body>.*)$",
                        result,
                        re.DOTALL,
                    )
                    if header_m:
                        final_url = header_m.group("final_url").strip()
                        status_code = int(header_m.group("status"))
                        title = header_m.group("title").strip()
                        content = header_m.group("body").strip()
                        url = final_url
                    else:
                        args = getattr(record, "arguments", {}) or {}
                        url = str(args.get("url", "")).strip() if isinstance(args, dict) else ""
                        final_url = url
                        parsed_u = urlparse(url)
                        title = parsed_u.netloc or "Web Resource"
                        content = result.strip()
                elif isinstance(result, dict):
                    url = str(result.get("url", "")).strip()
                    final_url = url
                    title = str(result.get("title", "")).strip()
                    content = str(result.get("content", "")).strip()
                    status_code = result.get("http_status", 200)

                # Skip failed or empty fetches
                if not content or len(content) < 30 or (status_code and status_code >= 400):
                    continue

                source = self.create_source(
                    url=url,
                    title=title,
                    http_status=status_code,
                    final_url=final_url,
                    retrieval_status=f"HTTP {status_code}" if status_code else "HTTP 200",
                )

                raw_paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
                paragraphs = [p for p in raw_paragraphs if len(p) > 35]
                if len(paragraphs) < 3 and "\n" in content:
                    paragraphs = []
                    current_block = []
                    current_len = 0
                    for line in content.split("\n"):
                        lp = line.strip()
                        if not lp:
                            continue
                        if len(lp) < 40 and any(h in lp.lower() for h in ["introduction", "documentation", "table of contents", "section titled"]):
                            continue
                        current_block.append(lp)
                        current_len += len(lp)
                        if current_len >= 120:
                            paragraphs.append(" ".join(current_block))
                            current_block = []
                            current_len = 0
                    if current_block:
                        paragraphs.append(" ".join(current_block))
                paragraphs = [p for p in paragraphs if len(p) >= 35]
                if not paragraphs and len(content) > 35:
                    paragraphs = [content[:800]]

                for para in paragraphs[:25]:
                    ev_id = f"ev-{uuid.uuid4().hex[:8]}"
                    evidence = Evidence(
                        id=ev_id,
                        source=source,
                        claim_text=para[:180],
                        supporting_snippet=para[:800],
                        confidence=0.95 if source.source_type in (SourceType.PRIMARY, SourceType.OFFICIAL_REPO) else 0.80,
                        status=EvidenceStatus.UNVERIFIED,
                        explanation=f"Direct passage from page {source.title} ({source.source_type.value}, HTTP {status_code})",
                        http_status=status_code,
                        retrieval_status=f"HTTP {status_code}",
                        final_url=final_url,
                    )
                    evidence_list.append(evidence)

            # 3. Parsing browser results
            elif tool_name == "browser" and isinstance(result, dict):
                url = str(result.get("url", "")).strip()
                title = str(result.get("title", "")).strip()
                content = str(result.get("content", "")).strip()
                if url and content and len(content) >= 30:
                    source = self.create_source(url=url, title=title, retrieval_status="browser_dom")
                    paragraphs = [p.strip() for p in content.split("\n\n") if len(p.strip()) > 35]
                    if not paragraphs and len(content) > 35:
                        paragraphs = [content[:500]]

                    for para in paragraphs[:8]:
                        ev_id = f"ev-{uuid.uuid4().hex[:8]}"
                        evidence = Evidence(
                            id=ev_id,
                            source=source,
                            claim_text=para[:180],
                            supporting_snippet=para[:500],
                            confidence=0.90 if source.source_type in (SourceType.PRIMARY, SourceType.OFFICIAL_REPO) else 0.75,
                            status=EvidenceStatus.UNVERIFIED,
                            explanation=f"Extracted DOM text from {source.title} ({source.source_type.value})",
                            retrieval_status="browser_dom",
                            final_url=url,
                        )
                        evidence_list.append(evidence)

        return evidence_list

    def extract_claims_from_text(self, text: str) -> List[Claim]:
        """Extract key factual statements from synthesized text, filtering markdown formatting."""
        if not text:
            return []

        lines = text.split("\n")
        current_subject = None
        claims: List[Claim] = []

        meta_disclaimers = [
            "evidence is unavailable",
            "evidence regarding",
            "evidence was unavailable",
            "cannot be verified at this time",
            "research evidence is unavailable",
            "no direct evidence",
            "details cannot be verified",
            "evidence could not be retrieved",
            "primary evidence is unavailable",
            "direct primary source evidence",
            "no confirmed technical details",
            "cannot be confirmed at this time",
            "unverified general knowledge",
            "corrective feedback instructions",
            "critical verification notice",
            "are unverified",
            "marked as unverified",
            "qualified as unverified",
            "were not fully fetched",
            "lack direct primary",
            "lack complete primary",
            "excerpts were not fully fetched",
            "partially unverified due to",
            "persisted to the workspace",
            "workspace sandbox",
            "research into the",
            "is complete",
            "error encountered",
            "successfully generated",
            "saved to the workspace",
            "the structured report",
            "final verified summary",
            "synthesis of findings",
            "conflicting claims & fact-checking",
        ]

        meta_label_prefixes = [
            "conflict ", "disagreement:", "resolution:", "resolution /",
            "qualified stance:", "note:", "status:", "path:", "file persisted:",
            "verification status:", "based on", "to adhere", "in accordance",
            "author:", "table of contents", "grounded framework", "explicit disclosure",
            "evidence source:", "source:", "reference:", "citation:", "url:",
            "unverified / qualified claims:", "unverified claims:", "qualified claims:",
            "unverified:", "workspace artifact status", "execution plan status",
            "claim:", "fact:",
        ]

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            # Skip markdown table rows and separators entirely (tables are multi-column summaries, not single assertions)
            if line.startswith("|"):
                continue

            # Skip markdown headers and section titles ending with colon
            if line.startswith("#") or line.endswith(":"):
                continue

            # Track active framework subject from headers (e.g. "1. **LangGraph**" or "### CrewAI")
            header_match = re.search(
                r"\b(LangGraph|CrewAI|AutoGen|Semantic\s+Kernel|LlamaIndex(?:\s+Workflows)?)\b",
                line,
                re.IGNORECASE,
            )
            if header_match and (re.match(r"^[0-9]+\.\s+", line) or "**" in line):
                matched_name = header_match.group(1).strip()
                if "semantic" in matched_name.lower():
                    current_subject = "Semantic Kernel"
                elif "autogen" in matched_name.lower():
                    current_subject = "AutoGen"
                elif "langgraph" in matched_name.lower():
                    current_subject = "LangGraph"
                elif "crew" in matched_name.lower():
                    current_subject = "CrewAI"
                elif "llama" in matched_name.lower():
                    current_subject = "LlamaIndex"

            # Clean bullet prefixes, markdown asterisks, backticks
            cleaned_line = re.sub(r"^[•\-*0-9.]+\s*", "", line).strip()
            cleaned_line = re.sub(r"[*_`]", "", cleaned_line).strip()

            # Normalize framework bullet prefixes: "**Framework:** provides..." -> "Framework provides..."
            m_fw = re.match(
                r"^(LangGraph|CrewAI|AutoGen|Semantic\s+Kernel|LlamaIndex(?:\s+Workflows)?):\s*(.*)$",
                cleaned_line,
                re.IGNORECASE,
            )
            if m_fw:
                fw_name = m_fw.group(1)
                rest = m_fw.group(2)
                rest_clean = rest[0].lower() + rest[1:] if rest and not rest.startswith("API") else rest
                cleaned_line = f"{fw_name} {rest_clean}"

            # Split line into distinct sentences
            sentences = re.split(r"(?<=[.!?])\s+", cleaned_line)
            for raw_s in sentences:
                s = raw_s.strip()
                if len(s) < 25:
                    continue

                s_low = s.lower()
                if any(d in s_low for d in meta_disclaimers):
                    continue

                if any(s_low.startswith(p) for p in meta_label_prefixes):
                    continue

                # Strip attribution and conversational assertion prefixes
                s = re.sub(
                    r"^(?:verified\s+claims|known\s+facts|reported\s+facts|factual\s+findings|core\s+findings|key\s+findings):\s*",
                    "",
                    s,
                    flags=re.IGNORECASE,
                ).strip()
                s = re.sub(
                    r"^(?:the\s+)?(?:official\s+)?(?:repository\s+)?(?:text|documentation|headers|summaries|release\s+notes)\s+(?:confirms|states|establishes|indicates|describes|explicitly\s+states)\s+(?:that\s+)?",
                    "",
                    s,
                    flags=re.IGNORECASE,
                ).strip()
                s = re.sub(r"^the\s+repository\s+explicitly\s+states\s+that\s+", "", s, flags=re.IGNORECASE).strip()
                s = re.sub(r"^repository\s+documentation\s+confirms\s+", "", s, flags=re.IGNORECASE).strip()
                s = re.sub(r"^repository\s+headers\s+indicate\s+", "", s, flags=re.IGNORECASE).strip()
                s = re.sub(r"^official\s+repository\s+text\s+confirms\s+", "", s, flags=re.IGNORECASE).strip()
                s = re.sub(r"^official\s+repository\s+text\s+establishes\s+", "", s, flags=re.IGNORECASE).strip()

                # Restore subject if statement starts with pronoun or verb
                if current_subject:
                    if re.match(r"^(?:it\s+is|it\s+provides|it\s+enables|it\s+features|it\s+acts|it\s+offers)\b", s, re.IGNORECASE):
                        s = re.sub(r"^it\b", current_subject, s, count=1, flags=re.IGNORECASE)
                    elif re.match(r"^(?:is|provides|enables|features|offers)\b", s, re.IGNORECASE):
                        s = f"{current_subject} {s}"
                    elif s.lower().startswith("it as a "):
                        s = f"{current_subject} is a " + s[len("it as a "):]
                    elif s.lower().startswith("as a "):
                        s = f"{current_subject} is " + s

                # Ensure the statement has sufficient semantic content
                tokens = self._extract_semantic_tokens(s)
                if len(tokens) < 3:
                    continue

                claims.append(
                    Claim(
                        id=f"clm-{uuid.uuid4().hex[:8]}",
                        statement=s,
                        status=EvidenceStatus.UNVERIFIED,
                        confidence=0.0,
                    )
                )
                if len(claims) >= 12:
                    break

            if len(claims) >= 12:
                break

        return claims

    def _clean_statement(self, statement: str) -> str:
        """Strip conversational or category header prefixes from statement."""
        stmt = re.sub(r"^[A-Z][A-Za-z0-9\s\-_/]{1,35}:\s+", "", statement).strip()
        return stmt or statement

    def _extract_entity_groups(self, statement: str) -> List[str]:
        """Extract multi-word proper nouns and key technical terms from statement."""
        stmt = self._clean_statement(statement)
        raw_entities = re.findall(r"\b[A-Z][a-zA-Z0-9_]*(?:\s+[A-Z][a-zA-Z0-9_]*)*\b", stmt)
        ignore_words = {
            "the", "this", "these", "those", "it", "its", "an", "a", "in", "on", "for", "with",
            "and", "or", "to", "of", "by", "as", "at", "from", "into", "top", "best", "enterprise",
            "key", "core", "why", "how", "what", "when", "where", "which", "choose", "build", "using",
            "all", "every", "both", "each", "note", "warning", "section", "overview", "summary"
        }
        groups: List[str] = []
        for ent in raw_entities:
            words = ent.split()
            filtered = [w for w in words if w.lower() not in ignore_words]
            if not filtered:
                continue
            ent_clean = " ".join(filtered)
            if len(ent_clean) >= 3 and ent_clean.lower() not in ignore_words:
                if ent_clean not in groups:
                    groups.append(ent_clean)
        return groups

    def _split_compound_clauses(self, statement: str) -> List[str]:
        """Split a statement into component clauses if it represents a compound claim."""
        stmt = self._clean_statement(statement)
        parts = re.split(
            r",\s*(?:signaling|indicating|resulting in|enabling|demonstrating|which allows|which provides|allowing|and provides|while also)\b|;\s*|\b(?<!\w)and\s+(?:it\s+)?(?=[a-z]+ing\b|[a-z]+s\b)",
            stmt,
            flags=re.IGNORECASE
        )
        clauses = [p.strip() for p in parts if p.strip() and len(p.strip()) > 10]
        return clauses if len(clauses) > 1 else [stmt]

    def _extract_semantic_tokens(self, text: str) -> Set[str]:
        """Extract lower-case non-stopword tokens of length >= 2."""
        raw = re.findall(r"\b[a-zA-Z0-9_\-\.]{2,}\b", text.lower())
        return {w for w in raw if w not in STOPWORDS}

    def _is_clause_supported(self, clause: str, snippet: str) -> bool:
        """Check whether an individual clause is substantiated by a retrieved passage."""
        c_tokens = self._extract_semantic_tokens(clause)
        s_tokens = self._extract_semantic_tokens(snippet)
        s_low = snippet.lower()
        if not c_tokens:
            return False

        overlap = c_tokens.intersection(s_tokens)
        overlap_ratio = len(overlap) / max(len(c_tokens), 1)

        # Entity group check for this clause
        ent_groups = self._extract_entity_groups(clause)
        if len(ent_groups) >= 2:
            for ent in ent_groups:
                ent_words = [w.lower() for w in ent.split() if w.lower() not in STOPWORDS]
                if not any(w in s_low for w in ent_words):
                    return False
        elif len(ent_groups) == 1:
            ent_words = [w.lower() for w in ent_groups[0].split() if w.lower() not in STOPWORDS]
            if not any(w in s_low for w in ent_words):
                return False

        # Relational action check for this clause
        rel_actions = {w for w in c_tokens if w in RELATIONAL_ACTION_WORDS}
        if rel_actions and not any(w in s_low for w in rel_actions):
            return False

        return (overlap_ratio >= 0.40) or (len(overlap) >= 3 and any(w in s_low for w in c_tokens))

    def _detect_contradiction(self, claim_stmt: str, snippet: str) -> bool:
        """Conservative contradiction detection between claim and evidence snippet."""
        c_low = claim_stmt.lower()
        s_low = snippet.lower()

        # 1. Negation mismatch on core assertions
        c_neg = any(w in c_low.split() for w in ("not", "cannot", "never", "without", "lacks", "unsupported", "false"))
        s_neg = any(w in s_low.split() for w in ("not", "cannot", "never", "without", "lacks", "unsupported", "false"))

        # Explicit opposing patterns
        if ("only" in c_low or "exclusively" in c_low) and any(
            w in s_low for w in ["also", "both", "supports multiple", "supports all", "not only"]
        ):
            c_tokens = self._extract_semantic_tokens(claim_stmt)
            s_tokens = self._extract_semantic_tokens(snippet)
            if len(c_tokens.intersection(s_tokens)) >= 3:
                return True

        if ("requires" in c_low or "must use" in c_low) and any(
            w in s_low for w in ["optional", "does not require", "independent", "without", "standalone"]
        ):
            c_tokens = self._extract_semantic_tokens(claim_stmt)
            s_tokens = self._extract_semantic_tokens(snippet)
            if len(c_tokens.intersection(s_tokens)) >= 3:
                return True

        if ("cannot" in c_low or "does not support" in c_low) and any(
            w in s_low for w in ["supports", "first-class support", "native support", "provides support"]
        ):
            c_tokens = self._extract_semantic_tokens(claim_stmt)
            s_tokens = self._extract_semantic_tokens(snippet)
            if len(c_tokens.intersection(s_tokens)) >= 3:
                return True

        # Claim affirms negative while snippet affirms positive (specifically regarding feature support)
        if any(neg_pat in c_low for neg_pat in ["cannot", "does not support", "unsupported", "lacks support", "no support"]):
            if any(pos_pat in s_low for pos_pat in ["supports", "native support", "provides support", "first-class support", "supported"]):
                c_tokens = self._extract_semantic_tokens(claim_stmt)
                s_tokens = self._extract_semantic_tokens(snippet)
                if len(c_tokens.intersection(s_tokens)) >= 2:
                    return True

        # Claim affirms positive while snippet affirms negative
        if any(pos_pat in c_low for pos_pat in ["supports", "native support", "provides support", "supported"]) and not c_neg:
            if any(neg_pat in s_low for neg_pat in ["does not support", "cannot", "unsupported", "not supported", "lacks support"]):
                c_tokens = self._extract_semantic_tokens(claim_stmt)
                s_tokens = self._extract_semantic_tokens(snippet)
                if len(c_tokens.intersection(s_tokens)) >= 2:
                    return True

        # Incompatible attributes: Open source vs proprietary
        if any(w in c_low for w in ["proprietary", "closed source", "closed-source"]) and any(
            w in s_low for w in ["open-source", "open source", "mit license", "apache"]
        ):
            return True

        # Deprecation status opposition
        if any(w in c_low for w in ["deprecated", "obsolete", "abandoned"]) and any(
            w in s_low for w in ["active", "maintained", "latest release", "v0.", "v1."]
        ):
            return True

        return False

    def verify_claims_against_evidence(
        self,
        claims: List[Claim],
        evidence_items: List[Evidence],
    ) -> Tuple[List[Claim], List[str]]:
        """Conservative factual entailment and contradiction verification.
        
        Verification Policy:
        - Check whether retrieved passages actually support the complete claim (subject, relation, action, conclusion).
        - Multi-entity relational claims require all entity groups and relational action words to be substantiated.
        - If evidence only supports part of a compound claim, cap strictly at PARTIALLY_VERIFIED.
        - Detect contradictions when evidence opposes a claim.
        - An official-domain search snippet cannot independently establish an unsupported relationship.
        - Single secondary search snippet support is CAPPED at PARTIALLY_VERIFIED.
        - Full VERIFIED status requires either:
            a) Primary documentation full-page passage with high-fidelity alignment, OR
            b) Corroboration across at least 2 distinct source domains, OR
            c) Authoritative official repository passage directly and completely entailing an atomic claim.
        - Ambiguous, partial, or non-entailing matches fail closed to UNVERIFIED or PARTIALLY_VERIFIED.
        """
        conflicts: List[str] = []

        for claim in claims:
            cleaned_statement = self._clean_statement(claim.statement)
            c_tokens = self._extract_semantic_tokens(cleaned_statement)
            if not c_tokens:
                claim.status = EvidenceStatus.UNVERIFIED
                claim.reasoning = "Empty semantic claim content."
                continue

            # Identify key named entities / technical terms
            entity_groups = self._extract_entity_groups(cleaned_statement)
            rel_actions_in_claim = {w for w in c_tokens if w in RELATIONAL_ACTION_WORDS}
            clauses = self._split_compound_clauses(cleaned_statement)

            supporting_evs: List[Evidence] = []
            contradicting_evs: List[Evidence] = []
            is_any_partial_support = False

            for ev in evidence_items:
                snippet = ev.supporting_snippet.strip()
                if len(snippet) < 25:
                    continue

                # 1. Contradiction Check
                if self._detect_contradiction(cleaned_statement, snippet):
                    contradicting_evs.append(ev)
                    ev.status = EvidenceStatus.CONFLICTING
                    ev.claim_id = claim.id
                    ev.explanation = (
                        f"Opposes statement '{claim.statement[:90]}...': "
                        f"snippet asserts contradictory evidence: '{snippet[:120]}...'"
                    )
                    continue

                # 2. Entailment Check
                ev_is_partial = False
                if len(clauses) > 1:
                    cl_support = [self._is_clause_supported(cl, snippet) for cl in clauses]
                    # If primary clause is not supported, snippet fails entailment
                    if not cl_support[0]:
                        continue
                    if cl_support[0] and not all(cl_support):
                        ev_is_partial = True
                        is_any_partial_support = True
                else:
                    if not self._is_clause_supported(cleaned_statement, snippet):
                        continue

                # 3. Entity Co-occurrence check in coherent clause if multiple entity groups in supported clause
                clause_to_check = clauses[0] if len(clauses) > 1 else cleaned_statement
                c_ents = self._extract_entity_groups(clause_to_check)
                if len(c_ents) >= 2:
                    snippet_sentences = [
                        s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", snippet) if s.strip()
                    ]
                    entity_cooccur = False
                    prev_sentence = ""
                    for s_sentence in snippet_sentences:
                        s_text = s_sentence.lower()
                        if re.match(r"^(?:it|this framework|the framework|these agents)\b", s_text):
                            s_text = f"{prev_sentence.lower()} {s_text}"

                        all_groups_present = True
                        for ent in c_ents:
                            ent_words = [w.lower() for w in ent.split() if w.lower() not in STOPWORDS]
                            if not any(w in s_text for w in ent_words):
                                all_groups_present = False
                                break
                        if all_groups_present:
                            entity_cooccur = True
                            break
                        prev_sentence = s_sentence

                    if not entity_cooccur:
                        continue

                # 7. Valid Support Established
                supporting_evs.append(ev)
                if ev_is_partial:
                    ev.status = EvidenceStatus.PARTIALLY_VERIFIED
                    ev.claim_id = claim.id
                    ev.explanation = (
                        f"Partially supports compound statement '{claim.statement[:80]}...': "
                        f"primary assertion corroborated by {ev.source.title}, but secondary clause lacks evidence."
                    )
                else:
                    ev.status = EvidenceStatus.VERIFIED
                    ev.claim_id = claim.id
                    ev.explanation = (
                        f"Directly supports statement '{claim.statement[:90]}...': "
                        f"confirmed by {ev.source.title} ({ev.source.source_type.value})"
                    )

            claim.evidence_ids = [e.id for e in supporting_evs]
            claim.conflicting_evidence_ids = [e.id for e in contradicting_evs]
            claim.source_urls = list({e.source.url for e in (supporting_evs + contradicting_evs)})

            # Assign Status according to conservative verification policy
            if contradicting_evs:
                claim.status = EvidenceStatus.CONFLICTING
                claim.confidence = 0.20
                conflict_msg = (
                    f"Conflict detected on claim '{claim.statement[:80]}...': "
                    f"Opposed by {len(contradicting_evs)} source passage(s)."
                )
                claim.reasoning = conflict_msg
                conflicts.append(conflict_msg)

            elif supporting_evs:
                distinct_domains = len({
                    urlparse(e.source.url).netloc.lower()
                    for e in supporting_evs
                })
                distinct_urls = len({e.source.url for e in supporting_evs})
                has_full_page = any(
                    bool(e.retrieval_status) and (e.retrieval_status.startswith("HTTP") or e.retrieval_status == "browser_dom")
                    for e in supporting_evs
                )
                has_primary = any(
                    e.source.source_type in (SourceType.PRIMARY, SourceType.OFFICIAL_REPO, SourceType.DOCUMENTATION)
                    for e in supporting_evs
                )
                is_official_primary = (
                    supporting_evs[0].source.source_type in (SourceType.PRIMARY, SourceType.OFFICIAL_REPO)
                )

                # Requirement 1: If evidence supports only part of a compound claim, mark it PARTIALLY_VERIFIED
                if is_any_partial_support:
                    claim.status = EvidenceStatus.PARTIALLY_VERIFIED
                    claim.confidence = 0.65
                    claim.reasoning = (
                        f"Partially verified from evidence ({supporting_evs[0].source.url}). "
                        "Evidence substantiates the primary assertion, but cannot independently verify the entire compound claim."
                    )
                # Requirement 2: Strict retrieval policy - multi-domain cross-corroboration
                elif distinct_domains >= 2:
                    claim.status = EvidenceStatus.VERIFIED
                    claim.confidence = 0.90
                    claim.reasoning = (
                        f"Factually verified across {distinct_domains} independent source domains "
                        f"({distinct_urls} distinct citations)."
                    )
                # Primary documentation or official repo full-page fetch
                elif has_primary and has_full_page:
                    claim.status = EvidenceStatus.VERIFIED
                    claim.confidence = 0.95
                    claim.reasoning = (
                        f"Factually verified by authoritative primary documentation ({supporting_evs[0].source.title}, "
                        f"{supporting_evs[0].source.url})."
                    )
                # Authoritative official repo search snippet that directly and completely entails an atomic claim
                elif is_official_primary and not is_any_partial_support and not rel_actions_in_claim:
                    claim.status = EvidenceStatus.VERIFIED
                    claim.confidence = 0.90
                    claim.reasoning = (
                        f"Factually verified by authoritative official repository snippet ({supporting_evs[0].source.title}, "
                        f"{supporting_evs[0].source.url})."
                    )
                # Single secondary search snippet capped at PARTIALLY_VERIFIED
                elif len(supporting_evs) == 1 and not has_full_page:
                    claim.status = EvidenceStatus.PARTIALLY_VERIFIED
                    claim.confidence = 0.65
                    claim.reasoning = (
                        f"Partially verified from single secondary search snippet ({supporting_evs[0].source.url}). "
                        "Full page retrieval or independent corroboration required for definitive status."
                    )
                else:
                    claim.status = EvidenceStatus.PARTIALLY_VERIFIED
                    claim.confidence = 0.70
                    claim.reasoning = (
                        f"Partially verified from single domain ({supporting_evs[0].source.domain}). "
                        "Cross-domain corroboration required for definitive status."
                    )

            else:
                claim.status = EvidenceStatus.UNVERIFIED
                claim.confidence = 0.0
                claim.reasoning = "Insufficient evidence: no retrieved passage provides direct factual support for this statement."

        return claims, conflicts

    def run_pipeline(
        self,
        final_answer: str,
        tool_results: List[Any],
    ) -> EvidencePipelineResult:
        """Execute the end-to-end evidence collection and claim verification pipeline."""
        evidence_items = self.extract_evidence_from_tool_results(tool_results)
        claims = self.extract_claims_from_text(final_answer)

        verified_claims, conflicts = self.verify_claims_against_evidence(claims, evidence_items)

        # Count source authorities and distinct domains
        primary_count = sum(
            1 for ev in evidence_items
            if ev.source.source_type in (SourceType.PRIMARY, SourceType.OFFICIAL_REPO, SourceType.DOCUMENTATION)
        )
        secondary_count = len(evidence_items) - primary_count

        all_urls = list({ev.source.url for ev in evidence_items if ev.source.url})
        distinct_domains = len({urlparse(u).netloc.lower() for u in all_urls})

        # Count claim statuses
        v_count = sum(1 for c in verified_claims if c.status == EvidenceStatus.VERIFIED)
        pv_count = sum(1 for c in verified_claims if c.status == EvidenceStatus.PARTIALLY_VERIFIED)
        cf_count = sum(1 for c in verified_claims if c.status == EvidenceStatus.CONFLICTING)
        uv_count = sum(1 for c in verified_claims if c.status == EvidenceStatus.UNVERIFIED)
        total_c = len(verified_claims)

        # Calculate factual verification score from actual claim results
        if total_c > 0:
            factual_score = round((v_count * 1.0 + pv_count * 0.5) / total_c, 2)
        else:
            factual_score = 0.0 if evidence_items else 1.0

        # Compute overall status based on conservative semantics
        if conflicts or cf_count > 0:
            overall = EvidenceStatus.CONFLICTING
        elif total_c == 0:
            overall = EvidenceStatus.VERIFIED if not evidence_items else EvidenceStatus.UNVERIFIED
        elif uv_count == total_c:
            overall = EvidenceStatus.UNVERIFIED
        elif v_count == total_c and v_count > 0:
            overall = EvidenceStatus.VERIFIED
        elif (v_count + pv_count) > 0:
            overall = EvidenceStatus.PARTIALLY_VERIFIED
        else:
            overall = EvidenceStatus.UNVERIFIED

        return EvidencePipelineResult(
            claims=verified_claims,
            evidence_items=evidence_items,
            overall_status=overall,
            conflicts_detected=conflicts,
            primary_sources_count=primary_count,
            secondary_sources_count=secondary_count,
            distinct_domains_count=distinct_domains,
            source_urls=all_urls,
            claims_verified_count=v_count,
            claims_partially_verified_count=pv_count,
            claims_conflicting_count=cf_count,
            claims_unverified_count=uv_count,
            factual_verification_score=factual_score,
        )


evidence_service = EvidenceService()
