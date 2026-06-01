"""Pydantic model for repograph.yaml (expanded in plan 02-03)."""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from repograph.config.defaults import SENSITIVE_GLOBS


class VocabRow(BaseModel):
    kind: str
    code: str
    label: str | None = Field(
        default=None,
        validation_alias=AliasChoices("label", "label_ru"),
    )
    sort_order: int = 0

    model_config = ConfigDict(populate_by_name=True)


class SemanticConfig(BaseModel):
    embedding_model: str | None = None


class RepographConfig(BaseModel):
    domains: dict[str, str] = Field(default_factory=dict)
    ignore: list[str] = Field(default_factory=list)
    sensitive_globs: list[str] = Field(default_factory=lambda: list(SENSITIVE_GLOBS))
    expected_toplevel: list[str] = Field(default_factory=list)
    vocab: list[VocabRow] = Field(default_factory=list)
    semantic: SemanticConfig | None = None

    @field_validator("domains")
    @classmethod
    def reject_dotdot_in_domains(cls, value: dict[str, str]) -> dict[str, str]:
        for prefix in value:
            if ".." in prefix:
                msg = f"domain prefix must not contain '..': {prefix!r}"
                raise ValueError(msg)
        return value
