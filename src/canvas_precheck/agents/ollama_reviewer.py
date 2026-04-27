import json
import re

import requests
from pydantic import ValidationError

from canvas_precheck.models import FeedbackJSON, LLMJSON


class OllamaReviewerAgent:
    name = "OllamaReviewerAgent"

    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def run(self, state: dict) -> dict:
        cfg = state["config"]
        if not cfg.get("llm", {}).get("enabled", True):
            state["llm"] = None
            return state

        fb: FeedbackJSON = state["feedback"]
        prompts = cfg.get("llm_prompts", [])
        if not prompts:
            state["llm"] = LLMJSON(items=[], overall="No prompts configured.")
            return state

        system = (
            "Return JSON ONLY with this schema:\n"
            "{ \"items\": [{ \"rubric_item\": string, \"score\": number|null, "
            "\"finding\": string, \"suggestion\": string, \"evidence_keys\": [string] }], "
            "\"overall\": string, \"section_scores\": { \"coding\": number, \"writing\": number, "
            "\"document\": number }, \"overall_score\": number|null }\n"
            "Rules:\n"
            "1) evidence_keys MUST be chosen only from allowed_evidence_keys.\n"
            "2) If content.coding.preview is present, grade the coding/notebook section independently "
            "and put its 0-100 score in section_scores.coding.\n"
            "3) If content.writing.preview is present, grade the writing/PDF section independently "
            "and put its 0-100 score in section_scores.writing.\n"
            "4) overall_score MUST be one aggregate 0-100 grade for the student. If multiple section "
            "scores are present, use their average unless the assignment prompt says otherwise.\n"
            "5) If you comment on submission content, include the relevant preview key, such as "
            "'content.coding.preview', 'content.writing.preview', or 'content.preview', in evidence_keys.\n"
            "6) content_preview below is the extracted submission text. If content_preview_present is true, "
            "you MUST assess that content and MUST NOT say content.preview is missing.\n"
            "7) If content_preview_present is false, say you cannot assess content and only comment on metadata.\n"
            "8) Grade and review ONLY the academic/content quality of extracted content. Do NOT penalize "
            "or discuss filename conventions, missing required files, duplicate files, lateness, Canvas "
            "metadata, or submission-format issues. Those administrative checks are handled separately "
            "by deterministic agents.\n"
            "9) You MUST return exactly three items in this order, with rubric_item values exactly: "
            "'What was done well', 'What is missing', and 'What can be improved'. Do not replace "
            "these names with the assignment prompt name.\n"
            "10) Each item's finding MUST discuss every present content section independently before "
            "summarizing the student as a whole. Cite specific parts of the notebook/code and PDF/writing "
            "when both are present.\n"
            "11) Each item should include a numeric score from 0 to 100 based only on content quality. "
            "Use the suggestion field for actionable next steps.\n"
        )

        content_preview = fb.evidence.get("content.preview", "")
        payload = {
            "feedback": fb.model_dump(mode="json"),
            "allowed_evidence_keys": sorted(list(fb.evidence.keys())),
            "content_preview_present": bool(content_preview.strip()),
            "content_preview": content_preview,
            "content_sections": self._content_sections(fb),
            "prompts": prompts,
        }

        try:
            content = self._call_ollama([
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload)},
            ])
            raw = self._parse_json(content)
            raw = self._sanitize_raw(raw)
            if content_preview.strip() and self._claims_missing_content(raw):
                content = self._call_ollama([
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": json.dumps({
                            "allowed_evidence_keys": sorted(list(fb.evidence.keys())),
                            "content_preview_present": True,
                            "content_preview": content_preview,
                            "content_sections": self._content_sections(fb),
                            "prompts": prompts,
                            "instruction": (
                                "The extracted submission text is present in content_preview. "
                                "Assess it directly. Do not say content.preview is missing."
                            ),
                        }),
                    },
                ])
                raw = self._parse_json(content)
                raw = self._sanitize_raw(raw)
            if content_preview.strip() and not raw.get("items"):
                content = self._call_ollama([
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": json.dumps({
                            "allowed_evidence_keys": sorted(list(fb.evidence.keys())),
                            "content_sections": self._content_sections(fb),
                            "prompts": prompts,
                            "instruction": (
                                "Your previous response only gave numeric scores. Return valid JSON with "
                                "exactly three items now: What was done well, What is missing, and What can "
                                "be improved. Each item must include rubric_item, score, finding, suggestion, "
                                "and evidence_keys. Keep section_scores and overall_score too."
                            ),
                        }),
                    },
                ])
                retry_raw = self._sanitize_raw(self._parse_json(content))
                if retry_raw.get("items"):
                    raw = retry_raw
            state["llm"] = LLMJSON.model_validate(raw)
        except (requests.RequestException, json.JSONDecodeError, ValidationError, TypeError) as e:
            state["llm"] = LLMJSON(
                items=[],
                overall=(
                    "Local Ollama review failed. Make sure Ollama is running and the "
                    f"model '{self.model}' is installed. Error: {type(e).__name__}: {e}"
                ),
            )

        return state

    def _call_ollama(self, messages: list[dict[str, str]]) -> str:
        resp = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "messages": messages,
                "format": "json",
            },
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")

    def _parse_json(self, content: str) -> dict:
        content = content.strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, flags=re.DOTALL)
            if not match:
                raise
            return json.loads(match.group(0))

    def _claims_missing_content(self, raw: dict) -> bool:
        haystack = json.dumps(raw).lower()
        return "content.preview" in haystack and any(
            phrase in haystack
            for phrase in ["missing", "not present", "cannot assess", "can't assess"]
        )

    def _content_sections(self, fb: FeedbackJSON) -> dict:
        sections = {}
        for section in ["coding", "writing", "document"]:
            preview = fb.evidence.get(f"content.{section}.preview", "")
            if preview.strip():
                sections[section] = {
                    "preview_key": f"content.{section}.preview",
                    "preview": preview,
                    "files": fb.evidence.get(f"content.{section}.files_json", "[]"),
                }
        return sections

    def _sanitize_raw(self, raw: dict) -> dict:
        if not isinstance(raw, dict):
            return {"items": [], "overall": str(raw)}

        raw.setdefault("items", [])
        raw.setdefault("overall", "")
        raw.setdefault("section_scores", {})
        raw.setdefault("overall_score", None)

        if not isinstance(raw["items"], list):
            raw["items"] = []
        if not isinstance(raw["overall"], str):
            raw["overall"] = str(raw["overall"])
        if not isinstance(raw["section_scores"], dict):
            raw["section_scores"] = {}

        nested_overall = raw["section_scores"].pop("overall_score", None)
        if raw["overall_score"] is None and nested_overall is not None:
            raw["overall_score"] = nested_overall

        clean_scores = {}
        for section, score in raw["section_scores"].items():
            try:
                value = float(score)
            except (TypeError, ValueError):
                continue
            if 0 <= value <= 1:
                value *= 100
            elif 0 <= value <= 10:
                value *= 10
            clean_scores[str(section)] = max(0, min(100, value))
        raw["section_scores"] = clean_scores

        if raw["overall_score"] is not None:
            try:
                value = float(raw["overall_score"])
                if 0 <= value <= 1:
                    value *= 100
                elif 0 <= value <= 10:
                    value *= 10
                raw["overall_score"] = max(0, min(100, value))
            except (TypeError, ValueError):
                raw["overall_score"] = None

        clean_items = []
        for item in raw["items"]:
            if not isinstance(item, dict):
                continue
            item.setdefault("rubric_item", "")
            item.setdefault("score", None)
            item.setdefault("finding", "")
            item.setdefault("suggestion", "")
            item.setdefault("evidence_keys", [])

            for key in ["rubric_item", "finding", "suggestion"]:
                if item[key] is None:
                    item[key] = ""
                elif not isinstance(item[key], str):
                    item[key] = str(item[key])

            if not isinstance(item["evidence_keys"], list):
                item["evidence_keys"] = []
            item["evidence_keys"] = [str(k) for k in item["evidence_keys"]]
            clean_items.append(item)

        raw["items"] = clean_items
        if not raw["overall"].strip():
            findings = []
            for item in clean_items:
                rubric = item.get("rubric_item", "").strip()
                finding = item.get("finding", "").strip()
                if rubric and finding:
                    findings.append(f"{rubric}: {finding}")
            if findings:
                raw["overall"] = " ".join(findings)[:600]
            elif raw["section_scores"] or raw["overall_score"] is not None:
                score_parts = [
                    f"{section}: {round(score)}"
                    for section, score in raw["section_scores"].items()
                ]
                if raw["overall_score"] is not None:
                    score_parts.append(f"aggregate: {round(raw['overall_score'])}")
                raw["overall"] = "Ollama returned numeric scores but omitted written feedback: " + ", ".join(score_parts)
            else:
                raw["overall"] = "No overall feedback was generated."
        return raw
