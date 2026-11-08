"""Three-way merge of a skill directory: base (pinned upstream), ours (local), theirs (new upstream)."""

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

MARKER_LOCAL = b"<<<<<<< local"
MARKER_UPSTREAM = b">>>>>>> upstream"


@dataclass
class MergeResult:
    files: dict = field(default_factory=dict)
    conflicts: list = field(default_factory=list)


def is_text(data):
    if b"\0" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def has_conflict_markers(data):
    """True when a file still holds the markers merge_text writes."""
    lines = data.split(b"\n")
    return any(line.startswith(MARKER_LOCAL) for line in lines) and any(line.startswith(MARKER_UPSTREAM) for line in lines)


def merge_text(base, ours, theirs):
    """Line-based three-way merge with `git merge-file`; returns (bytes, conflicted)."""
    with tempfile.TemporaryDirectory() as tmp:
        paths = {}
        for name, data in (("ours", ours), ("base", base), ("theirs", theirs)):
            path = Path(tmp) / name
            path.write_bytes(data)
            paths[name] = str(path)
        result = subprocess.run(
            ["git", "merge-file", "-p", "-L", "local", "-L", "base", "-L", "upstream", paths["ours"], paths["base"], paths["theirs"]],
            capture_output=True,
        )
    if result.returncode > 127 or result.returncode < 0:
        raise RuntimeError(f"git merge-file failed: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout, result.returncode > 0


def merge_files(base, ours, theirs):
    """Merge three {relative path: bytes} maps. Conflicted files are listed and carry markers (text) or keep ours (binary)."""
    out = MergeResult()
    for path in sorted(set(base) | set(ours) | set(theirs)):
        b, o, t = base.get(path), ours.get(path), theirs.get(path)
        if o == t:
            if o is not None:
                out.files[path] = o
            continue
        if t == b:  # upstream did not touch it: keep the local state, including a local delete
            if o is not None:
                out.files[path] = o
            continue
        if o == b:  # not edited locally: follow upstream, including an upstream delete
            if t is not None:
                out.files[path] = t
            continue
        # both sides changed this path differently
        if o is None or t is None:
            out.conflicts.append(path)
            out.files[path] = o if o is not None else t
            continue
        if b is not None and not (is_text(b) and is_text(o) and is_text(t)):
            out.conflicts.append(path)
            out.files[path] = o
            continue
        if b is None and not (is_text(o) and is_text(t)):
            out.conflicts.append(path)
            out.files[path] = o
            continue
        merged, conflicted = merge_text(b if b is not None else b"", o, t)
        out.files[path] = merged
        if conflicted:
            out.conflicts.append(path)
    return out
