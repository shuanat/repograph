#!/usr/bin/env python3
"""Generate labeled file-exception annotations from export batch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DOMAIN_BELONGS = {
    "kubernetes": "kubernetes",
    "mikrotik": "mikrotik",
    "proxmox": "proxmox",
    "other": "unknown",
    "root": "unknown",
    "hub_tools": "unknown",
}


def label_file(item: dict) -> dict:
    path = item["path_norm"]
    name = item["name"]
    domain = item["domain_auto"]
    belongs = DOMAIN_BELONGS.get(domain, "unknown")
    ext = (item.get("extension") or "").lower()
    legacy = item.get("legacy_auto") or 0
    issues = item.get("issues") or []
    issue_codes = " ".join(issues)

    fk = "config"
    if ext in (".sh", ".ps1", ".py", ".rsc"):
        fk = "script"
    elif ext == ".md":
        fk = "doc"
    elif ext in (".yaml", ".yml"):
        fk = "manifest"
    elif ext == ".json":
        fk = "config"

    lifecycle = "legacy" if legacy else "active"
    action = "keep"
    dup_kind = "none"
    canonical = None
    keep_reason = None
    wave = None
    risk = "low"
    tags: list[str] = []

    # Root orphans
    if "/" not in path and path.endswith((".ps1", ".reg")):
        lifecycle = "out_of_scope"
        action = "move"
        target = "tools/host-maintenance/" + name
        purpose = f"Host-side bluetooth/network utility script at repo root; not infra config."
        wave = "wave0_safe"
        tags.append("orphan-root")
        return _pack(
            path,
            purpose,
            belongs,
            fk,
            lifecycle,
            action,
            wave,
            risk,
            tags,
            target_path_norm=target,
            duplicate_kind=dup_kind,
            canonical_path_norm=canonical,
            keep_reason=keep_reason,
        )

    if "OPENVAS_PARALLEL_TREE" in issue_codes:
        dup_kind = "parallel_tree"
        lifecycle = "duplicate"
        action = "delete"
        wave = "wave1_scripts"
        risk = "medium"
        tags.append("openvas")
        # flat copy under openvas/ -> canonical in guest/ if exists
        base = name
        guest = f"proxmox/scripts/openvas/guest/{base}"
        deploy = f"proxmox/scripts/openvas/deploy/{base}"
        archive = f"proxmox/scripts/openvas/archive/debug/{base}"
        if path.startswith("proxmox/scripts/openvas/") and "/guest/" not in path:
            if "guest" in issue_codes or True:
                canonical = guest
                keep_reason = "Prefer guest/ tree over flat duplicate."
        purpose = f"Duplicate OpenVAS script ({name}); parallel flat vs structured tree."
        return _pack(
            path,
            purpose,
            belongs,
            fk,
            lifecycle,
            action,
            wave,
            risk,
            tags,
            duplicate_kind=dup_kind,
            canonical_path_norm=canonical,
            keep_reason=keep_reason,
        )

    if legacy or "LEGACY" in issue_codes:
        lifecycle = "legacy"
        action = "archive"
        wave = "wave0_safe"
        purpose = f"Legacy file: {path}."
        if "proxmox/configs/k8s" in path:
            tags.append("legacy-k8s")
            action = "delete"
            purpose = "Legacy K8s manifest on Proxmox; use kubernetes/manifests instead."
        return _pack(
            path,
            purpose,
            belongs,
            fk,
            lifecycle,
            action,
            wave,
            risk,
            tags,
            duplicate_kind=dup_kind,
        )

    if "BROKEN_MD_LINK" in issue_codes:
        purpose = f"Markdown file with broken outbound links: {path}."
        action = "none"
        return _pack(path, purpose, belongs, fk, lifecycle, action, None, risk, tags)

  # default
    purpose = f"File exception: {path} ({fk})."
    return _pack(path, purpose, belongs, fk, lifecycle, action, wave, risk, tags)


def _pack(
    path: str,
    purpose: str,
    belongs: str,
    file_kind: str,
    lifecycle: str,
    action: str,
    wave: str | None,
    risk: str,
    tags: list[str],
    target_path_norm: str | None = None,
    duplicate_kind: str = "none",
    canonical_path_norm: str | None = None,
    keep_reason: str | None = None,
) -> dict:
    o = {
        "path_norm": path,
        "purpose": purpose,
        "belongs_to": belongs,
        "file_kind": file_kind,
        "lifecycle": lifecycle,
        "operational_status": "in_use" if lifecycle == "active" else "docs_only",
        "action_planned": action,
        "duplicate_kind": duplicate_kind,
        "label_status": "labeled",
    }
    if wave:
        o["restructure_wave"] = wave
    if risk != "low":
        o["risk_level"] = risk
    if target_path_norm:
        o["target_path_norm"] = target_path_norm
    if canonical_path_norm:
        o["canonical_path_norm"] = canonical_path_norm
    if keep_reason:
        o["keep_reason"] = keep_reason
    if tags:
        o["tags"] = tags
    return o


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch", type=Path)
    parser.add_argument("-o", type=Path, required=True)
    args = parser.parse_args()
    items = json.loads(args.batch.read_text(encoding="utf-8"))
    labeled = [label_file(i) for i in items]
    args.o.write_text(json.dumps(labeled, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Labeled {len(labeled)} files -> {args.o}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
