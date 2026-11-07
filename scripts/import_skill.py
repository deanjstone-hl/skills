#!/usr/bin/env python3
"""Import one skill from an upstream GitHub repo, pinned to a commit.

The import is verbatim: edits are made afterwards, in their own commit, so the
pinned upstream stays the merge base.

    scripts/import_skill.py cursor/plugins pstack/skills/correct \
        --license MIT --license-path pstack/LICENSE --license-scope pstack
"""

import argparse
import base64
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skills_lib as lib  # noqa: E402


def license_file_name(repo, scope):
    base = repo.replace("/", "__")
    if scope:
        base += "__" + scope.strip("/").replace("/", "_")
    return f"licenses/{base}.LICENSE"


def import_skill(root, *, repo, path, name, ref, spdx, license_text, fetch, license_scope="", status=None):
    root = Path(root)
    dest = root / "skills" / name
    if dest.exists():
        raise FileExistsError(f"{dest} already exists")
    files = fetch(repo, ref, path)
    if "SKILL.md" not in files:
        raise ValueError(f"{repo}:{path} has no SKILL.md at {ref}")
    for rel, data in files.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    digest = lib.hash_files(files)
    lic_file = license_file_name(repo, license_scope)
    (root / "licenses").mkdir(exist_ok=True)
    (root / lic_file).write_text(license_text)
    entry = {
        "source": repo,
        "sourceType": "github",
        "skillPath": path,
        "ref": ref,
        "upstreamHash": digest,
        "localHash": digest,
        "computedHash": digest,
        "edited": False,
        "license": {"spdx": spdx, "file": lic_file},
    }
    if status:
        entry["status"] = status
    (dest / lib.SOURCE_NAME).write_text(lib.source_note(name, entry))
    lock = lib.load_lock(root)
    lock["skills"][name] = entry
    lib.save_lock(root, lock)
    return entry


def gh_api(*args):
    result = subprocess.run(["gh", "api", *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"gh api {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def gh_fetch(repo, ref, path):
    tree = json.loads(gh_api(f"repos/{repo}/git/trees/{ref}?recursive=1"))
    if tree.get("truncated"):
        raise RuntimeError(f"tree for {repo}@{ref} is truncated")
    prefix = path.rstrip("/") + "/"
    files = {}
    for item in tree["tree"]:
        if item["type"] == "blob" and item["path"].startswith(prefix):
            blob = gh_api(f"repos/{repo}/git/blobs/{item['sha']}", "--jq", ".content")
            files[item["path"][len(prefix):]] = base64.b64decode(blob.replace("\\n", "").strip())
    return files


def resolve_ref(repo, ref):
    return gh_api(f"repos/{repo}/commits/{ref or 'HEAD'}", "--jq", ".sha").strip()


def gh_file(repo, ref, path):
    out = gh_api(f"repos/{repo}/contents/{path}?ref={ref}", "--jq", ".content")
    return base64.b64decode(out.replace("\\n", "").strip()).decode()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repo", help="owner/repo")
    parser.add_argument("path", help="skill directory inside the repo")
    parser.add_argument("--name", help="local skill name (default: last path segment)")
    parser.add_argument("--ref", help="upstream commit (default: HEAD, resolved to a SHA)")
    parser.add_argument("--license", required=True, dest="spdx", help="SPDX id of the upstream licence")
    parser.add_argument("--license-path", default="LICENSE", help="licence file inside the upstream repo")
    parser.add_argument("--license-scope", default="", help="subdirectory the licence covers (names the licence file)")
    parser.add_argument("--status", help="lock status, e.g. unadapted")
    parser.add_argument("--root", default=".", help="repo root")
    args = parser.parse_args(argv)
    ref = resolve_ref(args.repo, args.ref)
    name = args.name or args.path.rstrip("/").split("/")[-1]
    entry = import_skill(
        args.root,
        repo=args.repo,
        path=args.path,
        name=name,
        ref=ref,
        spdx=args.spdx,
        license_text=gh_file(args.repo, ref, args.license_path),
        fetch=gh_fetch,
        license_scope=args.license_scope,
        status=args.status,
    )
    print(f"imported {name} from {args.repo}@{ref[:8]} ({entry['upstreamHash'][:12]})")


if __name__ == "__main__":
    main()
