import os
import json
import pathlib
from dateutil import parser

CANVAS_BASE_URL = os.getenv("CANVAS_BASE_URL", "https://jhu.instructure.com")
CANVAS_TOKEN = os.getenv("CANVAS_API_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

from canvas_precheck.canvas_client import CanvasClient
from canvas_precheck.models import SubmissionMetadata, FeedbackJSON
from canvas_precheck.pipeline import Pipeline
from canvas_precheck.report_excel import row_from_state, write_assignment_summary_xlsx

from canvas_precheck.agents.intake import IntakeAgent
from canvas_precheck.agents.file_structure import FileStructureAgent
from canvas_precheck.agents.test_runner import TestRunnerAgent
from canvas_precheck.agents.llm_reviewer import LLMReviewerAgent
from canvas_precheck.agents.ollama_reviewer import OllamaReviewerAgent
from canvas_precheck.agents.feedback_composer import FeedbackComposerAgent
from canvas_precheck.agents.lms_poster import LMSPosterAgent
from canvas_precheck.agents.content_extract import ContentExtractAgent


def build_reviewer(llm_cfg: dict, openai_api_key: str | None = None):
    if not llm_cfg.get("enabled", True):
        return None

    provider = llm_cfg.get("provider", "openai").lower()
    if provider == "ollama":
        model = llm_cfg.get("model", "llama3.1:8b")
        base_url = llm_cfg.get("base_url", "http://localhost:11434")
        return OllamaReviewerAgent(model=model, base_url=base_url)

    if provider == "openai":
        api_key = openai_api_key or OPENAI_API_KEY
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required when llm.provider is 'openai'")
        os.environ["OPENAI_API_KEY"] = api_key
        model = llm_cfg.get("model", "gpt-4.1-mini")
        return LLMReviewerAgent(model=model)

    raise ValueError(f"Unsupported llm.provider: {provider}")


def build_pipeline(
    canvas,
    cfg: dict,
    posting_enabled: bool,
    openai_api_key: str | None = None,
) -> Pipeline:
    agents = [
        IntakeAgent(canvas),
        FileStructureAgent(),
        ContentExtractAgent(max_chars=6000),
        TestRunnerAgent(),
    ]
    reviewer = build_reviewer(cfg.get("llm", {}), openai_api_key=openai_api_key)
    if reviewer is not None:
        agents.append(reviewer)
    agents.extend([
        FeedbackComposerAgent(),
        LMSPosterAgent(canvas, enabled=posting_enabled),
    ])
    return Pipeline(agents)


def filter_submissions(
    submissions: list[dict],
    limit: int | None = None,
    user_id: int | None = None,
) -> list[dict]:
    if user_id is not None:
        submissions = [s for s in submissions if s.get("user_id") == user_id]
    if limit is not None:
        submissions = submissions[:limit]
    return submissions


def run_precheck(
    cfg: dict,
    canvas: CanvasClient,
    limit: int | None = None,
    user_id: int | None = None,
    openai_api_key: str | None = None,
    progress_callback=None,
    should_cancel=None,
) -> dict:
    course_id = cfg["course_id"]
    assignment_id = cfg["assignment_id"]

    posting_enabled = bool(cfg.get("posting", {}).get("enabled", False))

    subs = canvas.list_submissions(course_id, assignment_id)
    subs = filter_submissions(subs, limit=limit, user_id=user_id)
    if not subs:
        target = f"user_id={user_id}" if user_id is not None else "the selected filters"
        return {"status": "empty", "message": f"No submissions matched {target}."}
    if progress_callback is not None:
        progress_callback({
            "status": "running",
            "processed": 0,
            "total": len(subs),
            "current_student": "",
        })

    pipeline = build_pipeline(canvas, cfg, posting_enabled, openai_api_key=openai_api_key)

    out_root = pathlib.Path("runs") / f"course_{course_id}" / f"assignment_{assignment_id}"
    out_root.mkdir(parents=True, exist_ok=True)
    rows_for_excel = []
    for index, s in enumerate(subs, start=1):
        if should_cancel is not None and should_cancel():
            if progress_callback is not None:
                progress_callback({
                    "status": "cancelled",
                    "processed": index - 1,
                    "total": len(subs),
                    "current_student": "",
                })
            break

        user = s.get("user") or {}
        user_id = s.get("user_id")
        student_name = user.get("name", f"user_{user_id}")
        if progress_callback is not None:
            progress_callback({
                "status": "running",
                "processed": index - 1,
                "total": len(subs),
                "current_student": student_name,
            })

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
        rows_for_excel.append(row_from_state(state))

        (workdir / "feedback.json").write_text(state["feedback"].model_dump_json(indent=2), encoding="utf-8")
        if state.get("llm") is not None:
            (workdir / "llm.json").write_text(state["llm"].model_dump_json(indent=2), encoding="utf-8")

        print(f"Done: {student_name} -> {workdir/'feedback.md'}")
        if progress_callback is not None:
            progress_callback({
                "status": "running",
                "processed": index,
                "total": len(subs),
                "current_student": student_name,
            })

    was_cancelled = should_cancel is not None and should_cancel()

    for filename in ["summary.xlsx", "summary1.xlsx"]:
        xlsx_path = out_root / filename
        try:
            write_assignment_summary_xlsx(rows_for_excel, str(xlsx_path))
            print(f"Wrote Excel summary: {xlsx_path}")
        except PermissionError:
            print(f"Could not write Excel summary because it is open or locked: {xlsx_path}")

    return {
        "status": "cancelled" if was_cancelled else "completed",
        "course_id": course_id,
        "assignment_id": assignment_id,
        "processed": len(rows_for_excel),
        "output_dir": str(out_root),
        "summary_path": str(out_root / "summary1.xlsx"),
    }


def main(config_path: str, limit: int | None = None, user_id: int | None = None):
    if not CANVAS_TOKEN:
        raise RuntimeError("CANVAS_API_TOKEN is not set")

    cfg = json.loads(pathlib.Path(config_path).read_text(encoding="utf-8"))
    canvas = CanvasClient(CANVAS_BASE_URL, CANVAS_TOKEN)
    result = run_precheck(cfg, canvas, limit=limit, user_id=user_id)
    if result.get("status") == "empty":
        print(result["message"])

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument(
        "--config",
        default="configs/a6.json",
        help="Path to assignment config JSON (default: configs/a6.json)"
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N submissions after filtering."
    )
    p.add_argument(
        "--user-id",
        type=int,
        default=None,
        help="Process only one Canvas user ID."
    )
    args = p.parse_args()
    main(args.config, limit=args.limit, user_id=args.user_id)
