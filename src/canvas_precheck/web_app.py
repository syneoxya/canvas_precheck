from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from canvas_precheck.canvas_client import CanvasClient
from canvas_precheck.run_precheck import CANVAS_BASE_URL, run_precheck


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).resolve().parent / "web_static"
RUNS_DIR = PROJECT_ROOT / "runs"


app = FastAPI(title="Canvas Precheck")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

CANVAS_SETTINGS = {
    "base_url": os.getenv("CANVAS_BASE_URL", CANVAS_BASE_URL),
    "token": os.getenv("CANVAS_API_TOKEN", ""),
}
OPENAI_SETTINGS = {
    "token": os.getenv("OPENAI_API_KEY", ""),
}
RUN_PROGRESS = {
    "status": "idle",
    "processed": 0,
    "total": 0,
    "current_student": "",
    "cancel_requested": False,
}


class RunRequest(BaseModel):
    config_path: str = "configs/a6.json"
    course_id: int | None = None
    assignment_id: int | None = None
    limit: int | None = 1
    user_id: int | None = None


class CanvasSettingsRequest(BaseModel):
    token: str
    base_url: str = "https://jhu.instructure.com"


class OpenAISettingsRequest(BaseModel):
    token: str


class ConfigSaveRequest(BaseModel):
    config_path: str = "configs/a6.json"
    config: dict[str, Any]


def _canvas() -> CanvasClient:
    token = CANVAS_SETTINGS.get("token") or os.getenv("CANVAS_API_TOKEN", "")
    base_url = CANVAS_SETTINGS.get("base_url") or os.getenv("CANVAS_BASE_URL", CANVAS_BASE_URL)
    if not token:
        raise HTTPException(status_code=400, detail="CANVAS_API_TOKEN is not set")
    return CanvasClient(base_url, token)


def _load_config(config_path: str) -> dict[str, Any]:
    path = (PROJECT_ROOT / config_path).resolve()
    if not str(path).startswith(str(PROJECT_ROOT.resolve())):
        raise HTTPException(status_code=400, detail="Config path must stay inside the project")
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Config not found: {config_path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _config_file_path(config_path: str) -> Path:
    path = (PROJECT_ROOT / config_path).resolve()
    configs_root = (PROJECT_ROOT / "configs").resolve()
    if not str(path).startswith(str(configs_root)):
        raise HTTPException(status_code=400, detail="Config path must stay inside configs/")
    if path.suffix != ".json":
        raise HTTPException(status_code=400, detail="Config file must be JSON")
    return path


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _overall_from_llm(llm: dict[str, Any] | None) -> str:
    if not llm:
        return ""
    overall = str(llm.get("overall") or "").strip()
    if overall:
        return overall
    parts = []
    for item in llm.get("items", []) or []:
        rubric = str(item.get("rubric_item") or "").strip()
        finding = str(item.get("finding") or "").strip()
        if rubric and finding:
            parts.append(f"{rubric}: {finding}")
    return " ".join(parts)[:600]


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    token = CANVAS_SETTINGS.get("token") or os.getenv("CANVAS_API_TOKEN", "")
    base_url = CANVAS_SETTINGS.get("base_url") or os.getenv("CANVAS_BASE_URL", CANVAS_BASE_URL)
    openai_token = OPENAI_SETTINGS.get("token") or os.getenv("OPENAI_API_KEY", "")
    return {
        "ok": True,
        "canvas_token_set": bool(token),
        "canvas_base_url": base_url,
        "token_source": "website" if CANVAS_SETTINGS.get("token") else "terminal" if os.getenv("CANVAS_API_TOKEN") else "unset",
        "openai_token_set": bool(openai_token),
        "openai_token_source": "website" if OPENAI_SETTINGS.get("token") else "terminal" if os.getenv("OPENAI_API_KEY") else "unset",
    }


@app.post("/api/settings/canvas")
def set_canvas_settings(req: CanvasSettingsRequest) -> dict[str, Any]:
    token = req.token.strip()
    base_url = req.base_url.strip().rstrip("/")
    if not token:
        raise HTTPException(status_code=400, detail="Canvas token cannot be empty")
    if not base_url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Canvas base URL must start with https://")

    CANVAS_SETTINGS["token"] = token
    CANVAS_SETTINGS["base_url"] = base_url

    return {
        "ok": True,
        "canvas_token_set": True,
        "canvas_base_url": base_url,
        "message": "Canvas settings saved for this server session only.",
    }


@app.post("/api/settings/openai")
def set_openai_settings(req: OpenAISettingsRequest) -> dict[str, Any]:
    token = req.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="OpenAI API token cannot be empty")
    OPENAI_SETTINGS["token"] = token
    return {
        "ok": True,
        "openai_token_set": True,
        "message": "OpenAI token saved for this server session only. Ollama remains active until config llm.provider is set to openai.",
    }


@app.get("/api/courses")
def courses() -> list[dict[str, Any]]:
    return [
        {
            "id": c.get("id"),
            "name": c.get("name") or c.get("course_code") or f"Course {c.get('id')}",
            "course_code": c.get("course_code", ""),
            "workflow_state": c.get("workflow_state", ""),
        }
        for c in _canvas().list_courses()
    ]


@app.get("/api/config")
def get_config(config_path: str = "configs/a6.json") -> dict[str, Any]:
    return {
        "config_path": config_path,
        "config": _load_config(config_path),
    }


