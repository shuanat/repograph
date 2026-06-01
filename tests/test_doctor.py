"""Tests for repograph doctor and ONNX path/contract helpers."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from repograph.cli import doctor
from repograph.cli.main import app
from repograph.semantic import onnx_contract

runner = CliRunner(env={"NO_COLOR": "1"})


class TestResolveModelPath:
    def test_resolve_rejects_null_bytes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REPOGRAPH_ONNX_MODEL", raising=False)
        with pytest.raises(doctor.ModelPathError, match="null"):
            doctor.resolve_model_path("foo\x00bar.onnx")

    def test_resolve_rejects_url_scheme(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REPOGRAPH_ONNX_MODEL", raising=False)
        with pytest.raises(doctor.ModelPathError, match="URL"):
            doctor.resolve_model_path("http://evil/model.onnx")

    def test_resolve_rejects_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REPOGRAPH_ONNX_MODEL", raising=False)
        with pytest.raises(doctor.ModelPathError, match="directory"):
            doctor.resolve_model_path(str(tmp_path))

    def test_resolve_unset_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REPOGRAPH_ONNX_MODEL", raising=False)
        assert doctor.resolve_model_path(None) is None

    def test_resolve_from_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        model = tmp_path / "model.onnx"
        model.write_bytes(b"\x00")
        monkeypatch.setenv("REPOGRAPH_ONNX_MODEL", str(model))
        assert doctor.resolve_model_path(None) == model.resolve()


class TestOnnxContract:
    def test_shape_check_wildcards(self) -> None:
        # Dynamic dims (strings/None) must not fail when rank matches
        assert onnx_contract.dims_compatible(
            [None, "batch", 384],
            expected_rank=3,
            static_dims={2: 384},
        )
        assert onnx_contract.dims_compatible(
            ["batch", 128],
            expected_rank=2,
            static_dims={},
        )
        assert not onnx_contract.dims_compatible(
            [1, 2],
            expected_rank=3,
            static_dims={},
        )


class TestDoctorRun:
    def test_doctor_smoke(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REPOGRAPH_ONNX_MODEL", raising=False)
        doctor.run(strict=False)

    def test_doctor_strict_warn(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REPOGRAPH_ONNX_MODEL", raising=False)
        monkeypatch.setattr(doctor.shutil, "which", lambda _name: None)
        with pytest.raises(typer.Exit) as exc:
            doctor.run(strict=True)
        assert exc.value.exit_code == 1

    @pytest.mark.skipif(sys.version_info < (3, 11), reason="needs 3.11+ to test failure")
    def test_doctor_python_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REPOGRAPH_ONNX_MODEL", raising=False)
        fake = (3, 10, 0, "final", 0)
        monkeypatch.setattr(doctor.sys, "version_info", fake)
        with pytest.raises(typer.Exit) as exc:
            doctor.run(strict=False)
        assert exc.value.exit_code == 1

    def test_doctor_migration_temp(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REPOGRAPH_ONNX_MODEL", raising=False)
        cwd_before = Path.cwd()
        repograph_dir = cwd_before / ".repograph"
        existed = repograph_dir.exists()
        migrate_calls: list[Path] = []
        temp_root = Path(tempfile.gettempdir()).resolve()

        def _track_migrate(db_path: Path, repo_root: Path | None = None) -> None:
            migrate_calls.append(db_path.resolve())
            from repograph.store.migrate import migrate as real_migrate

            real_migrate(db_path, repo_root=repo_root)

        monkeypatch.setattr(doctor, "migrate", _track_migrate)
        doctor.run(strict=False)
        assert migrate_calls, "migrate should run"
        for p in migrate_calls:
            assert temp_root in p.parents, f"migration must use temp dir, got {p}"
            assert ".repograph" in p.parts
        if not existed and repograph_dir.exists():
            pytest.fail("doctor created .repograph in cwd")

    def test_onnx_bad_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REPOGRAPH_ONNX_MODEL", "/nonexistent/repograph-model.onnx")
        with pytest.raises(typer.Exit) as exc:
            doctor.run(strict=False)
        assert exc.value.exit_code == 1

    def test_onnx_load_no_run(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        model = tmp_path / "fake.onnx"
        model.write_bytes(b"not-real-onnx")
        monkeypatch.setenv("REPOGRAPH_ONNX_MODEL", str(model))

        mock_session = MagicMock()
        mock_inp = MagicMock()
        mock_inp.name = "input"
        mock_inp.shape = [None, 384]
        mock_out = MagicMock()
        mock_out.name = "output"
        mock_out.shape = [None, 384]
        mock_session.get_inputs.return_value = [mock_inp]
        mock_session.get_outputs.return_value = [mock_out]

        with patch("onnxruntime.InferenceSession", return_value=mock_session) as mock_ctor:
            doctor.run(strict=False)
            mock_ctor.assert_called_once()
            mock_session.run.assert_not_called()


class TestDoctorCli:
    def test_cli_doctor_exit_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REPOGRAPH_ONNX_MODEL", raising=False)
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0

    def test_doctor_allows_fastembed_warn_without_strict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("REPOGRAPH_ONNX_MODEL", raising=False)
        monkeypatch.setattr(
            doctor,
            "probe_fastembed_cache",
            lambda _model_id: ("WARN", "model not cached yet (test)"),
        )
        doctor.run(strict=False)

    def test_cli_doctor_strict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REPOGRAPH_ONNX_MODEL", raising=False)
        monkeypatch.setattr(doctor.shutil, "which", lambda _name: None)
        result = runner.invoke(app, ["doctor", "--strict"])
        assert result.exit_code == 1
