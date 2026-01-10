from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from datetime import datetime

class SubmissionMetadata(BaseModel):
    course_id: int
    assignment_id: int
    user_id: int
    student_name: str
    submitted_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    attachments: List[Dict[str, Any]] = Field(default_factory=list)

class Finding(BaseModel):
    key: str
    severity: str  # info|warning|error
    message: str
    evidence_keys: List[str] = Field(default_factory=list)

class FeedbackJSON(BaseModel):
    metadata: SubmissionMetadata
    is_late: bool = False
    late_by_seconds: int = 0
    filename_ok: bool = True
    file_inventory: List[str] = Field(default_factory=list)
    findings: List[Finding] = Field(default_factory=list)
    test_results: Dict[str, Any] = Field(default_factory=dict)
    evidence: Dict[str, str] = Field(default_factory=dict)

class LLMRubricItem(BaseModel):
    rubric_item: str
    score: Optional[float] = None
    finding: str
    suggestion: str
    evidence_keys: List[str] = Field(default_factory=list)

class LLMJSON(BaseModel):
    items: List[LLMRubricItem]
    overall: str