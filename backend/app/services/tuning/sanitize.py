"""Sanitisation + exclusion for fine-tuning candidates (Prompt 18).

The pipeline teaches BEHAVIOUR, not facts, and must never carry sensitive or
volatile content into a training set. This module enforces the exclusion rules on
every candidate BEFORE it is stored:

* **chain-of-thought** — always stripped (we teach the final answer, never the
  reasoning trace).
* **passwords / tokens / secrets** — always redacted (no exception).
* **private contracts** — blocked unless explicitly approved AND anonymised.
* **private member data** (emails / phone numbers) — blocked unless anonymised.
* **temporary task statuses / obsolete-fact markers** — flagged as warnings for
  the reviewer (the behaviour-not-facts taxonomy + human review are the gate).

``unapproved model outputs`` are handled by the review workflow (nothing is
exported without explicit approval), not here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- chain-of-thought (always stripped) ------------------------------------
_COT_BLOCK_PATTERNS = [
    re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<thinking>.*?</thinking>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<scratchpad>.*?</scratchpad>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<reasoning>.*?</reasoning>", re.IGNORECASE | re.DOTALL),
    re.compile(r"```(?:thought|reasoning|scratchpad).*?```", re.IGNORECASE | re.DOTALL),
]
_COT_LINE_PATTERN = re.compile(
    r"^[ \t]*(chain[- ]of[- ]thought|reasoning|thought process|let me think|"
    r"thinking step by step|scratchpad)\b.*$",
    re.IGNORECASE | re.MULTILINE,
)

# --- secrets / tokens (always redacted) ------------------------------------
_SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?i)\b(api[_-]?key|secret|password|passwd|bearer|authorization|"
                r"credential|access[_-]?token|service[_-]?token)\b\s*[:=]\s*\S+"), "secret_kv"),
    (re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"), "openai_key"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "github_token"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "slack_token"),
    (re.compile(r"\bey[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), "jwt"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "aws_access_key"),
    (re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"), "private_key"),
]
_SECRET_PLACEHOLDER = "[REDACTED_SECRET]"

# --- private member data (blocked unless anonymised) -----------------------
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}(?!\d)")

# --- private contracts (blocked unless approved + anonymised) --------------
_CONTRACT_RE = re.compile(
    r"(?i)\b(this agreement|whereas[, ]|hereinafter|in witness whereof|governing law|"
    r"royalty rate|advance against|grant of rights|indemnif(y|ication)|"
    r"confidentiality clause|term sheet|net receipts)\b"
)

# --- temporary statuses / obsolete-fact markers (warned, not blocked) ------
_VOLATILE_RE = re.compile(
    r"(?i)\b(status\s*[:=]\s*(todo|to-do|in[_ -]?progress|blocked|wip|pending|in[_ -]?review)|"
    r"currently (blocked|in progress|assigned)|as of (today|now|this week)|"
    r"due (today|tomorrow|this week))\b"
)


@dataclass
class SanitizeResult:
    ok: bool
    cleaned_messages: list = field(default_factory=list)
    cleaned_target: str = ""
    redactions: list = field(default_factory=list)   # types of content redacted
    notes: list = field(default_factory=list)        # non-blocking warnings
    contains_sensitive: bool = False
    blocked_reasons: list = field(default_factory=list)


def scan(text: str) -> dict:
    """Report what the sanitiser would find in ``text`` (used by tests + review)."""
    text = text or ""
    return {
        "chain_of_thought": bool(
            any(p.search(text) for p in _COT_BLOCK_PATTERNS) or _COT_LINE_PATTERN.search(text)
        ),
        "secrets": [label for pat, label in _SECRET_PATTERNS if pat.search(text)],
        "member_data": bool(_EMAIL_RE.search(text) or _PHONE_RE.search(text)),
        "contract": bool(_CONTRACT_RE.search(text)),
        "volatile": bool(_VOLATILE_RE.search(text)),
    }


def _strip_cot(text: str, redactions: list) -> str:
    out = text
    for pat in _COT_BLOCK_PATTERNS:
        if pat.search(out):
            out = pat.sub("", out)
            if "chain_of_thought" not in redactions:
                redactions.append("chain_of_thought")
    if _COT_LINE_PATTERN.search(out):
        out = _COT_LINE_PATTERN.sub("", out)
        if "chain_of_thought" not in redactions:
            redactions.append("chain_of_thought")
    return out


def _redact_secrets(text: str, redactions: list) -> tuple[str, bool]:
    out = text
    found = False
    for pat, label in _SECRET_PATTERNS:
        if pat.search(out):
            out = pat.sub(_SECRET_PLACEHOLDER, out)
            found = True
            if label not in redactions:
                redactions.append(label)
    return out, found


def sanitize_example(
    messages: list,
    target_output: str,
    *,
    allow_contract: bool = False,
    anonymised: bool = False,
) -> SanitizeResult:
    """Strip CoT, redact secrets, and decide admissibility per the exclusion rules.

    Blocking (``ok=False``) happens for unapproved/unanonymised private contracts
    and for private member data that has not been anonymised — the proposer must
    fix and resubmit. Secrets and chain-of-thought are always removed in place."""
    redactions: list = []
    notes: list = []
    blocked: list = []
    contains_sensitive = False

    def _clean(text: str) -> str:
        nonlocal contains_sensitive
        out = _strip_cot(str(text or ""), redactions)
        out, had_secret = _redact_secrets(out, redactions)
        contains_sensitive = contains_sensitive or had_secret
        return out.strip()

    cleaned_messages = [
        {"role": m.get("role", "user"), "content": _clean(m.get("content", ""))}
        for m in messages
    ]
    cleaned_target = _clean(target_output)

    # Hard exclusions are evaluated on the CLEANED content — so chain-of-thought
    # is already gone and a redacted secret can't masquerade as a phone number.
    cleaned_all = "\n".join([m["content"] for m in cleaned_messages] + [cleaned_target])
    if _CONTRACT_RE.search(cleaned_all) and not (allow_contract and anonymised):
        blocked.append("private_contract_requires_approval_and_anonymisation")
    if (_EMAIL_RE.search(cleaned_all) or _PHONE_RE.search(cleaned_all)) and not anonymised:
        blocked.append("private_member_data_requires_anonymisation")
    if _VOLATILE_RE.search(cleaned_all):
        notes.append("contains_temporary_status_or_volatile_fact")

    if blocked:
        notes.extend(f"blocked:{b}" for b in blocked)

    return SanitizeResult(
        ok=not blocked,
        cleaned_messages=cleaned_messages,
        cleaned_target=cleaned_target,
        redactions=redactions,
        notes=notes,
        contains_sensitive=contains_sensitive,
        blocked_reasons=blocked,
    )
