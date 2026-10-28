"""Tests for the evaluation harness."""

from pathlib import Path

import pytest

from evals.judge import _fallback_judge, check_canary_leak, check_tool_correctness
from evals.runner import load_all_suites, load_suite

SUITES_DIR = Path("evals/suites")


@pytest.mark.unit
class TestEvalSuites:
    def test_all_suites_load(self):
        """All suite YAML files should load without errors."""
        suites = load_all_suites()
        assert len(suites) >= 4

    def test_task_success_suite(self):
        suite = load_suite("task_success")
        assert suite["name"] == "task_success"
        assert len(suite["cases"]) >= 15

    def test_permission_leakage_suite(self):
        suite = load_suite("permission_leakage")
        assert suite["name"] == "permission_leakage"
        assert len(suite["cases"]) >= 20

    def test_tool_correctness_suite(self):
        suite = load_suite("tool_correctness")
        assert suite["name"] == "tool_correctness"
        assert len(suite["cases"]) >= 10

    def test_over_refusal_suite(self):
        suite = load_suite("over_refusal")
        assert suite["name"] == "over_refusal"
        assert len(suite["cases"]) >= 10

    def test_all_cases_have_ids(self):
        """Every eval case should have a unique ID."""
        suites = load_all_suites()
        all_ids = []
        for suite in suites.values():
            for case in suite.get("cases", []):
                assert "id" in case, f"Case without ID in suite {suite['name']}"
                all_ids.append(case["id"])
        assert len(all_ids) == len(set(all_ids)), "Duplicate case IDs found"

    def test_all_cases_have_user(self):
        """Every case should specify a user with role."""
        suites = load_all_suites()
        for name, suite in suites.items():
            for case in suite.get("cases", []):
                assert "user" in case, f"Case {case['id']} in {name} has no user"
                assert "role" in case["user"], f"Case {case['id']} in {name} has no role"

    def test_all_cases_have_message(self):
        """Every case should have a message."""
        suites = load_all_suites()
        for name, suite in suites.items():
            for case in suite.get("cases", []):
                assert "message" in case and case["message"], f"Case {case['id']} in {name} has no message"


@pytest.mark.unit
class TestJudge:
    def test_canary_leak_clean(self):
        result = check_canary_leak("This is a normal response.", "ic", 20, [])
        assert not result["leaked"]

    def test_canary_leak_detected(self):
        registry = [
            {
                "canary": "CANARY-SAL-1234",
                "resource_type": "salary",
                "required_permission": "read:salary",
                "allowed_roles": ["hr_partner", "executive"],
                "allowed_employee_ids": [1],
            }
        ]
        result = check_canary_leak(
            "The salary is $100k CANARY-SAL-1234",
            "contractor",
            25,
            registry,
        )
        assert result["leaked"]
        assert len(result["leaked_canaries"]) == 1

    def test_canary_allowed(self):
        registry = [
            {
                "canary": "CANARY-SAL-1234",
                "resource_type": "salary",
                "required_permission": "read:salary",
                "allowed_roles": ["hr_partner", "executive"],
                "allowed_employee_ids": [1],
            }
        ]
        result = check_canary_leak(
            "The salary is $100k CANARY-SAL-1234",
            "executive",
            1,
            registry,
        )
        assert not result["leaked"]

    def test_tool_correctness_pass(self):
        result = check_tool_correctness(
            actual_tools=["hr_search_employees"],
            expected_tools=["hr_search_employees"],
        )
        assert result["pass"]
        assert result["score"] == 1.0

    def test_tool_correctness_missing(self):
        result = check_tool_correctness(
            actual_tools=["hr_search_employees"],
            expected_tools=["hr_search_employees", "hr_get_salary"],
        )
        assert not result["pass"]

    def test_tool_correctness_extra(self):
        result = check_tool_correctness(
            actual_tools=["hr_search_employees", "docs_search"],
            expected_tools=["hr_search_employees"],
        )
        assert result["pass"]  # Extra tools are OK
        assert result["score"] < 1.0

    def test_fallback_judge(self):
        result = _fallback_judge(
            "The Engineering department has about 28 employees.",
            "Around 28 employees in Engineering",
        )
        assert result["score"] > 0.2
