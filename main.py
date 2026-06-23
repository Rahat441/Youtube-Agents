#!/usr/bin/env python3
"""CLI for the clean YouTube Agents rebuild."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from youtube_agents.agents.idea_agent import IdeaAgent
from youtube_agents.agents.research_agent import ResearchAgent
from youtube_agents.agents.strategy_agent import StrategyAgent
from youtube_agents.core.paths import project_root, read_json, slugify, timestamp, write_json
from youtube_agents.sources.youtube_source import YouTubeDataSource


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="YouTube Agents local-first pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    research = subparsers.add_parser("research", help="Run ResearchAgent only")
    research.add_argument("--topic", required=True, help="Topic to research")
    research.add_argument("--audience", default="general viewers", help="Target audience")
    research.add_argument("--style", default="clear, evidence-led YouTube video", help="Video/channel style")
    research.add_argument("--manual-brief", default=None, help="Path to a JSON manual brief")
    research.add_argument("--topic-context", default=None, help="Manual disambiguation context")
    research.add_argument(
        "--content-type",
        choices=["both", "shortform", "midform", "longform", "scriptable"],
        default=None,
        help="Filter YouTube evidence by duration. scriptable keeps videos at least 180 seconds.",
    )
    research.add_argument(
        "--language",
        choices=["auto", "english"],
        default=None,
        help="Filter YouTube evidence by language. english rejects mostly non-English titles.",
    )
    research.add_argument("--include-keyword", action="append", default=[], help="Keyword to include in queries/filtering")
    research.add_argument("--exclude-keyword", action="append", default=[], help="Keyword to exclude from results")
    research.add_argument("--source", choices=["auto", "youtube", "offline"], default="auto", help="Research source")
    research.add_argument("--youtube-max-results", type=int, default=8, help="Max search results per YouTube query")
    research.add_argument("--youtube-max-queries", type=int, default=10, help="Max query-plan items to search")
    research.add_argument("--youtube-comments-per-video", type=int, default=3, help="Comments to sample per selected video")
    research.add_argument("--output-dir", default=None, help="Optional output directory for research.json")

    strategy = subparsers.add_parser("strategy", help="Run StrategyAgent from a research.json file")
    strategy.add_argument("--research", required=True, help="Path to research.json")
    strategy.add_argument("--output-dir", default=None, help="Optional output directory for strategy.json")

    ideas = subparsers.add_parser("ideas", help="Run IdeaAgent from research.json and strategy.json")
    ideas.add_argument("--research", required=True, help="Path to research.json")
    ideas.add_argument("--strategy", required=True, help="Path to strategy.json")
    ideas.add_argument("--ideas-per-run", type=int, default=5, help="Number of final ideas to save")
    ideas.add_argument("--max-candidates", type=int, default=12, help="Max internal candidates to generate and score")
    ideas.add_argument("--provider", choices=["template", "ollama", "openai"], default="template", help="Idea generation provider")
    ideas.add_argument("--model", default=None, help="LLM model name when using --provider ollama or openai")
    ideas.add_argument("--output-dir", default=None, help="Optional output directory for ideas.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "research":
        return run_research(args)
    if args.command == "strategy":
        return run_strategy(args)
    if args.command == "ideas":
        return run_ideas(args)
    parser.error(f"Unknown command: {args.command}")
    return 2


def run_research(args: argparse.Namespace) -> int:
    manual = {}
    if args.manual_brief:
        manual = read_json(Path(args.manual_brief))
    if args.topic_context:
        manual["topic_context"] = args.topic_context
    if args.content_type:
        manual["content_type"] = args.content_type
    if args.language:
        manual["language"] = args.language
    if args.include_keyword:
        manual["include_keywords"] = [*manual.get("include_keywords", []), *args.include_keyword]
    if args.exclude_keyword:
        manual["exclude_keywords"] = [*manual.get("exclude_keywords", []), *args.exclude_keyword]

    youtube_source = YouTubeDataSource()
    if args.source == "offline":
        youtube_source = None

    agent = ResearchAgent(youtube_source=youtube_source)
    research = agent.run(
        topic=args.topic,
        audience=args.audience,
        style=args.style,
        manual_brief=manual,
        youtube_settings={
            "source": args.source,
            "max_results": args.youtube_max_results,
            "max_queries": args.youtube_max_queries,
            "comments_per_video": args.youtube_comments_per_video,
        },
    )
    output_dir = Path(args.output_dir) if args.output_dir else default_run_dir(args.topic)
    output_path = output_dir / "research.json"
    write_json(output_path, research)
    ok = not (
        args.source == "youtube"
        and not research["evidence_status"]["has_live_youtube_data"]
        and research["source_errors"]
    )
    print(
        json.dumps(
            {
                "ok": ok,
                "research_path": str(output_path),
                "source_errors": research["source_errors"],
            },
            indent=2,
        )
    )
    return 0 if ok else 1


def default_run_dir(topic: str) -> Path:
    return project_root() / "workspace" / "agent_runs" / f"{timestamp()}_{slugify(topic)}"


def run_strategy(args: argparse.Namespace) -> int:
    research_path = Path(args.research)
    research = read_json(research_path)
    strategy = StrategyAgent().run(research)
    output_dir = Path(args.output_dir) if args.output_dir else research_path.parent
    output_path = output_dir / "strategy.json"
    write_json(output_path, strategy)
    print(
        json.dumps(
            {
                "ok": True,
                "strategy_path": str(output_path),
                "recommended_niche_lane": strategy["recommended_niche_lane"],
                "recommended_angle": strategy["recommended_angle"],
            },
            indent=2,
        )
    )
    return 0


def run_ideas(args: argparse.Namespace) -> int:
    research_path = Path(args.research)
    strategy_path = Path(args.strategy)
    research = read_json(research_path)
    strategy = read_json(strategy_path)
    ideas = IdeaAgent().run(
        research=research,
        strategy=strategy,
        ideas_per_run=args.ideas_per_run,
        max_candidates=args.max_candidates,
        provider=args.provider,
        model=args.model,
    )
    output_dir = Path(args.output_dir) if args.output_dir else strategy_path.parent
    output_path = output_dir / "ideas.json"
    write_json(output_path, ideas)
    print(
        json.dumps(
            {
                "ok": True,
                "ideas_path": str(output_path),
                "selected_idea_id": ideas.get("selected_idea", {}).get("idea_id"),
                "selected_working_title": ideas.get("selected_idea", {}).get("working_title"),
                "generation": ideas.get("generation", {}),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
