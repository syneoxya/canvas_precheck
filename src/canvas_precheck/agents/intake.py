import os
from canvas_precheck.models import FeedbackJSON, Finding
from canvas_precheck.utils import ext_allowed, canonicalize_filename


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

        # config
        expected = cfg.get("expected_filenames", [])
        allowed_exts = cfg.get("allowed_extensions", [])
        preserve_original_filenames = bool(cfg.get("preserve_original_filenames", False))
        canonical_base = cfg.get("canonical_filename", "a6")

        filename_ok = True

        # Track which canonical destination filenames have already been created in root
        # This enforces the invariant: canonical stays in root; duplicates go to dupes/
        seen_dest_names = set()

        for att in meta.attachments:
            url = att.get("url")
            orig = att.get("filename", "attachment")
            if not url:
                continue

            if preserve_original_filenames:
                normalized = os.path.basename(orig)
                _ext = os.path.splitext(normalized)[1]
            else:
                # Force canonical naming: a6.<original extension>
                normalized, _ext = canonicalize_filename(orig, canonical_base)

            # Evidence + warning if student didn't follow naming convention
            if not preserve_original_filenames and orig != normalized:
                k = f"filename_map.{orig}"
                fb.evidence[k] = normalized
                fb.findings.append(Finding(
                    key="filename_noncanonical",
                    severity="warning",
                    message=f"Filename '{orig}' does not follow required naming. Using '{normalized}'.",
                    evidence_keys=[k]
                ))

            # If you set expected_filenames, treat canonical output as expected
            # (This keeps the check meaningful but not brittle.)
            if expected and (normalized not in expected):
                filename_ok = False
                fb.findings.append(Finding(
                    key="filename_unexpected",
                    severity="warning",
                    message=f"Unexpected canonical filename '{normalized}'. Expected one of {expected}."
                ))

            root_dest = os.path.join(workdir, normalized)

            # Duplicate handling:
            # - First time we see this normalized name -> keep it in root
            # - Subsequent times -> save into dupes/ with __dup suffix
            if normalized in seen_dest_names:
                dupes_dir = os.path.join(workdir, "dupes")
                os.makedirs(dupes_dir, exist_ok=True)

                base, ext = os.path.splitext(normalized)
                i = 2
                while True:
                    dup_name = f"{base}__dup{i}{ext}"
                    dup_dest = os.path.join(dupes_dir, dup_name)
                    if not os.path.exists(dup_dest):
                        break
                    i += 1

                fb.findings.append(Finding(
                    key="filename_duplicate",
                    severity="warning",
                    message=f"Multiple attachments resolved to destination '{normalized}'. Keeping additional copy as '{dup_name}' in dupes/."
                ))

                self.canvas.download_file(url, dup_dest)

                if allowed_exts and not ext_allowed(dup_dest, allowed_exts):
                    fb.findings.append(Finding(
                        key="filetype_not_allowed",
                        severity="error",
                        message=f"File type not allowed: {dup_name}. Allowed: {allowed_exts}"
                    ))

                fb.file_inventory.append(dup_dest)
                continue  # Do not overwrite canonical; grade the duplicate copy too.

            # First (canonical) file -> download to root
            self.canvas.download_file(url, root_dest)
            seen_dest_names.add(normalized)

            # Validate file types for canonical file
            if allowed_exts and not ext_allowed(root_dest, allowed_exts):
                fb.findings.append(Finding(
                    key="filetype_not_allowed",
                    severity="error",
                    message=f"File type not allowed: {normalized}. Allowed: {allowed_exts}"
                ))

            # Only canonical files go into inventory
            fb.file_inventory.append(root_dest)

        fb.filename_ok = filename_ok
        state["feedback"] = fb
        return state
