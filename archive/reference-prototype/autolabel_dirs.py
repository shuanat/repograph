#!/usr/bin/env python3
"""Generate labeled directory annotations from export batch JSON."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DOMAIN_BELONGS = {
    "kubernetes": "kubernetes",
    "mikrotik": "mikrotik",
    "proxmox": "proxmox",
    "services": "services",
    "windows_server": "windows_server",
    "cursor_meta": "cursor_meta",
    "internal_docs": "internal_docs",
    "personal": "personal",
    "archive_global": "archive_global",
    "hub_tools": "unknown",
    "apps": "unknown",
    "tests": "kubernetes",
    "other": "unknown",
    "root": "unknown",
}

ZONE = {
    "kubernetes": "infra_kubernetes",
    "mikrotik": "infra_mikrotik",
    "proxmox": "infra_proxmox",
    "services": "shared_services",
    "windows_server": "infra_proxmox",
    "cursor_meta": "meta_cursor",
    "internal_docs": "internal_docs",
    "archive_global": "global_archive",
    "personal": "personal",
    "hub_tools": "hub_tools",
}


def infer_folder_kind(path: str, name: str, role_auto: str, legacy: int) -> str:
    if legacy or name == "archive" or "/archive" in path:
        return "archive"
    if name in ("configs", "config") or "/configs" in path:
        return "configs"
    if name == "scripts" or role_auto == "scripts":
        return "scripts"
    if name == "docs" or role_auto == "docs":
        return "docs"
    if name == "manifests" or "/manifests" in path:
        return "manifests"
    if name == "dashboards" or "/dashboards" in path:
        return "dashboards"
    if name == "terraform" or "/terraform" in path:
        return "terraform"
    if name in ("plans", "reports", "analysis", "runbooks", "queries"):
        return "docs" if name != "reports" else "docs"
    if name == "backups":
        return "backup"
    if "project-inventory" in path or name == "tests" and path.startswith("tools"):
        return "tooling"
    if path.startswith(".cursor"):
        return "tooling"
    if name in ("rules", "skills", "prompts"):
        return "tooling"
    if name == "examples":
        return "subsystem"
    if name in ("guest", "deploy", "archive", "pve-cron", "pipeline", "debug"):
        return "subsystem"
    if path.count("/") <= 1 and path.split("/")[0] in DOMAIN_BELONGS:
        return "domain_root"
    return role_auto if role_auto in (
        "subsystem",
        "domain_root",
        "tooling",
        "generated",
    ) else "subsystem"


def purpose_for(path: str, name: str, domain: str, children: list) -> str:
    base = path or "(repo root)"
    if path.startswith("kubernetes/manifests/"):
        app = path.split("/")[2]
        return f"Kubernetes manifests and resources for {app}."
    if path == "kubernetes/manifests":
        return "All Kubernetes application and platform manifests."
    if path.startswith("proxmox/scripts/openvas"):
        if name == "guest":
            return "Canonical OpenVAS scripts for VM152 guest (install, phases, gvm)."
        if name in ("deploy", "archive", "pve-cron", "debug", "pipeline"):
            return f"OpenVAS {name} scripts (supporting VM152 scanner pipeline)."
        return "OpenVAS/Greenbone automation (see parent consolidate plan)."
    if path.startswith("proxmox/scripts/"):
        area = path.split("/")[2] if len(path.split("/")) > 2 else "automation"
        return f"Proxmox automation scripts: {area}."
    if path.startswith("proxmox/configs/k8s"):
        return "Legacy K8s snippets on Proxmox host; superseded by kubernetes/manifests."
    if path.startswith("mikrotik/"):
        return f"MikroTik {name}: router configs, scripts, or documentation."
    if path.startswith("archive/"):
        return f"Archived historical material: {name}."
    if path.startswith("internal-docs/"):
        return f"Internal documentation: {name}."
    if path.startswith(".cursor/"):
        return f"Cursor agent {name} for this repository."
    if domain == "hub_tools" and "project-inventory" in path:
        return "SQLite project inventory: scan, label, and restructure planning."
    if domain == "personal":
        return f"Personal CV materials ({name})."
    if name == "backups":
        return f"Backup artifacts for {path.split('/')[0]}."
    return f"Directory {base} ({domain})."


def label_item(item: dict) -> dict:
    path = item["path_norm"]
    name = item["name"]
    domain = item["domain_auto"]
    legacy = item.get("legacy_auto") or 0
    belongs = DOMAIN_BELONGS.get(domain, "unknown")
    fk = infer_folder_kind(path, name, item.get("role_auto", ""), legacy)

    lifecycle = "active"
    op = "in_use"
    action = "keep"
    wave = None
    risk = "low"
    repo_fit = "in_scope"
    git_pol = None
    tags: list[str] = []

    if legacy or path.startswith("archive/") or (name == "archive" and "archive" in path):
        lifecycle = "archive"
        op = "docs_only"
        wave = "wave0_safe"
    if path.startswith("proxmox/configs/k8s"):
        lifecycle = "legacy"
        action = "archive"
        wave = "wave0_safe"
        risk = "medium"
        tags.append("legacy-k8s")
    if "openvas" in path and path != "proxmox/scripts/openvas":
        if name in ("guest", "deploy"):
            pass
        elif path.count("/") > 3:
            op = "in_use"
    if path == "proxmox/scripts/openvas" or path.endswith("/openvas/archive"):
        if "archive" in path:
            lifecycle = "archive"
            op = "docs_only"
    if ".pytest_cache" in path or ".playwright-mcp" in path:
        lifecycle = "candidate_delete"
        op = "generated"
        action = "delete"
        wave = "wave0_safe"
        git_pol = "should_gitignore"
    if domain == "personal":
        lifecycle = "out_of_scope"
        op = "docs_only"
        repo_fit = "relocate_out"
    if path.startswith("kubernetes/manifests") or path.startswith("kubernetes/dashboards"):
        risk = "high"
        wave = "wave2_manifests" if action != "keep" else None
    if path.startswith("mikrotik/configs") or path.startswith("mikrotik/scripts"):
        risk = "high"
    if path.startswith("proxmox/scripts/k8s"):
        risk = "high"
        wave = "wave1_scripts"

    zone = ZONE.get(domain, "hub_tools")
    if repo_fit == "relocate_out":
        zone = "personal"

    out = {
        "path_norm": path,
        "purpose": purpose_for(path, name, domain, item.get("child_sample") or []),
        "belongs_to": belongs,
        "folder_kind": fk,
        "lifecycle": lifecycle,
        "operational_status": op,
        "structure_zone": zone,
        "action_planned": action,
        "applies_to_descendants": 1,
        "label_status": "labeled",
    }
    if wave:
        out["restructure_wave"] = wave
    if risk != "low":
        out["risk_level"] = risk
    if repo_fit != "in_scope":
        out["repo_fit"] = repo_fit
    if git_pol:
        out["git_policy"] = git_pol
    if tags:
        out["tags"] = tags
    if path.startswith("proxmox/configs/k8s"):
        out["restructure_notes"] = "Migrate references to kubernetes/manifests; do not apply from here."
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch", type=Path)
    parser.add_argument("-o", type=Path, required=True)
    args = parser.parse_args()
    items = json.loads(args.batch.read_text(encoding="utf-8"))
    labeled = [label_item(i) for i in items]
    args.o.write_text(json.dumps(labeled, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Labeled {len(labeled)} -> {args.o}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
