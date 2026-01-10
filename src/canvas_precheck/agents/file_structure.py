import os, zipfile, shutil
from canvas_precheck.models import FeedbackJSON, Finding

class FileStructureAgent:
    name = "FileStructureAgent"

    def run(self, state: dict) -> dict:
        cfg = state["config"]
        fb: FeedbackJSON = state["feedback"]
        workdir = state["workdir"]

        zip_policy = cfg.get("zip_policy", {})
        allow_zip = zip_policy.get("allow_zip", True)
        flatten = zip_policy.get("flatten", True)

        new_files = []
        for p in list(fb.file_inventory):
            if p.lower().endswith(".zip"):
                if not allow_zip:
                    fb.findings.append(Finding(
                        key="zip_not_allowed",
                        severity="error",
                        message="ZIP submitted but ZIP is not allowed."
                    ))
                    continue

                unzip_dir = os.path.join(workdir, "_unzipped")
                os.makedirs(unzip_dir, exist_ok=True)

                try:
                    with zipfile.ZipFile(p) as z:
                        z.extractall(unzip_dir)
                except zipfile.BadZipFile:
                    fb.findings.append(Finding(
                        key="zip_bad",
                        severity="error",
                        message="ZIP is corrupted/unreadable."
                    ))
                    continue

                fb.findings.append(Finding(
                    key="zip_unpacked",
                    severity="info",
                    message="ZIP unpacked successfully."
                ))

                if flatten:
                    for root, _, files in os.walk(unzip_dir):
                        for f in files:
                            src = os.path.join(root, f)
                            dst = os.path.join(workdir, f)
                            if os.path.abspath(src) != os.path.abspath(dst):
                                shutil.copy2(src, dst)
                                new_files.append(dst)

        fb.file_inventory.extend(new_files)

        required = set(cfg.get("required_files", []))
        if required:
            present = {os.path.basename(x) for x in fb.file_inventory}
            missing = sorted(required - present)
            if missing:
                fb.findings.append(Finding(
                    key="missing_required_files",
                    severity="error",
                    message=f"Missing required files: {missing}"
                ))

        state["feedback"] = fb
        return state