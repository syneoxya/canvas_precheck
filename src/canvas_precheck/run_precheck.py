import os, json, pathlib
from dateutil import parser

from canvas_precheck.secrets import CANVAS_BASE_URL, CANVAS_TOKEN, OPENAI_API_KEY
# Make LangChain/OpenAI read the key
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

from canvas_precheck.canvas_client import CanvasClient
from canvas_precheck.models import SubmissionMetadata, FeedbackJSON
from canvas_precheck.pipeline import Pipeline

from canvas_precheck.agents.intake import IntakeAgent
from canvas_precheck.agents.file_structure import FileStructureAgent
from canvas_precheck.agents.test_runner import TestRunnerAgent
from canvas_precheck.agents.llm_reviewer import LLMReviewerAgent
from canvas_precheck.agents.feedback_composer import FeedbackComposerAgent
from canvas_precheck.agents.lms_poster import LMSPosterAgent

def main(config_path: str):
    cfg = json.loads(pathlib.Path(config_path).read_text(encoding="utf-8"))
    course_id = cfg["course_id"]
    assignment_id = cfg["assignment_id"]

    posting_enabled = bool(cfg.get("posting", {}).get("enabled", False))
    llm_model = cfg.get("llm", {}).get("model", "gpt-4.1-mini")

    canvas = CanvasClient(CANVAS_BASE_URL, CANVAS_TOKEN)
    subs = canvas.list_submissions(course_id, assignment_id)

    pipeline = Pipeline([
        IntakeAgent(canvas),
        FileStructureAgent(),
        TestRunnerAgent(),
        LLMReviewerAgent(model=llm_model),
        FeedbackComposerAgent(),
        LMSPosterAgent(canvas, enabled=posting_enabled),
    ])

    out_root = pathlib.Path("runs") / f"course_{course_id}" / f"assignment_{assignment_id}"
    out_root.mkdir(parents=True, exist_ok=True)

    for s in subs:
        user = s.get("user") or {}
        user_id = s.get("user_id")
        student_name = user.get("name", f"user_{user_id}")

        submitted_at = parser.isoparse(s["submitted_at"]) if s.get("submitted_at") else None
        due_at = parser.isoparse(s["cached_due_date"]) if s.get("cached_due_date") else None
        attachments = s.get("attachments") or []

        meta = SubmissionMetadata(
            course_id=course_id,
            assignment_id=assignment_id,
            user_id=user_id,
            student_name=student_name,
            submitted_at=submitted_at,
            due_at=due_at,
            attachments=attachments
        )

        fb = FeedbackJSON(metadata=meta)
        workdir = out_root / f"user_{user_id}"
        workdir.mkdir(parents=True, exist_ok=True)

        state = {"config": cfg, "workdir": str(workdir), "feedback": fb, "llm": None, "artifacts": {}}
        state = pipeline.run(state)

        (workdir / "feedback.json").write_text(state["feedback"].model_dump_json(indent=2), encoding="utf-8")
        if state.get("llm") is not None:
            (workdir / "llm.json").write_text(state["llm"].model_dump_json(indent=2), encoding="utf-8")

        print(f"Done: {student_name} -> {workdir/'feedback.md'}")

if __name__ == "__main__":
    import sys
    main(sys.argv[1])