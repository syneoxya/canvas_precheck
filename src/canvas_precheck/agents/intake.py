import os
from canvas_precheck.models import FeedbackJSON, Finding
from canvas_precheck.utils import normalize_filename, ext_allowed

class IntakeAgent:
    name = "IntakeAgent"

    def __init__(self, canvas_client):
        self.canvas = canvas_client

    def run(self, state: dict) -> dict:
        cfg = state["config"]
        fb: FeedbackJSON = state["feedback"]
        meta = fb.metadata
        workdir = state["workdir"]
        os.makedirs(workdir, exist_ok=True)

        # evidence keys
        fb.evidence["meta.student_name"] = meta.student_name
        fb.evidence["meta.submitted_at"] = str(meta.submitted_at)
        fb.evidence["meta.due_at"] = str(meta.due_at)

        # late check
        late_sec = 0
        if meta.submitted_at and meta.due_at:
            late_sec = int(max(0, (meta.submitted_at - meta.due_at).total_seconds()))
        fb.is_late = late_sec > 0
        fb.late_by_seconds = late_sec
        if fb.is_late:
            fb.findings.append(Finding(
                key="late_submission",
                severity="warning",
                message=f"Submitted late by {late_sec} seconds.",
                evidence_keys=["meta.submitted_at", "meta.due_at"]
            ))

        expected = cfg.get("expected_filenames", [])
        aliases = cfg.get("filename_aliases", {})
        allowed_exts = cfg.get("allowed_extensions", [])

        filename_ok = True

        for att in meta.attachments:
            url = att.get("url")
            orig = att.get("filename", "attachment")
            if not url:
                continue

            normalized, was_norm, is_expected = normalize_filename(orig, aliases, expected)

            if expected and not is_expected:
                filename_ok = False
                fb.findings.append(Finding(
                    key="filename_unexpected",
                    severity="warning",
                    message=f"Unexpected filename '{orig}'. Expected one of {expected}."
                ))

            if was_norm:
                fb.findings.append(Finding(
                    key="filename_normalized",
                    severity="info",
                    message=f"Renamed '{orig}' -> '{normalized}'."
                ))

            dest = os.path.join(workdir, normalized)
            self.canvas.download_file(url, dest)

            if allowed_exts and not ext_allowed(dest, allowed_exts):
                fb.findings.append(Finding(
                    key="filetype_not_allowed",
                    severity="error",
                    message=f"File type not allowed: {normalized}. Allowed: {allowed_exts}"
                ))

            fb.file_inventory.append(dest)

        fb.filename_ok = filename_ok
        state["feedback"] = fb
        return state