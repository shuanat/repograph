"""repograph doctor — environment and dependency health checks."""

from __future__ import annotations

import contextlib
import os
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table

from repograph.config.model import RepographConfig
from repograph.semantic import onnx_contract
from repograph.semantic.config import DEFAULT_EMBEDDING_MODEL, resolve_embedding_model
from repograph.semantic.preflight import probe_fastembed_cache
from repograph.store.migrate import _SCHEMA_VERSION, migrate

_ENV_ONNX_MODEL = "REPOGRAPH_ONNX_MODEL"
_MAX_PATH_LEN = 4096
_URL_SCHEMES = ("http://", "https://", "file://", "ftp://")


class ModelPathError(ValueError):
    """Invalid REPOGRAPH_ONNX_MODEL or explicit path."""


class Level(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class CheckResult:
    name: str
    level: Level
    message: str


def resolve_model_path(raw: str | None = None) -> Path | None:
    """Resolve ONNX model path from argument or REPOGRAPH_ONNX_MODEL.

    Returns None when unset. Raises ModelPathError on invalid values.
    """
    value = raw if raw is not None else os.environ.get(_ENV_ONNX_MODEL)
    if value is None or value == "":
        return None
    if "\x00" in value:
        raise ModelPathError("path must not contain null bytes")
    lowered = value.strip().lower()
    for scheme in _URL_SCHEMES:
        if lowered.startswith(scheme):
            raise ModelPathError("URL schemes are not supported; use a filesystem path")
    if len(value) > _MAX_PATH_LEN:
        raise ModelPathError(f"path exceeds maximum length ({_MAX_PATH_LEN})")
    path = Path(value).expanduser().resolve(strict=False)
    if path.exists() and path.is_dir():
        raise ModelPathError("expected a .onnx file, got a directory")
    return path


def _import_onnxruntime():
    import onnxruntime as ort_module

    return ort_module.InferenceSession


def _python_version_tuple() -> tuple[int, int, int]:
    vi = sys.version_info
    return (int(vi[0]), int(vi[1]), int(vi[2]))


def _check_python() -> CheckResult:
    major, minor, micro = _python_version_tuple()
    if (major, minor) < (3, 11):
        return CheckResult("python", Level.FAIL, f"Python {major}.{minor} < 3.11 required")
    return CheckResult("python", Level.PASS, f"Python {major}.{minor}.{micro}")


def _check_sqlite() -> CheckResult:
    try:
        with contextlib.closing(sqlite3.connect(":memory:")) as conn:
            conn.execute("SELECT 1")
    except sqlite3.Error as exc:
        return CheckResult("sqlite3", Level.FAIL, f"sqlite3 unavailable: {exc}")
    return CheckResult("sqlite3", Level.PASS, "sqlite3 :memory: OK")


def _check_onnxruntime_import() -> CheckResult:
    try:
        _import_onnxruntime()
    except ImportError as exc:
        return CheckResult("onnxruntime-import", Level.FAIL, f"import failed: {exc}")
    return CheckResult("onnxruntime-import", Level.PASS, "onnxruntime import OK")


def _check_embedding_model_resolve() -> CheckResult:
    model_id = resolve_embedding_model(RepographConfig())
    if not model_id:
        return CheckResult(
            "embedding-model-resolve",
            Level.FAIL,
            "resolve_embedding_model returned empty id",
        )
    return CheckResult(
        "embedding-model-resolve",
        Level.PASS,
        f"resolved {model_id!r} (default {DEFAULT_EMBEDDING_MODEL!r})",
    )


def _check_fastembed_model_cache() -> CheckResult:
    model_id = resolve_embedding_model(RepographConfig())
    level_str, message = probe_fastembed_cache(model_id)
    level = Level(level_str)
    return CheckResult("fastembed-model-cache", level, message)


def _check_git() -> CheckResult:
    if shutil.which("git") is None:
        return CheckResult("git", Level.WARN, "git not on PATH")
    return CheckResult("git", Level.PASS, "git on PATH")


def _check_onnx_path_configured(model_path: Path | None) -> CheckResult:
    if model_path is None:
        return CheckResult(
            "onnx-path",
            Level.WARN,
            f"{_ENV_ONNX_MODEL} unset (optional until semantic commands)",
        )
    return CheckResult("onnx-path", Level.PASS, str(model_path))


def _check_onnx_file(model_path: Path) -> CheckResult:
    if not model_path.is_file():
        return CheckResult(
            "onnx-file",
            Level.FAIL,
            f"model not found or not a file: {model_path}",
        )
    try:
        inference_session = _import_onnxruntime()
        session = inference_session(
            str(model_path),
            providers=["CPUExecutionProvider"],
        )
        err = onnx_contract.check_io_contract(session.get_inputs(), session.get_outputs())
        if err:
            return CheckResult("onnx-file", Level.FAIL, err)
    except Exception as exc:
        return CheckResult("onnx-file", Level.FAIL, f"load failed: {exc}")
    return CheckResult("onnx-file", Level.PASS, "ONNX session loaded (no inference)")


def _check_migration() -> CheckResult:
    try:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / ".repograph" / "db.sqlite"
            migrate(db, repo_root=root)
            if not db.is_file():
                return CheckResult("migration", Level.FAIL, "db.sqlite not created in temp")
            with contextlib.closing(sqlite3.connect(db)) as conn:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version < 1:
                return CheckResult("migration", Level.FAIL, f"user_version={version}, expected >= 1")
    except Exception as exc:
        return CheckResult("migration", Level.FAIL, str(exc))
    return CheckResult(
        "migration",
        Level.PASS,
        f"schema v{_SCHEMA_VERSION} applies in temp dir",
    )


def _collect_checks() -> list[CheckResult]:
    results: list[CheckResult] = [
        _check_python(),
        _check_sqlite(),
        _check_onnxruntime_import(),
        _check_embedding_model_resolve(),
        _check_fastembed_model_cache(),
        _check_git(),
    ]

    model_path: Path | None = None
    try:
        model_path = resolve_model_path()
    except ModelPathError as exc:
        results.append(CheckResult("onnx-path", Level.FAIL, str(exc)))
    else:
        results.append(_check_onnx_path_configured(model_path))
        if model_path is not None:
            results.append(_check_onnx_file(model_path))

    results.append(_check_migration())
    return results


def _render_results(console: Console, results: list[CheckResult]) -> None:
    table = Table(title="repograph doctor")
    table.add_column("Check", style="bold")
    table.add_column("Level")
    table.add_column("Message")
    for row in results:
        style = {
            Level.PASS: "green",
            Level.WARN: "yellow",
            Level.FAIL: "red",
        }.get(row.level, "")
        table.add_row(row.name, row.level.value, row.message, style=style)
    console.print(table)


def run(*, strict: bool) -> None:
    """Run health checks and exit 1 on FAIL or strict WARN."""
    console = Console()
    results = _collect_checks()
    _render_results(console, results)

    has_fail = any(r.level == Level.FAIL for r in results)
    has_warn = any(r.level == Level.WARN for r in results)
    if has_fail or (strict and has_warn):
        raise typer.Exit(code=1)
