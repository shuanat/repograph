"""Auto-classification hints for scan phase (not final semantic labels)."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

# Top-level dirs expected per README (for issues)
EXPECTED_TOPLEVEL = frozenset(
    {
        "internal-docs",
        "mikrotik",
        "kubernetes",
        "proxmox",
        "services",
        "tests",
        "archive",
        ".cursor",
        "tools",
    }
)

OPTIONAL_TOPLEVEL = frozenset({"tools", "secrets"})
DEPRECATED_TOPLEVEL = frozenset({"backups"})

DOMAIN_PREFIXES: list[tuple[str, str]] = [
    (".git/", "dot_git"),
    (".cursor/", "cursor_meta"),
    ("mikrotik/", "mikrotik"),
    ("kubernetes/", "kubernetes"),
    ("proxmox/", "proxmox"),
    ("services/", "services"),
    ("proxmox/vms/windows-server/", "windows_server"),
    ("internal-docs/", "internal_docs"),
    ("archive/", "archive_global"),
    ("tests/", "tests"),
    ("tools/", "hub_tools"),
]

LEGACY_PREFIXES = (
    "kubernetes/archive/",
    "archive/",
)

SENSITIVE_GLOB_PATTERNS = [
    "*.env",
    "*.env.local",
    "*credentials*",
    "*password*",
    "*.key",
    "*.pem",
    "*.crt",
    "*.cert",
    "kubeconfig*",
    "*.kubeconfig",
    ".k8s-admin-pass",
    ".mcp-credentials*",
    "**/htpasswd",
    "id_rsa*",
    "id_ed25519*",
    "secrets/**",
    "**/vault-backup/**",
    ".kube/config",
]

BINARY_EXTENSIONS = frozenset(
    {
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".npk",
        ".zip",
        ".tar",
        ".gz",
        ".rar",
        ".7z",
        ".pcap",
        ".pcapng",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".ico",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".pyc",
        ".whl",
        ".deb",
        ".rpm",
    }
)

TEXT_LIKE_EXTENSIONS = frozenset(
    {
        ".md",
        ".txt",
        ".yaml",
        ".yml",
        ".json",
        ".rsc",
        ".sh",
        ".ps1",
        ".py",
        ".tf",
        ".sql",
        ".cron",
        ".service",
        ".mdc",
        ".html",
        ".htm",
        ".xml",
        ".ini",
        ".cfg",
        ".conf",
        ".env.example",
    }
)


def domain_auto(path_norm: str) -> str:
    if path_norm == "" or path_norm == ".":
        return "root"
    for prefix, domain in DOMAIN_PREFIXES:
        if path_norm == prefix.rstrip("/") or path_norm.startswith(prefix):
            return domain
    return "other"


def legacy_auto(path_norm: str) -> int:
    """Legacy zones; root archive/ is intentional (see EXPECTED_TOPLEVEL)."""
    if path_norm.startswith("kubernetes/archive/"):
        return 1
    return 0


def role_auto(path_norm: str, entry_kind: str, extension: str | None) -> str:
    if entry_kind == "directory":
        p = PurePosixPath(path_norm)
        name = p.name.lower()
        if "/manifests/" in f"/{path_norm}/" or path_norm.endswith("/manifests"):
            return "manifests"
        if "/dashboards/" in f"/{path_norm}/":
            return "dashboards"
        if "/archive/" in f"/{path_norm}/" or name == "archive":
            return "archive"
        if "/scripts/" in f"/{path_norm}/" or name == "scripts":
            return "scripts"
        if "/configs/" in f"/{path_norm}/" or name == "configs":
            return "configs"
        if "/docs/" in f"/{path_norm}/" or name == "docs":
            return "docs"
        if "/terraform/" in f"/{path_norm}/":
            return "terraform"
        if depth(path_norm) == 0:
            return "domain_root"
        return "subsystem"

    ext = (extension or "").lower()
    if ext == ".rsc":
        return "script"
    if ext in (".sh", ".ps1", ".py"):
        return "script"
    if ext in (".yaml", ".yml"):
        if "/manifests/" in f"/{path_norm}/":
            return "manifest"
        return "config"
    if ext == ".tf":
        return "terraform"
    if ext == ".md":
        return "doc"
    if ext == ".json":
        if "/dashboards/" in f"/{path_norm}/" or "/panels/" in f"/{path_norm}/":
            return "dashboard_panel"
        return "config"
    if ext in (".backup", ".rsc") and "/backups/" in f"/{path_norm}/":
        return "backup"
    if "example" in path_norm.lower():
        return "example"
    if ext in BINARY_EXTENSIONS:
        return "binary"
    return "unknown"


def depth(path_norm: str) -> int:
    if not path_norm:
        return 0
    return path_norm.count("/") + 1


def is_probably_binary(extension: str | None, size_bytes: int | None) -> int:
    if extension and extension.lower() in BINARY_EXTENSIONS:
        return 1
    if extension and extension.lower() in TEXT_LIKE_EXTENSIONS:
        return 0
    if size_bytes is not None and size_bytes == 0:
        return 0
    # no extension but under .git/objects
    return 0


def is_orphan_root_file(path_norm: str, entry_kind: str) -> bool:
    if entry_kind != "file":
        return False
    return "/" not in path_norm and path_norm not in (
        "README.md",
        ".gitignore",
        ".gitattributes",
        "LICENSE",
        "LICENSE.md",
        "project-inventory-summary.md",
        "mitmproxy-ca-cert.cer",
    )


def openvas_parallel_candidate(path_norm: str) -> bool:
    if not path_norm.startswith("proxmox/scripts/openvas/"):
        return False
    return "/archive/" not in path_norm


def parse_extension(name: str) -> str | None:
    if "." not in name or name.startswith("."):
        # .gitignore etc still have extension concept
        if name.startswith(".") and name.count(".") == 1:
            return name
        if "." in name[1:]:
            return "." + name.rsplit(".", 1)[-1].lower()
        return None
    return "." + name.rsplit(".", 1)[-1].lower()


MARKDOWN_LINK_RE = re.compile(r"\]\(([^)#\s]+(?:\.md|/)[^)]*)\)")
