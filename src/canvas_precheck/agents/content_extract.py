import os
import json
import re
import shutil
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
            [".ipynb", ".pdf", ".docx", ".md", ".txt", ".py", ".r", ".json", ".csv"]
        )
        max_chars = int(ce_cfg.get("max_chars", self.max_chars))
        chunk_chars = int(ce_cfg.get("chunk_chars", 3000))
        max_chunks = int(ce_cfg.get("max_chunks", 4))
        min_pdf_text_chars = int(ce_cfg.get("min_pdf_text_chars_for_ocr", 500))
        ocr_enabled = bool(ce_cfg.get("ocr_enabled", True))

        targets = self._pick_content_files(cfg, fb.file_inventory, workdir, prefer_exts)
        if not targets:
            fb.findings.append(Finding(
                key="content_extract_missing",
                severity="warning",
                message="No suitable file found for content extraction."
            ))
            state["feedback"] = fb
            return state

        sections = {}
        section_files = {}
        total_length = 0
        total_chunks = 0
        selected_total = 0

        for target in targets:
            filename = os.path.basename(target)
            try:
                text, extract_meta = self._extract_text(
                    target,
                    min_pdf_text_chars=min_pdf_text_chars,
                    ocr_enabled=ocr_enabled,
                )
                text = self._redact_secrets((text or "").strip())
                section = self._section_for_file(target, extract_meta)

                fb.evidence[f"content.{section}.file"] = filename
                fb.evidence[f"content.{section}.extract_method"] = extract_meta.get("method", "unknown")
                fb.evidence[f"content.{section}.source_type"] = extract_meta.get("source_type", "document")

                if extract_meta.get("ocr_error"):
                    fb.findings.append(Finding(
                        key="content_ocr_failed",
                        severity="warning",
                        message=f"OCR fallback failed for {filename}: {extract_meta['ocr_error']}"
                    ))

                if not text:
                    fb.findings.append(Finding(
                        key="content_extract_empty",
                        severity="warning",
                        message=f"Could not extract readable text from {filename}."
                    ))
                    continue

                chunks = self._chunk_text(text, chunk_chars=chunk_chars)
                selected_chunks = self._select_relevant_chunks(
                    chunks,
                    prompts=cfg.get("llm_prompts", []),
                    max_chunks=max_chunks,
                )
                preview = "\n\n".join(selected_chunks)[:max_chars]

                if section in sections:
                    sections[section] = f"{sections[section]}\n\n--- {filename} ---\n\n{preview}".strip()
                    section_files[section].append(filename)
                else:
                    sections[section] = preview
                    section_files[section] = [filename]

                total_length += len(text)
                total_chunks += len(chunks)
                selected_total += len(selected_chunks)
                fb.evidence[f"content.{section}.length_chars"] = str(
                    int(fb.evidence.get(f"content.{section}.length_chars", "0")) + len(text)
                )
                fb.evidence[f"content.{section}.chunk_count"] = str(
                    int(fb.evidence.get(f"content.{section}.chunk_count", "0")) + len(chunks)
                )

                if extract_meta.get("used_ocr"):
                    fb.findings.append(Finding(
                        key="content_ocr_used",
                        severity="info",
                        message=f"{filename} had little embedded text, so OCR fallback was used."
                    ))

            except Exception as e:
                fb.findings.append(Finding(
                    key="content_extract_error",
                    severity="warning",
                    message=f"Content extraction failed for {filename}: {type(e).__name__}: {e}"
                ))

        if sections:
            combined_parts = []
            for section in ["coding", "writing", "document"]:
                if section not in sections:
                    continue
                combined_parts.append(f"## {section.title()} section\n\n{sections[section]}")
                fb.evidence[f"content.{section}.preview"] = sections[section]
                fb.evidence[f"content.{section}.files_json"] = json.dumps(section_files[section])

            fb.evidence["content.preview"] = "\n\n".join(combined_parts)[:max_chars]
            fb.evidence["content.sections_json"] = json.dumps([
                {
                    "section": section,
                    "files": section_files[section],
                    "preview_key": f"content.{section}.preview",
                }
                for section in ["coding", "writing", "document"]
                if section in sections
            ])
            fb.evidence["content.file"] = ", ".join(
                name for names in section_files.values() for name in names
            )
            fb.evidence["content.extract_method"] = "multi_file" if len(targets) > 1 else "single_file"
            fb.evidence["content.source_type"] = "mixed" if len(sections) > 1 else next(iter(sections.keys()))
            fb.evidence["content.length_chars"] = str(total_length)
            fb.evidence["content.chunk_count"] = str(total_chunks)
            fb.evidence["content.selected_chunk_count"] = str(selected_total)
            fb.evidence["content.chunks_json"] = json.dumps(list(sections.values()))

        state["feedback"] = fb
        return state

    def _pick_content_files(
        self,
        cfg: dict,
        inventory: list[str],
        workdir: str,
        prefer_exts: list[str]
    ) -> list[str]:
        readable_exts = {ext.lower() for ext in prefer_exts}
        canonical_base = None if cfg.get("preserve_original_filenames") else cfg.get("canonical_filename")
        candidates = []

        if canonical_base:
            for ext in prefer_exts:
                p = os.path.join(workdir, f"{canonical_base}{ext}")
                if os.path.exists(p):
                    candidates.append(p)

        for p in inventory:
            if not os.path.exists(p):
                continue
            if os.path.splitext(p.lower())[1] in readable_exts:
                candidates.append(p)

        deduped = []
        seen = set()
        for p in candidates:
            real = os.path.abspath(p)
            if real in seen:
                continue
            seen.add(real)
            deduped.append(p)

        def sort_key(path: str) -> tuple[int, str]:
            ext = os.path.splitext(path.lower())[1]
            try:
                ext_rank = prefer_exts.index(ext)
            except ValueError:
                ext_rank = len(prefer_exts)
            return ext_rank, os.path.basename(path).lower()

        return sorted(deduped, key=sort_key)

    def _section_for_file(self, path: str, extract_meta: dict[str, str]) -> str:
        ext = os.path.splitext(path.lower())[1]
        if ext in [".ipynb", ".py", ".r", ".java", ".c", ".cpp", ".js", ".ts"]:
            return "coding"
        if ext in [".pdf", ".docx"]:
            if extract_meta.get("source_type") == "notebook_pdf":
                return "coding"
            return "writing"
        return "document"

    def _pick_primary_file(
        self,
        cfg: dict,
        inventory: list[str],
        workdir: str,
        prefer_exts: list[str]
    ) -> Optional[str]:
        """
        Legacy helper retained for callers that may still import it.
        """
        files = self._pick_content_files(cfg, inventory, workdir, prefer_exts)
        return files[0] if files else None

    def _extract_text(
        self,
        path: str,
        min_pdf_text_chars: int = 500,
        ocr_enabled: bool = True,
    ) -> tuple[str, dict[str, str]]:
        ext = os.path.splitext(path.lower())[1]

        if ext == ".ipynb":
            return self._extract_ipynb(path), {
                "method": "ipynb_json",
                "source_type": "notebook",
            }

        if ext in [".txt", ".md", ".py", ".r", ".java", ".c", ".cpp", ".js", ".ts", ".json", ".csv"]:
            return open(path, "r", encoding="utf-8", errors="ignore").read(), {
                "method": "plain_text",
                "source_type": "document",
            }

        if ext == ".docx":
            return self._extract_docx(path), {
                "method": "docx",
                "source_type": "document",
            }

        if ext == ".pdf":
            text = self._extract_pdf(path)
            meta = {
                "method": "pypdf",
                "source_type": "notebook_pdf" if self._looks_like_notebook_pdf(text) else "pdf",
            }
            if len((text or "").strip()) >= min_pdf_text_chars or not ocr_enabled:
                return text, meta

            try:
                ocr_text = self._extract_pdf_ocr(path)
            except Exception as e:
                meta["ocr_error"] = f"{type(e).__name__}: {e}"
                return text, meta

            if len((ocr_text or "").strip()) > len((text or "").strip()):
                meta["method"] = "ocr"
                meta["used_ocr"] = "true"
                meta["source_type"] = (
                    "notebook_pdf" if self._looks_like_notebook_pdf(ocr_text) else "pdf"
                )
                return ocr_text, meta

            return text, meta

        # fallback
        return "", {"method": "unsupported", "source_type": "unknown"}

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

    def _extract_pdf_ocr(self, path: str) -> str:
        if shutil.which("tesseract") is None:
            raise RuntimeError("tesseract is not installed or not on PATH")

        try:
            import fitz
            from PIL import Image
            import pytesseract
        except ImportError as e:
            raise RuntimeError(
                "OCR dependencies are missing. Install PyMuPDF, Pillow, and pytesseract."
            ) from e

        doc = fitz.open(path)
        texts = []
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(image)
            if text.strip():
                texts.append(text)
        return "\n\n".join(texts)

    def _chunk_text(self, text: str, chunk_chars: int) -> list[str]:
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks = []
        current = ""

        for paragraph in paragraphs:
            if len(paragraph) > chunk_chars:
                if current:
                    chunks.append(current.strip())
                    current = ""
                for i in range(0, len(paragraph), chunk_chars):
                    chunks.append(paragraph[i:i + chunk_chars].strip())
                continue

            candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
            if len(candidate) > chunk_chars and current:
                chunks.append(current.strip())
                current = paragraph
            else:
                current = candidate

        if current:
            chunks.append(current.strip())
        return chunks

    def _select_relevant_chunks(
        self,
        chunks: list[str],
        prompts: object,
        max_chunks: int,
    ) -> list[str]:
        if not chunks:
            return []

        prompt_text = json.dumps(prompts).lower()
        terms = {
            term.strip(".,:;()[]{}\"'").lower()
            for term in prompt_text.split()
            if len(term.strip(".,:;()[]{}\"'")) >= 5
        }

        scored = []
        for i, chunk in enumerate(chunks):
            lower = chunk.lower()
            score = sum(1 for term in terms if term in lower)
            scored.append((score, i, chunk))

        selected = sorted(scored, key=lambda x: (-x[0], x[1]))[:max_chunks]
        selected = sorted(selected, key=lambda x: x[1])
        return [chunk for _, _, chunk in selected]

    def _looks_like_notebook_pdf(self, text: str) -> bool:
        lower = (text or "").lower()
        signals = ["in [", "out[", "execution count", "import ", "def ", "traceback"]
        return sum(1 for signal in signals if signal in lower) >= 2

    def _redact_secrets(self, text: str) -> str:
        patterns = [
            # OpenAI-style API keys
            (r"sk-[A-Za-z0-9_-]{20,}", "[REDACTED_OPENAI_KEY]"),
            # Canvas-style tokens commonly look like numeric_prefix~token
            (r"\b\d+~[A-Za-z0-9_-]{20,}\b", "[REDACTED_CANVAS_TOKEN]"),
            # Generic inline api_key assignments in notebooks/scripts
            (
                r"(?i)(api[_-]?key[\"']?\s*[:=]\s*[\"'])([^\"']+)([\"'])",
                r"\1[REDACTED_API_KEY]\3",
            ),
        ]
        for pattern, replacement in patterns:
            text = re.sub(pattern, replacement, text)
        return text
