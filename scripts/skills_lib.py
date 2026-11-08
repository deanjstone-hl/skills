"""Shared helpers for the skills repo: hashing, the lockfile and the checks."""

import hashlib
import json
import re
from pathlib import Path

import merge_lib

LOCK_NAME = "skills-lock.json"
CONFIG_NAME = "skills-config.json"
DEFAULT_CONFIG = {"privacyCheck": True}
SOURCE_NAME = "SOURCE"
SIZE_WARN_BYTES = 8 * 1024
PRIVATE_MARKERS = (
    "/home/deanj",
    "Aquila",
    "homelab",
    "~/CONTEXT",
    "~/CORTEX",
    "argus-config",
    "deanjstone-hl",
)


def hash_files(files):
    """Order-independent sha256 over relative path and file content, SOURCE excluded."""
    digest = hashlib.sha256()
    for rel in sorted(k for k in files if k != SOURCE_NAME):
        digest.update(rel.encode() + b"\0" + hashlib.sha256(files[rel]).digest())
    return digest.hexdigest()


def read_dir(path):
    path = Path(path)
    return {p.relative_to(path).as_posix(): p.read_bytes() for p in sorted(path.rglob("*")) if p.is_file()}


def load_lock(root):
    lock_path = Path(root) / LOCK_NAME
    if not lock_path.exists():
        return {"version": 1, "skills": {}}
    return json.loads(lock_path.read_text())


def save_lock(root, lock):
    (Path(root) / LOCK_NAME).write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")


def parse_front_matter(text):
    match = re.match(r"---\r?\n(.*?)\r?\n---", text, re.S)
    if not match:
        return None
    import yaml

    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def source_note(name, entry):
    lic = entry.get("license", {})
    state = "edited locally" if entry.get("edited") else "unedited"
    return (
        f"{name}: imported from https://github.com/{entry['source']} "
        f"path {entry['skillPath']} at {entry['ref']}; {state}; "
        f"licence {lic.get('spdx', 'unknown')} ({lic.get('file', 'missing')}).\n"
    )


def load_config(root):
    """Per-repo settings from skills-config.json; privacyCheck is on unless the file turns it off."""
    config = dict(DEFAULT_CONFIG)
    path = Path(root) / CONFIG_NAME
    if path.exists():
        config.update(json.loads(path.read_text()))
    return config


def check(root, privacy=None):
    """Return (errors, warnings) for the repo at root.

    privacy=None follows skills-config.json (default on); True or False overrides it.
    The marker screen is for repos that publish skills; a private repo can switch it off.
    """
    root = Path(root)
    if privacy is None:
        privacy = load_config(root)["privacyCheck"]
    errors, warnings = [], []
    lock = load_lock(root)
    entries = lock.get("skills", {})
    skills_dir = root / "skills"
    dirs = sorted(p for p in skills_dir.iterdir() if p.is_dir()) if skills_dir.exists() else []
    dir_names = {p.name for p in dirs}

    for name in sorted(set(entries) - dir_names):
        errors.append(f"{name}: lock entry but no skill directory")

    for skill_dir in dirs:
        name = skill_dir.name
        files = read_dir(skill_dir)
        skill_md = files.get("SKILL.md")
        if skill_md is None:
            errors.append(f"{name}: missing SKILL.md")
            continue
        text = skill_md.decode("utf-8", "replace")
        front = parse_front_matter(text)
        if front is None:
            errors.append(f"{name}: SKILL.md has no valid front matter")
        else:
            if front.get("name") != name:
                errors.append(f"{name}: front matter name {front.get('name')!r} does not match the directory")
            desc = front.get("description")
            if not isinstance(desc, str) or not desc.strip():
                errors.append(f"{name}: front matter needs a non-empty description")
        if len(skill_md) > SIZE_WARN_BYTES:
            warnings.append(f"{name}: SKILL.md is {len(skill_md)} bytes, over the 8 KB budget")

        for rel, data in files.items():
            if merge_lib.has_conflict_markers(data):
                errors.append(f"{name}: conflict marker in {rel}")
            if privacy:
                body = data.decode("utf-8", "ignore")
                for marker in PRIVATE_MARKERS:
                    if marker in body:
                        errors.append(f"{name}: private marker {marker!r} in {rel}")

        entry = entries.get(name)
        if entry is None:
            # No lock entry and no SOURCE note: authored here, tracked by git alone.
            if (skill_dir / SOURCE_NAME).exists():
                errors.append(f"{name}: no lock entry")
            continue
        actual = hash_files(files)
        if entry.get("edited"):
            if actual != entry.get("localHash"):
                errors.append(f"{name}: edited, but content does not match localHash (update the lock)")
        else:
            if actual != entry.get("upstreamHash") or actual != entry.get("localHash"):
                errors.append(f"{name}: marked unedited but content differs from the pinned upstream")
        lic = entry.get("license", {})
        if not lic.get("file") or not (root / lic["file"]).exists():
            errors.append(f"{name}: licence file {lic.get('file')!r} is missing")
        if entry.get("status") == "merge-conflict":
            errors.append(f"{name}: merge-conflict pending; fix the files and run update_skill.py resolve")
        if entry.get("status") == "unadapted":
            warnings.append(f"{name}: unadapted import, not ready to use as shipped")
    return errors, warnings


def refresh(root, name, adapted=False):
    """Recompute hashes and SOURCE after an edit; set edited when content differs from upstream.

    adapted=True also clears an `unadapted` status: the edit made the skill usable.
    """
    root = Path(root)
    lock = load_lock(root)
    entry = lock["skills"][name]
    files = read_dir(root / "skills" / name)
    local = hash_files(files)
    entry["localHash"] = local
    entry["computedHash"] = local
    entry["edited"] = local != entry["upstreamHash"]
    if adapted:
        entry.pop("status", None)
    save_lock(root, lock)
    (root / "skills" / name / SOURCE_NAME).write_text(source_note(name, entry))
    return entry
