"""Command line interface for Business Intel Agent.

Subcommands:
- ask: Ask a question in natural language.
- tool: Directly invoke a deterministic tool.
- report: Generate and export an Obsidian-compatible markdown report.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

_agent_root = str(Path(__file__).resolve().parent.parent)
if _agent_root not in sys.path:
    sys.path.insert(0, _agent_root)

from business_intel.agents.business_intel_agent import BusinessIntelAgent
from business_intel.schemas import OutOfScopeResponse
from business_intel.tools.registry import call_tool


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="business-intel",
        description="Business Intel Agent CLI for Alexa Business Autopilot",
    )
    parser.add_argument("--db", type=str, default=None, help="Path to demo.db")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: ask
    ask_parser = subparsers.add_parser("ask", help="Ask a natural language question")
    ask_parser.add_argument("question", type=str, help="Question text")
    ask_parser.add_argument("--json", action="store_true", help="Output full JSON response")

    # Subcommand: tool
    tool_parser = subparsers.add_parser("tool", help="Directly invoke a deterministic tool")
    tool_parser.add_argument("tool_name", type=str, help="Tool name")
    tool_parser.add_argument("--args", type=str, default="{}", help="JSON string of arguments")

    # Subcommand: report
    report_parser = subparsers.add_parser("report", help="Generate business report")
    report_parser.add_argument("--type", type=str, default="executive_brief", help="Report type")
    report_parser.add_argument("--period", type=str, default="last_30d", help="Period (last_7d, last_30d, etc.)")
    report_parser.add_argument("--export-obsidian", action="store_true", help="Export to reports/ directory")
    report_parser.add_argument("--out-dir", type=str, default="reports", help="Output directory for export")

    args = parser.parse_args(argv)

    if args.command == "ask":
        agent = BusinessIntelAgent(db_path=args.db)
        ans = agent.ask(args.question, db_path=args.db)
        if args.json:
            print(json.dumps(ans.model_dump(), indent=2))
        else:
            if isinstance(ans, OutOfScopeResponse):
                print(f"[OUT OF SCOPE] Suggested agent: {ans.suggested_agent}")
                print(f"Reason: {ans.reason}")
                print(f"Refusal Voice: {ans.speech_refusal or ans.speech_summary}")
            else:
                print(f"\n🗣️ Voice Speech:\n{ans.speech}\n")
                if ans.warnings:
                    print("⚠️ Caveats/Warnings:")
                    for w in ans.warnings:
                        print(f"  - {w}")
                    print("")
                print(f"Confidence: {ans.confidence} | Tools used: {', '.join(ans.tools_used)}")
                if ans.details_markdown:
                    print("\n📱 Screen Display:\n" + "-" * 40)
                    print(ans.details_markdown)
        return 0

    elif args.command == "tool":
        try:
            tool_args = json.loads(args.args)
        except Exception as e:
            print(f"Error parsing --args JSON: {e}", file=sys.stderr)
            return 1

        env = call_tool(args.tool_name, tool_args, db_path=args.db)
        print(json.dumps(env.model_dump(), indent=2))
        return 0 if env.ok else 1

    elif args.command == "report":
        env = call_tool(
            "generate_business_report",
            {"report_type": args.type, "period": args.period, "export_format": "markdown"},
            db_path=args.db,
        )
        if not env.ok:
            print(f"Report generation failed: {env.error}", file=sys.stderr)
            return 1

        report_md = env.data.get("report_markdown", "")
        if args.export_obsidian:
            os.makedirs(args.out_dir, exist_ok=True)
            filename = f"2026-10-10_{args.type}_{args.period}.md"
            filepath = os.path.join(args.out_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(report_md)
            print(f"✅ Report exported successfully to: {filepath}")
        else:
            print(report_md)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())

