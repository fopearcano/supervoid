from __future__ import annotations

import json
from typing import Optional, Sequence

from app.services.ai.providers.base import (
    CAPS_DRYRUN,
    ChatMessage,
    CompletionResult,
    LLMProvider,
    ProviderCapabilities,
    ProviderHealth,
)


# Each feature embeds a tag in its system prompt; the dry-run provider
# pattern-matches the tag and returns deterministic JSON the feature
# parser can ingest.  This keeps the full call → parse cycle exercised
# without network access.
_CANNED_PAYLOADS: dict[str, dict] = {
    "FEATURE:summarize": {
        "one_line": "A quiet, archival workshop novel.",
        "summary": (
            "A short editorial summary placeholder. Connect a real "
            "provider (LM Studio, OpenAI, OpenRouter, …) to replace "
            "this with grounded text."
        ),
        "themes": ["archive", "labour", "letters"],
    },
    "FEATURE:style_analysis": {
        "register": "literary · restrained",
        "voice": "third-person, past tense, dry humour in long sentences",
        "rhythm": "long → short → long; comma-led parentheticals throughout",
        "concerns": [
            "Long opening paragraphs may slow the first chapter.",
            "Dialogue tags occasionally telegraph the next emotion.",
        ],
    },
    "FEATURE:editorial_suggestions": {
        "suggestions": [
            {
                "kind": "structural",
                "title": "Compress the central correspondence",
                "rationale": "The middle third loses momentum across letters 8–14.",
            },
            {
                "kind": "line",
                "title": "Tighten chapter three",
                "rationale": "Two paragraphs restate the same image.",
            },
        ]
    },
    "FEATURE:semantic_tags": {
        "tags": ["epistolary", "provincial-life", "20th-century", "memory", "letters"],
    },
    "FEATURE:consistency_check": {
        "issues": [
            {
                "kind": "name",
                "where": "ch. 4 vs ch. 11",
                "description": "Character spelled 'Iren' early and 'Iryn' later.",
            }
        ]
    },
    # Model-driven agent runner (Prompt 9): a VALID, conforming AgentOutput so the
    # full request → parse → validate cycle is exercised offline. Deliberately
    # emits no findings / tool calls so the deterministic validators remain the
    # source of findings + proposals in dry-run (governance behaviour unchanged).
    "AGENT:": {
        "result": {
            "synthesis": (
                "Dry-run agent synthesis placeholder. Connect a real provider "
                "(vLLM) for grounded, model-driven analysis."
            ),
            "method": "deterministic-validators + model-synthesis",
        },
        "findings": [],
        "proposed_tool_calls": [],
        "evidence_references": [],
        "confidence": 0.5,
        "unanswered_questions": [],
    },
}

_DEFAULT_PAYLOAD = {
    "note": (
        "Dry-run AI provider · canned response. Configure AI_PROVIDER + "
        "AI_BASE_URL to call a real backend."
    )
}


class DryRunProvider(LLMProvider):
    """A deterministic stub provider that never leaves the process.

    The default in development, in tests, and whenever AI_PROVIDER is
    unset.
    """

    name = "dry_run"

    def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> CompletionResult:
        # Tolerate messages with no text body (e.g. an assistant tool-call turn
        # whose content is None) — join only the textual parts.
        joined = "\n".join(m.content for m in messages if m.content)
        payload = _DEFAULT_PAYLOAD
        for tag, canned in _CANNED_PAYLOADS.items():
            if tag in joined:
                payload = canned
                break

        return CompletionResult(
            content=json.dumps(payload, ensure_ascii=False),
            model=model or "stub",
            provider=self.name,
            usage=None,
            finish_reason="stop",
        )

    # The dry-run provider is offline: it is always "reachable" (it never
    # leaves the process) and advertises only the basics. This keeps the
    # health endpoint meaningful even with no backend configured.
    def capabilities(self) -> ProviderCapabilities:
        return CAPS_DRYRUN

    def list_models(self) -> list[str]:
        return ["stub"]

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.name,
            configured=True,
            reachable=True,
            model="stub",
            capabilities=CAPS_DRYRUN,
            latency_ms=0.0,
            detail="dry-run (offline; no backend configured)",
        )
