"""Semantic layer tests (Phase 6)."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import seed_annotations
from repograph.cli.main import app
from repograph.config.load import load_config
from repograph.config.model import RepographConfig, SemanticConfig
from repograph.constants import DB_SQLITE, REPOGRAPH_DIR
from repograph.changes.finalize import run_finalize
from repograph.changes.ingest import run_ingest
from repograph.changes.models import FinalizePayload
from repograph.scan.runner import run_scan
from repograph.cli import doctor
from repograph.semantic.blob import vector_to_blob
from repograph.semantic.config import DEFAULT_EMBEDDING_MODEL, resolve_embedding_model
from repograph.semantic.embedder import FakeEmbedder
from repograph.semantic.objects import collect_semantic_objects
from repograph.semantic.query import run_semantic_query
from repograph.semantic.rebuild import SemanticRebuildError, run_semantic_rebuild
from repograph.store.migrate import migrate

FIXTURES = Path(__file__).parent / "fixtures"
CLI_RUNNER = CliRunner()
VOCAB_FIXTURE = FIXTURES / "label-vocab.json"
APPLY_FIXTURE = FIXTURES / "label-batch-apply.json"
FINALIZE_FIXTURE = FIXTURES / "changes-finalize.json"


def _run_repograph(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "repograph", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _scan_config_vocab(repo: Path) -> None:
    run_scan(repo)
    assert _run_repograph(repo, "config", "init").returncode == 0
    assert _run_repograph(repo, "config", "apply").returncode == 0
    assert _run_repograph(
        repo, "label", "vocab-apply", "-f", str(VOCAB_FIXTURE)
    ).returncode == 0


def test_resolve_embedding_model_env_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPOGRAPH_EMBEDDING_MODEL", "custom/model")
    cfg = RepographConfig(semantic=SemanticConfig(embedding_model="yaml/model"))
    assert resolve_embedding_model(cfg) == "custom/model"


def test_resolve_embedding_model_yaml_fallback() -> None:
    cfg = RepographConfig(semantic=SemanticConfig(embedding_model="yaml/model"))
    assert resolve_embedding_model(cfg) == "yaml/model"


def test_resolve_embedding_model_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REPOGRAPH_EMBEDDING_MODEL", raising=False)
    assert resolve_embedding_model(RepographConfig()) == DEFAULT_EMBEDDING_MODEL


def test_rebuild_skips_sensitive(mini_lab_copy) -> None:
    repo = mini_lab_copy
    _scan_config_vocab(repo)
    db_path = repo / REPOGRAPH_DIR / DB_SQLITE
    conn = sqlite3.connect(db_path)
    try:
        seed_annotations(
            conn,
            [
                {
                    "path_norm": ".env",
                    "purpose": "should not embed",
                    "action_planned": "keep",
                    "label_status": "labeled",
                },
                {
                    "path_norm": "alpha/readme.md",
                    "purpose": "safe labeled entry",
                    "action_planned": "keep",
                    "label_status": "labeled",
                },
            ],
        )
        config = load_config(repo)
        objects = collect_semantic_objects(conn, repo, config)
        entry_paths = {
            o.path_norm for o in objects if o.object_type == "entry"
        }
        assert ".env" not in entry_paths
        assert "alpha/readme.md" in entry_paths
    finally:
        conn.close()


def test_issue_cluster_view(mini_lab_copy) -> None:
    repo = mini_lab_copy
    run_scan(repo)
    db_path = repo / REPOGRAPH_DIR / DB_SQLITE
    migrate(db_path, repo_root=repo)
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT issue_code, domain_auto, path_count
            FROM v_sem_issue_clusters
            WHERE issue_code = 'BROKEN_MD_LINK'
            """
        ).fetchall()
        assert rows, "expected broken-link cluster in mini-lab"
        domains = {r[1] for r in rows}
        assert any("docs" in (d or "") for d in domains)
        config = load_config(repo)
        clusters = [
            o
            for o in collect_semantic_objects(conn, repo, config)
            if o.object_type == "issue_cluster"
        ]
        assert clusters
        broken = [
            c
            for c in clusters
            if "BROKEN_MD_LINK" in c.object_key
        ]
        assert broken
        assert "issue_code:" in broken[0].embed_text
        assert "path_count:" in broken[0].embed_text
    finally:
        conn.close()


