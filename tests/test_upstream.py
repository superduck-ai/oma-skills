import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import urllib.error


SPEC = importlib.util.spec_from_file_location("upstream", Path(__file__).resolve().parents[1] / "scripts/upstream.py")
upstream = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(upstream)
COMMIT = "a" * 40
PREFIX = f"anthropics-skills-{COMMIT[:7]}/skills/claude-api/"
SKILL = b'---\nname: claude-api\ndescription: "Official description"\n---\n\n# Claude API\n\n  Exact upstream whitespace.  \n'
SOURCE = {"SKILL.md": (SKILL, 0o644), "LICENSE.txt": (b"Official license\n", 0o644),
          "references/tools.md": (b"Official tool schemas and descriptions\n", 0o644),
          "scripts/example.sh": (b"echo official\n", 0o755)}


def archive_bytes(files=SOURCE, extra=()):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name, (data, mode) in files.items():
            item = tarfile.TarInfo(PREFIX + name)
            item.size = len(data)
            item.mode = mode
            archive.addfile(item, io.BytesIO(data))
        for item in extra:
            archive.addfile(item, io.BytesIO(b""))
    return stream.getvalue()


class UpstreamTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "overlays").mkdir()
        self.entrypoint = self.root / "overlays/entrypoint.md"
        self.entrypoint.write_bytes(upstream.BEGIN + b"\nDeployment instructions.\n" + upstream.END + b"\n")
        (self.root / "overlays/deployment.md").write_bytes(b"Deployment configuration.\n")
        self.archive = self.root / "official.tar.gz"
        self.archive.write_bytes(archive_bytes())

    def sync(self):
        return upstream.sync(self.root, COMMIT, self.archive)

    def snapshot(self):
        return (upstream.read_tree(self.root / upstream.SUBTREE), (self.root / "upstream.lock.json").read_bytes())

    def test_rejects_short_sha_before_mutation_or_network(self):
        with patch.object(upstream, "download") as download:
            with self.assertRaises(upstream.Invalid):
                upstream.sync(self.root, "aaaaaaa")
        download.assert_not_called()
        self.assertFalse((self.root / upstream.SUBTREE).exists())

    def test_detects_tampered_missing_and_extra_files(self):
        for kind in ("tamper", "missing", "extra", "mode", "symlink"):
            with self.subTest(kind=kind):
                self.sync()
                target = self.root / upstream.SUBTREE / "references/tools.md"
                if kind == "tamper":
                    target.write_bytes(b"changed")
                elif kind == "missing":
                    target.unlink()
                elif kind == "extra":
                    target = target.parent / "extra.md"
                    target.write_bytes(b"extra")
                elif kind == "mode":
                    target.chmod(0o755)
                else:
                    target.unlink()
                    target.symlink_to(self.entrypoint)
                with self.assertRaises(upstream.Invalid):
                    upstream.check(self.root)
                with self.assertRaises(upstream.Invalid):
                    self.sync()
                target.unlink(missing_ok=True)
                if kind != "extra":
                    target.write_bytes(SOURCE["references/tools.md"][0])
                    target.chmod(0o644)

    def test_rejects_untracked_output(self):
        target = self.root / upstream.SUBTREE
        target.mkdir(parents=True)
        (target / "manual.md").write_bytes(b"manual")
        with self.assertRaises(upstream.Invalid):
            self.sync()
        self.assertEqual((target / "manual.md").read_bytes(), b"manual")

    def test_rejects_unsafe_archives_without_changing_distribution(self):
        self.sync()
        previous = self.snapshot()
        for name, kind in ((PREFIX + "../outside", tarfile.REGTYPE),
                           ("/absolute", tarfile.REGTYPE),
                           (PREFIX + "alias", tarfile.SYMTYPE),
                           (PREFIX + "hardlink", tarfile.LNKTYPE),
                           (PREFIX + "device", tarfile.CHRTYPE),
                           (PREFIX + "SKILL.md", tarfile.REGTYPE),
                           (PREFIX + "nested//file", tarfile.REGTYPE)):
            with self.subTest(name=name, kind=kind):
                item = tarfile.TarInfo(name)
                item.type = kind
                item.linkname = "SKILL.md"
                self.archive.write_bytes(archive_bytes(extra=[item]))
                with self.assertRaises(upstream.Invalid):
                    self.sync()
                self.assertEqual(self.snapshot(), previous)

    def test_invalid_upstream_layout_preserves_distribution(self):
        self.sync()
        previous = self.snapshot()
        files = dict(SOURCE)
        files["SKILL.md"] = (b"missing frontmatter and heading", 0o644)
        self.archive.write_bytes(archive_bytes(files))
        with self.assertRaises(upstream.Invalid):
            self.sync()
        self.assertEqual(self.snapshot(), previous)

    def test_invalid_overlay_preserves_distribution(self):
        self.sync()
        previous = self.snapshot()
        self.entrypoint.write_bytes(b"unmarked instructions\n")
        with self.assertRaises(upstream.Invalid):
            self.sync()
        self.assertEqual(self.snapshot(), previous)

    def test_lock_provenance_cannot_silently_change(self):
        self.sync()
        lock_path = self.root / "upstream.lock.json"
        lock = json.loads(lock_path.read_text())
        lock["archive_url"] = "https://example.invalid/replacement"
        lock_path.write_text(json.dumps(lock))
        with self.assertRaisesRegex(upstream.Invalid, "metadata"):
            upstream.check(self.root)

    def test_parent_symlink_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / "skills").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(upstream.Invalid):
            self.sync()
        self.assertEqual(list(outside.iterdir()), [])

    def test_network_failure_is_failure_and_preserves_distribution(self):
        self.sync()
        previous = self.snapshot()
        with patch.object(upstream.urllib.request, "urlopen", side_effect=urllib.error.URLError("offline")):
            with self.assertRaises(urllib.error.URLError):
                upstream.check(self.root, online=True)
            with self.assertRaises(urllib.error.URLError):
                upstream.sync(self.root, COMMIT)
            with patch.object(upstream, "ROOT", self.root), patch("sys.argv", ["upstream.py", "check", "--online"]):
                with patch("sys.stderr", new=io.StringIO()):
                    self.assertEqual(upstream.main(), 1)
        self.assertEqual(self.snapshot(), previous)

    def test_failed_replacement_rolls_back_tree_and_lock(self):
        self.sync()
        previous = self.snapshot()
        (self.root / "overlays/deployment.md").write_bytes(b"Updated deployment\n")
        replace = os.replace

        def fail_lock(source, target):
            if Path(source).name == "lock":
                raise OSError("injected replacement failure")
            return replace(source, target)

        with patch.object(upstream.os, "replace", side_effect=fail_lock):
            with self.assertRaises(OSError):
                self.sync()
        self.assertEqual(self.snapshot(), previous)
        self.assertEqual(list(self.root.glob(".upstream-*")), [])

    def test_authoritative_check_does_not_trust_rewritten_local_hashes(self):
        self.sync()
        target = self.root / upstream.SUBTREE / "references/tools.md"
        target.write_bytes(b"edited upstream")
        lock_path = self.root / "upstream.lock.json"
        lock = json.loads(lock_path.read_text())
        distribution = upstream.read_tree(self.root / upstream.SUBTREE)
        lock["distribution"] = upstream.inventory(distribution)
        lock["source"] = upstream.inventory(upstream.restore(distribution))
        lock_path.write_text(json.dumps(lock))
        upstream.check(self.root)
        with self.assertRaisesRegex(upstream.Invalid, "authoritative"):
            upstream.check(self.root, archive=self.archive)

    def test_composition_preserves_official_bytes_modes_and_frontmatter(self):
        lock = self.sync()
        files = upstream.read_tree(self.root / upstream.SUBTREE)
        self.assertEqual(upstream.restore(files), SOURCE)
        for name, value in SOURCE.items():
            if name != "SKILL.md":
                self.assertEqual(files[name], value)
        original_frontmatter = SKILL.split(b"---", 2)[:2]
        self.assertEqual(files["SKILL.md"][0].split(b"---", 2)[:2], original_frontmatter)
        self.assertTrue(files["SKILL.md"][0].startswith(SKILL[:SKILL.index(b"# Claude API\n") + len(b"# Claude API\n")]))
        self.assertEqual(lock["source"], upstream.inventory(SOURCE))
        self.assertEqual(upstream.check(self.root, archive=self.archive), lock)

    def test_repeated_sync_is_identical_and_does_not_replace_files(self):
        self.sync()
        previous = self.snapshot()
        with patch.object(upstream.os, "replace") as replace:
            self.sync()
        replace.assert_not_called()
        self.assertEqual(self.snapshot(), previous)

    def test_archive_permissions_round_trip_through_git_modes(self):
        files = {name: (data, mode | 0o020) for name, (data, mode) in SOURCE.items()}
        self.archive.write_bytes(archive_bytes(files))
        self.sync()
        self.assertEqual(upstream.restore(upstream.read_tree(self.root / upstream.SUBTREE)), SOURCE)
        upstream.check(self.root, archive=self.archive)

    def test_overlay_changes_require_rebuild_and_keep_source_intact(self):
        self.sync()
        self.entrypoint.write_bytes(upstream.BEGIN + b"\nUpdated instructions.\n" + upstream.END + b"\n")
        (self.root / "overlays/deployment.md").write_bytes(b"Updated configuration.\n")
        with self.assertRaisesRegex(upstream.Invalid, "overlays changed"):
            upstream.check(self.root)
        self.sync()
        upstream.check(self.root, archive=self.archive)
        files = upstream.read_tree(self.root / upstream.SUBTREE)
        self.assertEqual(upstream.restore(files), SOURCE)
        self.assertIn(self.entrypoint.read_bytes(), files["SKILL.md"][0])
        self.assertEqual(files["oma/deployment.md"][0], b"Updated configuration.\n")


if __name__ == "__main__":
    unittest.main()
