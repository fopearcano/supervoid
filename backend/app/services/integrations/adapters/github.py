"""GitHub project adapter.

Stores repository identifiers in (non-secret) config and links commits, issues
and pull requests to production tasks. Linking uses explicit, configured
operations (the caller supplies the ref); the remote status sync uses dry-run
fixtures and is recorded unless network access is enabled. Credentials are
referenced from the environment and never embedded.
"""
from __future__ import annotations

from app.models.enums import (
    IntegrationAdapterKind,
    IntegrationDirectionKind,
    IntegrationLinkKind,
)
from app.services.integrations import effects, transport
from app.services.integrations.base import (
    AdapterContext,
    AdapterOperation,
    HealthReport,
    IntegrationAdapter,
    recorded_result,
)

_LINK_KIND_BY_OP = {
    "link_commit": IntegrationLinkKind.COMMIT,
    "link_issue": IntegrationLinkKind.ISSUE,
    "link_pull_request": IntegrationLinkKind.PULL_REQUEST,
}


class GitHubProjectAdapter(IntegrationAdapter):
    key = "github_project"
    kind = IntegrationAdapterKind.GITHUB
    name = "GitHub project"
    description = (
        "Link commits, issues and pull requests to production tasks. Repository "
        "identifiers live in config; the access token is referenced from the "
        "environment, never embedded."
    )
    required_config = ("owner", "repo")
    credential_names = ("token",)
    operations = (
        AdapterOperation(
            key="link_commit",
            name="Link commit",
            summary="Link a commit to a production task.",
            direction=IntegrationDirectionKind.INBOUND,
            mutating=True,
        ),
        AdapterOperation(
            key="link_issue",
            name="Link issue",
            summary="Link an issue to a production task.",
            direction=IntegrationDirectionKind.INBOUND,
            mutating=True,
        ),
        AdapterOperation(
            key="link_pull_request",
            name="Link pull request",
            summary="Link a pull request to a production task.",
            direction=IntegrationDirectionKind.INBOUND,
            mutating=True,
        ),
        AdapterOperation(
            key="sync_status",
            name="Sync status",
            summary="Fetch issue/PR status from GitHub (remote).",
            direction=IntegrationDirectionKind.OUTBOUND,
            external=True,
            touches_network=True,
            risk="medium",
        ),
    )

    # --- health / status ---------------------------------------------------

    def health_check(self, ctx: AdapterContext) -> HealthReport:
        return self.base_health(ctx)

    def status(self, ctx: AdapterContext) -> dict:
        return {
            "adapter": self.key,
            "repository": self._repo_slug(ctx),
            "token_present": ctx.has_secret("token"),
        }

    # --- operations --------------------------------------------------------

    def dry_run(self, op: AdapterOperation, ctx: AdapterContext) -> dict:
        if op.key in _LINK_KIND_BY_OP:
            return {
                "operation": op.key,
                "would_link": self._link_preview(op, ctx),
                "note": "Dry-run: no link created.",
            }
        if op.key == "sync_status":
            return {
                "operation": op.key,
                "would_fetch": self._sync_request(ctx),
                "fixture": self._sync_fixture(ctx),
                "note": "Dry-run: returning a fixture, nothing fetched.",
            }
        return {"operation": op.key, "note": "Dry-run."}

    def inbound(self, op: AdapterOperation, ctx: AdapterContext) -> dict:
        kind = _LINK_KIND_BY_OP.get(op.key)
        if kind is None:
            raise ValueError(f"Unsupported GitHub inbound operation '{op.key}'.")
        ref = ctx.payload.get("external_ref") or ctx.payload.get("ref")
        return effects.create_task_link(
            ctx.session,
            ctx.point,
            external_kind=kind,
            external_ref=ref,
            target_id=ctx.payload.get("target_id", ""),
            external_url=ctx.payload.get("external_url") or self._guess_url(ctx, kind, ref),
            title=ctx.payload.get("title"),
            extra={"repository": self._repo_slug(ctx)},
        )

    def outbound(self, op: AdapterOperation, ctx: AdapterContext) -> dict:
        if op.key != "sync_status":
            raise ValueError(f"Unsupported GitHub outbound operation '{op.key}'.")
        request = self._sync_request(ctx)
        if not ctx.allow_network:
            result = recorded_result(
                request,
                "Network disabled (local-first): returning a fixture, nothing fetched.",
            )
            result["fixture"] = self._sync_fixture(ctx)
            return result
        token = ctx.secret("token")
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        result = transport.get_json(request["url"], headers=headers)
        result["request"] = {"method": "GET", "url": request["url"]}
        return result

    # --- helpers -----------------------------------------------------------

    def _repo_slug(self, ctx: AdapterContext) -> str:
        owner = ctx.config.get("owner", "")
        repo = ctx.config.get("repo", "")
        return f"{owner}/{repo}".strip("/")

    def _link_preview(self, op: AdapterOperation, ctx: AdapterContext) -> dict:
        kind = _LINK_KIND_BY_OP[op.key]
        ref = ctx.payload.get("external_ref") or ctx.payload.get("ref")
        return {
            "external_kind": kind.value,
            "external_ref": ref,
            "external_url": ctx.payload.get("external_url") or self._guess_url(ctx, kind, ref),
            "target_id": ctx.payload.get("target_id"),
            "repository": self._repo_slug(ctx),
        }

    def _guess_url(self, ctx: AdapterContext, kind: IntegrationLinkKind, ref):
        if not ref:
            return None
        slug = self._repo_slug(ctx)
        if not slug:
            return None
        path = {
            IntegrationLinkKind.COMMIT: "commit",
            IntegrationLinkKind.ISSUE: "issues",
            IntegrationLinkKind.PULL_REQUEST: "pull",
        }.get(kind)
        return f"https://github.com/{slug}/{path}/{ref}" if path else None

    def _sync_request(self, ctx: AdapterContext) -> dict:
        slug = self._repo_slug(ctx)
        number = ctx.payload.get("number", "")
        return {"method": "GET", "url": f"https://api.github.com/repos/{slug}/issues/{number}"}

    def _sync_fixture(self, ctx: AdapterContext) -> dict:
        return {
            "repository": self._repo_slug(ctx),
            "number": ctx.payload.get("number"),
            "state": "open",
            "title": ctx.payload.get("title", "Fixture issue"),
            "source": "fixture",
        }
