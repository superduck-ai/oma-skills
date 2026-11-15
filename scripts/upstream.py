import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.request


REPOSITORY = "anthropics/skills"
SUBTREE = "skills/claude-api"
BEGIN = b"<!-- BEGIN OMA DEPLOYMENT ADAPTER -->"
END = b"<!-- END OMA DEPLOYMENT ADAPTER -->"
MAX_ARCHIVE = 128 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[1]


class Invalid(ValueError):
    pass


def commit_sha(value):
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise Invalid("commit must be a full lowercase 40-character SHA")
    return value


def archive_url(commit):
    return f"https://api.github.com/repos/{REPOSITORY}/tarball/{commit}"


def download(commit):
    request = urllib.request.Request(archive_url(commit), headers={"User-Agent": "oma-skills-upstream"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = response.read(MAX_ARCHIVE + 1)
    if len(payload) > MAX_ARCHIVE:
        raise Invalid("upstream archive exceeds size limit")
    return payload


def read_archive(payload, commit):
    commit_sha(commit)
    files = {}
    seen = set()
    total = 0
    root = f"anthropics-skills-{commit[:7]}"
    prefix = root + "/" + SUBTREE + "/"
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        for member in archive:
            name = member.name.rstrip("/")
            path = PurePosixPath(name)
            if (path.is_absolute() or ".." in path.parts or "\\" in name
                    or str(path) != name or name in seen):
                raise Invalid(f"unsafe or duplicate archive path: {name}")
            seen.add(name)
            if path.parts[0] != root:
                raise Invalid("archive root does not match the pinned repository and commit")
            if member.type not in (tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE):
                raise Invalid(f"unsupported archive entry: {name}")
            if not name.startswith(prefix) or member.isdir():
                continue
            relative = name[len(prefix):]
            if member.mode & 0o7000:
                raise Invalid(f"unsupported archive permissions: {name}")
            total += member.size
            if total > MAX_ARCHIVE:
                raise Invalid("upstream subtree exceeds size limit")
            with archive.extractfile(member) as source:
                files[relative] = (source.read(), 0o755 if member.mode & 0o111 else 0o644)
    if "SKILL.md" not in files or "LICENSE.txt" not in files:
        raise Invalid("upstream skill or license is missing")
    return files


def inventory(files):
    return {name: {"sha256": hashlib.sha256(data).hexdigest(), "mode": mode}
            for name, (data, mode) in sorted(files.items())}


def read_tree(directory):
    if directory.is_symlink() or not directory.is_dir():
        raise Invalid(f"expected generated directory: {directory}")
    files = {}
    for path in directory.rglob("*"):
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            continue
        if not stat.S_ISREG(info.st_mode):
            raise Invalid(f"unsupported generated entry: {path}")
        files[path.relative_to(directory).as_posix()] = (path.read_bytes(), stat.S_IMODE(info.st_mode))
    return files


def insertion(root):
    overlay = (root / "overlays/entrypoint.md").read_bytes()
    if (not overlay.startswith(BEGIN + b"\n") or not overlay.endswith(END + b"\n")
            or overlay.count(BEGIN) != 1 or overlay.count(END) != 1):
        raise Invalid("entrypoint overlay must have exactly one enclosing OMA marker pair")
    return b"\n" + overlay + b"\n"


def compose(root, source):
    files = dict(source)
    skill, mode = files["SKILL.md"]
    if BEGIN in skill or END in skill:
        raise Invalid("upstream contains reserved OMA markers")
    heading = re.match(rb"\A---\r?\n.*?\r?\n---\r?\n.*?^# [^\r\n]+\r?\n", skill, re.S | re.M)
    if not heading:
        raise Invalid("upstream must contain frontmatter followed by an H1")
    if "oma/deployment.md" in files:
        raise Invalid("upstream collides with the deployment overlay")
    position = heading.end()
    files["SKILL.md"] = (skill[:position] + insertion(root) + skill[position:], mode)
    files["oma/deployment.md"] = ((root / "overlays/deployment.md").read_bytes(), 0o644)
    return files


def restore(files):
    source = dict(files)
    source.pop("oma/deployment.md", None)
    skill, mode = source["SKILL.md"]
    start = b"\n" + BEGIN + b"\n"
    finish = END + b"\n\n"
    if skill.count(BEGIN) != 1 or skill.count(END) != 1 or start not in skill or finish not in skill:
        raise Invalid("generated skill has invalid OMA markers")
    left, rest = skill.split(start, 1)
    _, right = rest.split(finish, 1)
    source["SKILL.md"] = (left + right, mode)
    return source


def load_lock(root):
    lock = json.loads((root / "upstream.lock.json").read_text())
    if lock.get("schema") != 1 or lock.get("repository") != REPOSITORY or lock.get("subtree") != SUBTREE:
        raise Invalid("unsupported upstream lock")
    commit_sha(lock["commit"])
    return lock


def require_manifest(files, expected, label):
    actual = inventory(files)
    if actual != expected:
        changed = sorted(name for name in actual.keys() | expected.keys() if actual.get(name) != expected.get(name))
        raise Invalid(f"{label} mismatch: {', '.join(changed)}")


def current_distribution(root, lock):
    if (root / "skills").is_symlink():
        raise Invalid("skills directory must not be a symlink")
    files = read_tree(root / SUBTREE)
    require_manifest(files, lock["distribution"], "generated distribution (manual edits are not overwritten)")
    return files


def make_lock(commit, source, files):
    return {"schema": 1, "repository": REPOSITORY, "subtree": SUBTREE,
            "commit": commit, "archive_url": archive_url(commit),
            "license": {"path": "LICENSE.txt", "url": f"https://github.com/{REPOSITORY}/blob/{commit}/{SUBTREE}/LICENSE.txt"},
            "source": inventory(source), "distribution": inventory(files)}


def check(root, archive=None, online=False):
    lock = load_lock(root)
    files = current_distribution(root, lock)
    source = restore(files)
    require_manifest(source, lock["source"], "restored upstream source")
    if compose(root, source) != files:
        raise Invalid("overlays changed; run sync to rebuild the distribution")
    if lock != make_lock(lock["commit"], source, files):
        raise Invalid("upstream lock metadata is inconsistent")
    if archive is not None or online:
        authoritative = read_archive(archive.read_bytes() if archive is not None else download(lock["commit"]), lock["commit"])
        if source != authoritative:
            raise Invalid("distribution differs from authoritative upstream archive")
    return lock


def sync(root, commit, archive=None):
    commit_sha(commit)
    if (root / "skills").is_symlink():
        raise Invalid("skills directory must not be a symlink")
    target = root / SUBTREE
    lock_path = root / "upstream.lock.json"
    if lock_path.exists():
        current_distribution(root, load_lock(root))
    elif target.exists() or target.is_symlink():
        raise Invalid("refusing to overwrite an untracked skill directory")
    payload = archive.read_bytes() if archive is not None else download(commit)
    source = read_archive(payload, commit)
    files = compose(root, source)
    lock = make_lock(commit, source, files)
    serialized = json.dumps(lock, indent=2, sort_keys=True) + "\n"
    if target.exists() and read_tree(target) == files and lock_path.read_text() == serialized:
        return lock
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".upstream-", dir=root) as temporary:
        stage = Path(temporary)
        tree = stage / "tree"
        tree.mkdir()
        for name, (data, mode) in files.items():
            path = tree / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(mode)
        require_manifest(read_tree(tree), lock["distribution"], "staged distribution")
        staged_lock = stage / "lock"
        staged_lock.write_text(serialized)
        backup = stage / "previous"
        old_lock = lock_path.read_bytes() if lock_path.exists() else None
        if target.exists():
            os.replace(target, backup)
        try:
            os.replace(tree, target)
            os.replace(staged_lock, lock_path)
        except BaseException:
            if target.exists():
                shutil.rmtree(target)
            if backup.exists():
                os.replace(backup, target)
            if old_lock is None:
                lock_path.unlink(missing_ok=True)
            else:
                lock_path.write_bytes(old_lock)
            raise
    return lock


def main():
    parser = argparse.ArgumentParser(description="Maintain the pinned official Claude API skill plus the OMA deployment overlay.")
    commands = parser.add_subparsers(dest="command", required=True)
    update = commands.add_parser("sync")
    update.add_argument("--commit", required=True)
    update.add_argument("--archive", type=Path)
    verify = commands.add_parser("check")
    authority = verify.add_mutually_exclusive_group()
    authority.add_argument("--archive", type=Path)
    authority.add_argument("--online", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.command == "sync":
            lock = sync(ROOT, arguments.commit, arguments.archive)
        else:
            lock = check(ROOT, arguments.archive, arguments.online)
        print(f"{arguments.command} passed: {REPOSITORY}@{lock['commit']} ({len(lock['source'])} upstream files)")
    except (OSError, ValueError, KeyError, tarfile.TarError) as error:
        print(f"upstream: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
