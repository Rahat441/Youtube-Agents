"""YouTube Data API evidence collection.

This source is intentionally factual and low-level. It searches YouTube,
normalizes video/channel/comment records, and computes basic metrics. Strategic
choices belong to later agents.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from youtube_agents.core.env import load_dotenv


class YouTubeDataSource:
    SEARCH_ORDERS = ("relevance", "viewCount")
    MAIN_QUERY_SEARCH_ORDERS = ("relevance", "viewCount", "date")
    SHORTFORM_MAX_SECONDS = 60
    MIDFORM_MAX_SECONDS = 239
    SCRIPTABLE_MIN_SECONDS = 180
    LONGFORM_MIN_SECONDS = 240
    NOISE_MARKERS = {
        "asmr",
        "cartoon",
        "dance",
        "gameplay",
        "lyrics",
        "minecraft",
        "music video",
        "nursery",
        "phonics",
        "prank",
        "roblox",
        "song",
        "toy",
        "toys",
    }

    def __init__(self, api_key: str | None = None, timeout_seconds: int = 20):
        load_dotenv()
        self.api_key = api_key or os.getenv("YOUTUBE_API_KEY")
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.ssl_context = ssl.create_default_context()

    def available(self) -> bool:
        return bool(self.api_key)

    def collect(
        self,
        topic: str,
        query_plan: list[dict[str, Any]],
        max_results: int = 8,
        max_queries: int = 10,
        comments_per_video: int = 3,
        manual_brief: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.api_key:
            return {"ok": False, "source": "youtube", "error": "YOUTUBE_API_KEY is not configured."}

        manual_brief = manual_brief or {}
        source_errors = []
        search = self._collect_search_results(query_plan, max_results, max_queries)
        if not search["ok"]:
            return search
        source_errors.extend(search.get("errors", []))

        video_ids = self._dedupe(item["video_id"] for item in search["items"])
        video_stats = self._video_stats(video_ids)
        if not video_stats["ok"]:
            return video_stats

        channel_ids = self._dedupe(
            item.get("channel_id", "")
            for item in list(search["items"]) + list(video_stats["items"].values())
        )
        channel_stats = self._channel_stats(channel_ids)
        if not channel_stats["ok"]:
            return channel_stats

        videos = self._merge(search["items"], video_stats["items"], channel_stats["items"])
        videos, relevance_filter = self._filter_videos(videos, topic, manual_brief)
        videos = [self._score_video(video) for video in videos]
        videos.sort(key=lambda item: item.get("views_per_day", 0), reverse=True)

        comment_targets = [video["video_id"] for video in videos[: min(5, len(videos))]]
        comments = self._comment_threads(comment_targets, comments_per_video)
        if comments["ok"]:
            for video in videos:
                video["comments"] = comments["items"].get(video["video_id"], [])
            source_errors.extend(comments.get("errors", []))

        return {
            "ok": True,
            "source": "youtube",
            "collected_at": datetime.now().isoformat(),
            "videos": videos,
            "source_errors": source_errors,
            "relevance_filter": relevance_filter,
        }

    def _collect_search_results(
        self,
        query_plan: list[dict[str, Any]],
        max_results: int,
        max_queries: int,
    ) -> dict[str, Any]:
        collected: dict[str, dict[str, Any]] = {}
        errors = []
        for query_index, query_item in enumerate(query_plan[: max(1, max_queries)]):
            query = query_item["query"]
            orders = self.MAIN_QUERY_SEARCH_ORDERS if query_index == 0 else self.SEARCH_ORDERS
            for order in orders:
                response = self._search_videos(query, max_results, order)
                if not response["ok"]:
                    errors.append(response.get("error", "Unknown YouTube search error."))
                    continue
                for item in response["items"]:
                    existing = collected.setdefault(item["video_id"], item)
                    existing.setdefault("query_matches", [])
                    existing["query_matches"].append(
                        {
                            "query": query,
                            "order": order,
                            "purpose": query_item.get("purpose", ""),
                        }
                    )

        if not collected and errors:
            return {"ok": False, "source": "youtube_search", "error": errors[0]}
        return {"ok": True, "source": "youtube_search", "items": list(collected.values()), "errors": errors}

    def _search_videos(self, query: str, max_results: int, order: str) -> dict[str, Any]:
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": max(1, min(max_results, 25)),
            "order": order,
            "key": self.api_key,
        }
        payload = self._get_json("/search", params)
        if not payload["ok"]:
            return payload

        items = []
        for rank, item in enumerate(payload["data"].get("items", []), 1):
            video_id = item.get("id", {}).get("videoId")
            snippet = item.get("snippet", {})
            if not video_id:
                continue
            items.append(
                {
                    "rank": rank,
                    "video_id": video_id,
                    "title": snippet.get("title", ""),
                    "description": snippet.get("description", ""),
                    "channel_id": snippet.get("channelId", ""),
                    "channel_title": snippet.get("channelTitle", ""),
                    "published_at": snippet.get("publishedAt", ""),
                    "thumbnail_url": self._thumbnail_url(snippet),
                    "query_matches": [],
                }
            )
        return {"ok": True, "source": "youtube_search", "items": items}

    def _video_stats(self, video_ids: list[str]) -> dict[str, Any]:
        items: dict[str, dict[str, Any]] = {}
        for chunk in self._chunks(video_ids, 50):
            params = {
                "part": "snippet,statistics,contentDetails,status",
                "id": ",".join(chunk),
                "key": self.api_key,
            }
            payload = self._get_json("/videos", params)
            if not payload["ok"]:
                return payload
            for item in payload["data"].get("items", []):
                snippet = item.get("snippet", {})
                stats = item.get("statistics", {})
                content = item.get("contentDetails", {})
                status = item.get("status", {})
                video_id = item.get("id", "")
                items[video_id] = {
                    "video_id": video_id,
                    "title": snippet.get("title", ""),
                    "description": snippet.get("description", ""),
                    "channel_id": snippet.get("channelId", ""),
                    "channel_title": snippet.get("channelTitle", ""),
                    "published_at": snippet.get("publishedAt", ""),
                    "thumbnail_url": self._thumbnail_url(snippet),
                    "tags": snippet.get("tags", []),
                    "duration": content.get("duration", ""),
                    "duration_seconds": self._duration_seconds(content.get("duration", "")),
                    "made_for_kids": status.get("madeForKids", False),
                    "view_count": self._to_int(stats.get("viewCount")),
                    "like_count": self._to_int(stats.get("likeCount")),
                    "comment_count": self._to_int(stats.get("commentCount")),
                }
        return {"ok": True, "source": "youtube_videos", "items": items}

    def _channel_stats(self, channel_ids: list[str]) -> dict[str, Any]:
        items: dict[str, dict[str, Any]] = {}
        for chunk in self._chunks(channel_ids, 50):
            params = {"part": "snippet,statistics", "id": ",".join(chunk), "key": self.api_key}
            payload = self._get_json("/channels", params)
            if not payload["ok"]:
                return payload
            for item in payload["data"].get("items", []):
                snippet = item.get("snippet", {})
                stats = item.get("statistics", {})
                channel_id = item.get("id", "")
                items[channel_id] = {
                    "channel_id": channel_id,
                    "channel_title": snippet.get("title", ""),
                    "channel_description": snippet.get("description", ""),
                    "subscriber_count": self._to_int(stats.get("subscriberCount")),
                    "channel_view_count": self._to_int(stats.get("viewCount")),
                    "channel_video_count": self._to_int(stats.get("videoCount")),
                }
        return {"ok": True, "source": "youtube_channels", "items": items}

    def _comment_threads(self, video_ids: list[str], comments_per_video: int) -> dict[str, Any]:
        if comments_per_video <= 0:
            return {"ok": True, "source": "youtube_comments", "items": {}}
        items: dict[str, list[dict[str, Any]]] = {}
        errors = []
        for video_id in video_ids:
            params = {
                "part": "snippet",
                "videoId": video_id,
                "maxResults": max(1, min(comments_per_video, 20)),
                "order": "relevance",
                "textFormat": "plainText",
                "key": self.api_key,
            }
            payload = self._get_json("/commentThreads", params)
            if not payload["ok"]:
                errors.append(f"comments unavailable for {video_id}: {payload.get('error', 'unknown error')}")
                continue
            items[video_id] = []
            for item in payload["data"].get("items", []):
                snippet = item.get("snippet", {})
                top = snippet.get("topLevelComment", {}).get("snippet", {})
                text = top.get("textDisplay", "").strip()
                if text:
                    items[video_id].append(
                        {
                            "text": text,
                            "like_count": self._to_int(top.get("likeCount")),
                            "published_at": top.get("publishedAt", ""),
                            "reply_count": self._to_int(snippet.get("totalReplyCount")),
                        }
                    )
        return {"ok": True, "source": "youtube_comments", "items": items, "errors": errors}

    def _merge(
        self,
        search_items: list[dict[str, Any]],
        stats_items: dict[str, dict[str, Any]],
        channel_items: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        by_id = {item["video_id"]: dict(item) for item in search_items}
        videos = []
        for video_id, item in by_id.items():
            merged = {**item, **stats_items.get(video_id, {})}
            channel = channel_items.get(merged.get("channel_id", ""), {})
            view_count = merged.get("view_count", 0)
            published_at = merged.get("published_at", "")
            duration_seconds = merged.get("duration_seconds", 0)
            videos.append(
                {
                    **merged,
                    **channel,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "age_days": self._age_days(published_at),
                    "format_bucket": self._format_bucket(duration_seconds),
                    "views_per_day": self._views_per_day(view_count, published_at),
                    "engagement_rate": self._engagement_rate(
                        view_count,
                        merged.get("like_count", 0),
                        merged.get("comment_count", 0),
                    ),
                    "comments": [],
                }
            )
        return videos

    def _filter_videos(
        self,
        videos: list[dict[str, Any]],
        topic: str,
        manual_brief: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        kept = []
        rejected = []
        topic_terms = self._topic_terms(topic, manual_brief)
        include_terms = self._manual_list(manual_brief, "include_keywords")
        include_terms += self._manual_list(manual_brief, "must_include_keywords")
        exclude_terms = self._manual_list(manual_brief, "exclude_keywords")
        exclude_terms += self._manual_list(manual_brief, "hard_exclude_keywords")
        avoid_kids = manual_brief.get("avoid_kids_content", True)
        content_type = manual_brief.get("content_type", "both")
        language = manual_brief.get("language", "auto")

        for video in videos:
            full_text = self._video_text(video)
            score = 0
            reasons = []
            penalties = []
            rejected_reason = ""
            if any(term in full_text for term in exclude_terms):
                rejected_reason = "matched manual exclude keyword"
            elif include_terms and not any(term in full_text for term in include_terms):
                rejected_reason = "missing manual include keyword"
            elif not self._content_type_allowed(video, content_type):
                rejected_reason = f"video duration does not match content_type '{content_type}'"
            elif language == "english" and self._non_latin_ratio(video.get("title", "")) > 0.35:
                rejected_reason = "language filter is english but title appears mostly non-English"
            elif avoid_kids and video.get("made_for_kids"):
                rejected_reason = "made for kids"
            elif any(marker in full_text for marker in self.NOISE_MARKERS):
                penalties.append("contains common irrelevant-result marker")
                score -= 20

            for term in topic_terms:
                if term and term in video.get("title", "").lower():
                    score += 35
                elif term and term in full_text:
                    score += 15
            if video.get("tags"):
                score += 5
            if video.get("view_count", 0) > 0:
                score += 5
            if score < 20 and not rejected_reason:
                rejected_reason = "low topic relevance"

            video["relevance"] = {
                "score": max(0, min(score, 100)),
                "reasons": reasons,
                "penalties": penalties,
                "rejected": bool(rejected_reason),
            }
            if rejected_reason:
                rejected.append(
                    {
                        "video_id": video.get("video_id"),
                        "title": video.get("title", ""),
                        "reason": rejected_reason,
                        "score": video["relevance"]["score"],
                    }
                )
            else:
                kept.append(video)

        return kept, {
            "input_videos": len(videos),
            "kept_videos": len(kept),
            "rejected_videos": len(rejected),
            "rejected_examples": rejected[:10],
            "content_type": content_type,
            "language": language,
        }

    def _content_type_allowed(self, video: dict[str, Any], content_type: str) -> bool:
        duration_seconds = int(video.get("duration_seconds") or 0)
        if content_type == "both":
            return True
        if duration_seconds <= 0:
            return content_type == "both"
        if content_type == "shortform":
            return duration_seconds <= self.SHORTFORM_MAX_SECONDS
        if content_type == "midform":
            return self.SHORTFORM_MAX_SECONDS < duration_seconds <= self.MIDFORM_MAX_SECONDS
        if content_type == "longform":
            return duration_seconds >= self.LONGFORM_MIN_SECONDS
        if content_type == "scriptable":
            return duration_seconds >= self.SCRIPTABLE_MIN_SECONDS
        return True

    def _score_video(self, video: dict[str, Any]) -> dict[str, Any]:
        subscribers = video.get("subscriber_count", 0)
        views = video.get("view_count", 0)
        outlier_ratio = round(views / subscribers, 3) if subscribers else None
        video["outlier_ratio"] = outlier_ratio
        video["is_breakout"] = bool(video.get("views_per_day", 0) >= 1000 or (outlier_ratio or 0) >= 1.5)
        return video

    def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout_seconds, context=self.ssl_context) as response:
                return {"ok": True, "data": json.loads(response.read().decode("utf-8"))}
        except urllib.error.HTTPError as error:
            message = error.read().decode("utf-8", errors="replace")
            return {"ok": False, "source": "youtube", "error": f"HTTP {error.code}: {message}"}
        except (urllib.error.URLError, TimeoutError, ssl.SSLError, json.JSONDecodeError) as error:
            return {"ok": False, "source": "youtube", "error": str(error)}

    def _topic_terms(self, topic: str, manual_brief: dict[str, Any]) -> list[str]:
        raw_terms = [topic, *self._manual_list(manual_brief, "topic_context")]
        words = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9-]+", topic.lower())
        raw_terms.extend(word for word in words if len(word) > 2)
        return self._dedupe(term.lower().strip() for term in raw_terms if term)

    def _video_text(self, video: dict[str, Any]) -> str:
        return " ".join(
            [
                video.get("title", ""),
                video.get("description", ""),
                video.get("channel_title", ""),
                " ".join(video.get("tags", [])),
            ]
        ).lower()

    def _manual_list(self, manual_brief: dict[str, Any], key: str) -> list[str]:
        value = manual_brief.get(key, [])
        if isinstance(value, str):
            return [item.strip().lower() for item in re.split(r"[,;]", value) if item.strip()]
        if isinstance(value, list):
            return [str(item).strip().lower() for item in value if str(item).strip()]
        return []

    def _thumbnail_url(self, snippet: dict[str, Any]) -> str:
        thumbnails = snippet.get("thumbnails", {})
        for key in ("maxres", "high", "medium", "default"):
            if key in thumbnails:
                return thumbnails[key].get("url", "")
        return ""

    def _duration_seconds(self, duration: str) -> int:
        match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration or "")
        if not match:
            return 0
        hours, minutes, seconds = (int(part or 0) for part in match.groups())
        return hours * 3600 + minutes * 60 + seconds

    def _format_bucket(self, duration_seconds: int) -> str:
        if duration_seconds <= 0:
            return "unknown"
        if duration_seconds <= self.SHORTFORM_MAX_SECONDS:
            return "shortform"
        if duration_seconds <= self.MIDFORM_MAX_SECONDS:
            return "midform"
        return "longform"

    def _non_latin_ratio(self, text: str) -> float:
        letters = [char for char in text if char.isalpha()]
        if not letters:
            return 0
        non_latin = [
            char
            for char in letters
            if not ("a" <= char.lower() <= "z")
        ]
        return len(non_latin) / len(letters)

    def _age_days(self, published_at: str) -> int | None:
        if not published_at:
            return None
        try:
            published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        except ValueError:
            return None
        return max(1, (datetime.now(timezone.utc) - published).days)

    def _views_per_day(self, views: int, published_at: str) -> float:
        age_days = self._age_days(published_at)
        if not age_days:
            return 0
        return round(views / age_days, 2)

    def _engagement_rate(self, views: int, likes: int, comments: int) -> float:
        if not views:
            return 0
        return round((likes + comments) / views, 4)

    def _to_int(self, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _chunks(self, items: list[str], size: int) -> list[list[str]]:
        return [items[index : index + size] for index in range(0, len(items), size) if items[index : index + size]]

    def _dedupe(self, items: Any) -> list[str]:
        seen = set()
        result = []
        for item in items:
            if item and item not in seen:
                seen.add(item)
                result.append(item)
        return result
