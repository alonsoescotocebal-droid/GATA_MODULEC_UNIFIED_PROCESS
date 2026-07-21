from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import modulec_test_tooling_bootstrap as bootstrap


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config" / "test_tooling_policy.json"


class TestToolingBootstrapContract(unittest.TestCase):
    def test_version_matrix(self) -> None:
        self.assertEqual(bootstrap.select_pytest((3, 14, 0)), "9.1.1")
        self.assertEqual(bootstrap.select_pytest((3, 9, 0)), "8.4.2")
        self.assertEqual(bootstrap.select_pytest((3, 8, 0)), "8.3.5")
        self.assertEqual(bootstrap.select_pytest((3, 7, 0)), "7.4.4")
        with self.assertRaisesRegex(RuntimeError, "UNSUPPORTED"):
            bootstrap.select_pytest((3, 6, 9))

    def test_policy_is_safe_and_allowlisted(self) -> None:
        policy = bootstrap.load_policy(POLICY)
        self.assertTrue(policy["only_binary"])
        self.assertFalse(policy["allow_source_distributions"])
        self.assertFalse(policy["allow_global_install"])
        self.assertFalse(policy["allow_user_install"])
        self.assertEqual(policy["pytest_cache"], "disabled")

    def test_root_must_be_under_runtime_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "OUTSIDE"):
                bootstrap.validate_root(Path(tmp), ROOT, Path(tmp) / "tooling")

    def test_nonempty_root_is_rejected_by_plan(self) -> None:
        self.assertIn("BLOCKED_BOOTSTRAP_ROOT_NOT_EMPTY", Path(bootstrap.__file__).read_text(encoding="utf-8"))

    def test_network_modes_require_approval(self) -> None:
        self.assertIn("BLOCKED_TEST_TOOLING_DOWNLOAD_APPROVAL_REQUIRED", Path(bootstrap.__file__).read_text(encoding="utf-8"))

    def test_source_distributions_and_global_install_are_blocked(self) -> None:
        text = Path(bootstrap.__file__).read_text(encoding="utf-8")
        self.assertIn("allow_source_distributions", text)
        self.assertIn("allow_global_install", text)
        self.assertIn("only_binary", text)

    def test_checkpoint_binds_plan_and_targets(self) -> None:
        text = Path(bootstrap.__file__).read_text(encoding="utf-8")
        for field in ("approved_targets_sha256", "policy_sha256", "plan_sha256", "next_authorized_action"):
            self.assertIn(field, text)

    def test_no_scientific_full_runtime(self) -> None:
        self.assertNotIn("moduleC_pipeline_v2", Path(bootstrap.__file__).read_text(encoding="utf-8"))

    def test_required_targets_are_frozen(self) -> None:
        selected = bootstrap.targets(ROOT)
        self.assertEqual(selected[:3], [
            "tests/test_structural_launcher_contract.py",
            "tests/test_phase1b_structural_completion.py",
            "tests/test_test_tooling_bootstrap_contract.py",
        ])


if __name__ == "__main__":
    unittest.main()
