from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.validate_controlled_test_environment import EXPECTED_LOCK_SHA256, validate


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent.parent
ENVIRONMENT = REPO / ".codex" / "environments" / "environment.toml"
POLICY = ROOT / "config" / "test_tooling_policy.json"
RUNNER = ROOT / "tools" / "modulec_canonical_structural_run.py"


class TestPhase1CControlledEnvironment(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = validate(REPO, ROOT)
        cls.environment_text = ENVIRONMENT.read_text(encoding="utf-8")
        cls.policy = json.loads(POLICY.read_text(encoding="utf-8"))

    def test_controlled_environment_replaces_obsolete_gate(self) -> None:
        self.assertEqual(self.result["status"], "PASS", self.result)
        self.assertNotIn("ENVIRONMENT_INERT", RUNNER.read_text(encoding="utf-8"))

    def test_environment_is_tracked_and_clean(self) -> None:
        self.assertEqual(self.result["status"], "PASS")

    def test_lock_hash_exact(self) -> None:
        self.assertEqual(self.result["lock_sha256"], EXPECTED_LOCK_SHA256)

    def test_pytest_version_exact(self) -> None:
        self.assertEqual(self.result["pytest_version"], "9.1.1")

    def test_pytest_under_tool_root(self) -> None:
        self.assertTrue(self.result["pytest_path"].lower().startswith(self.result["tool_root"].lower()))

    def test_pip_check_passes(self) -> None:
        self.assertEqual(self.result["pip_check"], "PASS")

    def test_no_global_install_policy(self) -> None:
        self.assertIn("allow_global_install", self.policy)
        self.assertFalse(self.policy["allow_global_install"])

    def test_no_user_install_policy(self) -> None:
        self.assertFalse(self.policy["allow_user_install"])

    def test_official_index_only(self) -> None:
        self.assertEqual(self.policy["official_index"], "https://pypi.org/simple")

    def test_wheels_only(self) -> None:
        self.assertTrue(self.policy["only_binary"])
        self.assertFalse(self.policy["allow_source_distributions"])

    def test_plugin_autoload_disabled(self) -> None:
        self.assertFalse(self.policy["allow_plugins_autoload"])
        self.assertIn("PYTEST_DISABLE_PLUGIN_AUTOLOAD", self.environment_text)

    def test_bytecode_disabled(self) -> None:
        self.assertFalse(self.policy["write_bytecode"])
        self.assertIn("PYTHONDONTWRITEBYTECODE", self.environment_text)

    def test_pytest_cache_disabled(self) -> None:
        self.assertEqual(self.policy["pytest_cache"], "disabled")

    def test_setup_does_not_run_scientific_pipeline(self) -> None:
        self.assertNotIn("moduleC_pipeline_v2.py", self.environment_text)

    def test_cleanup_is_non_destructive(self) -> None:
        cleanup = self.environment_text.split("[cleanup.win32]", 1)[1].split("[[actions]]", 1)[0]
        self.assertNotIn("Remove-Item", cleanup)

    def test_policy_separates_persistent_tooling(self) -> None:
        self.assertIn("persistent_tooling_parent", self.policy)
        self.assertIn("resolution_staging_parent", self.policy)
        self.assertNotIn("tooling_parent", self.policy)

    def test_preflight_does_not_download(self) -> None:
        self.assertEqual(self.result["download_performed_this_phase"], "false")

    def test_lock_mismatch_is_a_distinct_gate(self) -> None:
        self.assertIn("BLOCKED_LOCK_SHA256_MISMATCH", self.environment_text)

    def test_pytest_mismatch_is_a_distinct_gate(self) -> None:
        self.assertIn("BLOCKED_PYTEST_VERSION_MISMATCH", self.environment_text)

    def test_pytest_outside_tool_root_is_a_distinct_gate(self) -> None:
        self.assertIn("BLOCKED_PYTEST_OUTSIDE_PROJECT_TOOLING", self.environment_text)

    def test_smokerun_requires_controlled_environment(self) -> None:
        self.assertIn("CONTROLLED_PROJECT_TEST_ENVIRONMENT", RUNNER.read_text(encoding="utf-8"))

    def test_scientific_runtime_disallowed(self) -> None:
        self.assertFalse(self.policy["scientific_runtime_allowed"])
        self.assertEqual(self.result["scientific_runtime_started"], "false")


if __name__ == "__main__":
    unittest.main()
