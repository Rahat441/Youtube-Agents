"""IdeaAgent v1: generate scored video ideas from research and strategy."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from youtube_agents.core.llm import OllamaChatClient, OpenAIChatClient


class IdeaAgent:
    """Generate candidate video ideas without outlining or scripting."""

    DEFAULT_IDEAS_PER_RUN = 5
    DEFAULT_MAX_CANDIDATES = 12

    def __init__(self, llm_client: Any | None = None):
        self.llm_client = llm_client

    def run(
        self,
        research: dict[str, Any],
        strategy: dict[str, Any],
        ideas_per_run: int = DEFAULT_IDEAS_PER_RUN,
        max_candidates: int = DEFAULT_MAX_CANDIDATES,
        provider: str = "template",
        model: str | None = None,
    ) -> dict[str, Any]:
        if research.get("schema_version") != "research.v1":
            raise ValueError("IdeaAgent requires a research.v1 artifact")
        if strategy.get("schema_version") != "strategy.v1":
            raise ValueError("IdeaAgent requires a strategy.v1 artifact")

        ideas_per_run = max(1, ideas_per_run)
        max_candidates = max(ideas_per_run, max_candidates)
        candidates, generation = self._generate_candidates(research, strategy, provider, model, max_candidates)
        ideas = [self._build_idea(index + 1, candidate, research, strategy) for index, candidate in enumerate(candidates)]
        ideas.sort(key=lambda item: item["score"]["total"], reverse=True)
        selected_idea = ideas[0] if ideas else {}

        return {
            "schema_version": "ideas.v1",
            "agent": "IdeaAgent",
            "created_at": datetime.now().isoformat(),
            "input": {
                "topic": research.get("input", {}).get("topic", ""),
                "research_created_at": research.get("created_at"),
                "strategy_created_at": strategy.get("created_at"),
                "ideas_per_run": ideas_per_run,
                "max_candidates": max_candidates,
                "provider": provider,
                "model": model,
            },
            "strategy_used": {
                "recommended_niche_lane": strategy.get("recommended_niche_lane", ""),
                "recommended_angle": strategy.get("recommended_angle", ""),
                "recommended_angle_type": strategy.get("recommended_angle_type", ""),
                "positioning": strategy.get("positioning", ""),
                "confidence": strategy.get("confidence", {}),
            },
            "generation": generation,
            "ideas": ideas[:ideas_per_run],
            "selected_idea": selected_idea,
            "handoff_contract": {
                "next_agent": "OutlineAgent",
                "outline_agent_should_use": [
                    "selected_idea.working_title",
                    "selected_idea.niche_lane",
                    "selected_idea.angle_type",
                    "selected_idea.viewer_promise",
                    "selected_idea.evidence_used",
                    "selected_idea.risk_notes",
                ],
                "idea_agent_must_not_decide": [
                    "full outline",
                    "script",
                    "thumbnail package",
                    "final edited title",
                ],
            },
        }

    def _generate_candidates(
        self,
        research: dict[str, Any],
        strategy: dict[str, Any],
        provider: str,
        model: str | None,
        max_candidates: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        template_candidates = self._candidate_templates(research, strategy)
        if provider == "template":
            return template_candidates[:max_candidates], {
                "requested_provider": "template",
                "used_provider": "template",
                "fallback_used": False,
                "errors": [],
            }
        if provider not in {"openai", "ollama"}:
            return template_candidates[:max_candidates], {
                "requested_provider": provider,
                "used_provider": "template",
                "fallback_used": True,
                "errors": [f"Unknown idea provider '{provider}'."],
            }

        client = self.llm_client or self._llm_client(provider, model)
        response = client.json_chat(
            system_prompt=self._llm_system_prompt(),
            user_prompt=self._llm_user_prompt(research, strategy, max_candidates),
        )
        if not response.get("ok"):
            return template_candidates[:max_candidates], {
                "requested_provider": provider,
                "used_provider": "template",
                "model": response.get("model") or model,
                "fallback_used": True,
                "errors": [response.get("error", "Unknown LLM error.")],
            }

        llm_candidates = self._normalize_llm_candidates(response.get("data", {}))
        if not llm_candidates:
            return template_candidates[:max_candidates], {
                "requested_provider": provider,
                "used_provider": "template",
                "model": response.get("model") or model,
                "fallback_used": True,
                "errors": ["LLM response did not include valid idea candidates."],
            }
        merged = self._dedupe_candidates(llm_candidates + template_candidates)
        return merged[:max_candidates], {
            "requested_provider": provider,
            "used_provider": provider,
            "model": response.get("model") or model,
            "fallback_used": False,
            "errors": [],
        }

    def _llm_client(self, provider: str, model: str | None) -> Any:
        if provider == "ollama":
            return OllamaChatClient(model=model)
        return OpenAIChatClient(model=model)

    def _llm_system_prompt(self) -> str:
        return (
            "You generate YouTube video idea candidates from structured research and strategy. "
            "Return strict JSON only. Do not write outlines, scripts, thumbnails, or final titles."
        )

    def _llm_user_prompt(self, research: dict[str, Any], strategy: dict[str, Any], max_candidates: int) -> str:
        topic = research.get("input", {}).get("topic", "")
        audience = research.get("input", {}).get("audience", "")
        compact = {
            "topic": topic,
            "audience": audience,
            "strategy": {
                "recommended_niche_lane": strategy.get("recommended_niche_lane"),
                "recommended_angle": strategy.get("recommended_angle"),
                "recommended_angle_type": strategy.get("recommended_angle_type"),
                "positioning": strategy.get("positioning"),
                "secondary_niche_lane": strategy.get("secondary_niche_lane"),
                "confidence": strategy.get("confidence"),
            },
            "key_evidence": strategy.get("key_evidence", [])[:6],
            "strong_fit_competitors": [
                {
                    "title": video.get("title"),
                    "views_per_day": video.get("views_per_day"),
                    "fit_score": video.get("competitor_fit", {}).get("score"),
                }
                for video in research.get("strong_fit_competitors", [])[:6]
            ],
            "claims_to_verify": research.get("claims_to_verify", [])[:5],
        }
        return (
            f"Generate up to {max_candidates} candidate YouTube video ideas. "
            "Each candidate must include working_title, niche_lane, angle_type, "
            "viewer_promise, and differentiation. Return JSON in this shape: "
            '{"ideas":[{"working_title":"...","niche_lane":"...","angle_type":"...",'
            '"viewer_promise":"...","differentiation":"..."}]}\n\n'
            f"Evidence:\n{compact}"
        )

    def _normalize_llm_candidates(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        raw_ideas = data.get("ideas", [])
        if not isinstance(raw_ideas, list):
            return []
        candidates = []
        for item in raw_ideas:
            if not isinstance(item, dict):
                continue
            candidate = {
                "working_title": str(item.get("working_title", "")).strip(),
                "niche_lane": str(item.get("niche_lane", "")).strip() or "education",
                "angle_type": str(item.get("angle_type", "")).strip() or "custom_llm_angle",
                "viewer_promise": str(item.get("viewer_promise", "")).strip(),
                "differentiation": str(item.get("differentiation", "")).strip(),
            }
            if candidate["working_title"] and candidate["viewer_promise"] and candidate["differentiation"]:
                candidates.append(candidate)
        return candidates

    def _candidate_templates(self, research: dict[str, Any], strategy: dict[str, Any]) -> list[dict[str, Any]]:
        topic = research.get("input", {}).get("topic", "this topic")
        topic_title = self._title_case_topic(topic)
        lane = strategy.get("recommended_niche_lane", "education")
        angle_type = strategy.get("recommended_angle_type", "what_happens")
        secondary_lane = strategy.get("secondary_niche_lane")
        candidates: list[dict[str, Any]] = []

        if angle_type == "claims_vs_truth":
            candidates.extend(
                [
                    {
                        "working_title": f"What Really Happens When You Eat {topic_title}",
                        "angle_type": "claims_vs_truth",
                        "niche_lane": lane,
                        "viewer_promise": "Separate supported benefits from exaggerated or risky claims.",
                        "differentiation": "More balanced and evidence-led than sensational health claims.",
                    },
                    {
                        "working_title": f"{topic_title}: What Science Says vs What YouTube Claims",
                        "angle_type": "claims_vs_truth",
                        "niche_lane": lane,
                        "viewer_promise": "Show viewers which popular claims deserve trust and which need caution.",
                        "differentiation": "Turns market hype into a clear claim-by-claim breakdown.",
                    },
                    {
                        "working_title": f"The Truth About {topic_title}: Benefits, Risks, and Myths",
                        "angle_type": "benefits_risks_myths",
                        "niche_lane": lane,
                        "viewer_promise": "Give a complete, less one-sided view of the topic.",
                        "differentiation": "Combines benefit, risk, and myth framing in one package.",
                    },
                    {
                        "working_title": f"What Changes After 30 Days of {topic_title}?",
                        "angle_type": "time_bound_outcome",
                        "niche_lane": lane,
                        "viewer_promise": "Clarify what might change, what probably will not, and what is overpromised.",
                        "differentiation": "Uses a familiar 30-day hook with stronger caution language.",
                    },
                ]
            )
        elif angle_type == "mistakes_to_avoid":
            candidates.extend(
                [
                    {
                        "working_title": f"The Biggest {topic_title} Mistakes Viewers Keep Falling For",
                        "angle_type": "mistakes_to_avoid",
                        "niche_lane": lane,
                        "viewer_promise": "Help viewers avoid common mistakes and understand the safer path.",
                        "differentiation": "Practical and corrective rather than just informational.",
                    },
                    {
                        "working_title": f"Before You Try {topic_title}, Avoid These Mistakes",
                        "angle_type": "before_you_try",
                        "niche_lane": lane,
                        "viewer_promise": "Give viewers a clear warning checklist before taking action.",
                        "differentiation": "Packages risk control as practical viewer protection.",
                    },
                ]
            )
        elif angle_type == "comparison":
            candidates.extend(
                [
                    {
                        "working_title": f"{topic_title} Compared: What Is Actually Worth Choosing",
                        "angle_type": "comparison",
                        "niche_lane": lane,
                        "viewer_promise": "Compare the topic against nearby alternatives with clear tradeoffs.",
                        "differentiation": "Decision-focused rather than generic overview.",
                    }
                ]
            )
        elif angle_type == "surprising_truth":
            candidates.extend(
                [
                    {
                        "working_title": f"The Surprising Truth About {topic_title}",
                        "angle_type": "surprising_truth",
                        "niche_lane": lane,
                        "viewer_promise": "Reveal what viewers misunderstand while staying grounded in evidence.",
                        "differentiation": "Curiosity packaging with guardrails.",
                    }
                ]
            )

        candidates.extend(self._secondary_candidates(topic_title, lane, secondary_lane))
        return self._dedupe_candidates(candidates)

    def _secondary_candidates(self, topic_title: str, lane: str, secondary_lane: str | None) -> list[dict[str, Any]]:
        candidates = [
            {
                "working_title": f"Why {topic_title} Became So Overhyped",
                "angle_type": "hype_check",
                "niche_lane": "random_curiosity" if lane != "random_curiosity" else lane,
                "viewer_promise": "Explain why the topic gets attention and what viewers should believe.",
                "differentiation": "Uses curiosity without letting hype dominate the facts.",
            },
            {
                "working_title": f"{topic_title} Benefits People Get Wrong",
                "angle_type": "misconceptions",
                "niche_lane": lane,
                "viewer_promise": "Correct common misunderstandings from popular videos.",
                "differentiation": "Targets misconceptions instead of repeating generic facts.",
            },
        ]
        if secondary_lane == "goal_instruction":
            candidates.append(
                {
                    "working_title": f"How To Use {topic_title} Without Falling For Bad Advice",
                    "angle_type": "safe_practical_guide",
                    "niche_lane": "goal_instruction",
                    "viewer_promise": "Turn the strategy into a practical guide with warnings.",
                    "differentiation": "Bridges education and practical instruction.",
                }
            )
        return candidates

    def _build_idea(
        self,
        index: int,
        candidate: dict[str, Any],
        research: dict[str, Any],
        strategy: dict[str, Any],
    ) -> dict[str, Any]:
        evidence = self._evidence_used(research, strategy)
        risk_notes = self._risk_notes(research)
        score = self._score_idea(candidate, research, strategy, evidence, risk_notes)
        return {
            "idea_id": f"idea_{index:03d}",
            "working_title": candidate["working_title"],
            "niche_lane": candidate["niche_lane"],
            "angle_type": candidate["angle_type"],
            "viewer_promise": candidate["viewer_promise"],
            "why_it_can_work": self._why_it_can_work(candidate, research, strategy),
            "evidence_used": evidence,
            "differentiation": candidate["differentiation"],
            "risk_notes": risk_notes,
            "score": score,
        }

    def _score_idea(
        self,
        candidate: dict[str, Any],
        research: dict[str, Any],
        strategy: dict[str, Any],
        evidence: list[dict[str, Any]],
        risk_notes: list[str],
    ) -> dict[str, Any]:
        strategy_fit = 25 if candidate["niche_lane"] == strategy.get("recommended_niche_lane") else 17
        if candidate["angle_type"] == strategy.get("recommended_angle_type"):
            strategy_fit += 5
        strategy_fit = min(30, strategy_fit)

        evidence_support = min(20, 8 + len(evidence) * 3)
        click_potential = self._click_potential(candidate["working_title"])
        differentiation = 13 if candidate.get("differentiation") else 8
        feasibility = 10
        audience_fit = 10 if research.get("input", {}).get("audience") else 7
        risk_penalty = -min(12, len(risk_notes) * 3)
        total = max(
            0,
            min(
                100,
                strategy_fit
                + evidence_support
                + click_potential
                + differentiation
                + feasibility
                + audience_fit
                + risk_penalty,
            ),
        )
        return {
            "total": round(total, 2),
            "strategy_fit": strategy_fit,
            "evidence_support": evidence_support,
            "click_potential": click_potential,
            "differentiation": differentiation,
            "feasibility": feasibility,
            "audience_fit": audience_fit,
            "risk_penalty": risk_penalty,
        }

    def _click_potential(self, title: str) -> int:
        lowered = title.lower()
        score = 10
        if any(term in lowered for term in ("what really", "truth", "mistakes", "before", "wrong")):
            score += 5
        if any(term in lowered for term in ("30 days", "science", "claims", "benefits", "risks")):
            score += 3
        if len(title) <= 72:
            score += 2
        return min(20, score)

    def _why_it_can_work(
        self,
        candidate: dict[str, Any],
        research: dict[str, Any],
        strategy: dict[str, Any],
    ) -> list[str]:
        reasons = []
        if candidate["niche_lane"] == strategy.get("recommended_niche_lane"):
            reasons.append("Matches the recommended strategy lane.")
        if candidate["angle_type"] == strategy.get("recommended_angle_type"):
            reasons.append("Uses the recommended angle type.")
        if research.get("strong_fit_competitors"):
            reasons.append("Supported by strong-fit competitor evidence.")
        if strategy.get("confidence", {}).get("level"):
            reasons.append(f"Strategy confidence is {strategy['confidence']['level']}.")
        if research.get("claims_to_verify"):
            reasons.append("Acknowledges claims that need verification before scripting.")
        return reasons

    def _evidence_used(self, research: dict[str, Any], strategy: dict[str, Any]) -> list[dict[str, Any]]:
        evidence = []
        for item in strategy.get("key_evidence", [])[:4]:
            evidence.append({"source": "strategy_key_evidence", **item})
        for video in research.get("strong_fit_competitors", [])[:3]:
            evidence.append(
                {
                    "source": "strong_fit_competitor",
                    "video_id": video.get("video_id"),
                    "title": video.get("title", ""),
                    "views_per_day": video.get("views_per_day", 0),
                    "fit_score": video.get("competitor_fit", {}).get("score"),
                }
            )
        return evidence[:6]

    def _risk_notes(self, research: dict[str, Any]) -> list[str]:
        return [
            item.get("reason", "")
            for item in research.get("claims_to_verify", [])
            if item.get("reason")
        ][:5]

    def _title_case_topic(self, topic: str) -> str:
        small_words = {"and", "as", "for", "in", "of", "on", "or", "the", "to", "vs", "with"}
        words = topic.strip().split()
        titled = []
        for index, word in enumerate(words):
            lowered = word.lower()
            if index > 0 and lowered in small_words:
                titled.append(lowered)
            else:
                titled.append(word[:1].upper() + word[1:])
        return " ".join(titled) or "This Topic"

    def _dedupe_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen = set()
        deduped = []
        for candidate in candidates:
            key = re.sub(r"\W+", "", candidate["working_title"].lower())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)
        return deduped
