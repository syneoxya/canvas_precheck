# Canvas Precheck – Multi-Agent Assignment Pre-Grading System

Canvas Precheck is a config-driven, multi-agent system for performing automated preliminary checks on Canvas assignments.
It pulls submissions from Canvas, runs deterministic checks and LLM-based reviews, and generates structured feedback for instructors and TAs.

The system is designed to scale across:
- multiple courses
- multiple assignments
- different assignment types (writing, coding, mixed)

------------------------------------------------------------
1. Installation & Setup
------------------------------------------------------------

1.1 Prerequisites
- Python 3.10+
- Access to a Canvas course 
- A Canvas API token
- An OpenAI API key

------------------------------------------------------------

1.2 Clone the repository

    git clone https://github.com/JalIrani/agent-feedback.git
    cd canvas-precheck

------------------------------------------------------------

1.3 Install dependencies (editable mode)

    pip install -e .

------------------------------------------------------------

1.4 Set environment variables

    export CANVAS_API_TOKEN="your_canvas_api_token"
    export OPENAI_API_KEY="your_openai_api_key"
    export CANVAS_BASE_URL="https://jhu.instructure.com"

Important:
Always use the canonical *.instructure.com domain for Canvas APIs.
Vanity domains (e.g. canvas.jhu.edu) may be blocked by Cloudflare.

------------------------------------------------------------
2. Running the System
------------------------------------------------------------

2.1 Prepare an assignment config

Assignment behavior is fully controlled by JSON config files.

Example: configs/a6.json

    {
      "course_id": 99716,
      "assignment_id": 1054077,

      "expected_filenames": ["a6.pdf"],
      "filename_aliases": {
        "assignment6.pdf": "a6.pdf",
        "Assignment 6.pdf": "a6.pdf"
      },

      "allowed_extensions": [".pdf", ".ipynb", ".py", ".md"],
      "required_files": ["a6.pdf"],

      "tests": [
        {
          "name": "nl_smoke",
          "type": "nl_check",
          "rules": [{ "id": "min_length", "min_chars": 800 }]
        }
      ],

      "llm": { "enabled": true, "model": "gpt-4.1-mini" },
      "posting": { "enabled": false }
    }

------------------------------------------------------------

2.2 Run the pipeline

From the project root:

    python -m canvas_precheck.run_precheck --config configs/a6.json

------------------------------------------------------------

2.3 Output structure

Results are written to:

    runs/
    └── course_<course_id>/
        └── assignment_<assignment_id>/
            └── user_<user_id>/
                ├── feedback.json
                ├── feedback.md
                └── llm.json

- feedback.json → structured machine-readable results
- feedback.md   → TA-friendly human-readable feedback
- llm.json      → raw LLM evaluation output

------------------------------------------------------------
3. System Architecture
------------------------------------------------------------

The pipeline is composed of independent agents, executed sequentially.
Each agent:
- reads from shared state
- appends evidence or annotations
- never mutates raw submissions

------------------------------------------------------------

3.1 CanvasClient
Responsibility: Canvas API interaction

- Lists assignments and submissions
- Downloads submission attachments
- Handles authentication and rate limits

------------------------------------------------------------

3.2 Pipeline
Responsibility: Agent orchestration

- Executes agents in a fixed order
- Passes a shared state dictionary
- Enables modular extension and reordering

------------------------------------------------------------
4. Agents
------------------------------------------------------------

4.1 IntakeAgent
Purpose: Submission metadata validation

Checks:
- submission timestamp vs due date
- late status and lateness duration
- student identity
- attachment name normalization

Adds:
- evidence keys (e.g. late_by, filename_mismatch)
- normalized filenames

------------------------------------------------------------

4.2 FileStructureAgent
Purpose: File system and archive validation

Checks:
- allowed file extensions
- required files present
- ZIP flattening and directory sanity

Outputs:
- file inventory
- missing or invalid files

------------------------------------------------------------

4.3 TestRunnerAgent
Purpose: Assignment-specific automated tests

Driven by config:
- natural language checks
- basic content validation
- extensible to unit tests for coding assignments

Adds:
- pass/fail test results
- structured evidence

------------------------------------------------------------

4.4 LLMReviewerAgent
Purpose: High-level qualitative review

Consumes:
- structured feedback
- allowed evidence keys
- assignment-specific prompts

Guarantees:
- strict JSON output
- schema-safe validation
- evidence-backed suggestions

Outputs:
- rubric-style feedback
- actionable improvement suggestions

------------------------------------------------------------

4.5 FeedbackComposerAgent
Purpose: Final feedback synthesis

Combines:
- deterministic checks
- test results
- LLM suggestions

Produces:
- feedback.md (human-readable)
- feedback.json (machine-readable)

------------------------------------------------------------

4.6 LMSPosterAgent (NOT YET IMPLEMENTED / NOT WORKING)
Purpose: Post feedback back to Canvas

Status:
- Not yet implemented
- Posting is disabled and treated as a stub
- Feedback is generated locally only

Planned functionality:
- Post comments to Canvas submissions
- Config-controlled enable/disable
- Dry-run safety mode

------------------------------------------------------------
5. Design Principles
------------------------------------------------------------

- Config-first: No hardcoded assignment logic
- Deterministic before LLMs: Rules first, LLMs second
- Evidence-based feedback: All suggestions cite evidence
- Safe by default: No Canvas mutations unless enabled
- Scalable: New assignments require only new configs

------------------------------------------------------------
6. Project Status
------------------------------------------------------------

- Core pipeline complete
- Canvas API integration validated
- Multi-agent execution working
- LLM feedback generation working
- Canvas posting not yet implemented

------------------------------------------------------------
7. Future Extensions
------------------------------------------------------------

- Assignment-type routing (writing vs coding)
- CLI commands (list-assignments, dry-run)
- Parallel processing for large courses
- Docker and CI support
