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
            "Important: evidence_keys MUST be chosen only from allowed_evidence_keys."
        )

        payload = {
            "feedback": fb.model_dump(),
            "allowed_evidence_keys": sorted(list(fb.evidence.keys())),
            "prompts": prompts
        }

        resp = self.llm.invoke([
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload)}
        ])

        state["llm"] = LLMJSON.model_validate(json.loads(resp.content))
        return state