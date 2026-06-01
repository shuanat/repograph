"""Semantic / ONNX contract helpers for Repograph."""

from repograph.semantic.onnx_contract import (
    check_io_contract,
    dims_compatible,
    expected_input_rank,
    expected_output_rank,
)

__all__ = [
    "check_io_contract",
    "dims_compatible",
    "expected_input_rank",
    "expected_output_rank",
]
