import requests
from typing import Any, Dict, List

class CanvasClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}"})

    def _get_paginated(self, url: str, params: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        next_url = url
        next_params = params or {}

        while next_url:
            r = self.s.get(next_url, params=next_params, timeout=30)
            r.raise_for_status()
            results.extend(r.json())
            next_url = r.links.get("next", {}).get("url")
            next_params = {}

        return results

    def list_courses(self) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/v1/courses"
        params = {
            "enrollment_state": "active",
            "include[]": ["term"],
            "per_page": 100,
        }
        return self._get_paginated(url, params=params)

    def list_assignments(self, course_id: int) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/v1/courses/{course_id}/assignments"
        params = {"per_page": 100, "order_by": "due_at"}
        return self._get_paginated(url, params=params)

    def list_submissions(self, course_id: int, assignment_id: int) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions"
        params = {"include[]": ["user"], "per_page": 100}
        return self._get_paginated(url, params=params)

    def download_file(self, file_url: str, dest_path: str) -> None:
        with self.s.get(file_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)

    def post_comment(self, course_id: int, assignment_id: int, user_id: int, comment_md: str) -> None:
        url = f"{self.base_url}/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/{user_id}"
        data = {"comment[text_comment]": comment_md}
        r = self.s.put(url, data=data, timeout=30)
        r.raise_for_status()
