import os
import unittest
from unittest.mock import patch

from youtube_agents.agents.idea_agent import IdeaAgent
from youtube_agents.core.llm import OllamaChatClient


class FakeLLMClient:
    def json_chat(self, system_prompt, user_prompt):
        return {
            "ok": True,
            "model": "fake-model",
            "data": {
                "ideas": [
                    {
                        "working_title": "The Walnut Claim Nobody Explains Clearly",
                        "niche_lane": "education",
                        "angle_type": "claims_vs_truth",
                        "viewer_promise": "Clarify the most confusing walnut health claim.",
                        "differentiation": "Uses a sharper LLM-created curiosity hook.",
                    }
                ]
            },
        }


class IdeaAgentSmokeTest(unittest.TestCase):
    def test_idea_agent_generates_scored_ideas(self):
        research = {
            "schema_version": "research.v1",
            "created_at": "2026-06-23T00:00:00",
            "input": {
                "topic": "walnuts",
                "audience": "health curious adults",
                "style": "documentary explainer",
            },
            "strong_fit_competitors": [
                {
                    "video_id": "vid1",
                    "title": "What Happens When You Eat Walnuts Every Day",
                    "views_per_day": 1000,
                    "competitor_fit": {"score": 82, "bucket": "strong_fit"},
                }
            ],
            "claims_to_verify": [
                {"claim_area": "health", "reason": "Verify health claims before scripting."}
            ],
        }
        strategy = {
            "schema_version": "strategy.v1",
            "created_at": "2026-06-23T00:00:00",
            "recommended_niche_lane": "education",
            "recommended_angle": "What Really Happens When You Eat Walnuts",
            "recommended_angle_type": "claims_vs_truth",
            "positioning": "Evidence-led health explainer.",
            "confidence": {"level": "high", "score": 0.85},
            "secondary_niche_lane": "goal_instruction",
            "key_evidence": [
                {
                    "type": "breakout_video",
                    "video_id": "vid1",
                    "title": "What Happens When You Eat Walnuts Every Day",
                    "views_per_day": 1000,
                    "reason": "Matched education keywords.",
                }
            ],
        }

        ideas = IdeaAgent().run(research, strategy, ideas_per_run=5, max_candidates=8)

        self.assertEqual(ideas["schema_version"], "ideas.v1")
        self.assertEqual(ideas["agent"], "IdeaAgent")
        self.assertEqual(len(ideas["ideas"]), 5)
        self.assertEqual(ideas["selected_idea"]["idea_id"], ideas["ideas"][0]["idea_id"])
        self.assertEqual(ideas["handoff_contract"]["next_agent"], "OutlineAgent")
        self.assertTrue(ideas["selected_idea"]["working_title"])
        self.assertIn("score", ideas["selected_idea"])
        self.assertNotIn("outline", ideas["selected_idea"])
        self.assertNotIn("script", ideas["selected_idea"])

    def test_idea_agent_can_use_llm_candidates(self):
        research = {
            "schema_version": "research.v1",
            "created_at": "2026-06-23T00:00:00",
            "input": {"topic": "walnuts", "audience": "health curious adults"},
            "strong_fit_competitors": [],
            "claims_to_verify": [],
        }
        strategy = {
            "schema_version": "strategy.v1",
            "created_at": "2026-06-23T00:00:00",
            "recommended_niche_lane": "education",
            "recommended_angle": "What Really Happens When You Eat Walnuts",
            "recommended_angle_type": "claims_vs_truth",
            "positioning": "Evidence-led health explainer.",
            "confidence": {"level": "medium", "score": 0.65},
            "secondary_niche_lane": None,
            "key_evidence": [],
        }

        ideas = IdeaAgent(llm_client=FakeLLMClient()).run(
            research,
            strategy,
            ideas_per_run=5,
            max_candidates=5,
            provider="openai",
        )

        self.assertEqual(ideas["generation"]["used_provider"], "openai")
        self.assertFalse(ideas["generation"]["fallback_used"])
        self.assertTrue(any("Nobody Explains" in idea["working_title"] for idea in ideas["ideas"]))

    def test_idea_agent_can_use_ollama_candidates(self):
        research = {
            "schema_version": "research.v1",
            "created_at": "2026-06-23T00:00:00",
            "input": {"topic": "walnuts", "audience": "health curious adults"},
            "strong_fit_competitors": [],
            "claims_to_verify": [],
        }
        strategy = {
            "schema_version": "strategy.v1",
            "created_at": "2026-06-23T00:00:00",
            "recommended_niche_lane": "education",
            "recommended_angle": "What Really Happens When You Eat Walnuts",
            "recommended_angle_type": "claims_vs_truth",
            "positioning": "Evidence-led health explainer.",
            "confidence": {"level": "medium", "score": 0.65},
            "secondary_niche_lane": None,
            "key_evidence": [],
        }

        ideas = IdeaAgent(llm_client=FakeLLMClient()).run(
            research,
            strategy,
            ideas_per_run=5,
            max_candidates=5,
            provider="ollama",
        )

        self.assertEqual(ideas["generation"]["used_provider"], "ollama")
        self.assertFalse(ideas["generation"]["fallback_used"])

    def test_ollama_client_uses_uncapped_defaults(self):
        keys = [
            "OLLAMA_IDEA_MODEL",
        ]
        clean_env = {key: value for key, value in os.environ.items() if key not in keys}
        with patch.dict(os.environ, clean_env, clear=True), patch("youtube_agents.core.llm.load_dotenv"):
            client = OllamaChatClient()

        self.assertEqual(client.model, "llama3.1")
        self.assertIsNone(client.timeout_seconds)


if __name__ == "__main__":
    unittest.main()
