"""StrategyAgent v1: choose a niche lane and angle from research evidence."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import Any


class StrategyAgent:
    """Interpret ResearchAgent output without generating full video ideas."""

    LANES = {
        "education": {
            "label": "Education / Explainer",
            "description": "Evidence-led explanation of the topic, claims, mechanisms, and tradeoffs.",
            "keywords": {
                "benefit",
                "benefits",
                "body",
                "explained",
                "facts",
                "health",
                "nutrition",
                "science",
                "truth",
                "what happens",
                "why",
            },
            "patterns": {"plain topic explainer", "why framing", "truth/myth framing", "number/list title"},
            "query_purposes": {
                "educational demand",
                "positive claims and demand",
                "risk objections and caveats",
                "misconceptions and claims to verify",
                "outcome-driven framing",
                "evidence and expert framing",
                "nutrition evidence",
                "health caveats and safety claims",
                "consumption outcome framing",
            },
        },
        "goal_instruction": {
            "label": "Goal Instruction",
            "description": "Practical guidance that helps viewers avoid mistakes or achieve a specific outcome.",
            "keywords": {
                "avoid",
                "beginner",
                "guide",
                "how to",
                "mistake",
                "mistakes",
                "right way",
                "steps",
                "tips",
            },
            "patterns": {"how-to framing", "mistakes framing", "number/list title"},
            "query_purposes": {"beginner search demand", "viewer problems and confusion"},
        },
        "review_comparison": {
            "label": "Review / Comparison",
            "description": "Compare options, evaluate tradeoffs, or answer whether something is worth it.",
            "keywords": {"best", "better", "comparison", "review", "versus", "vs", "worth it"},
            "patterns": {"number/list title"},
            "query_purposes": {"purchase-intent evidence", "comparison demand", "product or tech objections"},
        },
        "random_curiosity": {
            "label": "Random Curiosity",
            "description": "Curiosity-first packaging around surprises, myths, weird facts, or hidden history.",
            "keywords": {
                "hidden",
                "myth",
                "secret",
                "shocking",
                "surprising",
                "truth",
                "weird",
                "won't believe",
            },
            "patterns": {"truth/myth framing", "why framing", "number/list title"},
            "query_purposes": {"misconceptions and claims to verify", "outcome-driven framing"},
        },
        "pov_life_as": {
            "label": "POV / Life As",
            "description": "Story or identity-led simulation of living as, becoming, or experiencing the topic.",
            "keywords": {"day in the life", "life as", "pov", "story", "survived"},
            "patterns": set(),
            "query_purposes": set(),
        },
    }

    RISKY_CLAIM_AREAS = {"health", "diet", "medical", "supplement", "finance", "invest", "legal", "law"}

    def run(self, research: dict[str, Any]) -> dict[str, Any]:
        if research.get("schema_version") != "research.v1":
            raise ValueError("StrategyAgent requires a research.v1 artifact")

        lane_scores = [self._score_lane(lane, config, research) for lane, config in self.LANES.items()]
        lane_scores.sort(key=lambda item: item["score"], reverse=True)
        recommended = lane_scores[0]
        secondary = lane_scores[1] if len(lane_scores) > 1 else None
        angle_candidates = self._angle_candidates(recommended["lane"], research)
        primary_angle = angle_candidates[0] if angle_candidates else {}
        confidence = self._confidence(lane_scores, research)
        key_evidence = self._key_evidence(recommended, research)

        return {
            "schema_version": "strategy.v1",
            "agent": "StrategyAgent",
            "created_at": datetime.now().isoformat(),
            "input": {
                "research_schema_version": research.get("schema_version"),
                "research_created_at": research.get("created_at"),
                "topic": research.get("input", {}).get("topic", ""),
                "audience": research.get("input", {}).get("audience", ""),
                "style": research.get("input", {}).get("style", ""),
                "manual_brief": research.get("input", {}).get("manual_brief", {}),
            },
            "evidence_summary": self._evidence_summary(research),
            "recommended_niche_lane": recommended["lane"],
            "recommended_niche_label": recommended["label"],
            "recommended_angle": primary_angle.get("angle", ""),
            "recommended_angle_type": primary_angle.get("angle_type", ""),
            "positioning": primary_angle.get("positioning", ""),
            "confidence": confidence,
            "key_evidence": key_evidence,
            "secondary_niche_lane": secondary["lane"] if secondary else None,
            "lane_scores": lane_scores,
            "angle_candidates": angle_candidates,
            "strategy_notes": self._strategy_notes(recommended, research),
            "handoff_contract": {
                "next_agent": "IdeaAgent",
                "idea_agent_should_use": [
                    "recommended_niche_lane",
                    "recommended_angle",
                    "recommended_angle_type",
                    "positioning",
                    "confidence",
                    "key_evidence",
                    "lane_scores",
                    "angle_candidates",
                    "evidence_summary",
                ],
                "strategy_agent_must_not_decide": [
                    "final title",
                    "script premise details",
                    "thumbnail package",
                ],
            },
        }

    def _score_lane(self, lane: str, config: dict[str, Any], research: dict[str, Any]) -> dict[str, Any]:
        videos = self._primary_strategy_videos(research)
        breakout_videos = [video for video in videos if video.get("is_breakout")]
        if not breakout_videos:
            breakout_videos = research.get("breakout_videos", [])
        title_patterns = self._title_patterns_from_videos(videos) if videos else research.get("title_patterns", [])
        claims = research.get("claims_to_verify", [])
        input_data = research.get("input", {})

        query_score, query_evidence = self._query_score(config, videos, breakout_videos)
        title_score, title_evidence = self._title_score(config, title_patterns)
        breakout_score, breakout_evidence = self._breakout_score(config, breakout_videos)
        audience_score, audience_evidence = self._audience_score(lane, input_data)
        risk_score, risk_evidence = self._risk_score(lane, claims)
        saturation_penalty, saturation_evidence = self._saturation_penalty(config, title_patterns, videos)

        components = {
            "query_score": query_score,
            "title_pattern_score": title_score,
            "breakout_score": breakout_score,
            "audience_fit_score": audience_score,
            "risk_fit_score": risk_score,
            "saturation_penalty": saturation_penalty,
        }
        score = max(0, min(100, round(sum(components.values()), 2)))
        evidence = query_evidence + title_evidence + breakout_evidence + audience_evidence + risk_evidence
        if saturation_evidence:
            evidence.extend(saturation_evidence)

        return {
            "lane": lane,
            "label": config["label"],
            "score": score,
            "components": components,
            "rationale": self._rationale(lane, score, evidence, saturation_penalty),
            "evidence": evidence[:10],
        }

    def _query_score(
        self,
        config: dict[str, Any],
        videos: list[dict[str, Any]],
        breakout_videos: list[dict[str, Any]],
    ) -> tuple[float, list[dict[str, Any]]]:
        purposes = config["query_purposes"]
        if not purposes:
            return 0, []
        breakout_ids = {video.get("video_id") for video in breakout_videos}
        score = 0.0
        matched: Counter[str] = Counter()
        for video in videos:
            weight = 2.0 if video.get("video_id") in breakout_ids or video.get("is_breakout") else 1.0
            for match in video.get("query_matches", []) or []:
                purpose = match.get("purpose", "")
                if purpose in purposes:
                    score += weight
                    matched[purpose] += 1
        evidence = [
            {"type": "query_purpose", "value": purpose, "count": count}
            for purpose, count in matched.most_common(4)
        ]
        return min(25, score * 1.25), evidence

    def _title_score(
        self,
        config: dict[str, Any],
        title_patterns: list[dict[str, Any]],
    ) -> tuple[float, list[dict[str, Any]]]:
        score = 0.0
        evidence = []
        for pattern in title_patterns:
            name = pattern.get("pattern", "")
            count = int(pattern.get("count") or 0)
            if name in config["patterns"]:
                score += min(8, count * 1.25)
                evidence.append(
                    {
                        "type": "title_pattern",
                        "value": name,
                        "count": count,
                        "examples": pattern.get("examples", [])[:2],
                    }
                )
        return min(20, score), evidence[:4]

    def _breakout_score(
        self,
        config: dict[str, Any],
        breakout_videos: list[dict[str, Any]],
    ) -> tuple[float, list[dict[str, Any]]]:
        keywords = config["keywords"]
        score = 0.0
        evidence = []
        for video in breakout_videos[:12]:
            title = video.get("title", "")
            text = title.lower()
            matched = sorted(keyword for keyword in keywords if keyword in text)
            if matched:
                velocity = float(video.get("views_per_day") or 0)
                score += 2.5 + min(2.5, velocity / 1500)
                evidence.append(
                    {
                        "type": "breakout_video",
                        "title": title,
                        "video_id": video.get("video_id"),
                        "matched_keywords": matched[:4],
                        "views_per_day": video.get("views_per_day", 0),
                        "outlier_ratio": video.get("outlier_ratio"),
                    }
                )
        return min(25, score), evidence[:4]

    def _audience_score(self, lane: str, input_data: dict[str, Any]) -> tuple[float, list[dict[str, Any]]]:
        audience = input_data.get("audience", "").lower()
        style = input_data.get("style", "").lower()
        context = input_data.get("manual_brief", {}).get("topic_context", "").lower()
        combined = f"{audience} {style} {context}"
        score = 6.0
        reasons = []

        if lane == "education" and any(term in combined for term in ("health", "curious", "science", "documentary", "explainer")):
            score += 9
            reasons.append("audience/style/context favor evidence-led explanation")
        elif lane == "goal_instruction" and any(term in combined for term in ("beginner", "mistake", "how", "guide", "tips")):
            score += 8
            reasons.append("audience/style/context favor practical instruction")
        elif lane == "review_comparison" and any(term in combined for term in ("best", "review", "compare", "comparison", "worth")):
            score += 8
            reasons.append("audience/style/context favor comparison")
        elif lane == "random_curiosity" and any(term in combined for term in ("curious", "surprising", "mystery", "weird")):
            score += 6
            reasons.append("audience/style/context favor curiosity packaging")
        elif lane == "pov_life_as" and any(term in combined for term in ("story", "pov", "simulation")):
            score += 8
            reasons.append("audience/style/context favor POV/story format")

        evidence = [{"type": "audience_fit", "reason": reason} for reason in reasons]
        return min(15, score), evidence

    def _risk_score(self, lane: str, claims: list[dict[str, Any]]) -> tuple[float, list[dict[str, Any]]]:
        claim_areas = {str(item.get("claim_area", "")).lower() for item in claims}
        risky = bool(claim_areas & self.RISKY_CLAIM_AREAS)
        if not risky:
            return 7, []
        if lane == "education":
            return 10, [{"type": "risk_fit", "reason": "risky claims favor an evidence-led explainer lane"}]
        if lane == "goal_instruction":
            return 7, [{"type": "risk_fit", "reason": "practical advice can work if claims are carefully verified"}]
        if lane == "random_curiosity":
            return 3, [{"type": "risk_fit", "reason": "curiosity packaging can overstate risky claims"}]
        return 5, [{"type": "risk_fit", "reason": "claims require verification before downstream scripting"}]

    def _saturation_penalty(
        self,
        config: dict[str, Any],
        title_patterns: list[dict[str, Any]],
        videos: list[dict[str, Any]],
    ) -> tuple[float, list[dict[str, Any]]]:
        if not videos:
            return 0, []
        matching_count = 0
        for pattern in title_patterns:
            if pattern.get("pattern") in config["patterns"]:
                matching_count += int(pattern.get("count") or 0)
        ratio = matching_count / len(videos)
        if ratio < 0.45:
            return 0, []
        penalty = -min(10, round((ratio - 0.45) * 20, 2))
        return penalty, [{"type": "saturation", "reason": f"{round(ratio * 100, 1)}% of titles match this lane's common patterns"}]

    def _angle_candidates(self, lane: str, research: dict[str, Any]) -> list[dict[str, Any]]:
        topic = research.get("input", {}).get("topic", "this topic")
        topic_title = self._title_case_topic(topic)
        claims = {item.get("claim_area", "") for item in research.get("claims_to_verify", [])}
        top_patterns = [item.get("pattern", "") for item in research.get("title_patterns", [])[:3]]
        pains = research.get("viewer_pains", [])

        if lane == "education":
            angle = f"What Really Happens When You Eat {topic_title}"
            angle_type = "claims_vs_truth" if claims else "what_happens"
            positioning = "Evidence-led explainer that separates supported benefits from exaggerated or risky claims."
            if claims:
                positioning = "Evidence-led health explainer that clarifies what is supported, what is uncertain, and what needs caution."
        elif lane == "goal_instruction":
            angle = f"The Biggest {topic_title} Mistakes Viewers Keep Falling For"
            angle_type = "mistakes_to_avoid"
            positioning = "Practical guidance built around common viewer confusion and avoidable mistakes."
        elif lane == "review_comparison":
            angle = f"{topic_title} Compared: What Is Actually Worth Choosing"
            angle_type = "comparison"
            positioning = "Comparison-led strategy that weighs tradeoffs against nearby alternatives."
        elif lane == "random_curiosity":
            angle = f"The Surprising Truth About {topic_title}"
            angle_type = "surprising_truth"
            positioning = "Curiosity-led packaging that still needs evidence guardrails."
        else:
            angle = f"POV: The Hidden World of {topic_title}"
            angle_type = "pov_story"
            positioning = "Story-led framing if later evidence supports a POV format."

        candidates = [
            {
                "angle": angle,
                "angle_type": angle_type,
                "lane": lane,
                "positioning": positioning,
                "why_this_angle": self._angle_reason(lane, top_patterns, bool(pains), bool(claims)),
            }
        ]
        if lane != "goal_instruction" and any("mistakes" in pattern for pattern in top_patterns):
            candidates.append(
                {
                    "angle": f"The Biggest {topic_title} Mistakes Viewers Keep Falling For",
                    "angle_type": "mistakes_to_avoid",
                    "lane": "goal_instruction",
                    "positioning": "Secondary practical angle because mistakes framing appears strongly in the market.",
                    "why_this_angle": "Mistakes framing appears in the strongest title-pattern evidence.",
                }
            )
        return candidates

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

    def _confidence(self, lane_scores: list[dict[str, Any]], research: dict[str, Any]) -> dict[str, Any]:
        top_score = lane_scores[0]["score"] if lane_scores else 0
        second_score = lane_scores[1]["score"] if len(lane_scores) > 1 else 0
        gap = max(0, top_score - second_score)
        market = research.get("market_stats", {})
        videos = int(market.get("videos_collected") or len(research.get("competitor_videos", [])))
        breakouts = int(market.get("breakout_count") or len(research.get("breakout_videos", [])))
        source_errors = research.get("source_errors", [])
        has_live_data = bool(research.get("evidence_status", {}).get("has_live_youtube_data", videos > 0))

        score = 0.35
        reasons = []
        if gap >= 18:
            score += 0.25
            reasons.append("top lane has a strong lead over the second lane")
        elif gap >= 8:
            score += 0.15
            reasons.append("top lane has a moderate lead over the second lane")
        else:
            score += 0.05
            reasons.append("top two lanes are close, so confidence is limited")

        if videos >= 40:
            score += 0.2
            reasons.append("research includes a healthy competitor sample")
        elif videos >= 15:
            score += 0.12
            reasons.append("research includes a usable competitor sample")
        else:
            reasons.append("research has a small competitor sample")

        if breakouts >= 8:
            score += 0.15
            reasons.append("multiple breakout videos support the read")
        elif breakouts >= 3:
            score += 0.08
            reasons.append("some breakout videos support the read")

        if source_errors:
            score -= 0.15
            reasons.append("source errors reduce confidence")
        if not has_live_data:
            score -= 0.25
            reasons.append("no live YouTube evidence was available")

        score = max(0, min(1, round(score, 2)))
        if score >= 0.78:
            level = "high"
        elif score >= 0.55:
            level = "medium"
        else:
            level = "low"
        return {
            "level": level,
            "score": score,
            "top_lane_score": top_score,
            "second_lane_score": second_score,
            "score_gap": round(gap, 2),
            "reasons": reasons,
        }

    def _key_evidence(self, recommended: dict[str, Any], research: dict[str, Any]) -> list[dict[str, Any]]:
        evidence = []
        seen_video_ids = set()
        for item in recommended.get("evidence", []):
            if item.get("type") == "breakout_video":
                video_id = item.get("video_id")
                if video_id in seen_video_ids:
                    continue
                seen_video_ids.add(video_id)
                evidence.append(
                    {
                        "type": "breakout_video",
                        "video_id": video_id,
                        "title": item.get("title", ""),
                        "views_per_day": item.get("views_per_day", 0),
                        "outlier_ratio": item.get("outlier_ratio"),
                        "reason": f"Matched {recommended['lane']} keywords: {', '.join(item.get('matched_keywords', []))}",
                    }
                )
        for item in recommended.get("evidence", []):
            if item.get("type") == "title_pattern":
                evidence.append(
                    {
                        "type": "title_pattern",
                        "pattern": item.get("value", ""),
                        "count": item.get("count", 0),
                        "examples": item.get("examples", []),
                        "reason": f"Common title pattern for the {recommended['lane']} lane.",
                    }
                )
        for claim in research.get("claims_to_verify", [])[:3]:
            evidence.append(
                {
                    "type": "claim_risk",
                    "claim_area": claim.get("claim_area", ""),
                    "reason": claim.get("reason", ""),
                }
            )
        return evidence[:8]

    def _angle_reason(self, lane: str, top_patterns: list[str], has_pains: bool, has_claims: bool) -> str:
        details = []
        if top_patterns:
            details.append(f"top title patterns include {', '.join(top_patterns)}")
        if has_pains:
            details.append("viewer comments include questions or confusion")
        if has_claims:
            details.append("research flagged claims that need verification")
        if not details:
            return f"This angle matches the highest-scoring {lane} lane."
        return "; ".join(details) + "."

    def _evidence_summary(self, research: dict[str, Any]) -> dict[str, Any]:
        market = research.get("market_stats", {})
        videos = research.get("competitor_videos", [])
        breakouts = research.get("breakout_videos", [])
        return {
            "videos_collected": market.get("videos_collected", len(videos)),
            "strong_fit_count": len(research.get("strong_fit_competitors", [])),
            "adjacent_opportunity_count": len(research.get("adjacent_opportunity_videos", [])),
            "off_context_outlier_count": len(research.get("off_context_outliers", [])),
            "breakout_count": market.get("breakout_count", len(breakouts)),
            "median_views_per_day": market.get("median_views_per_day", 0),
            "median_duration_seconds": market.get("median_duration_seconds", 0),
            "format_counts": market.get("format_counts", {}),
            "competitor_fit_counts": market.get("competitor_fit_counts", {}),
            "top_title_patterns": research.get("title_patterns", [])[:5],
            "claims_to_verify": research.get("claims_to_verify", []),
            "source_errors": research.get("source_errors", []),
        }

    def _primary_strategy_videos(self, research: dict[str, Any]) -> list[dict[str, Any]]:
        strong_fit = research.get("strong_fit_competitors", [])
        if strong_fit:
            return strong_fit
        return research.get("competitor_videos", [])

    def _title_patterns_from_videos(self, videos: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
            if not candidates:
                candidates.append("plain topic explainer")
            for pattern in candidates:
                patterns[pattern] += 1
                examples.setdefault(pattern, []).append(title)
        return [
            {"pattern": pattern, "count": count, "examples": examples.get(pattern, [])[:3]}
            for pattern, count in patterns.most_common()
        ]

    def _strategy_notes(self, recommended: dict[str, Any], research: dict[str, Any]) -> list[str]:
        notes = [
            f"{recommended['label']} scored highest from query matches, title patterns, breakout videos, and audience fit.",
        ]
        if research.get("source_errors"):
            notes.append("Research contains source errors; review them before treating the strategy as final.")
        if not research.get("evidence_status", {}).get("has_live_youtube_data"):
            notes.append("No live YouTube evidence was available, so confidence should be low.")
        return notes

    def _rationale(
        self,
        lane: str,
        score: float,
        evidence: list[dict[str, Any]],
        saturation_penalty: float,
    ) -> list[str]:
        if not evidence:
            return [f"{lane} scored {score}, but had limited direct evidence."]
        rationale = [f"{lane} scored {score} from {len(evidence)} evidence signals."]
        if saturation_penalty < 0:
            rationale.append(f"Applied saturation penalty of {abs(saturation_penalty)} because this lane appears common.")
        return rationale
