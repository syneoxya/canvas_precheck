# Canvas Precheck

Canvas Precheck is a local web app and Python pipeline for reviewing Canvas assignment submissions before final grading. It downloads student submissions from Canvas, reads every supported file a student submitted, runs deterministic checks, optionally asks an LLM for feedback, and writes per-student feedback plus an Excel summary.

It is designed for assignments that may include coding files, notebooks, PDFs, Word docs, Markdown reports, text files, CSV/JSON files, and mixed submissions.

## Features

- Canvas API integration for courses, assignments, submissions, and attachment downloads
- Local FastAPI web app at `http://127.0.0.1:8000`
- Per-assignment JSON configuration
- Canvas token entry through the web UI or environment variables
- Supports local Ollama models, including `qwen2.5:3b`
- Supports OpenAI models when configured
- Reads all supported files submitted by each student
- Handles ZIP extraction
- Preserves original filenames when configured
- Groups extracted content into coding, writing, and document sections
- Produces per-student `feedback.md`, `feedback.json`, and `llm.json`
- Produces assignment-level `summary.xlsx` and `summary1.xlsx`
- Safe by default: Canvas posting is disabled unless explicitly enabled

## Requirements

- Python 3.10 or newer
- Canvas API token
- Access to the Canvas course/assignment
- Optional: Ollama for local LLM review
- Optional: OpenAI API key for OpenAI-based review
- Optional: Tesseract for OCR fallback on image-based PDFs

## Install

Clone the repo:

```bash
git clone https://github.com/syneoxya/canvas_precheck.git
cd canvas_precheck
```

Create and activate an environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install the package in editable mode:

```bash
pip install -e .
```

The editable install reads dependencies from `pyproject.toml`, including FastAPI, Uvicorn, PDF/doc extraction libraries, LangChain, and Excel export support.

## Canvas Setup

Create a Canvas API token from your Canvas account settings.

Use the canonical Instructure domain for API calls:

```text
https://jhu.instructure.com
```

Avoid vanity domains such as `canvas.jhu.edu`; Canvas API requests may be blocked by Cloudflare when using them.

You can enter the Canvas token in the web UI after launching the app. Alternatively, export it in your shell:

```bash
export CANVAS_API_TOKEN="your_canvas_api_token"
export CANVAS_BASE_URL="https://jhu.instructure.com"
```

Do not commit API tokens. The old local `secrets.py` approach has been removed.

## Ollama Setup

Install Ollama from:

```text
https://ollama.com
```

Pull Qwen:

```bash
ollama pull qwen2.5:3b
```

Start Ollama if it is not already running:

```bash
ollama serve
```

If the port is already in use, Ollama is already running.

Check the server:

```bash
curl http://localhost:11434/api/version
```

List installed models:

```bash
curl http://localhost:11434/api/tags
```

Use Ollama in a config like this:

```json
"llm": {
  "enabled": true,
  "provider": "ollama",
  "model": "qwen2.5:3b"
}
```

## OpenAI Setup

If you want to use OpenAI instead of Ollama, set:

```bash
export OPENAI_API_KEY="your_openai_api_key"
```

And configure:

```json
"llm": {
  "enabled": true,
  "provider": "openai",
  "model": "gpt-4.1-mini"
}
```

The web UI can also accept an OpenAI key for the current server session.

## Run The Local Website

From the repo root:

