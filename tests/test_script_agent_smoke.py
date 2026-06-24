import socket
import unittest
from unittest.mock import patch

from youtube_agents.agents.script_agent import ScriptAgent
from youtube_agents.core.llm import OllamaChatClient


class FakeScriptLLMClient:
    def json_chat(self, system_prompt, user_prompt):
        full_script = " ".join(["This is a careful evidence-led script sentence."] * 35)
        return {
            "ok": True,
            "model": "fake-script-model",
            "data": {
                "working_title": "What Really Happens When You Eat Walnuts",
                "target_duration_minutes": 8,
                "estimated_word_count": 1080,
                "hook": "Most walnut videos make the promise sound simple, but the real answer needs nuance.",
                "intro": "Today we are separating popular walnut claims from what the evidence can actually support.",
                "body_sections": [
                    {
                        "heading": "Why the claim became popular",
                        "narration": "Walnut videos work because they connect a simple daily habit to a meaningful health promise.",
                        "evidence_used": ["Strong-fit competitor evidence showed daily walnut framing."],
                        "claims_to_verify": ["Verify the exact nutrition and health claim wording before final script."],
                    }
                ],
                "cta": "If you want the practical version, save this before changing your routine.",
                "full_script": full_script,
                "claims_used": ["Walnut videos commonly use daily habit framing."],
                "claims_to_verify": ["Verify any health outcome claims before publication."],
                "editor_notes": ["Add final source citations before recording."],
            },
        }


class FailingLLMClient:
    def json_chat(self, system_prompt, user_prompt):
        return {"ok": False, "model": "fake-script-model", "error": "Local model unavailable."}


class CapturingScriptAgent(ScriptAgent):
    def __init__(self):
        super().__init__()
        self.timeout_seconds = None

    def _llm_client(self, provider, model, timeout_seconds):
        self.timeout_seconds = timeout_seconds
        return FakeScriptLLMClient()


class ScriptAgentSmokeTest(unittest.TestCase):
    def test_script_agent_generates_script_json(self):
        script = ScriptAgent(llm_client=FakeScriptLLMClient()).run(
            research=self.research(),
            strategy=self.strategy(),
            ideas=self.ideas(),
            provider="ollama",
            model="fake-script-model",
            target_duration_minutes=8,
        )

        self.assertEqual(script["schema_version"], "script.v1")
        self.assertEqual(script["agent"], "ScriptAgent")
        self.assertEqual(script["status"], "complete")
        self.assertEqual(script["generation"]["used_provider"], "ollama")
        self.assertEqual(script["selected_idea_used"]["idea_id"], "idea_001")
        self.assertTrue(script["script"]["full_script"])
        self.assertTrue(script["source_evidence_used"])
        self.assertEqual(script["handoff_contract"]["next_agent"], "CritiqueAgent")

    def test_script_agent_fails_clearly_without_llm(self):
        script = ScriptAgent(llm_client=FailingLLMClient()).run(
            research=self.research(),
            strategy=self.strategy(),
            ideas=self.ideas(),
            provider="ollama",
        )

        self.assertEqual(script["status"], "failed")
        self.assertEqual(script["script"], {})
        self.assertIn("Local model unavailable.", script["generation"]["errors"])
        self.assertIn("Script generation failed", script["revision_notes"][0])

    def test_script_agent_passes_timeout_to_llm_client(self):
        agent = CapturingScriptAgent()
        script = agent.run(
            research=self.research(),
            strategy=self.strategy(),
            ideas=self.ideas(),
            provider="ollama",
            llm_timeout_seconds=123,
        )

        self.assertEqual(script["status"], "complete")
        self.assertEqual(agent.timeout_seconds, 123)
        self.assertEqual(script["input"]["llm_timeout_seconds"], 123)

    def test_ollama_socket_timeout_returns_error(self):
        with patch("youtube_agents.core.llm.load_dotenv"), patch(
            "youtube_agents.core.llm.urllib.request.urlopen",
            side_effect=socket.timeout("timed out"),
        ):
            response = OllamaChatClient(model="llama3.1", timeout_seconds=1).json_chat("system", "user")

        self.assertFalse(response["ok"])
        self.assertEqual(response["model"], "llama3.1")
        self.assertIn("timed out", response["error"])

    def research(self):
        return {
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
            "title_patterns": [{"pattern": "what happens", "count": 3}],
            "viewer_pains": [{"pain": "confusing health claims"}],
            "claims_to_verify": [{"claim_area": "health", "reason": "Verify health claims before scripting."}],
        }

    def strategy(self):
        return {
            "schema_version": "strategy.v1",
            "created_at": "2026-06-23T00:00:00",
            "recommended_niche_lane": "education",
            "recommended_angle": "What Really Happens When You Eat Walnuts",
            "recommended_angle_type": "claims_vs_truth",
            "positioning": "Evidence-led health explainer.",
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

    def ideas(self):
        return {
            "schema_version": "ideas.v1",
            "created_at": "2026-06-23T00:00:00",
            "selected_idea": {
                "idea_id": "idea_001",
                "working_title": "What Really Happens When You Eat Walnuts",
                "niche_lane": "education",
                "angle_type": "claims_vs_truth",
                "viewer_promise": "Separate supported benefits from exaggerated or risky claims.",
                "differentiation": "More balanced and evidence-led than sensational health claims.",
                "evidence_used": [{"source": "strategy_key_evidence", "video_id": "vid1"}],
                "risk_notes": ["Verify health claims before scripting."],
            },
        }


if __name__ == "__main__":
    unittest.main()
