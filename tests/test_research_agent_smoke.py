import unittest

from youtube_agents.agents.research_agent import ResearchAgent
from youtube_agents.sources.youtube_source import YouTubeDataSource


class FakeYouTubeSource:
    def available(self):
        return True

    def collect(self, topic, query_plan, max_results, max_queries, comments_per_video, manual_brief):
        return {
            "ok": True,
            "videos": [
                {
                    "video_id": "abc123",
                    "url": "https://www.youtube.com/watch?v=abc123",
                    "title": "Walnuts Explained: Benefits, Mistakes, and Myths",
                    "description": "A clean explainer about walnuts.",
                    "tags": ["walnuts", "nutrition"],
                    "duration": "PT8M10S",
                    "duration_seconds": 490,
                    "published_at": "2025-01-01T00:00:00Z",
                    "view_count": 250000,
                    "like_count": 9000,
                    "comment_count": 600,
                    "engagement_rate": 0.0384,
                    "views_per_day": 900,
                    "channel_id": "channel-1",
                    "channel_title": "Food Science",
                    "subscriber_count": 100000,
                    "outlier_ratio": 2.5,
                    "is_breakout": True,
                    "competitor_fit": {
                        "score": 82,
                        "bucket": "strong_fit",
                        "reasons": ["matches intended context terms: nutrition"],
                        "penalties": [],
                    },
                    "query_matches": [{"query": query_plan[0]["query"], "purpose": query_plan[0]["purpose"]}],
                    "comments": [
                        {"text": "How do I know how many walnuts are too many?", "like_count": 12}
                    ],
                }
            ],
            "relevance_filter": {"input_videos": 1, "kept_videos": 1, "rejected_videos": 0},
        }


class ResearchAgentSmokeTest(unittest.TestCase):
    def test_research_agent_smoke(self):
        agent = ResearchAgent(youtube_source=FakeYouTubeSource())
        result = agent.run(
            topic="walnuts",
            audience="health curious adults",
            style="documentary explainer",
            manual_brief={"topic_context": "nutrition", "include_keywords": ["omega 3"]},
        )

        self.assertEqual(result["schema_version"], "research.v1")
        self.assertEqual(result["agent"], "ResearchAgent")
        self.assertTrue(result["evidence_status"]["has_live_youtube_data"])
        self.assertEqual(result["market_stats"]["videos_collected"], 1)
        self.assertEqual(len(result["strong_fit_competitors"]), 1)
        self.assertEqual(result["breakout_videos"][0]["video_id"], "abc123")
        self.assertTrue(result["viewer_pains"])
        self.assertEqual(result["handoff_contract"]["next_agent"], "StrategyAgent")
        self.assertIn("recommended niche lane", result["handoff_contract"]["strategy_should_decide"])
        self.assertFalse(any("POV life as" in item["query"] for item in result["query_plan"]))
        self.assertTrue(any(item["query"] == "walnuts benefits" for item in result["query_plan"]))
        self.assertTrue(any(item["query"] == "walnuts side effects" for item in result["query_plan"]))

    def test_content_type_filters_short_videos_for_scriptable(self):
        source = YouTubeDataSource(api_key="fake-key")
        videos = [
            {
                "video_id": "short1",
                "title": "Walnuts benefits #shorts",
                "description": "Walnuts nutrition facts.",
                "tags": ["walnuts"],
                "duration_seconds": 45,
                "format_bucket": "shortform",
                "view_count": 1000,
                "made_for_kids": False,
            },
            {
                "video_id": "long1",
                "title": "Walnuts Benefits Explained",
                "description": "Walnuts nutrition facts.",
                "tags": ["walnuts"],
                "duration_seconds": 420,
                "format_bucket": "longform",
                "view_count": 1000,
                "made_for_kids": False,
            },
        ]

        kept, relevance_filter = source._filter_videos(
            videos,
            topic="walnuts",
            manual_brief={"content_type": "scriptable", "avoid_kids_content": True},
        )

        self.assertEqual([video["video_id"] for video in kept], ["long1"])
        self.assertEqual(relevance_filter["content_type"], "scriptable")
        self.assertEqual(relevance_filter["rejected_videos"], 1)

    def test_language_filter_rejects_non_english_titles(self):
        source = YouTubeDataSource(api_key="fake-key")
        videos = [
            {
                "video_id": "english1",
                "title": "Walnuts Benefits Explained",
                "description": "Walnuts nutrition facts.",
                "tags": ["walnuts"],
                "duration_seconds": 420,
                "format_bucket": "longform",
                "view_count": 1000,
                "made_for_kids": False,
            },
            {
                "video_id": "nonenglish1",
                "title": "अखरोट खाने से क्या होता है?",
                "description": "Walnuts nutrition facts.",
                "tags": ["walnuts"],
                "duration_seconds": 420,
                "format_bucket": "longform",
                "view_count": 1000,
                "made_for_kids": False,
            },
        ]

        kept, relevance_filter = source._filter_videos(
            videos,
            topic="walnuts",
            manual_brief={"language": "english", "content_type": "both", "avoid_kids_content": True},
        )

        self.assertEqual([video["video_id"] for video in kept], ["english1"])
        self.assertEqual(relevance_filter["language"], "english")
        self.assertEqual(relevance_filter["rejected_videos"], 1)

    def test_competitor_fit_preserves_off_context_outliers(self):
        source = YouTubeDataSource(api_key="fake-key")
        health_video = {
            "video_id": "health1",
            "title": "What Happens When You Eat Walnuts Every Day",
            "description": "Walnuts nutrition science and health benefits.",
            "tags": ["walnuts", "nutrition"],
            "view_count": 100000,
            "subscriber_count": 20000,
            "views_per_day": 800,
            "query_matches": [{"purpose": "nutrition evidence"}],
            "relevance": {"score": 65},
        }
        off_context_video = {
            "video_id": "game1",
            "title": "All 130 Golden Walnuts - Stardew Valley Guide",
            "description": "Gaming guide for golden walnuts.",
            "tags": ["stardew"],
            "view_count": 300000,
            "subscriber_count": 20000,
            "views_per_day": 1500,
            "query_matches": [{"purpose": "beginner search demand"}],
            "relevance": {"score": 40},
        }

        health_video = source._score_competitor_fit(
            source._score_video(health_video),
            topic="walnuts",
            manual_brief={"topic_context": "nutrition health benefits eating walnuts science"},
        )
        off_context_video = source._score_competitor_fit(
            source._score_video(off_context_video),
            topic="walnuts",
            manual_brief={"topic_context": "nutrition health benefits eating walnuts science"},
        )

        self.assertEqual(health_video["competitor_fit"]["bucket"], "strong_fit")
        self.assertEqual(off_context_video["competitor_fit"]["bucket"], "off_context_outlier")


if __name__ == "__main__":
    unittest.main()