```bash
python -m uvicorn canvas_precheck.web_app:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

The UI lets you:

- Enter Canvas and OpenAI tokens for the current server session
- Load and edit assignment config JSON
- Select courses and assignments from Canvas
- Run a precheck for one or more students
- Watch run progress
- Browse generated runs
- Read per-student feedback and raw LLM output
- Download the Excel summary

If you restart the server, tokens entered through the UI are cleared and must be entered again.

## Run From The CLI

You can also run the pipeline directly:

```bash
python -m canvas_precheck.run_precheck --config configs/a6.json
```

Process only the first N submissions:

```bash
python -m canvas_precheck.run_precheck --config configs/a6.json --limit 5
```

Process one Canvas user:

```bash
python -m canvas_precheck.run_precheck --config configs/a6.json --user-id 141124
```

## Assignment Config

Assignment behavior is controlled by JSON files in `configs/`.

Current all-files grading style:

```json
{
  "course_id": 99716,
  "assignment_id": 1054077,
  "preserve_original_filenames": true,
  "allowed_extensions": [],
  "required_files": [],
  "zip_policy": {
    "allow_zip": true,
    "flatten": true
  },
  "content_extract": {
    "enabled": true,
    "max_chars": 12000,
    "chunk_chars": 3000,
    "max_chunks": 4,
    "min_pdf_text_chars_for_ocr": 500,
    "ocr_enabled": true,
    "prefer_extensions": [
      ".ipynb",
      ".pdf",
      ".py",
      ".r",
      ".json",
      ".csv",
      ".docx",
      ".md",
      ".txt"
    ]
  },
  "tests": [
    {
      "name": "nl_smoke",
      "type": "nl_check",
      "rules": [
        { "id": "min_length", "min_chars": 800 }
      ]
    }
  ],
  "llm": {
    "enabled": true,
    "provider": "ollama",
    "model": "qwen2.5:3b"
  },
  "llm_prompts": [
    {
      "name": "mixed_review",
      "prompt_template": "Review each present section independently and return section scores plus one aggregate score."
    }
  ],
  "posting": {
    "enabled": false
  }
}
```

Important config fields:

- `course_id`: Canvas course ID
- `assignment_id`: Canvas assignment ID
- `preserve_original_filenames`: keeps submitted filenames instead of renaming everything to one canonical assignment name
- `allowed_extensions`: when empty, files are not rejected by extension; extraction still only reads supported types
- `required_files`: when empty, the grader does not fail students for missing specifically named files
- `zip_policy.allow_zip`: allows ZIP submissions
- `zip_policy.flatten`: copies ZIP contents into the student work directory
- `content_extract.prefer_extensions`: file types the extractor will try to read
- `llm.provider`: `ollama` or `openai`
- `posting.enabled`: should remain `false` unless Canvas posting is intentionally implemented and tested

## How File Reading Works

For each student, the system downloads submitted attachments into:

```text
runs/course_<course_id>/assignment_<assignment_id>/user_<user_id>/
```

The extractor reads all supported files in the inventory, including duplicate files saved under `dupes/`.

Supported readable types currently include:

- `.ipynb`
- `.pdf`
- `.py`
- `.r`
- `.json`
- `.csv`
- `.docx`
- `.md`
- `.txt`

Content is grouped into evidence sections:

- `content.coding.preview` for notebooks and code files
- `content.writing.preview` for PDF and Word writing
- `content.document.preview` for generic documents/data
- `content.preview` for the combined preview

The LLM is asked to grade each present section independently and produce one aggregate score for the student.

## Outputs

Each student gets:

```text
feedback.json
feedback.md
llm.json
```

Each assignment run also gets:

```text
summary.xlsx
summary1.xlsx
```

The Excel summary includes:

- Student name
- What was done well
- What is missing
- What can be improved
- Overall feedback
- Coding grade
- Writing grade
- Aggregate grade

## Pipeline Architecture

The pipeline runs these agents in order:

1. `IntakeAgent`: records metadata, downloads attachments, handles filenames, lateness, duplicates, and file inventory
2. `FileStructureAgent`: handles ZIP extraction and required-file checks
3. `ContentExtractAgent`: extracts text from notebooks, PDFs, code, docs, Markdown, text, CSV, and JSON
4. `TestRunnerAgent`: runs simple configured natural-language checks
5. `LLMReviewerAgent` or `OllamaReviewerAgent`: generates content feedback and grades
6. `FeedbackComposerAgent`: writes student-facing markdown feedback
7. `LMSPosterAgent`: placeholder for Canvas posting; disabled by default

## Notes On Local Models

Small local models can sometimes return malformed JSON or numeric scores without written feedback. The Ollama reviewer includes defensive parsing, score recovery, and a retry that asks for the three written sections when the first response only contains scores.

For more reliable written feedback, use a larger local model or an OpenAI model.

## Troubleshooting

`CANVAS_API_TOKEN is not set`:

Set the token in the UI or export `CANVAS_API_TOKEN`.

Canvas course list fails:

Use `https://jhu.instructure.com` as the base URL and confirm the token has access.

Ollama is not reachable:

Run `ollama serve`, then check `curl http://localhost:11434/api/version`.

Ollama returns only scores:

Rerun the student or assignment. The reviewer retries once, but local small models may still omit prose.

PDF text is empty:

Install Tesseract and keep `ocr_enabled` set to `true`.

Local web app does not reload code changes:

Stop and restart Uvicorn. Running without `--reload` avoids macOS file-watcher permission issues.

## Development

Compile-check the package:

```bash
python -m compileall src/canvas_precheck
```

Check JSON config formatting:

```bash
python -m json.tool configs/a6.json
```

Check Git status:

```bash
git status --short
```
