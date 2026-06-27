"""SUPERVOID evaluation harness (Prompt 17).

A SUPERVOID-specific evaluation system to run BEFORE considering fine-tuning. It
exercises the real governed surfaces (MCP tools, retrieval, policy, compiled
state, proposals) with a versioned corpus of studio tasks, applies deterministic
checks (schema / tool choice / permissions / citations / approval gates), records
benchmark metrics, and produces a report. Candidate models are compared purely
through configuration (``ai_provider`` / ``ai_model``) — no code changes.
"""
from app.eval import corpus, report, runners, scoring, world, harness  # noqa: F401
