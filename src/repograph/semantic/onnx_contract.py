"""Expected ONNX I/O contract for doctor shape checks on legacy custom `.onnx` files.

Phase 6 product encode uses FastEmbed (`BAAI/bge-small-en-v1.5`, 384-dim) via
onnxruntime under the hood — not this module. `REPOGRAPH_ONNX_MODEL` remains an
optional WARN-only doctor probe (D-11); primary availability is FastEmbed cache.
"""

from __future__ import annotations

from typing import Any

# Permissive Phase 1 contract: typical embedding models use rank-2 tensors.
EXPECTED_INPUT_RANK = 2
EXPECTED_OUTPUT_RANK = 2

# Static dimension checks: index -> required int dim (only when model reports int).
EXPECTED_INPUT_STATIC_DIMS: dict[int, int] = {}
EXPECTED_OUTPUT_STATIC_DIMS: dict[int, int] = {}


def expected_input_rank() -> int:
    return EXPECTED_INPUT_RANK


def expected_output_rank() -> int:
    return EXPECTED_OUTPUT_RANK


def _dim_value(dim: Any) -> int | None:
    if isinstance(dim, int):
        return dim
    return None


def dims_compatible(
    shape: list[Any],
    *,
    expected_rank: int,
    static_dims: dict[int, int],
) -> bool:
    """True if rank matches and static integer dims match; dynamic dims are wildcards."""
    if len(shape) != expected_rank:
        return False
    for idx, required in static_dims.items():
        if idx >= len(shape):
            return False
        actual = _dim_value(shape[idx])
        if actual is None:
            continue
        if actual != required:
            return False
    return True


def check_io_contract(inputs: list[Any], outputs: list[Any]) -> str | None:
    """Return error message if I/O metadata fails contract; else None."""
    if not inputs:
        return "model has no inputs"
    if not outputs:
        return "model has no outputs"
    inp = inputs[0]
    out = outputs[0]
    in_shape = list(getattr(inp, "shape", []) or [])
    out_shape = list(getattr(out, "shape", []) or [])
    if not dims_compatible(
        in_shape,
        expected_rank=EXPECTED_INPUT_RANK,
        static_dims=EXPECTED_INPUT_STATIC_DIMS,
    ):
        return (
            f"input {getattr(inp, 'name', '?')!r} shape {in_shape} "
            f"does not match expected rank {EXPECTED_INPUT_RANK}"
        )
    if not dims_compatible(
        out_shape,
        expected_rank=EXPECTED_OUTPUT_RANK,
        static_dims=EXPECTED_OUTPUT_STATIC_DIMS,
    ):
        return (
            f"output {getattr(out, 'name', '?')!r} shape {out_shape} "
            f"does not match expected rank {EXPECTED_OUTPUT_RANK}"
        )
    return None
