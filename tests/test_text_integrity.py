"""Text integrity guardrails for project files and Agent-facing copy."""

from scripts.check_text_integrity import check_core_text_clean, run_checks


def test_project_text_integrity():
    issues = run_checks()
    assert not issues, "\n".join(issue.format() for issue in issues)


def test_agent_core_text_has_no_mojibake():
    issues = check_core_text_clean()
    assert not issues, "\n".join(issue.format() for issue in issues)
