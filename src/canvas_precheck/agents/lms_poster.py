class LMSPosterAgent:
    name = "LMSPosterAgent"

    def __init__(self, canvas_client, enabled: bool):
        self.canvas = canvas_client
        self.enabled = enabled

    def run(self, state: dict) -> dict:
        if not self.enabled:
            return state
        meta = state["feedback"].metadata
        with open(state["artifacts"]["feedback_md"], "r", encoding="utf-8") as f:
            body = f.read()
        self.canvas.post_comment(meta.course_id, meta.assignment_id, meta.user_id, body)
        return state