def test_collect_entry_requires_labeled(mini_lab_copy) -> None:
    repo = mini_lab_copy
    run_scan(repo)
    db_path = repo / REPOGRAPH_DIR / DB_SQLITE
    migrate(db_path, repo_root=repo)
    conn = sqlite3.connect(db_path)
    try:
        seed_annotations(
            conn,
            [
                {
                    "path_norm": "beta/readme.md",
                    "purpose": "labeled path",
                    "action_planned": "keep",
                    "label_status": "labeled",
                },
                {
                    "path_norm": "README.md",
                    "purpose": "pending only",
                    "action_planned": "keep",
                    "label_status": "pending",
                },
            ],
        )
        config = load_config(repo)
        entry_paths = {
            o.path_norm
            for o in collect_semantic_objects(conn, repo, config)
            if o.object_type == "entry"
        }
        assert "beta/readme.md" in entry_paths
        assert "README.md" not in entry_paths
    finally:
        conn.close()


def test_rebuild_writes_domain_objects(mini_lab_copy) -> None:
    repo = mini_lab_copy
    db_path = repo / REPOGRAPH_DIR / DB_SQLITE
    migrate(db_path, repo_root=repo)

    config = load_config(repo)
    count = run_semantic_rebuild(repo, embedder=FakeEmbedder())
    assert count >= len(config.domains)

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT object_key, dim, model_id, length(embedding) "
            "FROM semantic_objects WHERE object_type = 'domain'"
        ).fetchall()
        assert len(rows) == len(config.domains)
        for _key, dim, model_id, blob_len in rows:
            assert dim == 384
            assert model_id == resolve_embedding_model(config)
            assert blob_len == 384 * 4
    finally:
        conn.close()


def test_rebuild_writes_objects(mini_lab_git: Path) -> None:
    repo = mini_lab_git
    _scan_config_vocab(repo)
    assert (
        _run_repograph(
            repo,
            "label",
            "apply-batch",
            "-f",
            str(APPLY_FIXTURE),
            "--no-semantic-rebuild",
        ).returncode
        == 0
    )

    (repo / "alpha" / "readme.md").write_text("staged\n", encoding="utf-8")
    run_ingest(repo)
    payload = FinalizePayload.model_validate(
        json.loads(FINALIZE_FIXTURE.read_text(encoding="utf-8"))
    )
    run_finalize(repo, payload)

    db_path = repo / REPOGRAPH_DIR / DB_SQLITE
    config = load_config(repo)
    count = run_semantic_rebuild(repo, embedder=FakeEmbedder())
    assert count > 0

    conn = sqlite3.connect(db_path)
    try:
        types = {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT object_type FROM semantic_objects"
            ).fetchall()
        }
        assert "domain" in types
        assert "entry" in types
        assert "narrative" in types
        assert "issue_cluster" in types
        total = conn.execute("SELECT COUNT(*) FROM semantic_objects").fetchone()[0]
        assert total == count
        for _otype, _key, dim, model_id, blob_len in conn.execute(
            "SELECT object_type, object_key, dim, model_id, length(embedding) "
            "FROM semantic_objects"
        ):
            assert dim == 384
            assert model_id == resolve_embedding_model(config)
            assert blob_len == 384 * 4
    finally:
        conn.close()


def test_rebuild_model_mismatch_wipes(mini_lab_copy) -> None:
    repo = mini_lab_copy
    db_path = repo / REPOGRAPH_DIR / DB_SQLITE
    migrate(db_path, repo_root=repo)
    config = load_config(repo)

    first = run_semantic_rebuild(repo, embedder=FakeEmbedder())
    assert first >= len(config.domains)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE semantic_objects SET model_id = ?",
            ("stale/wrong-model",),
        )
        conn.commit()
        before = conn.execute("SELECT COUNT(*) FROM semantic_objects").fetchone()[0]
        assert before == first
    finally:
        conn.close()

    second = run_semantic_rebuild(repo, embedder=FakeEmbedder())
    assert second == first

    conn = sqlite3.connect(db_path)
    try:
        model_ids = conn.execute(
            "SELECT DISTINCT model_id FROM semantic_objects"
        ).fetchall()
        assert model_ids == [(resolve_embedding_model(config),)]
        total = conn.execute("SELECT COUNT(*) FROM semantic_objects").fetchone()[0]
        assert total == second
    finally:
        conn.close()


def _rebuild_and_query(repo: Path, query: str, **kwargs) -> dict:
    run_semantic_rebuild(repo, embedder=FakeEmbedder())
    return run_semantic_query(repo, query, embedder=FakeEmbedder(), **kwargs)


