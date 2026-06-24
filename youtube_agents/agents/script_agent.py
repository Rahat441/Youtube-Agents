"""ScriptAgent v1: draft a video script from research, strategy, and ideas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from youtube_agents.core.llm import OllamaChatClient, OpenAIChatClient


class ScriptAgent:
    """Generate a structured script artifact using an LLM provider."""

    DEFAULT_TARGET_DURATION_MINUTES = 8.0
    DEFAULT_SCRIPT_STYLE = "clear, evidence-led YouTube narration"
    DEFAULT_LLM_TIMEOUT_SECONDS = 300

    def __init__(self, llm_client: Any | None = None):
        self.llm_client = llm_client

    def run(
        self,
        research: dict[str, Any],
        strategy: dict[str, Any],
        ideas: dict[str, Any],
        provider: str = "ollama",
        model: str | None = None,
        target_duration_minutes: float = DEFAULT_TARGET_DURATION_MINUTES,
        script_style: str = DEFAULT_SCRIPT_STYLE,
        llm_timeout_seconds: int | None = DEFAULT_LLM_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        if research.get("schema_version") != "research.v1":
            raise ValueError("ScriptAgent requires a research.v1 artifact")
        if strategy.get("schema_version") != "strategy.v1":
            raise ValueError("ScriptAgent requires a strategy.v1 artifact")
        if ideas.get("schema_version") != "ideas.v1":
            raise ValueError("ScriptAgent requires an ideas.v1 artifact")

        target_duration_minutes = max(1.0, float(target_duration_minutes))
        selected_idea = ideas.get("selected_idea") or {}
        generation, script = self._generate_script(
            research=research,
            strategy=strategy,
            selected_idea=selected_idea,
            provider=provider,
            model=model,
            target_duration_minutes=target_duration_minutes,
            script_style=script_style,
            llm_timeout_seconds=llm_timeout_seconds,
        )
        status = "complete" if generation.get("ok") else "failed"

        return {
            "schema_version": "script.v1",
            "agent": "ScriptAgent",
            "created_at": datetime.now().isoformat(),
            "status": status,
            "input": {
                "topic": research.get("input", {}).get("topic", ""),
                "research_created_at": research.get("created_at"),
                "strategy_created_at": strategy.get("created_at"),
                "ideas_created_at": ideas.get("created_at"),
                "provider": provider,
                "model": model,
                "target_duration_minutes": target_duration_minutes,
                "script_style": script_style,
                "llm_timeout_seconds": llm_timeout_seconds,
            },
            "selected_idea_used": {
                "idea_id": selected_idea.get("idea_id", ""),
                "working_title": selected_idea.get("working_title", ""),
                "niche_lane": selected_idea.get("niche_lane", ""),
                "angle_type": selected_idea.get("angle_type", ""),
                "viewer_promise": selected_idea.get("viewer_promise", ""),
                "differentiation": selected_idea.get("differentiation", ""),
            },
            "strategy_used": {
                "recommended_niche_lane": strategy.get("recommended_niche_lane", ""),
                "recommended_angle": strategy.get("recommended_angle", ""),
                "recommended_angle_type": strategy.get("recommended_angle_type", ""),
                "positioning": strategy.get("positioning", ""),
            },
            "generation": generation,
            "script": script,
            "claims_to_verify": self._claims_to_verify(research, script),
            "source_evidence_used": self._source_evidence_used(research, strategy, selected_idea, script),
            "revision_notes": self._revision_notes(status, generation, script),
            "handoff_contract": {
                "next_agent": "CritiqueAgent",
                "critique_agent_should_use": [
                    "script.full_script",
                    "script.body_sections",
                    "claims_to_verify",
                    "source_evidence_used",
                    "selected_idea_used",
                    "strategy_used",
                ],
                "script_agent_must_not_decide": [
                    "final published title",
                    "thumbnail package",
                    "upload metadata",
                    "final factual approval",
                ],
            },
        }

    def _generate_script(
        self,
        research: dict[str, Any],
        strategy: dict[str, Any],
        selected_idea: dict[str, Any],
        provider: str,
        model: str | None,
        target_duration_minutes: float,
        script_style: str,
        llm_timeout_seconds: int | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if provider not in {"openai", "ollama"}:
            return self._failed_generation(provider, model, f"Unknown script provider '{provider}'."), {}
        if not selected_idea:
            return self._failed_generation(provider, model, "ideas.json does not include selected_idea."), {}

        client = self.llm_client or self._llm_client(provider, model, llm_timeout_seconds)
        response = client.json_chat(
            system_prompt=self._llm_system_prompt(),
            user_prompt=self._llm_user_prompt(
                research=research,
                strategy=strategy,
                selected_idea=selected_idea,
                target_duration_minutes=target_duration_minutes,
                script_style=script_style,
            ),
        )
        if not response.get("ok"):
            generation = self._failed_generation(provider, response.get("model") or model, response.get("error", "Unknown LLM error."))
            generation["provider_settings"] = response.get("settings", {})
            return generation, {}

        data = response.get("data", {})
        if not isinstance(data, dict):
            generation = self._failed_generation(
                provider,
                response.get("model") or model,
                "LLM response JSON must be an object.",
            )
            generation["provider_settings"] = response.get("settings", {})
            return generation, {}

        script = self._normalize_script(data, selected_idea, target_duration_minutes)
        validation_errors = self._validate_script(script)
        if validation_errors:
            generation = self._failed_generation(
                provider,
                response.get("model") or model,
                "LLM response did not include a usable script artifact.",
            )
            generation["provider_settings"] = response.get("settings", {})
            generation["validation_errors"] = validation_errors
            return generation, script

        return {
            "ok": True,
            "requested_provider": provider,
            "used_provider": provider,
            "model": response.get("model") or model,
            "provider_settings": response.get("settings", {}),
            "errors": [],
        }, script

    def _llm_client(self, provider: str, model: str | None, timeout_seconds: int | None) -> Any:
        if provider == "ollama":
            return OllamaChatClient(model=model, timeout_seconds=timeout_seconds)
        return OpenAIChatClient(model=model, timeout_seconds=timeout_seconds or 60)

    def _failed_generation(self, provider: str, model: str | None, error: str) -> dict[str, Any]:
        return {
            "ok": False,
            "requested_provider": provider,
            "used_provider": None,
            "model": model,
            "provider_settings": {},
            "errors": [error],
        }

    def _llm_system_prompt(self) -> str:
        return (
            "You are ScriptAgent for a local YouTube production pipeline. "
            "Write scripts only from the provided research, strategy, and selected idea. "
            "Do not invent sources, studies, statistics, or medical/legal/financial claims. "
            "If a claim needs verification, place it in claims_to_verify instead of presenting it as fact. "
            "Return strict JSON only."
        )

    def _llm_user_prompt(
        self,
        research: dict[str, Any],
        strategy: dict[str, Any],
        selected_idea: dict[str, Any],
        target_duration_minutes: float,
        script_style: str,
    ) -> str:
        compact = {
            "topic": research.get("input", {}).get("topic", ""),
            "audience": research.get("input", {}).get("audience", ""),
            "style": research.get("input", {}).get("style", ""),
            "script_style": script_style,
            "target_duration_minutes": target_duration_minutes,
            "target_word_count": self._target_word_count(target_duration_minutes),
            "selected_idea": {
                "working_title": selected_idea.get("working_title"),
                "niche_lane": selected_idea.get("niche_lane"),
                "angle_type": selected_idea.get("angle_type"),
                "viewer_promise": selected_idea.get("viewer_promise"),
                "differentiation": selected_idea.get("differentiation"),
                "evidence_used": selected_idea.get("evidence_used", [])[:6],
                "risk_notes": selected_idea.get("risk_notes", [])[:6],
            },
            "strategy": {
                "recommended_niche_lane": strategy.get("recommended_niche_lane"),
                "recommended_angle": strategy.get("recommended_angle"),
                "recommended_angle_type": strategy.get("recommended_angle_type"),
                "positioning": strategy.get("positioning"),
                "key_evidence": strategy.get("key_evidence", [])[:8],
            },
            "top_competitors": [
                {
                    "video_id": video.get("video_id"),
                    "title": video.get("title"),
                    "views_per_day": video.get("views_per_day"),
                    "fit_score": video.get("competitor_fit", {}).get("score"),
                    "fit_reasons": video.get("competitor_fit", {}).get("reasons", [])[:3],
                }
                for video in research.get("strong_fit_competitors", [])[:6]
            ],
            "title_patterns": research.get("title_patterns", [])[:6],
            "viewer_pains": research.get("viewer_pains", [])[:8],
            "claims_to_verify": research.get("claims_to_verify", [])[:8],
        }
        return (
            "Draft a YouTube voiceover script for the selected idea. "
            "The script should be ready for CritiqueAgent, not final publication. "
            "Use clear sectioning, strong retention, and careful evidence language. "
            "Return JSON in exactly this shape: "
            '{"working_title":"...","target_duration_minutes":8,"estimated_word_count":1000,'
            '"hook":"...","intro":"...","body_sections":[{"heading":"...",'
            '"narration":"...","evidence_used":["..."],"claims_to_verify":["..."]}],'
            '"cta":"...","full_script":"...","claims_used":["..."],'
            '"claims_to_verify":["..."],"editor_notes":["..."]}\n\n'
            f"Evidence package:\n{compact}"
        )

    def _normalize_script(
        self,
        data: dict[str, Any],
        selected_idea: dict[str, Any],
        target_duration_minutes: float,
    ) -> dict[str, Any]:
        body_sections = []
        for item in data.get("body_sections", []):
            if not isinstance(item, dict):
                continue
            body_sections.append(
                {
                    "heading": str(item.get("heading", "")).strip(),
                    "narration": str(item.get("narration", "")).strip(),
                    "evidence_used": self._string_list(item.get("evidence_used", [])),
                    "claims_to_verify": self._string_list(item.get("claims_to_verify", [])),
                }
            )

        script = {
            "working_title": str(data.get("working_title") or selected_idea.get("working_title") or "").strip(),
            "target_duration_minutes": self._float_value(data.get("target_duration_minutes"), target_duration_minutes),
            "estimated_word_count": self._int_value(
                data.get("estimated_word_count"),
                self._target_word_count(target_duration_minutes),
            ),
            "hook": str(data.get("hook", "")).strip(),
            "intro": str(data.get("intro", "")).strip(),
            "body_sections": body_sections,
            "cta": str(data.get("cta", "")).strip(),
            "full_script": str(data.get("full_script", "")).strip(),
            "claims_used": self._string_list(data.get("claims_used", [])),
            "claims_to_verify": self._string_list(data.get("claims_to_verify", [])),
            "editor_notes": self._string_list(data.get("editor_notes", [])),
        }
        if not script["full_script"]:
            script["full_script"] = self._assemble_full_script(script)
        return script

    def _validate_script(self, script: dict[str, Any]) -> list[str]:
        errors = []
        if not script.get("working_title"):
            errors.append("Missing working_title.")
        if not script.get("hook"):
            errors.append("Missing hook.")
        if not script.get("intro"):
            errors.append("Missing intro.")
        if not script.get("body_sections"):
            errors.append("Missing body_sections.")
        if not script.get("full_script"):
            errors.append("Missing full_script.")
        if len(str(script.get("full_script", "")).split()) < 120:
            errors.append("full_script is too short to be useful.")
        return errors

    def _assemble_full_script(self, script: dict[str, Any]) -> str:
        parts = [script.get("hook", ""), script.get("intro", "")]
        parts.extend(section.get("narration", "") for section in script.get("body_sections", []))
        parts.append(script.get("cta", ""))
        return "\n\n".join(part for part in parts if part).strip()

    def _target_word_count(self, target_duration_minutes: float) -> int:
        return int(max(1.0, target_duration_minutes) * 135)

    def _float_value(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _int_value(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _string_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _claims_to_verify(self, research: dict[str, Any], script: dict[str, Any]) -> list[dict[str, Any]]:
        claims = []
        for item in research.get("claims_to_verify", [])[:10]:
            if isinstance(item, dict):
                claims.append(item)
        for claim in script.get("claims_to_verify", []):
            claims.append({"claim": claim, "source": "script_agent_llm"})
        return claims

    def _source_evidence_used(
        self,
        research: dict[str, Any],
        strategy: dict[str, Any],
        selected_idea: dict[str, Any],
        script: dict[str, Any],
    ) -> list[dict[str, Any]]:
        evidence = []
        for item in selected_idea.get("evidence_used", [])[:6]:
            if isinstance(item, dict):
                evidence.append({"source": "selected_idea", **item})
        for item in strategy.get("key_evidence", [])[:6]:
            if isinstance(item, dict):
                evidence.append({"source": "strategy_key_evidence", **item})
        for video in research.get("strong_fit_competitors", [])[:4]:
            evidence.append(
                {
                    "source": "strong_fit_competitor",
                    "video_id": video.get("video_id"),
                    "title": video.get("title", ""),
                    "views_per_day": video.get("views_per_day", 0),
                    "fit_score": video.get("competitor_fit", {}).get("score"),
                }
            )
        for claim in script.get("claims_used", [])[:8]:
            evidence.append({"source": "script_claims_used", "claim": claim})
        return evidence[:16]

    def _revision_notes(self, status: str, generation: dict[str, Any], script: dict[str, Any]) -> list[str]:
        notes = []
        if status != "complete":
            notes.append("Script generation failed; review generation.errors before retrying.")
        if script.get("claims_to_verify"):
            notes.append("Verify marked claims before treating the script as factual.")
        if not script.get("editor_notes"):
            notes.append("CritiqueAgent should check pacing, clarity, evidence strength, and retention.")
        return notes + script.get("editor_notes", [])
