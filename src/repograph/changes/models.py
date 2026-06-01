"""Pydantic models for changes finalize JSON (separate from label batches)."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from repograph.paths import normalize_path


class ChangeEventIn(BaseModel):
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    paths: list[str] = Field(min_length=1)

    @field_validator("paths")
    @classmethod
    def paths_normalized_unique(cls, paths: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for p in paths:
            n = normalize_path(p)
            if n not in seen:
                seen.add(n)
                out.append(n)
        return out


class FinalizePayload(BaseModel):
    events: list[ChangeEventIn] = Field(min_length=1)
