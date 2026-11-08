#!/usr/bin/env python3
"""Take upstream changes into an imported skill without losing local edits.

    update_skill.py status [<skill> ...]
    update_skill.py update <skill> [<skill> ...] [--ref SHA] [--path NEW_UPSTREAM_PATH]
    update_skill.py resolve <skill>

`update` is a three-way merge per file: base is the upstream skill at the commit pinned
in skills-lock.json, ours is the directory here, theirs is the skill at the new upstream
commit. A clean merge advances the pin. A conflict writes markers into the file, marks
the skill `merge-conflict` and leaves the pin where it was; fix the files, then run
`resolve`.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import import_skill as imp  # noqa: E402
import merge_lib  # noqa: E402
import skills_lib as lib  # noqa: E402


def local_files(root, name):
    files = lib.read_dir(Path(root) / "skills" / name)
    files.pop(lib.SOURCE_NAME, None)
    return files


def write_files(root, name, files):
    skill_dir = Path(root) / "skills" / name
    for path in sorted(skill_dir.rglob("*"), reverse=True):
        if path.is_file() and path.name != lib.SOURCE_NAME and path.relative_to(skill_dir).as_posix() not in files:
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    for rel, data in files.items():
        target = skill_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def _finish(root, name, ref, path, upstream_hash):
    lock = lib.load_lock(root)
    entry = lock["skills"][name]
    entry.update({"ref": ref, "skillPath": path, "upstreamHash": upstream_hash})
    if entry.get("status") == "merge-conflict":
        entry.pop("status")
    entry.pop("pending", None)
    lib.save_lock(root, lock)
    return lib.refresh(root, name)


def update_skill(root, name, *, fetch, resolve, new_ref=None, new_path=None):
    root = Path(root)
    lock = lib.load_lock(root)
    entry = lock["skills"][name]
    if entry.get("status") == "merge-conflict":
        raise ValueError(f"{name}: a conflicted update is pending; fix the files and run resolve")
    repo, path, old_ref = entry["source"], entry["skillPath"], entry["ref"]
    target = new_ref or resolve(repo, None)
    target_path = new_path or path
    if target == old_ref and target_path == path:
        return {"state": "current", "ref": old_ref}
    base = fetch(repo, old_ref, path)
    if lib.hash_files(base) != entry["upstreamHash"]:
        raise ValueError(f"{name}: upstream {repo}:{path} at {old_ref[:8]} no longer matches the lock's upstreamHash (history rewritten or lock edited); refusing to merge against it")
    theirs = fetch(repo, target, target_path)
    result = merge_lib.merge_files(base, local_files(root, name), theirs)
    write_files(root, name, result.files)
    upstream_hash = lib.hash_files(theirs)
    if result.conflicts:
        entry["status"] = "merge-conflict"
        entry["pending"] = {"ref": target, "skillPath": target_path, "upstreamHash": upstream_hash, "conflicts": result.conflicts}
        lib.save_lock(root, lock)
        return {"state": "conflict", "conflicts": result.conflicts, "ref": old_ref, "pendingRef": target}
    entry = _finish(root, name, target, target_path, upstream_hash)
    return {"state": "updated", "ref": target, "edited": entry["edited"]}


def resolve_update(root, name):
    root = Path(root)
    entry = lib.load_lock(root)["skills"][name]
    pending = entry.get("pending")
    if not pending:
        raise ValueError(f"{name}: no pending update to resolve")
    left = [rel for rel, data in local_files(root, name).items() if merge_lib.has_conflict_markers(data)]
    if left:
        raise ValueError(f"{name}: conflict markers remain in {', '.join(left)}")
    return _finish(root, name, pending["ref"], pending["skillPath"], pending["upstreamHash"])


def status(root, *, resolve, shas, names=None):
    """Compare each pinned skill with upstream HEAD without downloading file contents."""
    lock = lib.load_lock(root)
    heads = {}
    rows = []
    for name, entry in sorted(lock["skills"].items()):
        if names and name not in names:
            continue
        repo, path, ref = entry["source"], entry["skillPath"], entry["ref"]
        head = heads.setdefault(repo, resolve(repo, None))
        row = {"name": name, "ref": ref, "head": head, "edited": bool(entry.get("edited")), "files": 0, "path": path}
        if entry.get("status") == "merge-conflict":
            row["state"] = "conflict"
        else:
            try:
                old = shas(repo, ref, path)
                new = shas(repo, head, path)
            except FileNotFoundError:
                row["state"] = "path-missing"
            else:
                diff = {p for p in set(old) | set(new) if old.get(p) != new.get(p)}
                row["files"] = len(diff)
                row["state"] = "changed" if diff else "current"
        rows.append(row)
    return rows


def gh_fetch_checked(repo, ref, path):
    files = imp.gh_fetch(repo, ref, path)
    if not files:
        raise FileNotFoundError(f"{repo}:{path} not found at {ref}")
    return files


def gh_blob_shas(repo, ref, path):
    tree = json.loads(imp.gh_api(f"repos/{repo}/git/trees/{ref}?recursive=1"))
    prefix = path.rstrip("/") + "/"
    shas = {i["path"][len(prefix):]: i["sha"] for i in tree["tree"] if i["type"] == "blob" and i["path"].startswith(prefix)}
    if not shas:
        raise FileNotFoundError(f"{repo}:{path} not found at {ref}")
    return shas


def gh_resolve(repo, ref=None):
    return imp.resolve_ref(repo, ref)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status")
    st.add_argument("skills", nargs="*")
    upd = sub.add_parser("update")
    upd.add_argument("skills", nargs="+")
    upd.add_argument("--ref")
    upd.add_argument("--path")
    res = sub.add_parser("resolve")
    res.add_argument("skill")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    if args.cmd == "status":
        rows = status(root, resolve=gh_resolve, shas=gh_blob_shas, names=set(args.skills) or None)
        for r in rows:
            note = {"current": "", "changed": f"{r['files']} file(s) differ upstream", "path-missing": "skill path missing at HEAD or pin", "conflict": "merge-conflict pending"}[r["state"]]
            flag = "edited" if r["edited"] else "unedited"
            print(f"{r['name']:32} {r['state']:12} {r['ref'][:8]}..{r['head'][:8]} {flag:9} {note}")
        print(f"{sum(r['state'] == 'changed' for r in rows)} changed, {sum(r['state'] == 'current' for r in rows)} current")
        return 0
    if args.cmd == "resolve":
        entry = resolve_update(root, args.skill)
        print(f"{args.skill}: resolved, pinned at {entry['ref'][:8]}, edited={entry['edited']}")
        return 0
    code = 0
    for name in args.skills:
        report = update_skill(root, name, fetch=gh_fetch_checked, resolve=gh_resolve, new_ref=args.ref, new_path=args.path)
        if report["state"] == "conflict":
            code = 1
            print(f"{name}: CONFLICT in {', '.join(report['conflicts'])} (pin stays {report['ref'][:8]}); fix the files, then: update_skill.py resolve {name}")
        elif report["state"] == "current":
            print(f"{name}: already at {report['ref'][:8]}")
        else:
            print(f"{name}: updated to {report['ref'][:8]}, edited={report['edited']}")
    return code


if __name__ == "__main__":
    sys.exit(main())