@app.post("/api/config")
def save_config(req: ConfigSaveRequest) -> dict[str, Any]:
    path = _config_file_path(req.config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(req.config, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "config_path": str(path.relative_to(PROJECT_ROOT)),
        "message": f"Saved {path.relative_to(PROJECT_ROOT)}",
    }


@app.get("/api/courses/{course_id}/assignments")
def assignments(course_id: int) -> list[dict[str, Any]]:
    return [
        {
            "id": a.get("id"),
            "name": a.get("name") or f"Assignment {a.get('id')}",
            "due_at": a.get("due_at"),
            "points_possible": a.get("points_possible"),
            "published": a.get("published"),
        }
        for a in _canvas().list_assignments(course_id)
    ]


@app.post("/api/runs")
def start_run(req: RunRequest) -> dict[str, Any]:
    cfg = _load_config(req.config_path)
    if req.course_id is not None:
        cfg["course_id"] = req.course_id
    if req.assignment_id is not None:
        cfg["assignment_id"] = req.assignment_id
    openai_key = OPENAI_SETTINGS.get("token") or os.getenv("OPENAI_API_KEY", "")
    RUN_PROGRESS.update({
        "status": "starting",
        "processed": 0,
        "total": 0,
        "current_student": "",
        "cancel_requested": False,
    })
    try:
        result = run_precheck(
            cfg,
            _canvas(),
            limit=req.limit,
            user_id=req.user_id,
            openai_api_key=openai_key,
            progress_callback=lambda update: RUN_PROGRESS.update(update),
            should_cancel=lambda: bool(RUN_PROGRESS.get("cancel_requested")),
        )
        RUN_PROGRESS.update({
            "status": result.get("status", "completed"),
            "processed": result.get("processed", RUN_PROGRESS.get("processed", 0)),
            "current_student": "",
        })
        return result
    except Exception:
        RUN_PROGRESS.update({"status": "failed"})
        raise


@app.get("/api/runs/progress")
def run_progress() -> dict[str, Any]:
    return dict(RUN_PROGRESS)


@app.post("/api/runs/cancel")
def cancel_run() -> dict[str, Any]:
    if RUN_PROGRESS.get("status") not in {"starting", "running"}:
        return {
            "ok": True,
            "message": "No active run to cancel.",
            "status": RUN_PROGRESS.get("status", "idle"),
        }

    RUN_PROGRESS.update({
        "cancel_requested": True,
        "status": "cancelling",
    })
    return {
        "ok": True,
        "message": "Cancellation requested. The current student will finish, then the run will stop.",
        "status": "cancelling",
    }


@app.get("/api/runs")
def list_runs() -> list[dict[str, Any]]:
    runs = []
    for assignment_dir in sorted(RUNS_DIR.glob("course_*/assignment_*")):
        if not assignment_dir.is_dir():
            continue
        student_count = len([p for p in assignment_dir.glob("user_*") if p.is_dir()])
        runs.append({
            "course_id": assignment_dir.parent.name.replace("course_", ""),
            "assignment_id": assignment_dir.name.replace("assignment_", ""),
            "student_count": student_count,
            "path": str(assignment_dir.relative_to(PROJECT_ROOT)),
            "has_summary": (assignment_dir / "summary1.xlsx").exists() or (assignment_dir / "summary.xlsx").exists(),
        })
    return runs


@app.get("/api/runs/{course_id}/{assignment_id}/students")
def run_students(course_id: int, assignment_id: int) -> list[dict[str, Any]]:
    root = RUNS_DIR / f"course_{course_id}" / f"assignment_{assignment_id}"
    if not root.exists():
        raise HTTPException(status_code=404, detail="Run output not found")

    students = []
    for user_dir in sorted(root.glob("user_*")):
        fb = _read_json(user_dir / "feedback.json")
        llm = _read_json(user_dir / "llm.json")
        metadata = (fb or {}).get("metadata", {})
        students.append({
            "user_id": metadata.get("user_id") or user_dir.name.replace("user_", ""),
            "student_name": metadata.get("student_name") or user_dir.name,
            "is_late": (fb or {}).get("is_late", False),
            "findings_count": len((fb or {}).get("findings", [])),
            "overall": _overall_from_llm(llm),
            "has_feedback": (user_dir / "feedback.md").exists(),
        })
    return students


@app.get("/api/runs/{course_id}/{assignment_id}/students/{user_id}")
def student_detail(course_id: int, assignment_id: int, user_id: int) -> dict[str, Any]:
    user_dir = RUNS_DIR / f"course_{course_id}" / f"assignment_{assignment_id}" / f"user_{user_id}"
    if not user_dir.exists():
        raise HTTPException(status_code=404, detail="Student output not found")
    feedback_md = user_dir / "feedback.md"
    return {
        "feedback": _read_json(user_dir / "feedback.json"),
        "llm": _read_json(user_dir / "llm.json"),
        "feedback_md": feedback_md.read_text(encoding="utf-8") if feedback_md.exists() else "",
        "files": [p.name for p in user_dir.iterdir() if p.is_file()],
    }


@app.get("/api/runs/{course_id}/{assignment_id}/summary")
def summary_file(course_id: int, assignment_id: int) -> FileResponse:
    root = RUNS_DIR / f"course_{course_id}" / f"assignment_{assignment_id}"
    for name in ["summary1.xlsx", "summary.xlsx"]:
        path = root / name
        if path.exists():
            return FileResponse(path, filename=name)
    raise HTTPException(status_code=404, detail="Summary file not found")


@app.get("/api/runs/{course_id}/{assignment_id}/students/{user_id}/feedback.md")
def feedback_markdown(course_id: int, assignment_id: int, user_id: int) -> PlainTextResponse:
    path = RUNS_DIR / f"course_{course_id}" / f"assignment_{assignment_id}" / f"user_{user_id}" / "feedback.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Feedback markdown not found")
    return PlainTextResponse(path.read_text(encoding="utf-8"))
