"""Command line interface for jep-claude-replay."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from jep_claude_replay.archive.runtime import load_archive
from jep_claude_replay.claude.adapter import record_session
from jep_claude_replay.replay.engine import replay_session
from jep_claude_replay.ui.server import serve as serve_ui
from jep_claude_replay.verification.runtime import verify_archive_chain
from jep_claude_replay.adapters.claude_code import record_claude_code_transcript
from jep_claude_replay.adapters.mcp_transcript import record_mcp_transcript
from jep_claude_replay.archive.runtime import export_jsonl
from jep_claude_replay.signature.keyring import Keyring
from jep_claude_replay.signature.runtime import sign_events, verify_archive_signatures
from jep_claude_replay.verification.profile import verify_profiles
from jep_claude_replay.pack.runtime import export_pack, import_pack


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="jep-claude-replay")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    r = sub.add_parser("record"); r.add_argument("session_json"); r.add_argument("-o", "--output")
    v = sub.add_parser("verify"); v.add_argument("archive"); v.add_argument("--keyring")
    rp = sub.add_parser("replay"); rp.add_argument("archive"); rp.add_argument("--session-id")
    s = sub.add_parser("serve"); s.add_argument("--host", default="127.0.0.1"); s.add_argument("--port", type=int, default=8765)
    ic = sub.add_parser("import-claude-code"); ic.add_argument("transcript"); ic.add_argument("-o", "--output", required=True); ic.add_argument("--session-id")
    im = sub.add_parser("import-mcp"); im.add_argument("transcript"); im.add_argument("-o", "--output", required=True); im.add_argument("--session-id", default="mcp-import")
    kg = sub.add_parser("keygen"); kg.add_argument("path"); kg.add_argument("--kid", default="local-1"); kg.add_argument("--alg", choices=["HS256", "Ed25519"], default="HS256")
    kr = sub.add_parser("rotate-key"); kr.add_argument("path"); kr.add_argument("kid"); kr.add_argument("--alg", choices=["HS256", "Ed25519"], default="HS256")
    sg = sub.add_parser("sign"); sg.add_argument("archive"); sg.add_argument("--keyring", required=True); sg.add_argument("-o", "--output", required=True); sg.add_argument("--alg", choices=["HS256", "Ed25519"] )
    vp = sub.add_parser("verify-profile"); vp.add_argument("archive"); vp.add_argument("--keyring")
    pk = sub.add_parser("pack"); pk.add_argument("archive"); pk.add_argument("-o", "--output", required=True); pk.add_argument("--evidence", action="append", default=[]); pk.add_argument("--keyring")
    up = sub.add_parser("unpack"); up.add_argument("pack"); up.add_argument("-o", "--output-dir", required=True)
    args = p.parse_args(argv)
    if args.cmd == "record":
        out = args.output or f"examples/archives/{Path(args.session_json).stem}.jsonl"
        events = record_session(args.session_json, out)
        print(f"wrote {len(events)} events to {out}")
        return 0
    if args.cmd == "verify":
        events = load_archive(args.archive)
        res = verify_archive_chain(events)
        if args.keyring:
            sig = verify_archive_signatures(events, Keyring.load(args.keyring))
            res = {**res, "signature_validation": sig, "valid": res["valid"] and sig["valid"], "failure_codes": sorted(set(res["failure_codes"] + sig["failure_codes"]))}
        print(json.dumps(res, indent=2))
        return 0 if res["valid"] else 1
    if args.cmd == "replay":
        print(json.dumps(replay_session(load_archive(args.archive), args.session_id), indent=2))
        return 0
    if args.cmd == "serve":
        serve_ui(args.host, args.port)
        return 0
    if args.cmd == "verify-profile":
        keyring = Keyring.load(args.keyring) if args.keyring else None
        print(json.dumps(verify_profiles(load_archive(args.archive), keyring=keyring), indent=2))
        return 0
    if args.cmd == "pack":
        keyring = Keyring.load(args.keyring) if args.keyring else None
        print(json.dumps(export_pack(args.archive, args.output, evidence_paths=args.evidence, keyring=keyring), indent=2))
        return 0
    if args.cmd == "unpack":
        print(json.dumps(import_pack(args.pack, args.output_dir), indent=2))
        return 0
    if args.cmd == "import-claude-code":
        events = record_claude_code_transcript(args.transcript, args.output, session_id=args.session_id)
        print(f"imported {len(events)} Claude Code events to {args.output}")
        return 0
    if args.cmd == "import-mcp":
        events = record_mcp_transcript(args.transcript, args.output, session_id=args.session_id)
        print(f"imported {len(events)} MCP events to {args.output}")
        return 0
    if args.cmd == "keygen":
        Keyring.generate(args.kid, alg=args.alg).save(args.path)
        print(f"wrote keyring {args.path}")
        return 0
    if args.cmd == "rotate-key":
        keyring = Keyring.load(args.path); keyring.rotate(args.kid, alg=args.alg); keyring.save(args.path)
        print(f"rotated keyring {args.path} active={args.kid}")
        return 0
    if args.cmd == "sign":
        events = sign_events(load_archive(args.archive), Keyring.load(args.keyring), alg=args.alg)
        export_jsonl(events, args.output)
        print(f"signed {len(events)} events to {args.output}")
        return 0
    if args.cmd == "demo":
        for name in ["simple_tool_session", "code_edit_session"]:
            record_session(f"examples/mock_claude_session/{name}.json", f"examples/archives/{name}.jsonl")
        import json as _json
        source = Path("examples/archives/simple_tool_session.jsonl")
        rows = [_json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
        rows[2]["intent"] = "TAMPERED: read a different file"
        Path("examples/archives/tampered_session.jsonl").write_text("\n".join(_json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
        print("Generated demo archives. Starting UI...")
        serve_ui("127.0.0.1", 8765)
        return 0
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
