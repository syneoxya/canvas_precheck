import json
from canvas_precheck.models import FeedbackJSON, LLMJSON
from langchain_openai import ChatOpenAI

class LLMReviewerAgent:
    name = "LLMReviewerAgent"

    def __init__(self, model: str):
        self.llm = ChatOpenAI(model=model, temperature=0)

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
            "Return JSON ONLY with schema:\n"
            "{ items: [{ rubric_item, score, finding, suggestion, evidence_keys }], "
            "overall, section_scores: { coding?: number, writing?: number, document?: number }, "
            "overall_score }\n"
            "Rules:\n"
            "1) evidence_keys MUST be chosen only from allowed_evidence_keys.\n"
            "2) If content.coding.preview is present, grade the coding/notebook section independently "
            "and put its 0-100 score in section_scores.coding.\n"
            "3) If content.writing.preview is present, grade the writing/PDF section independently "
            "and put its 0-100 score in section_scores.writing.\n"
            "4) overall_score MUST be one aggregate 0-100 grade for the student. If multiple section "
            "scores are present, use their average unless the assignment prompt says otherwise.\n"
            "5) If you comment on the submission's CONTENT (writing, code, completeness, correctness), "
            "you MUST include the relevant preview key, such as 'content.coding.preview', "
            "'content.writing.preview', or 'content.preview', in evidence_keys.\n"
            "6) If 'content.preview' is not present or is empty, you MUST say you cannot assess content "
            "and only comment on metadata.\n"
            "7) Grade and review ONLY the academic/content quality of the extracted submission text. "
            "Do NOT penalize or discuss filename conventions, missing required "
            "files, duplicate files, lateness, Canvas metadata, or submission-format issues. Those "
            "administrative checks are handled separately by deterministic agents.\n"
            "8) You MUST return exactly three items in this order, with rubric_item values exactly: "
            "'What was done well', 'What is missing', and 'What can be improved'. Do not replace "
            "these names with the assignment prompt name.\n"
            "9) Each item's finding MUST discuss every present content section independently before "
            "summarizing the student as a whole. Cite specific parts of the notebook/code and PDF/writing "
            "when both are present.\n"
            "10) Each item should include a numeric score from 0 to 100 based only on content quality. "
            "Use the suggestion field for actionable next steps.\n"
        )

        content_preview = fb.evidence.get("content.preview", "")
        payload = {
            "feedback": fb.model_dump(mode="json"),
            "allowed_evidence_keys": sorted(list(fb.evidence.keys())),
            "content_preview_present": bool(content_preview.strip()),
            "content_sections": self._content_sections(fb),
            "prompts": prompts
        }

        resp = self.llm.invoke([
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload)}
        ])

        # Parse + sanitize model output defensively
        try:
            raw = json.loads(resp.content)
        except json.JSONDecodeError:
            raw = {"items": [], "overall": "Model returned non-JSON output."}

        # Ensure overall is always a string (model sometimes returns a number)
        if "overall" in raw and not isinstance(raw["overall"], str):
            raw["overall"] = str(raw["overall"])
        raw = self._sanitize_raw(raw)

        state["llm"] = LLMJSON.model_validate(raw)
        return state

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
        raw.setdefault("section_scores", {})
        raw.setdefault("overall_score", None)
        if not isinstance(raw.get("section_scores"), dict):
            raw["section_scores"] = {}

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

        if raw.get("overall_score") is not None:
            try:
                value = float(raw["overall_score"])
                if 0 <= value <= 1:
                    value *= 100
                elif 0 <= value <= 10:
                    value *= 10
                raw["overall_score"] = max(0, min(100, value))
            except (TypeError, ValueError):
                raw["overall_score"] = None

        if not str(raw.get("overall", "")).strip():
            findings = []
            for item in raw.get("items", []) or []:
                if not isinstance(item, dict):
                    continue
                rubric = str(item.get("rubric_item", "")).strip()
                finding = str(item.get("finding", "")).strip()
                if rubric and finding:
                    findings.append(f"{rubric}: {finding}")
            raw["overall"] = " ".join(findings)[:600] if findings else "No overall feedback was generated."
        return raw
