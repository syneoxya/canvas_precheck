from canvas_precheck.models import FeedbackJSON, Finding

class TestRunnerAgent:
    name = "TestRunnerAgent"

    def _read_text_files(self, inventory: list[str]) -> str:
        parts = []
        for p in inventory:
            if p.lower().endswith((".txt", ".md")):
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        parts.append(f.read())
                except Exception:
                    pass
        return "\n\n".join(parts)

    def run(self, state: dict) -> dict:
        cfg = state["config"]
        fb: FeedbackJSON = state["feedback"]
        text = self._read_text_files(fb.file_inventory)

        results = {}
        for t in cfg.get("tests", []):
            if t.get("type") != "nl_check":
                continue
            name = t["name"]
            rule_outcomes = []

            for r in t.get("rules", []):
                ok = True
                if "min_chars" in r:
                    ok = ok and (len(text) >= int(r["min_chars"]))
                if "contains_any" in r:
                    ok = ok and any(term.lower() in text.lower() for term in r["contains_any"])
                rule_outcomes.append({"rule": r, "ok": ok})

            passed = all(x["ok"] for x in rule_outcomes)
            results[name] = {"passed": passed, "rules": rule_outcomes}

            if not passed:
                fb.findings.append(Finding(
                    key=f"test_failed:{name}",
                    severity="warning",
                    message=f"Test '{name}' failed."
                ))

        fb.test_results = results
        state["feedback"] = fb
        return state