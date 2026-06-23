"""ResearchAgent v1: collect clean YouTube/topic evidence."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import Any


class ResearchAgent:
    """Gather evidence for StrategyAgent without choosing the final angle."""

    MAX_QUERY_PLAN_ITEMS = 14

    GENERAL_QUERY_TEMPLATES = [
        {"template": "{topic}", "purpose": "baseline market scan"},
        {"template": "{topic} explained", "purpose": "educational demand"},
        {"template": "{topic} benefits", "purpose": "positive claims and demand"},
        {"template": "{topic} risks", "purpose": "risk objections and caveats"},
        {"template": "{topic} mistakes", "purpose": "viewer problems and confusion"},
        {"template": "{topic} myths", "purpose": "misconceptions and claims to verify"},
        {"template": "{topic} what happens", "purpose": "outcome-driven framing"},
        {"template": "{topic} science", "purpose": "evidence and expert framing"},
        {"template": "{topic} beginner guide", "purpose": "beginner search demand"},
    ]

    TOPIC_SENSITIVE_QUERY_TEMPLATES = {
        "health": [
            {"template": "{topic} side effects", "purpose": "health caveats and safety claims"},
            {"template": "what happens when you eat {topic}", "purpose": "consumption outcome framing"},
            {"template": "{topic} nutrition facts", "purpose": "nutrition evidence"},
        ],
        "money": [
            {"template": "{topic} for beginners", "purpose": "beginner finance demand"},
            {"template": "{topic} mistakes", "purpose": "financial pitfalls and objections"},
            {"template": "{topic} risks", "purpose": "financial risk claims"},
        ],
        "tech": [
            {"template": "{topic} problems", "purpose": "product or tech objections"},
            {"template": "{topic} worth it", "purpose": "purchase-intent evidence"},
            {"template": "{topic} comparison", "purpose": "comparison demand"},
        ],
    }

    TOPIC_GROUP_MARKERS = {
        "health": {
            "diet",
            "eat",
            "fitness",
            "food",
            "health",
            "medical",
            "nutrition",
            "supplement",
            "vitamin",
            "walnut",
            "walnuts",
        },
        "money": {"business", "finance", "income", "invest", "money", "profit", "sales", "stock"},
        "tech": {"ai", "app", "camera", "iphone", "laptop", "phone", "saas", "software", "tool"},
    }

    RISK_MARKERS = {
        "health": "Verify health or medical claims with credible sources before scripting.",
        "diet": "Verify nutrition claims and avoid medical advice.",
        "supplement": "Verify supplement claims, dosage language, and safety caveats.",
        "finance": "Verify financial claims and avoid personalized financial advice.",
        "invest": "Verify investment claims and risk language.",
        "legal": "Verify legal claims by jurisdiction.",
        "law": "Verify legal claims by jurisdiction.",
        "review": "Verify pricing, product specs, availability, and sponsorship language.",
    }

    def __init__(self, youtube_source: Any | None = None):
        self.youtube_source = youtube_source

    def run(
        self,
        topic: str,
        audience: str = "general viewers",
        style: str = "clear, evidence-led YouTube video",
        manual_brief: dict[str, Any] | None = None,
        youtube_settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        topic = topic.strip()
        if not topic:
            raise ValueError("topic is required")
        manual = self._normalize_manual_brief(manual_brief or {})
        settings = {
            "source": "auto",
            "max_results": 8,
            "max_queries": 10,
            "comments_per_video": 3,
            **(youtube_settings or {}),
        }
        query_plan = self._query_plan(topic, audience, style, manual)
        source_errors: list[dict[str, Any]] = []
        videos: list[dict[str, Any]] = []
        relevance_filter = {}
        youtube_available = bool(self.youtube_source and getattr(self.youtube_source, "available", lambda: True)())

        if settings["source"] in {"auto", "youtube"} and self.youtube_source and youtube_available:
            result = self.youtube_source.collect(
                topic=topic,
                query_plan=query_plan,
                max_results=int(settings["max_results"]),
                max_queries=int(settings["max_queries"]),
                comments_per_video=int(settings["comments_per_video"]),
                manual_brief=manual,
            )
            if result.get("ok"):
                videos = result.get("videos", [])
                relevance_filter = result.get("relevance_filter", {})
                for error in result.get("source_errors", []):
                    source_errors.append({"source": "youtube", "error": str(error)})
            else:
                source_errors.append({"source": "youtube", "error": result.get("error", "Unknown YouTube error.")})
        elif settings["source"] == "youtube":
            source_errors.append({"source": "youtube", "error": "YouTube source unavailable or missing API key."})
        elif settings["source"] == "auto":
            source_errors.append({"source": "youtube", "error": "YouTube source skipped because no API key is available."})

        competitor_videos = self._competitor_videos(videos)
        breakout_videos = [video for video in competitor_videos if video.get("is_breakout")]
        title_patterns = self._title_patterns(competitor_videos)
        viewer_pains = self._viewer_pains(competitor_videos)

        return {
            "schema_version": "research.v1",
            "agent": "ResearchAgent",
            "created_at": datetime.now().isoformat(),
            "input": {
                "topic": topic,
                "audience": audience,
                "style": style,
                "manual_brief": manual,
                "youtube_settings": settings,
            },
            "query_plan": query_plan,
            "evidence_status": {
                "youtube_available": youtube_available,
                "video_count": len(competitor_videos),
                "has_live_youtube_data": bool(competitor_videos),
                "notes": self._evidence_notes(competitor_videos, source_errors),
            },
            "market_stats": self._market_stats(competitor_videos, relevance_filter),
            "competitor_videos": competitor_videos,
            "breakout_videos": breakout_videos[:10],
            "title_patterns": title_patterns,
            "viewer_pains": viewer_pains,
            "claims_to_verify": self._claims_to_verify(topic, competitor_videos, title_patterns),
            "source_errors": source_errors,
            "handoff_contract": {
                "next_agent": "StrategyAgent",
                "strategy_should_decide": [
                    "recommended niche lane",
                    "recommended video angle",
                    "positioning rationale",
                    "which evidence matters most for the chosen angle",
                ],
                "research_agent_must_not_decide": [
                    "final niche lane",
                    "final angle",
                    "script premise",
                ],
            },
        }

    def _query_plan(
        self,
        topic: str,
        audience: str,
        style: str,
        manual: dict[str, Any],
    ) -> list[dict[str, str]]:
        base = topic.strip()
        context = manual.get("topic_context", "").strip()
        include = manual.get("include_keywords", [])
        query_items = [dict(item) for item in self.GENERAL_QUERY_TEMPLATES]
        for group in self._topic_groups(topic, context):
            query_items.extend(dict(item) for item in self.TOPIC_SENSITIVE_QUERY_TEMPLATES[group])

        queries = [
            (item["template"].format(topic=base), item["purpose"])
            for item in query_items
        ]
        if audience and audience != "general viewers":
            queries.append((f"{base} for {audience}", "audience-specific demand"))
        if style:
            style_terms = self._style_terms(style)
            if style_terms:
                queries.append((f"{base} {style_terms}", "style-specific comparable videos"))
        if context:
            queries.append((f"{base} {context}", "manual topic context"))
        for keyword in include[:3]:
            queries.append((f"{base} {keyword}", "manual include keyword"))

        clean_queries = []
        seen = set()
        for query, purpose in queries:
            query = re.sub(r"\s+", " ", query).strip()
            if query.lower() in seen:
                continue
            seen.add(query.lower())
            clean_queries.append({"query": query, "purpose": purpose})
        return clean_queries[: self.MAX_QUERY_PLAN_ITEMS]

    def _topic_groups(self, topic: str, context: str) -> list[str]:
        text = f"{topic} {context}".lower()
        groups = []
        for group, markers in self.TOPIC_GROUP_MARKERS.items():
            if any(marker in text for marker in markers):
                groups.append(group)
        return groups

    def _style_terms(self, style: str) -> str:
        style_lower = style.lower()
        if "documentary" in style_lower:
            return "documentary"
        if "tutorial" in style_lower:
            return "tutorial"
        if "faceless" in style_lower:
            return "faceless"
        if "short" in style_lower:
            return "shorts"
        return ""

    def _normalize_manual_brief(self, manual: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(manual)
        list_fields = [
            "include_keywords",
            "must_include_keywords",
            "exclude_keywords",
            "hard_exclude_keywords",
            "seed_videos",
        ]
        for field in list_fields:
            normalized[field] = self._as_list(normalized.get(field, []))
        normalized.setdefault("topic_context", "")
        normalized.setdefault("language", "auto")
        normalized.setdefault("content_type", "both")
        normalized.setdefault("avoid_kids_content", True)
        return normalized

    def _competitor_videos(self, videos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        fields = [
            "video_id",
            "url",
            "title",
            "description",
            "tags",
            "duration",
            "duration_seconds",
            "format_bucket",
            "published_at",
            "view_count",
            "like_count",
            "comment_count",
            "engagement_rate",
            "views_per_day",
            "channel_id",
            "channel_title",
            "subscriber_count",
            "outlier_ratio",
            "is_breakout",
            "query_matches",
            "relevance",
            "comments",
        ]
        return [{field: video.get(field) for field in fields if field in video} for video in videos]

    def _market_stats(self, videos: list[dict[str, Any]], relevance_filter: dict[str, Any]) -> dict[str, Any]:
        views = [int(video.get("view_count") or 0) for video in videos]
        views_per_day = [float(video.get("views_per_day") or 0) for video in videos]
        durations = [int(video.get("duration_seconds") or 0) for video in videos]
        return {
            "videos_collected": len(videos),
            "total_views": sum(views),
            "median_views": self._median(views),
            "median_views_per_day": self._median(views_per_day),
            "median_duration_seconds": self._median(durations),
            "format_counts": self._format_counts(videos),
            "breakout_count": sum(1 for video in videos if video.get("is_breakout")),
            "relevance_filter": relevance_filter,
        }

    def _format_counts(self, videos: list[dict[str, Any]]) -> dict[str, int]:
        counts: Counter[str] = Counter(video.get("format_bucket", "unknown") for video in videos)
        return {
            "shortform": counts.get("shortform", 0),
            "midform": counts.get("midform", 0),
            "longform": counts.get("longform", 0),
            "unknown": counts.get("unknown", 0),
        }

    def _title_patterns(self, videos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        patterns: Counter[str] = Counter()
        examples: dict[str, list[str]] = {}
        for video in videos:
            title = video.get("title", "")
            lowered = title.lower()
            candidates = []
            if re.search(r"\b\d+\b", title):
                candidates.append("number/list title")
            if "why" in lowered:
                candidates.append("why framing")
            if "how to" in lowered:
                candidates.append("how-to framing")
            if "mistake" in lowered:
                candidates.append("mistakes framing")
            if "truth" in lowered or "myth" in lowered:
                candidates.append("truth/myth framing")
            if "before" in lowered and "after" in lowered:
                candidates.append("before-after framing")
            if not candidates:
                candidates.append("plain topic explainer")
            for pattern in candidates:
                patterns[pattern] += 1
                examples.setdefault(pattern, []).append(title)
        return [
            {"pattern": pattern, "count": count, "examples": examples.get(pattern, [])[:3]}
            for pattern, count in patterns.most_common()
        ]

    def _viewer_pains(self, videos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pain_markers = ("confused", "how do", "how can", "why", "help", "does anyone", "problem", "?")
        pains = []
        for video in videos:
            for comment in video.get("comments", []) or []:
                text = comment.get("text", "").strip()
                if len(text) < 12:
                    continue
                lowered = text.lower()
                if any(marker in lowered for marker in pain_markers):
                    pains.append(
                        {
                            "text": text[:500],
                            "video_id": video.get("video_id"),
                            "video_title": video.get("title"),
                            "like_count": comment.get("like_count", 0),
                        }
                    )
        return pains[:20]

    def _claims_to_verify(
        self,
        topic: str,
        videos: list[dict[str, Any]],
        title_patterns: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        claims = []
        combined = " ".join([topic, *[video.get("title", "") for video in videos]]).lower()
        for marker, reason in self.RISK_MARKERS.items():
            if marker in combined:
                claims.append({"claim_area": marker, "reason": reason})
        if any(pattern["pattern"] == "truth/myth framing" for pattern in title_patterns):
            claims.append({"claim_area": "myths and misconceptions", "reason": "Titles imply factual correction."})
        if any(re.search(r"\b(cure|prevent|guarantee|secret)\b", video.get("title", "").lower()) for video in videos):
            claims.append({"claim_area": "strong promise language", "reason": "At least one title uses high-risk promise wording."})
        return claims

    def _evidence_notes(self, videos: list[dict[str, Any]], source_errors: list[dict[str, Any]]) -> list[str]:
        if videos:
            return ["Live YouTube evidence collected and filtered."]
        if source_errors:
            return ["No live YouTube evidence collected. Inspect source_errors before using downstream agents."]
        return ["No competitor evidence collected."]

    def _median(self, values: list[int] | list[float]) -> float:
        if not values:
            return 0
        ordered = sorted(values)
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return round(float(ordered[middle]), 2)
        return round(float((ordered[middle - 1] + ordered[middle]) / 2), 2)

    def _as_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [item.strip() for item in re.split(r"[,;]", value) if item.strip()]
        return []
