"""Pydantic models for label vocab and batch JSON."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from repograph.config.model import VocabRow

__all__ = [
    "VocabRow",
    "VocabApplyPayload",
    "ParentEffective",
    "ExportItem",
    "LabelExportEnvelope",
    "LabelItem",
    "LabelApplyPayload",
]


class VocabApplyPayload(BaseModel):
    entries: list[VocabRow] = Field(default_factory=list)


class ParentEffective(BaseModel):
    purpose: str | None = None
    belongs_to: str | None = None
    lifecycle: str | None = None
    inherited_from: str | None = None


class ExportItem(BaseModel):
    path_norm: str
    entry_kind: str
    depth: int
    name: str
    domain_auto: str | None = None
    role_auto: str | None = None
    legacy_auto: int | None = None
    extension: str | None = None
    size_bytes: int | None = None
    child_sample: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    parent_effective: ParentEffective | None = None
    content_preview: str | None = None


class LabelExportEnvelope(BaseModel):
    project_vocab: list[VocabRow]
    items: list[ExportItem]


class LabelItem(BaseModel):
    path_norm: str
    purpose: str
    belongs_to: str
    lifecycle: str
    notes: str = ""
    label_status: str = "labeled"
    folder_kind: str | None = None
    file_kind: str | None = None
    operational_status: str | None = None
    action_planned: str | None = None
    structure_zone: str | None = None
    applies_to_descendants: int | bool | None = None
    model_config = ConfigDict(extra="allow")

    @field_validator("applies_to_descendants", mode="before")
    @classmethod
    def coerce_applies(cls, value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return 1 if value else 0
        return int(value)


class LabelApplyPayload(BaseModel):
    items: list[LabelItem]
