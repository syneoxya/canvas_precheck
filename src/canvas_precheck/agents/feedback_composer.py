import os
from canvas_precheck.models import FeedbackJSON, LLMJSON
from canvas_precheck.utils import time_ago

class FeedbackComposerAgent:
    name = "FeedbackComposerAgent"

    def run(self, state: dict) -> dict:
        fb: FeedbackJSON = state["feedback"]
        llm: LLMJSON | None = state.get("llm")
        workdir = state["workdir"]

        lines = []
        lines.append(f"## Preliminary checks — {fb.metadata.student_name}")
        lines.append("")
        lines.append(f"- Submitted at: {fb.metadata.submitted_at}")
        lines.append(f"- Due at: {fb.metadata.due_at}")
        lines.append(f"- Late: {'Yes' if fb.is_late else 'No'}" + (f" (by {time_ago(fb.late_by_seconds)})" if fb.is_late else ""))
        lines.append(f"- Filename OK: {'Yes' if fb.filename_ok else 'No'}")
        lines.append("")

        if fb.findings:
            lines.append("### Findings")
            for f in fb.findings:
                lines.append(f"- **[{f.severity}]** {f.message}")
            lines.append("")

        if fb.test_results:
            lines.append("### Tests")
            for name, r in fb.test_results.items():
                lines.append(f"- {name}: {'PASS' if r.get('passed') else 'FAIL'}")
            lines.append("")

        if llm and (llm.items or llm.section_scores or llm.overall_score is not None or llm.overall):
            lines.append("### LLM review")
            if llm.section_scores or llm.overall_score is not None:
                lines.append("#### Scores")
                for section, score in llm.section_scores.items():
                    lines.append(f"- {section.title()}: {round(score)}/100")
                if llm.overall_score is not None:
                    lines.append(f"- Aggregate: {round(llm.overall_score)}/100")
                lines.append("")
            for it in llm.items:
                lines.append(f"- **{it.rubric_item}**: {it.finding}")
                lines.append(f"  - Suggestion: {it.suggestion}")
                if it.evidence_keys:
                    lines.append(f"  - Evidence: {', '.join(it.evidence_keys)}")
            lines.append("")
            lines.append(f"**Overall:** {llm.overall}")

        out_path = os.path.join(workdir, "feedback.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        state.setdefault("artifacts", {})["feedback_md"] = out_path
        return state
