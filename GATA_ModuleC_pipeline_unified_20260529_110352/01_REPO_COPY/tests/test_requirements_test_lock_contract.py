from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "config" / "requirements-test.lock"
ALLOWLIST = {"pytest", "iniconfig", "packaging", "pluggy", "pygments", "colorama", "exceptiongroup", "tomli", "typing-extensions", "atomicwrites"}


class TestRequirementsTestLockContract(unittest.TestCase):
    def test_lock_is_exact_hashed_and_allowlisted(self) -> None:
        lines = [line.strip() for line in LOCK.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
        self.assertEqual(lines, sorted(lines))
        names = []
        for line in lines:
            match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^ ]+) --hash=sha256:([0-9a-f]{64})", line)
            self.assertIsNotNone(match, line)
            assert match is not None
            names.append(match.group(1))
            self.assertIn(match.group(1), ALLOWLIST)
        self.assertEqual(names.count("pytest"), 1)
        self.assertIn("pytest==9.1.1", "\n".join(lines))
        self.assertFalse(any(token in LOCK.read_text(encoding="utf-8") for token in (">=", "<=", "~=", "http://", "https://", "-e ")))

    def test_project_actions_require_locked_binary_tooling(self) -> None:
        environment = (ROOT.parent.parent / ".codex" / "environments" / "environment.toml").read_text(encoding="utf-8")
        self.assertIn("requirements-test.lock", environment)
        self.assertIn("--require-hashes", environment)
        self.assertIn("--only-binary=:all:", environment)
        self.assertNotIn("pip install -U", environment)


if __name__ == "__main__":
    unittest.main()
