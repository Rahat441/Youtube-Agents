import unittest

from youtube_agents.agents.strategy_agent import StrategyAgent


class StrategyAgentSmokeTest(unittest.TestCase):
    def test_strategy_agent_picks_education_from_health_research(self):
        research = {
            "schema_version": "research.v1",
            "created_at": "2026-06-23T00:00:00",
            "input": {
                "topic": "walnuts",
                "audience": "health curious adults",
                "style": "documentary explainer",
                "manual_brief": {
                    "topic_context": "nutrition health benefits eating walnuts science",
                    "content_type": "scriptable",
                    "language": "english",
                },
            },
            "market_stats": {
                "videos_collected": 3,
                "breakout_count": 2,
                "median_views_per_day": 800,
                "median_duration_seconds": 520,
                "format_counts": {"longform": 3},
            },
            "competitor_videos": [
                {
                    "video_id": "edu1",
                    "title": "What Happens When You Eat Walnuts Every Day",
                    "views_per_day": 1200,
                    "outlier_ratio": 2.0,
                    "is_breakout": True,
                    "query_matches": [
                        {"query": "what happens when you eat walnuts", "purpose": "consumption outcome framing"}
                    ],
                },
                {
                    "video_id": "edu2",
                    "title": "Walnuts Nutrition Facts Explained by Science",
                    "views_per_day": 900,
                    "outlier_ratio": 1.2,
                    "is_breakout": True,
                    "query_matches": [
                        {"query": "walnuts science", "purpose": "evidence and expert framing"},
                        {"query": "walnuts nutrition facts", "purpose": "nutrition evidence"},
                    ],
                },
                {
                    "video_id": "goal1",
                    "title": "Avoid These Walnut Mistakes",
                    "views_per_day": 200,
                    "outlier_ratio": 0.8,
                    "is_breakout": False,
                    "query_matches": [
                        {"query": "walnuts mistakes", "purpose": "viewer problems and confusion"}
                    ],
                },
            ],
            "strong_fit_competitors": [
                {
                    "video_id": "edu1",
                    "title": "What Happens When You Eat Walnuts Every Day",
                    "views_per_day": 1200,
                    "outlier_ratio": 2.0,
                    "is_breakout": True,
                    "competitor_fit": {"score": 88, "bucket": "strong_fit"},
                    "query_matches": [
                        {"query": "what happens when you eat walnuts", "purpose": "consumption outcome framing"}
                    ],
                },
                {
                    "video_id": "edu2",
                    "title": "Walnuts Nutrition Facts Explained by Science",
                    "views_per_day": 900,
                    "outlier_ratio": 1.2,
                    "is_breakout": True,
                    "competitor_fit": {"score": 82, "bucket": "strong_fit"},
                    "query_matches": [
                        {"query": "walnuts science", "purpose": "evidence and expert framing"},
                        {"query": "walnuts nutrition facts", "purpose": "nutrition evidence"},
                    ],
                },
            ],
            "adjacent_opportunity_videos": [],
            "off_context_outliers": [],
            "breakout_videos": [
                {
                    "video_id": "edu1",
                    "title": "What Happens When You Eat Walnuts Every Day",
                    "views_per_day": 1200,
                    "outlier_ratio": 2.0,
                    "is_breakout": True,
                },
                {
                    "video_id": "edu2",
                    "title": "Walnuts Nutrition Facts Explained by Science",
                    "views_per_day": 900,
                    "outlier_ratio": 1.2,
                    "is_breakout": True,
                },
            ],
            "title_patterns": [
                {"pattern": "plain topic explainer", "count": 2, "examples": ["What Happens When You Eat Walnuts Every Day"]},
                {"pattern": "mistakes framing", "count": 1, "examples": ["Avoid These Walnut Mistakes"]},
            ],
            "viewer_pains": [],
            "claims_to_verify": [
                {"claim_area": "health", "reason": "Verify health claims."}
            ],
            "source_errors": [],
        }

        strategy = StrategyAgent().run(research)

        self.assertEqual(strategy["schema_version"], "strategy.v1")
        self.assertEqual(strategy["agent"], "StrategyAgent")
        self.assertEqual(strategy["recommended_niche_lane"], "education")
        self.assertEqual(strategy["recommended_angle"], "What Really Happens When You Eat Walnuts")
        self.assertEqual(strategy["recommended_angle_type"], "claims_vs_truth")
        self.assertIn("Evidence-led", strategy["positioning"])
        self.assertIn(strategy["confidence"]["level"], {"low", "medium", "high"})
        self.assertTrue(strategy["key_evidence"])
        self.assertEqual(strategy["evidence_summary"]["strong_fit_count"], 2)
        self.assertEqual(strategy["handoff_contract"]["next_agent"], "IdeaAgent")
        self.assertGreater(strategy["lane_scores"][0]["score"], strategy["lane_scores"][1]["score"])


if __name__ == "__main__":
    unittest.main()
