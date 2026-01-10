Below is a complete, polished README.md you can copy-paste directly into your repo.
It is written at the level your professor / TA / technical reviewer expects.

⸻

Canvas Pre-Check System (Multi-Agent Assignment Tool)

Overview

This project implements a configurable, multi-agent system for performing preliminary checks on Canvas assignment submissions.

The system is designed to:
	•	Automatically pull submissions from Canvas
	•	Run deterministic checks (lateness, filenames, file structure)
	•	Run assignment-specific tests
	•	Optionally apply an LLM-based reviewer using LangChain
	•	Generate structured feedback
	•	(Optionally) post feedback back to Canvas

The goal is not auto-grading, but standardized pre-checks and feedback to support instructors and TAs.

⸻

High-Level Architecture

The system follows a pipeline of specialized agents, each responsible for one stage of processing.

Canvas API
   ↓
IntakeAgent
   ↓
FileStructureAgent
   ↓
TestRunnerAgent
   ↓
LLMReviewerAgent (optional, LangChain)
   ↓
FeedbackComposerAgent
   ↓
LMSPosterAgent (optional)

Each agent:
	•	Takes a shared state object
	•	Adds information or artifacts
	•	Passes the updated state to the next agent

This makes the system modular, debuggable, and scalable.

⸻

Features

Implemented
	•	Canvas API integration
	•	Per-assignment configuration via JSON
	•	Late submission detection (with time delta)
	•	Filename normalization and validation
	•	File type and ZIP structure checks
	•	Assignment-specific test rules
	•	Structured feedback (feedback.json)
	•	Human-readable feedback (feedback.md)
	•	Optional LLM review using LangChain
	•	Optional posting back to Canvas

Not Yet Implemented (by design)
	•	Full grading logic
	•	PDF text extraction
	•	Sandboxed code execution (e.g., Docker)
	•	OAuth / LTI deployment

⸻

Project Structure

canvas-precheck/
│
├── configs/
│   └── a6.json                  # Assignment configuration
│
├── runs/
│   └── course_<id>/
│       └── assignment_<id>/
│           └── user_<id>/        # Per-student outputs
│               ├── feedback.json
│               ├── llm.json
│               └── feedback.md
│
├── src/
│   ├── run_precheck.py           # Main runner
│   │
│   └── canvas_precheck/
│       ├── __init__.py
│       ├── secrets.py            # API keys (local only)
│       ├── models.py             # Pydantic schemas
│       ├── utils.py
│       ├── canvas_client.py
│       ├── pipeline.py
│       │
│       └── agents/
│           ├── intake.py
│           ├── file_structure.py
│           ├── test_runner.py
│           ├── llm_reviewer.py
│           ├── feedback_composer.py
│           └── lms_poster.py


⸻

Requirements
	•	Python 3.10+
	•	Conda or virtualenv
	•	Canvas API access token
	•	(Optional) OpenAI API key

Python dependencies:

requests
pydantic
python-dateutil
langchain
langchain-openai


⸻

Setup Instructions

1. Create Conda Environment

conda create -n canvas-precheck python=3.10 -y
conda activate canvas-precheck

2. Install Dependencies

pip install requests pydantic python-dateutil langchain langchain-openai


⸻

API Keys (Local Development)

For development, API keys are stored directly in Python (Option 1).

Create:

src/canvas_precheck/secrets.py

CANVAS_BASE_URL = "https://your-school.instructure.com"
CANVAS_TOKEN = "YOUR_CANVAS_API_TOKEN"
OPENAI_API_KEY = "YOUR_OPENAI_KEY"   # Optional

⚠️ Important
	•	Do not commit this file to GitHub
	•	Add to .gitignore:

src/canvas_precheck/secrets.py



The system is designed so this can later be replaced with environment variables without refactoring.

⸻

Assignment Configuration

Each assignment is defined by a JSON config file.

Example: configs/a6.json

{
  "course_id": 12345,
  "assignment_id": 67890,

  "expected_filenames": ["a6.pdf"],
  "filename_aliases": {
    "assignment6.pdf": "a6.pdf"
  },

  "allowed_extensions": [".pdf", ".zip", ".txt", ".md"],
  "required_files": ["a6.pdf"],
  "zip_policy": { "allow_zip": true, "flatten": true },

  "tests": [
    {
      "name": "nl_smoke",
      "type": "nl_check",
      "rules": [
        { "id": "min_length", "min_chars": 800 }
      ]
    }
  ],

  "llm": { "enabled": true, "model": "gpt-4.1-mini" },
  "llm_prompts": [
    {
      "name": "a6_review",
      "prompt_template": "Review the submission for clarity and completeness."
    }
  ],

  "posting": { "enabled": false }
}

This design allows new assignments to be added without code changes.

⸻

Running the System

From the project root:

python src/run_precheck.py configs/a6.json

What happens:
	•	Submissions are fetched from Canvas
	•	Files are downloaded per student
	•	Checks and tests are run
	•	Feedback is generated

⸻

Output Files

For each student:

runs/course_<course_id>/assignment_<assignment_id>/user_<user_id>/
├── feedback.json   # Structured machine-readable output
├── llm.json        # LLM output (if enabled)
└── feedback.md     # Human-readable feedback

