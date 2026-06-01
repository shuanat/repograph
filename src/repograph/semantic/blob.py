"""Float32 little-endian vector BLOB helpers (D-18)."""

from __future__ import annotations

import numpy as np


def vector_to_blob(vec: np.ndarray, *, dim: int) -> bytes:
    arr = np.asarray(vec, dtype=np.float32).reshape(-1)
    if arr.shape[0] != dim:
        msg = f"expected dim {dim}, got {arr.shape[0]}"
        raise ValueError(msg)
    return arr.tobytes()


def blob_to_vector(blob: bytes, *, dim: int) -> np.ndarray:
    arr = np.frombuffer(blob, dtype=np.float32)
    if arr.shape[0] != dim:
        msg = f"expected dim {dim}, got {arr.shape[0]}"
        raise ValueError(msg)
    return arr.copy()
