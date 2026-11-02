"""Offline backup contract tests. Run: python3 -m unittest discover -s tests -v."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "backup.sh"
DOCKER = """#!/bin/sh
case "$*" in
  'exec mailflow-postgres sh -c '*)
    case "$FAKE_MODE" in
      dump-failure) exit 1;;
      empty) exit 0;;
      *) printf 'fake-dump';;
    esac;;
  'exec -i mailflow-postgres pg_restore --list')
    input=$(cat)
    [ "$input" = fake-dump ] || exit 1
    case "$FAKE_MODE" in
      invalid) exit 1;;
      no-tables) printf 'archive header only';;
      *) printf '123; 0 123 TABLE DATA public messages postgres\\n';;
    esac;;
  *) echo "Unexpected Docker call" >&2; exit 99;;
esac
"""


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mailflow-backup-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dumps = self.root / "mailflow" / "backups"
        self.dumps.mkdir(parents=True)
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        docker = bin_dir / "docker"
        docker.write_text(DOCKER)
        docker.chmod(0o700)
        self.env = {**os.environ, "HOME": str(self.root),
                    "PATH": f"{bin_dir}:/usr/bin:/bin", "FAKE_MODE": "success"}

    def seed(self):
        # Nine automatic dumps, one in the legacy cron naming scheme.
        for i in range(9):
            name = f"mailflow-auto-2026010{i + 1}-0330.dump"
            if i == 0:
                name = "mailflow-20260101-0330.dump"
            path = self.dumps / name
            path.write_text("old dump")
            os.utime(path, (100 + i, 100 + i))
        for name in ("pre-failback.dump", "mailflow-20260101-1200.dump"):
            (self.dumps / name).write_text("manual dump")

    def run_backup(self, mode="success"):
        return subprocess.run(["sh", str(SCRIPT)], env={**self.env, "FAKE_MODE": mode},
                              capture_output=True, text=True, timeout=10)

    def test_success_verifies_rotates_and_preserves_manual_dumps(self):
        self.seed()
        result = self.run_backup()
        self.assertEqual(result.returncode, 0, result.stderr)
        automatic = list(self.dumps.glob("mailflow-auto-*.dump"))
        self.assertEqual(len(automatic), 7)
        self.assertFalse((self.dumps / "mailflow-20260101-0330.dump").exists())
        self.assertEqual((self.dumps / "pre-failback.dump").read_text(), "manual dump")
        self.assertEqual((self.dumps / "mailflow-20260101-1200.dump").read_text(), "manual dump")
        output = next(p for p in automatic if p.read_text() == "fake-dump")
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertIn(" OK ", (self.dumps / "backup.log").read_text())
        self.assertFalse(list(self.dumps.glob("*.tmp")))

    def test_failures_leave_previous_backups_untouched(self):
        self.seed()
        before = {p.name: p.read_bytes() for p in self.dumps.iterdir()}
        for mode in ("dump-failure", "empty", "invalid", "no-tables"):
            with self.subTest(mode=mode):
                result = self.run_backup(mode)
                self.assertNotEqual(result.returncode, 0)
                after = {p.name: p.read_bytes() for p in self.dumps.iterdir()
                         if p.name != "backup.log"}
                self.assertEqual(before, after)
                self.assertIn("ECHEC", (self.dumps / "backup.log").read_text())


if __name__ == "__main__":
    unittest.main()
