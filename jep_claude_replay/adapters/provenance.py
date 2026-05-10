"""Browser/API provenance adapters."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from jep_claude_replay.canonicalization.jcs import payload_digest
from jep_claude_replay.evidence.policy import EvidencePolicy


def browser_provenance(query: str, results: list[dict[str, Any]], *, policy: EvidencePolicy | None = None) -> dict:
    policy = policy or EvidencePolicy(mode="digest-preview")
    return {
        "kind": "browser.search",
        "query_digest": payload_digest(query),
        "query_preview": policy.apply(query)["preview"],
        "result_count": len(results),
        "origins": sorted({urlparse(r.get("url", "")).netloc for r in results if r.get("url")}),
        "results_digest": payload_digest(results),
    }


def api_provenance(method: str, endpoint: str, request: dict[str, Any], response: dict[str, Any], *, policy: EvidencePolicy | None = None) -> dict:
    policy = policy or EvidencePolicy(mode="digest-preview")
    return {
        "kind": "api.call",
        "method": method.upper(),
        "endpoint_origin": urlparse(endpoint).netloc,
        "endpoint_digest": payload_digest(endpoint),
        "request": policy.apply(request, field_name="request"),
        "response": policy.apply(response, field_name="response"),
        "status": response.get("status") or response.get("status_code"),
    }
