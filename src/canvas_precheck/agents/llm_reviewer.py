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
            "{ items: [{ rubric_item, score, finding, suggestion, evidence_keys }], overall }\n"
            "Rules:\n"
            "1) evidence_keys MUST be chosen only from allowed_evidence_keys.\n"
            "2) If you comment on the submission's CONTENT (writing, completeness, correctness), "
            "you MUST include 'content.preview' in evidence_keys.\n"
            "3) If 'content.preview' is not present or is empty, you MUST say you cannot assess content "
            "and only comment on metadata.\n"
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