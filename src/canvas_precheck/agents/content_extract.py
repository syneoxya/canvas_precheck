import os
import json
from typing import Optional

from canvas_precheck.models import FeedbackJSON, Finding


class ContentExtractAgent:
    name = "ContentExtractAgent"

    def __init__(self, max_chars: int = 8000):
        self.max_chars = max_chars

    def run(self, state: dict) -> dict:
        cfg = state["config"]
        fb: FeedbackJSON = state["feedback"]
        workdir = state["workdir"]

        ce_cfg = cfg.get("content_extract", {})
        if ce_cfg.get("enabled", True) is False:
            return state

        prefer_exts = ce_cfg.get(
            "prefer_extensions",
            [".ipynb", ".pdf", ".docx", ".md", ".txt", ".py"]
        )
        max_chars = int(ce_cfg.get("max_chars", self.max_chars))

        # Pick a primary file to read (canonical preferred if present)
        target = self._pick_primary_file(cfg, fb.file_inventory, workdir, prefer_exts)
        if not target:
            fb.findings.append(Finding(
                key="content_extract_missing",
                severity="warning",
                message="No suitable file found for content extraction."
            ))
            state["feedback"] = fb
            return state

        try:
            text = self._extract_text(target)
            text = (text or "").strip()

            fb.evidence["content.file"] = os.path.basename(target)

            if not text:
                fb.findings.append(Finding(
                    key="content_extract_empty",
                    severity="warning",
                    message=f"Could not extract readable text from {os.path.basename(target)}."
                ))
            else:
                fb.evidence["content.preview"] = text[:max_chars]
                fb.evidence["content.length_chars"] = str(len(text))

        except Exception as e:
            fb.findings.append(Finding(
                key="content_extract_error",
                severity="warning",
                message=f"Content extraction failed: {type(e).__name__}: {e}"
            ))

        state["feedback"] = fb
        return state

    def _pick_primary_file(
        self,
        cfg: dict,
        inventory: list[str],
        workdir: str,
        prefer_exts: list[str]
    ) -> Optional[str]:
        """
        Priority:
        1) canonical_filename + preferred extension if exists in workdir
        2) any file in inventory matching preferred extensions (skip dupes/)
        """
        canonical_base = cfg.get("canonical_filename")
        if canonical_base:
            for ext in prefer_exts:
                p = os.path.join(workdir, f"{canonical_base}{ext}")
                if os.path.exists(p):
                    return p

        # Otherwise pick first matching file by extension order
        inv = [p for p in inventory if os.path.exists(p)]
        # Avoid dupes folder by default
        inv = [p for p in inv if f"{os.sep}dupes{os.sep}" not in p]

        for ext in prefer_exts:
            for p in inv:
                if p.lower().endswith(ext):
                    return p
        return inv[0] if inv else None

    def _extract_text(self, path: str) -> str:
        ext = os.path.splitext(path.lower())[1]

        if ext == ".ipynb":
            return self._extract_ipynb(path)

        if ext in [".txt", ".md", ".py"]:
            return open(path, "r", encoding="utf-8", errors="ignore").read()

        if ext == ".docx":
            return self._extract_docx(path)

        if ext == ".pdf":
            return self._extract_pdf(path)

        # fallback
        return ""

    def _extract_ipynb(self, path: str) -> str:
        nb = json.loads(open(path, "r", encoding="utf-8", errors="ignore").read())
        chunks = []
        for cell in nb.get("cells", []):
            src = cell.get("source", [])
            if isinstance(src, list):
                chunks.append("".join(src))
            elif isinstance(src, str):
                chunks.append(src)
        return "\n\n".join(chunks)

    def _extract_docx(self, path: str) -> str:
        from docx import Document
        doc = Document(path)
        return "\n".join([p.text for p in doc.paragraphs if p.text])

    def _extract_pdf(self, path: str) -> str:
        from pypdf import PdfReader
        reader = PdfReader(path)
        texts = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip():
                texts.append(t)
        return "\n\n".join(texts)