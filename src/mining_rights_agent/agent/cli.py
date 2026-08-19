from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate an evidence-backed mining daily brief.")
    parser.add_argument("request", help="Natural-language brief request")
    parser.add_argument("--mode", choices=["live", "fixture"], default=None)
    parser.add_argument(
        "--pdf-url", default=None, help="Optional explicit technical report PDF URL"
    )
    parser.add_argument("--output", type=Path, default=None, help="Write Markdown to this file")
    return parser


async def run(args: argparse.Namespace) -> str:
    if args.mode:
        os.environ["APP_MODE"] = args.mode

    from mining_rights_agent.agent.gateway import McpProcessGateway
    from mining_rights_agent.agent.orchestrator import BriefOrchestrator
    from mining_rights_agent.common.settings import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    async with McpProcessGateway() as gateway:
        orchestrator = BriefOrchestrator(gateway, settings)
        markdown = await orchestrator.generate(args.request, args.pdf_url)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
    return markdown


def main() -> None:
    args = build_parser().parse_args()
    print(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
