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
            "You must return VALID JSON ONLY (no markdown, no code fences).\n"
            "Schema:\n"
            "{\n"
            '  "items": [\n'
            "    {\n"
            '      "rubric_item": "string",\n'
            '      "score": 0,\n'
            '      "finding": "string",\n'
            '      "suggestion": "string",\n'
            '      "evidence_keys": ["string"]\n'
            "    }\n"
            "  ],\n"
            '  "overall": "string"\n'
            "}\n"
            'Important: "overall" MUST be a string summary, not a number.\n'
            "Important: evidence_keys MUST be chosen only from allowed_evidence_keys.\n"
        )

        payload = {
            "feedback": fb.model_dump(mode="json"),
            "allowed_evidence_keys": sorted(list(fb.evidence.keys())),
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

        state["llm"] = LLMJSON.model_validate(raw)
        return state