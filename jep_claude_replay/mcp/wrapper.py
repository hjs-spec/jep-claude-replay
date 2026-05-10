"""Safe mock MCP tool wrapper that emits JEP-style accountability events."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from jep_claude_replay.events.model import JEPEvent, make_event

class MCPRecorder:
    def __init__(self, session_id: str, sandbox: str | Path = "examples/mock_mcp_tools/sandbox"):
        self.session_id = session_id
        self.sandbox = Path(sandbox)
        self.sandbox.mkdir(parents=True, exist_ok=True)
        self.events: list[JEPEvent] = []

    @property
    def previous_hash(self) -> str | None:
        return self.events[-1].event_hash if self.events else None

    def before_tool_call(self, name: str, tool_input: Any, authority_scope: dict) -> JEPEvent:
        e = make_event("delegation", actor="Claude", subject=name, session_id=self.session_id, previous_event_hash=self.previous_hash, intent=f"Invoke MCP tool {name}", tool_name=name, tool_input=tool_input, authority_scope=authority_scope, delegation_chain=["Human", "Claude", name])
        self.events.append(e)
        return e

    def after_tool_call(self, name: str, tool_input: Any, output: Any, parent: JEPEvent, authority_scope: dict) -> JEPEvent:
        e = make_event("verification", actor="Claude", subject=name, session_id=self.session_id, parent_event_id=parent.event_id, previous_event_hash=self.previous_hash, intent=f"Verify MCP tool {name} result", tool_name=name, tool_input=tool_input, tool_output=output, authority_scope=authority_scope, delegation_chain=["Human", "Claude", name], verification_state="passed", validation_result={"valid": True, "failure_codes": [], "warnings": []})
        self.events.append(e)
        return e

    def on_tool_error(self, name: str, tool_input: Any, error: Exception, parent: JEPEvent, authority_scope: dict) -> JEPEvent:
        e = make_event("termination", actor="MCP", subject=name, session_id=self.session_id, parent_event_id=parent.event_id, previous_event_hash=self.previous_hash, intent=str(error), tool_name=name, tool_input=tool_input, authority_scope=authority_scope, delegation_chain=["Human", "Claude", name], verification_state="failed", failure_code="tool_failed", validation_result={"valid": False, "failure_codes": ["tool_failed"], "warnings": []})
        self.events.append(e)
        return e

    def wrap_tool(self, name: str, fn: Callable[[Any], Any], authority_scope: dict | None = None) -> Callable[[Any], Any]:
        scope = authority_scope or {"profile": "neutral", "limits": ["mock-only"]}
        def wrapped(tool_input: Any) -> Any:
            parent = self.before_tool_call(name, tool_input, scope)
            try:
                out = fn(tool_input)
            except Exception as exc:
                self.on_tool_error(name, tool_input, exc, parent, scope)
                raise
            self.after_tool_call(name, tool_input, out, parent, scope)
            return out
        return wrapped


def filesystem_read(tool_input: dict) -> dict:
    path = Path(tool_input["path"])
    return {"path": str(path), "content": path.read_text(encoding="utf-8")}


def filesystem_write_factory(sandbox: str | Path):
    root = Path(sandbox).resolve()
    root.mkdir(parents=True, exist_ok=True)
    def write(tool_input: dict) -> dict:
        target = (root / tool_input["path"]).resolve()
        if root not in target.parents and target != root:
            raise ValueError("filesystem.write denied outside sandbox")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(tool_input.get("content", ""), encoding="utf-8")
        return {"path": str(target), "bytes": len(tool_input.get("content", ""))}
    return write


def shell_run(tool_input: dict) -> dict:
    return {"mock": True, "command": tool_input.get("command"), "stdout": "mock shell output", "returncode": 0}


def browser_search(tool_input: dict) -> dict:
    return {"mock": True, "query": tool_input.get("query"), "results": [{"title": "mock result", "url": "https://example.invalid"}]}


def api_call(tool_input: dict) -> dict:
    return {"mock": True, "endpoint": tool_input.get("endpoint"), "status": 200}
