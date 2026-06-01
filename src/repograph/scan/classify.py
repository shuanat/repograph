"""Neutral classification helpers (no homelab constants)."""

from __future__ import annotations

BINARY_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".pdf",
        ".zip",
        ".gz",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".woff",
        ".woff2",
    }
)

TEXT_LIKE_EXTENSIONS = frozenset(
    {".md", ".txt", ".yaml", ".yml", ".json", ".xml", ".html", ".css", ".js", ".py"}
)


def domain_auto(path_norm: str, domains: dict[str, str]) -> str:
    """Longest matching path prefix wins; else unknown."""
    if not domains:
        return "unknown"
    best_prefix = ""
    best_domain = "unknown"
    for prefix, domain_id in domains.items():
        norm = prefix.replace("\\", "/").rstrip("/")
        if not norm:
            continue
        candidate = f"{norm}/"
        if path_norm == norm or path_norm.startswith(candidate):
            if len(norm) > len(best_prefix):
                best_prefix = norm
                best_domain = domain_id
    return best_domain


def parse_extension(name: str) -> str | None:
    if "." not in name:
        return None
    if name.startswith(".") and name.count(".") == 1:
        return name.lower()
    return "." + name.rsplit(".", 1)[-1].lower()


def is_probably_binary(extension: str | None, size_bytes: int | None) -> int:
    if extension and extension.lower() in BINARY_EXTENSIONS:
        return 1
    if extension and extension.lower() in TEXT_LIKE_EXTENSIONS:
        return 0
    return 0


def role_auto(path_norm: str, entry_kind: str, extension: str | None) -> str:
    _ = path_norm, extension
    if entry_kind == "directory":
        return "directory"
    return "file"
