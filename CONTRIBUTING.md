# Contributing to Repograph

Thanks for your interest in improving Repograph. This guide covers local setup,
tests, and the rules for contributing to the public repository.

## Prerequisites

- **Python 3.12** (CI runs 3.12; 3.11+ works locally).
- **[uv](https://docs.astral.sh/uv/)** for dependency management.

## Local setup

From the repository root:

```powershell
uv sync --locked
uv run repograph doctor
```

`uv sync --locked` installs locked dependencies and the editable `repograph`
console script into `.venv`. `repograph doctor` checks your environment.

## Running tests

```powershell
uv run pytest -q
```

Try a full cycle against the bundled fixture:

```powershell
cd tests\fixtures\mini-lab
uv run repograph scan
uv run repograph config init
uv run repograph config apply
uv run repograph export
```

## Repository

Clone [github.com/shuanat/repograph](https://github.com/shuanat/repograph) and
work on branch `main`. Open pull requests against `main` on that repository.

## GitHub governance

Branch `main` is protected by the **Protect main** ruleset (see
`.github/rulesets/main-protection.json`). Merges require green CI:

- `test (ubuntu-latest, 3.12)`
- `test (windows-latest, 3.12)`

## Pull requests

- Keep public documentation in **English** and plain language.
- Make sure `uv run pytest -q` passes, including the documentation link gate
  (`tests/test_doc_links.py`).
