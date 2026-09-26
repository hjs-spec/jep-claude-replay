# Claude Session Replay for JEP-style Accountability

> **Maintenance: retired experiment — 2026-09-26.** Active feature development
> has ended. Source history, releases, examples and existing archive readers are
> retained for reproduction. Package names and historical formats are unchanged.

The Claude transcript importer, prototype signatures and .jcrpack reader remain available here. The maintained Agent SDK does not import these transcripts or packs; keep this tool for historical reproduction.

For new signed Core integrations, use the [maintained recording and report path](https://github.com/hjs-spec/jep-agent-sdk/blob/main/docs/INTEGRATIONS.md).
See the [repository directory](https://github.com/hjs-spec/.github/blob/main/PROJECTS.md#retired-experiments) for maintenance status. No automatic archive migration is provided.

This project turns Claude-style agent sessions into replayable accountability timelines.

**This is an experimental Claude session replay prototype aligned with JEP-style event semantics. It is not a normative JEP implementation and does not provide legal, compliance, or production security guarantees.**

This prototype has its own event envelope, signature metadata and `.jcrpack` format. Its detached signatures are not Core detached JWS. Session completion/failure labels are local instrumentation choices, not Core Termination semantics. For current signed Core 0.7 events, start with [Quickstart](https://github.com/hjs-spec/jep-quickstart).

## 1. What this is

A runtime-first prototype for answering:

- What did Claude do?
- Why was a tool invoked?
- Who authorized the step?
- Which file, shell, browser, or API actions were executed?
- Which actions were denied, failed, or terminated?
- Was the event chain or signature tampered with?
- Can the whole session be replayed as a timeline and lineage graph?

## 2. Why replay matters

Claude-style agents are not just chatting. They are running workflows: delegating to MCP tools, reading files, proposing edits, invoking shell commands, checking outputs, calling APIs, searching browsers, and terminating sessions. Plain logs preserve text. Replayable accountability events preserve execution semantics, lineage, verification state, evidence policy, provenance, and tamper evidence.

## 3. JEP alignment

The prototype borrows JEP v0.6 draft vocabulary and shape:

- Judgment Event (`J`) for task acceptance and action decisions.
- Delegation Event (`D`) for Claude → MCP/tool delegation.
- Verification Event (`V`) for result checking.
- Termination Event (`T`) for completion, stop, denial, abort, or failure.
- RFC 8785-compatible JSON Canonicalization Scheme helpers with golden vectors.
- SHA-256 `event_hash` and session-level `previous_event_hash` chain.
- `nonce`, `timestamp`, `validation_result`, `failure_code`, `ext`, and `ext_crit` fields.
- Detached signature metadata with HS256 local/dev signing, Ed25519 public-key signing, and key rotation.
- Profile-neutral design with no hidden governance hierarchy.
- Replay-safe JSONL archive and artifact manifest formats.

This project is aligned with JEP-style event semantics; it is not a normative or complete JEP implementation.

## 4. What this is not

- Not ordinary logging.
- Not an agent framework.
- Not a Claude API client.
- Not a legal liability, compliance, audit, or production security system.
- Not a real dangerous tool execution environment.

## 5. Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## 6. Run demo

```bash
jep-claude-replay demo
```

This regenerates demo archives and starts the local stdlib UI at <http://127.0.0.1:8765>.

## 7. Verify archive

```bash
jep-claude-replay verify examples/archives/simple_tool_session.jsonl
jep-claude-replay verify examples/archives/tampered_session.jsonl
```

The tampered archive intentionally fails with `invalid_event_hash` and reports the affected event.

## 8. Replay session

```bash
jep-claude-replay replay examples/archives/simple_tool_session.jsonl
```

Replay output includes a timeline, lineage graph, delegation chains, tool flow, and verification result.

## 9. UI screenshots placeholder

Screenshots are intentionally left as placeholders for the first public release:

- `docs/screenshots/timeline.png` — Replay Timeline
- `docs/screenshots/inspector.png` — Event Inspector
- `docs/screenshots/lineage.png` — React Flow Lineage Graph

The repository now includes a React/Vite + React Flow UI scaffold:

```bash
npm install
npm run dev
```

The Python `serve` command keeps a zero-dependency fallback UI for environments without Node.

## 10. Event model

Each event includes:

- identity: `event_id`, `event_type`, `verb`, `session_id`
- actors: `actor`, `subject`, `parent_event_id`, `delegation_chain`
- hash chain: `previous_event_hash`, `event_hash`, `nonce`, `timestamp`
- tool evidence: `tool_name`, `tool_input_digest`, `tool_output_digest`, redacted previews, and `evidence_refs`
- authority and validation: `authority_scope`, `verification_state`, `validation_result`, `failure_code`
- extensibility: `ext`, `ext_crit`
- detached signature metadata: `signature`

Events are immutable after hashing. Archive lines are canonical JSON objects. Raw tool input/output is not stored by default beyond digests and redacted previews.

## 11. Import real Claude Code / MCP transcripts

Claude Code-like JSON/JSONL transcripts can be imported when they contain common message/content-block shapes such as `tool_use` and `tool_result`:

```bash
jep-claude-replay import-claude-code examples/transcripts/claude_code_transcript.jsonl \
  -o examples/archives/claude_code_import.jsonl
```

MCP JSON-RPC transcript captures can be imported from `tools/call` request/result pairs:

```bash
jep-claude-replay import-mcp examples/transcripts/mcp_transcript.jsonl \
  -o examples/archives/mcp_import.jsonl
```

## 12. Detached signatures and key rotation

The prototype supports detached HS256 signatures for local/dev workflows and Ed25519 detached signatures for public-key verification. The signature is excluded from the event hash payload and can be rotated by `kid`:

```bash
jep-claude-replay keygen .local/keyring.json --kid local-1
jep-claude-replay sign examples/archives/simple_tool_session.jsonl --keyring .local/keyring.json \
  -o examples/archives/simple_tool_session.signed.jsonl
jep-claude-replay verify examples/archives/simple_tool_session.signed.jsonl --keyring .local/keyring.json
jep-claude-replay rotate-key .local/keyring.json local-2

# Public-key mode
jep-claude-replay keygen .local/ed25519-keyring.json --kid ed-1 --alg Ed25519
jep-claude-replay sign examples/archives/simple_tool_session.jsonl --keyring .local/ed25519-keyring.json --alg Ed25519 \
  -o examples/archives/simple_tool_session.ed25519.jsonl
```

## 13. Artifact manifests, diff verification, provenance, evidence policy

- Golden archive tests pin canonical events, event hashes, signatures, and replay output to catch compatibility regressions.
- Artifact manifests record digest, size, media type, role, and redaction mode for replay-safe evidence bundles.
- Diff-aware verification plugins validate required or forbidden additions in file edits.
- Browser/API provenance adapters capture query/request/response digests, origins, status, and preview policy.
- Evidence policies support `digest-only`, `digest-preview`, and tightly scoped `allow-raw` modes.
- Layered verification profiles report `basic`, `chain`, `signature`, `replay`, `evidence`, and `policy` results.

## 14. Artifact pack export/import

A `.jcrpack` bundles `archive.jsonl`, `manifest.json`, evidence files, `signatures.json`, and `verification-report.json` for replay-safe transport. Because `.jcrpack` is a zip container, generated pack files are intentionally ignored by git so pull requests stay text-reviewable:

```bash
jep-claude-replay pack examples/archives/simple_tool_session.signed.jsonl \
  -o examples/packs/simple_tool_session.jcrpack \
  --evidence examples/mock_claude_session/simple_tool_session.json \
  --keyring examples/keyrings/example_keyring.json

jep-claude-replay unpack examples/packs/simple_tool_session.jcrpack -o /tmp/jcrpack
```

## 15. Security and privacy limitations

- `shell.run` is mocked and never executes a real command.
- `filesystem.write` is sandbox-scoped in the mock MCP wrapper.
- Digests and previews reduce raw evidence exposure but are not a complete privacy solution.
- HS256 signatures are real stdlib MACs but are not public-key signatures and are not a production key-management system.
- Verification is prototype verification, not a legal or compliance guarantee.

## 16. Roadmap

- Add more Claude Code transcript dialect fixtures.
- Add optional KMS-backed detached signatures.
- Add richer evidence artifact manifests and encrypted evidence stores.
- Add more diff-aware verification plugins.
- Add browser/API provenance adapters for concrete tool providers.
- Build and publish the React Flow UI as package assets.

## Examples

- `simple_tool_session`: read-only file inspection, Replay PASS.
- `code_edit_session`: sandbox edit and mock diff verification, Replay PASS.
- `tampered_session`: manually edited event field, Replay FAIL.
- `claude_code_import`: imported Claude Code-style transcript, Replay PASS.
- `mcp_import`: imported MCP JSON-RPC transcript, Replay PASS.
- `matrix_*`: Claude Code dialect matrix for tool failure, permission denied, file patch, shell output, and MCP multi-server flows.
- `examples/packs/`: output directory for generated `.jcrpack` bundles; binary pack files are intentionally gitignored to keep PR diffs reviewable.
