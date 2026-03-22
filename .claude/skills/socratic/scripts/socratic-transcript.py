#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class QuestionOption(BaseModel):
    model_config = ConfigDict(strict=True)

    label: str
    description: str


class Question(BaseModel):
    model_config = ConfigDict(strict=True, populate_by_name=True)

    question: str
    header: str
    options: list[QuestionOption]
    multi_select: bool = Field(alias="multiSelect")


class QuestionAnnotation(BaseModel):
    model_config = ConfigDict(strict=True)

    notes: str | None = None
    preview: str | None = None


class ToolInput(BaseModel):
    model_config = ConfigDict(strict=True)

    questions: list[Question]
    answers: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, QuestionAnnotation] = Field(default_factory=dict)


class HookPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str = ""
    cwd: str = "."
    tool_input: ToolInput


class TranscriptRecord(BaseModel):
    model_config = ConfigDict(strict=True)

    timestamp: str
    session_id: str
    question: str
    header: str
    options: list[QuestionOption]
    multi_select: bool
    answer: str | None
    annotation: QuestionAnnotation | None


EMPTY_HOOK_RESPONSE = "{}"


def record_transcript(output_path: Path, payload: HookPayload) -> None:
    timestamp = datetime.now(UTC).isoformat()
    with output_path.open("a", encoding="utf-8") as f:
        for question in payload.tool_input.questions:
            record = TranscriptRecord(
                timestamp=timestamp,
                session_id=payload.session_id,
                question=question.question,
                header=question.header,
                options=question.options,
                multi_select=question.multi_select,
                answer=payload.tool_input.answers.get(question.question),
                annotation=payload.tool_input.annotations.get(question.question),
            )
            f.write(record.model_dump_json() + "\n")


def main() -> None:
    raw = sys.stdin.read()
    if not raw.strip():
        print(EMPTY_HOOK_RESPONSE)
        return

    payload = HookPayload.model_validate(json.loads(raw))

    if not payload.tool_input.questions:
        print(EMPTY_HOOK_RESPONSE)
        return

    transcript_path = Path(payload.cwd) / "interview-transcript.jsonl"
    record_transcript(transcript_path, payload)
    print(EMPTY_HOOK_RESPONSE)


if __name__ == "__main__":
    main()
