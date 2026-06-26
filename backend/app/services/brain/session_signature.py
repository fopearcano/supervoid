"""Pure value objects for the Brain stateful-session layer (Prompt 8).

This module is deliberately **DB-free** so the prefix-invalidation rules and the
per-turn metrics are unit-testable without a session. The session service
(`session.py`) reads/writes the durable ``BrainSession`` row; here we only
compare signatures and compute metrics from an already-assembled context.

The vLLM prefix cache is treated as a best-effort optimisation we make
*eligible* — never as durable memory. ``is_warm_eligible`` is keyed on the
assembler's authoritative ``prefix_hash``; the component diff only *explains*
why a prefix changed.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

from app.models.enums import SessionInvalidationReason as R
from app.services.brain import compiler
from app.utils.logging import get_logger

log = get_logger("app.brain.session")


def permissions_fingerprint(
    resolved_scopes, *, work_id: Optional[str], story_world_id: Optional[str]
) -> str:
    """A separable handle for "user permissions changed".

    The assembler folds the resolved scopes into the prefix TEXT (so a change
    moves ``prefix_hash`` too), but offers no isolated handle to *attribute* a
    change to permissions vs constitution/profile. This fingerprint gives one.
    """
    payload = {
        "scopes": sorted(resolved_scopes or []),
        "work_id": work_id,
        "story_world_id": story_world_id,
    }
    return hashlib.sha256(
        compiler.canonical_json(payload).encode("utf-8")
    ).hexdigest()[:32]


@dataclass(frozen=True)
class PrefixSignature:
    """The set of inputs that determine the stable prompt prefix."""

    prefix_hash: str  # == AssembledContext.prefix_hash (authoritative cache key)
    model: str
    constitution_version: Optional[int]
    profile_version: Optional[int]
    studio_state_version: Optional[int]
    project_state_version: Optional[int]
    studio_state_checksum: Optional[str]  # the true "materially changed" signal
    project_state_checksum: Optional[str]
    permissions_fingerprint: str
    work_id: Optional[str]
    story_world_id: Optional[str]

    @classmethod
    def from_context(
        cls, ctx, conversation, *, studio_state, project_state
    ) -> "PrefixSignature":
        v = ctx.versions
        # Only track a compiled state when it is ACTUALLY in this user's stable
        # prefix. A non-admin project-scoped session never sees studio state, so a
        # studio recompile must not register as a change for them (it would attribute
        # STUDIO_STATE_CHANGED while the prefix_hash is unmoved — a false reason).
        studio_in_prefix = any(
            s.name == "Studio state" and s.included for s in ctx.segments
        )
        project_in_prefix = any(
            s.name == "Project state" and s.included for s in ctx.segments
        )
        return cls(
            prefix_hash=ctx.prefix_hash,
            model=ctx.model,
            constitution_version=v.get("constitution"),
            profile_version=v.get("profile"),
            studio_state_version=v.get("studio_state") if studio_in_prefix else None,
            project_state_version=v.get("project_state") if project_in_prefix else None,
            studio_state_checksum=(
                studio_state.checksum if (studio_state and studio_in_prefix) else None
            ),
            project_state_checksum=(
                project_state.checksum if (project_state and project_in_prefix) else None
            ),
            permissions_fingerprint=permissions_fingerprint(
                ctx.resolved_scopes,
                work_id=conversation.work_id,
                story_world_id=conversation.story_world_id,
            ),
            work_id=conversation.work_id,
            story_world_id=conversation.story_world_id,
        )

    @classmethod
    def from_session(cls, sess) -> Optional["PrefixSignature"]:
        """Reconstruct the PRIOR signature from a persisted ``BrainSession``.
        Returns None when there is no prior turn (cold start)."""
        if sess is None or sess.last_prefix_hash is None:
            return None
        return cls(
            prefix_hash=sess.last_prefix_hash,
            model=sess.model,
            constitution_version=sess.constitution_version,
            profile_version=sess.profile_version,
            studio_state_version=sess.studio_state_version,
            project_state_version=sess.project_state_version,
            studio_state_checksum=sess.studio_state_checksum,
            project_state_checksum=sess.project_state_checksum,
            permissions_fingerprint=sess.permissions_fingerprint or "",
            work_id=sess.work_id,
            story_world_id=sess.story_world_id,
        )


@dataclass(frozen=True)
class InvalidationResult:
    invalidated: bool
    reasons: tuple  # tuple[SessionInvalidationReason, ...]
    prev_prefix_hash: Optional[str]
    new_prefix_hash: str

    @property
    def primary(self):
        return self.reasons[0] if self.reasons else None

    def reason_values(self) -> list:
        return [r.value for r in self.reasons]


def diff_signature(
    prev: Optional[PrefixSignature], curr: PrefixSignature
) -> InvalidationResult:
    """PURE. Map each Prompt 8 invalidation rule to a component comparison and a
    machine-readable reason. Empty reasons ⇒ the prefix is unchanged (warm
    eligible). ``prev is None`` ⇒ cold start (invalidated, no rule attributed).
    Deterministic priority order (model, constitution, profile, project,
    permissions, studio state, project state)."""
    if prev is None:
        return InvalidationResult(True, (), None, curr.prefix_hash)
    reasons = []
    # 6. model / chat template changed
    if prev.model != curr.model:
        reasons.append(R.MODEL_OR_TEMPLATE_CHANGED)
    # 1. constitution version changed
    if prev.constitution_version != curr.constitution_version:
        reasons.append(R.CONSTITUTION_CHANGED)
    # 2. profile changed
    if prev.profile_version != curr.profile_version:
        reasons.append(R.PROFILE_CHANGED)
    # 4. project changed
    if (prev.work_id, prev.story_world_id) != (curr.work_id, curr.story_world_id):
        reasons.append(R.PROJECT_CHANGED)
    # 3. user permissions changed
    if prev.permissions_fingerprint != curr.permissions_fingerprint:
        reasons.append(R.PERMISSIONS_CHANGED)
    # 5a. compiled studio state changed materially (checksum is the true signal;
    #     version corroborates).
    if (
        prev.studio_state_checksum != curr.studio_state_checksum
        or prev.studio_state_version != curr.studio_state_version
    ):
        reasons.append(R.STUDIO_STATE_CHANGED)
    # 5b. compiled project state changed materially
    if (
        prev.project_state_checksum != curr.project_state_checksum
        or prev.project_state_version != curr.project_state_version
    ):
        reasons.append(R.PROJECT_STATE_CHANGED)
    return InvalidationResult(
        bool(reasons), tuple(reasons), prev.prefix_hash, curr.prefix_hash
    )


def is_warm_eligible(
    prev: Optional[PrefixSignature], curr: PrefixSignature
) -> bool:
    """AUTHORITATIVE prefix-cache eligibility — keyed on the assembler's
    ``prefix_hash`` (the real cache key), NOT the component diff. The component
    diff only EXPLAINS a change. A divergence between the two is logged (a bug in
    the component map) but the hash is always the final arbiter, so eligibility
    can never be wrong even if a future assembler change adds an untracked prefix
    component.

    The STATE checksum comparison is intentionally STRICTER than the byte hash —
    it can fire STUDIO/PROJECT_STATE_CHANGED even when the 12-char rendered
    checksum prefix is byte-identical. That is the safe direction (never falsely
    warm)."""
    if prev is None:
        return False
    same_hash = prev.prefix_hash == curr.prefix_hash
    no_reasons = not diff_signature(prev, curr).invalidated
    if same_hash != no_reasons:
        log.warning(
            "session-signature divergence: same_hash=%s no_reasons=%s",
            same_hash,
            no_reasons,
        )
    return same_hash


# --- per-turn metrics (Prompt 8 requirement 8) ------------------------------
@dataclass(frozen=True)
class TurnMetrics:
    prompt_tokens: int  # 1
    stable_prefix_tokens: int  # 2
    suffix_tokens: int  # 3
    state_delta_tokens: int  # 4
    prefix_cache_eligible: bool  # 5 (estimated; never asserts vLLM holds it)
    time_to_first_token_ms: Optional[float]  # 6
    response_latency_ms: Optional[float]  # 7
    invalidation_reasons: list  # 8 (which rule(s) fired; [] when warm)
    completion_tokens: Optional[int] = None
    warmth: Optional[str] = None
    prefix_hash: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "stable_prefix_tokens": self.stable_prefix_tokens,
            "suffix_tokens": self.suffix_tokens,
            "state_delta_tokens": self.state_delta_tokens,
            "prefix_cache_eligible": self.prefix_cache_eligible,
            "time_to_first_token_ms": self.time_to_first_token_ms,
            "response_latency_ms": self.response_latency_ms,
            "invalidation_reasons": list(self.invalidation_reasons),
            "completion_tokens": self.completion_tokens,
            "warmth": self.warmth,
            "prefix_hash": self.prefix_hash,
        }


def compute_turn_metrics(
    ctx,
    *,
    prefix_cache_eligible: bool,
    invalidation: InvalidationResult,
    usage,
    response_latency_ms: Optional[float],
    ttft_ms: Optional[float],
    warmth: Optional[str],
) -> TurnMetrics:
    """Compute the 8 required metrics from an AssembledContext + provider usage.

    Token counts use the assembler's deterministic 4-chars/token estimate
    (``Segment.tokens``); ``prompt_tokens`` prefers the provider's reported value
    when present, else the deterministic sum."""
    inc = [s for s in ctx.segments if s.included]
    stable = sum(s.tokens for s in inc if s.stability == "stable-prefix")
    suffix = sum(s.tokens for s in inc if s.stability == "variable-suffix")
    delta = next((s.tokens for s in inc if s.name == "State delta"), 0)
    if isinstance(usage, dict) and usage.get("prompt_tokens") is not None:
        prompt = usage["prompt_tokens"]
    else:
        prompt = sum(s.tokens for s in inc)
    return TurnMetrics(
        prompt_tokens=prompt,
        stable_prefix_tokens=stable,
        suffix_tokens=suffix,
        state_delta_tokens=delta,
        prefix_cache_eligible=prefix_cache_eligible,
        time_to_first_token_ms=ttft_ms,
        response_latency_ms=response_latency_ms,
        invalidation_reasons=invalidation.reason_values(),
        completion_tokens=(usage or {}).get("completion_tokens")
        if isinstance(usage, dict)
        else None,
        warmth=warmth,
        prefix_hash=ctx.prefix_hash,
    )