def test_query_json(mini_lab_copy) -> None:
    repo = mini_lab_copy
    payload = _rebuild_and_query(repo, "broken link", limit=10)
    assert payload["query"] == "broken link"
    assert payload["model_id"] == resolve_embedding_model(load_config(repo))
    assert payload["limit"] == 10
    assert isinstance(payload["results"], list)
    assert payload["results"], "expected at least one domain hit"
    for hit in payload["results"]:
        assert set(hit.keys()) >= {
            "object_type",
            "object_key",
            "score",
            "path_norm",
            "event_id",
            "snippet",
        }
        assert isinstance(hit["score"], float)
        assert len(hit["snippet"]) <= 200


def test_query_excludes_sensitive(mini_lab_copy) -> None:
    repo = mini_lab_copy
    run_semantic_rebuild(repo, embedder=FakeEmbedder())
    db_path = repo / REPOGRAPH_DIR / DB_SQLITE
    config = load_config(repo)
    model_id = resolve_embedding_model(config)
    fake = FakeEmbedder()
    vec = fake.embed_passages(["sensitive leak text"])[0]
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO semantic_objects (
                object_type, object_key, embedding, model_id, dim,
                embedded_at, source_hash
            ) VALUES (?, ?, ?, ?, ?, datetime('now'), ?)
            """,
            (
                "entry",
                ".env",
                vector_to_blob(vec, dim=fake.dim),
                model_id,
                fake.dim,
                "deadbeef",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    payload = run_semantic_query(repo, "secret", embedder=FakeEmbedder())
    paths = {h.get("path_norm") for h in payload["results"]}
    keys = {h.get("object_key") for h in payload["results"]}
    assert ".env" not in paths
    assert ".env" not in keys


def test_query_respects_limit(mini_lab_copy) -> None:
    repo = mini_lab_copy
    payload = _rebuild_and_query(repo, "domain", limit=2)
    assert len(payload["results"]) <= 2
    scores = [h["score"] for h in payload["results"]]
    assert scores == sorted(scores, reverse=True)


def test_query_model_id_mismatch_raises(mini_lab_copy) -> None:
    repo = mini_lab_copy
    run_semantic_rebuild(repo, embedder=FakeEmbedder())
    db_path = repo / REPOGRAPH_DIR / DB_SQLITE
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE semantic_objects SET model_id = ?",
            ("other-model/same-dim",),
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(SemanticRebuildError, match="stored embeddings use"):
        run_semantic_query(repo, "domain", embedder=FakeEmbedder())


def test_query_stale_source_hash_skipped(mini_lab_copy) -> None:
    repo = mini_lab_copy
    run_semantic_rebuild(repo, embedder=FakeEmbedder())
    db_path = repo / REPOGRAPH_DIR / DB_SQLITE
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE semantic_objects SET source_hash = ? WHERE object_type = 'domain'",
            ("0000000000000000000000000000000000000000000000000000000000000000",),
        )
        conn.commit()
    finally:
        conn.close()

    payload = run_semantic_query(repo, "domain", embedder=FakeEmbedder())
    assert payload["stale_skipped"] >= 1
    domain_hits = [h for h in payload["results"] if h["object_type"] == "domain"]
    assert not domain_hits


def test_query_dim_mismatch_raises(mini_lab_copy) -> None:
    repo = mini_lab_copy
    run_semantic_rebuild(repo, embedder=FakeEmbedder())
    db_path = repo / REPOGRAPH_DIR / DB_SQLITE
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            UPDATE semantic_objects SET dim = 128
            WHERE rowid = (
                SELECT rowid FROM semantic_objects
                WHERE object_type = 'domain' LIMIT 1
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(SemanticRebuildError, match="stored embedding dim 128"):
        run_semantic_query(repo, "domain", embedder=FakeEmbedder())


def test_semantic_query_cli_json(mini_lab_copy) -> None:
    repo = mini_lab_copy
    run_semantic_rebuild(repo, embedder=FakeEmbedder())
    proc = _run_repograph(repo, "semantic", "query", "broken link", "--limit", "5")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["query"] == "broken link"
    assert len(payload["results"]) <= 5


def test_finalize_triggers_rebuild(
    mini_lab_git: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Path] = []

    def _fake(root: Path | str, **kwargs: object) -> int:
        calls.append(Path(root).resolve())
        return 0

    monkeypatch.setattr("repograph.cli.changes_cmd.run_semantic_rebuild", _fake)
    run_scan(mini_lab_git)
    (mini_lab_git / "alpha" / "readme.md").write_text("staged\n", encoding="utf-8")
    run_ingest(mini_lab_git)
    result = CLI_RUNNER.invoke(
        app,
        [
            "changes",
            "finalize",
            str(mini_lab_git),
            "--file",
            str(FINALIZE_FIXTURE),
        ],
    )
    assert result.exit_code == 0, result.stderr
    assert len(calls) == 1
    assert calls[0] == mini_lab_git.resolve()


def test_finalize_no_rebuild_flag(
    mini_lab_git: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Path] = []

    def _fake(root: Path | str, **kwargs: object) -> int:
        calls.append(Path(root).resolve())
        return 0

    monkeypatch.setattr("repograph.cli.changes_cmd.run_semantic_rebuild", _fake)
    run_scan(mini_lab_git)
    (mini_lab_git / "alpha" / "readme.md").write_text("staged\n", encoding="utf-8")
    run_ingest(mini_lab_git)
    result = CLI_RUNNER.invoke(
        app,
        [
            "changes",
            "finalize",
            str(mini_lab_git),
            "--file",
            str(FINALIZE_FIXTURE),
            "--no-semantic-rebuild",
        ],
    )
    assert result.exit_code == 0, result.stderr
    assert calls == []


def test_finalize_export_and_semantic_rebuild_independent(
    mini_lab_git: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rebuild_calls: list[Path] = []
    export_calls: list[Path] = []

    def _fake_rebuild(root: Path | str, **kwargs: object) -> int:
        rebuild_calls.append(Path(root).resolve())
        return 0

    def _fake_export(root: Path) -> None:
        export_calls.append(root.resolve())

    monkeypatch.setattr("repograph.cli.changes_cmd.run_semantic_rebuild", _fake_rebuild)
    monkeypatch.setattr("repograph.cli.export_cmd.run", _fake_export)
    run_scan(mini_lab_git)
    (mini_lab_git / "alpha" / "readme.md").write_text("staged\n", encoding="utf-8")
    run_ingest(mini_lab_git)
    result = CLI_RUNNER.invoke(
        app,
        [
            "changes",
            "finalize",
            str(mini_lab_git),
            "--file",
            str(FINALIZE_FIXTURE),
            "--export",
        ],
    )
    assert result.exit_code == 0, result.stderr
    assert len(rebuild_calls) == 1
    assert len(export_calls) == 1


def test_apply_batch_triggers_rebuild(
    mini_lab_git: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Path] = []

    def _fake(root: Path | str, **kwargs: object) -> int:
        calls.append(Path(root).resolve())
        return 0

    monkeypatch.setattr("repograph.cli.label_cmd.run_semantic_rebuild", _fake)
    _scan_config_vocab(mini_lab_git)
    result = CLI_RUNNER.invoke(
        app,
        [
            "label",
            "apply-batch",
            str(mini_lab_git),
            "--file",
            str(APPLY_FIXTURE),
            "--model",
            "test",
            "--prompt-version",
            "1",
        ],
    )
    assert result.exit_code == 0, result.stderr
    assert len(calls) == 1
    assert calls[0] == mini_lab_git.resolve()


def test_apply_batch_no_rebuild_on_dry_run(
    mini_lab_git: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Path] = []

    def _fake(root: Path | str, **kwargs: object) -> int:
        calls.append(Path(root).resolve())
        return 0

    monkeypatch.setattr("repograph.cli.label_cmd.run_semantic_rebuild", _fake)
    _scan_config_vocab(mini_lab_git)
    result = CLI_RUNNER.invoke(
        app,
        [
            "label",
            "apply-batch",
            str(mini_lab_git),
            "--file",
            str(APPLY_FIXTURE),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.stderr
    assert calls == []


@pytest.mark.semantic_integration
@pytest.mark.skip(reason="Manual UAT: run with pytest -m semantic_integration when model cached")
def test_semantic_query_authentication_domain_uat(mini_lab_copy: Path) -> None:
    """Optional real-model probe: semantic query for authentication-related context."""
    repo = mini_lab_copy
    _scan_config_vocab(repo)
    run_semantic_rebuild(repo)
    payload = run_semantic_query(repo, "authentication domain", limit=5)
    assert payload["results"]


def test_doctor_fastembed_warn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        doctor,
        "probe_fastembed_cache",
        lambda _model_id: ("WARN", "model not cached yet (test)"),
    )
    result = doctor._check_fastembed_model_cache()
    assert result.level == doctor.Level.WARN
    assert "cached" in result.message.lower() or "cache" in result.message.lower()
