"""Check repository text files for encoding and visible mojibake issues."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_TARGETS = (
    "backend",
    "frontend",
    "tests",
    "docs",
    "README.md",
    "task_plan.md",
    "findings.md",
    "progress.md",
    "pytest.ini",
    "requirements.txt",
    ".env.example",
    ".editorconfig",
)

TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".ini",
    ".cfg",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".csv",
    ".env",
    ".editorconfig",
}

SKIP_DIRS = {
    ".git",
    ".idea",
    ".pytest_cache",
    ".venv",
    "__pycache__",
}

STRONG_MOJIBAKE_FRAGMENTS = (
    "�",
    "锛",
    "锝",
    "銆",
    "鈥",
    "鈫",
    "鉁",
    "鈺",
    "愨",
    "晲",
    "€?",
    "Ã",
    "Â",
    "â€",
)

CORE_TEXT_FILES = (
    Path("backend/agent/tools.py"),
    Path("backend/agent/report_builder.py"),
    Path("backend/agent/nodes/understand_query.py"),
    Path("backend/api/agent_api.py"),
)


@dataclass(frozen=True)
class Issue:
    path: Path
    line: int | None
    code: str
    message: str

    def format(self) -> str:
        location = str(self.path)
        if self.line is not None:
            location = f"{location}:{self.line}"
        return f"{location}: {self.code}: {self.message}"


def iter_target_files(targets: Iterable[str] = DEFAULT_TARGETS) -> Iterable[Path]:
    for target in targets:
        path = ROOT / target
        if not path.exists():
            continue
        if path.is_file():
            if is_text_candidate(path):
                yield path
            continue
        for child in path.rglob("*"):
            if child.is_file() and is_text_candidate(child):
                yield child


def is_text_candidate(path: Path) -> bool:
    if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
        return False
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in {".env.example", ".editorconfig"}


def decode_utf8(path: Path) -> tuple[str | None, Issue | None]:
    try:
        return path.read_text(encoding="utf-8"), None
    except UnicodeDecodeError as exc:
        return None, Issue(
            path.relative_to(ROOT),
            None,
            "non_utf8",
            f"file is not valid UTF-8: {exc}",
        )


def check_visible_text(path: Path, text: str) -> list[Issue]:
    issues: list[Issue] = []
    rel = path.relative_to(ROOT)

    for line_no, line in enumerate(text.splitlines(), start=1):
        if "\ufeff" in line:
            issues.append(Issue(rel, line_no, "bom", "unexpected UTF-8 BOM marker in text"))
        if "\ufffd" in line:
            issues.append(Issue(rel, line_no, "replacement_char", "contains U+FFFD replacement character"))
        if any("\ue000" <= ch <= "\uf8ff" for ch in line):
            issues.append(Issue(rel, line_no, "private_use", "contains Unicode private-use character"))

        matches = [fragment for fragment in STRONG_MOJIBAKE_FRAGMENTS if fragment in line]
        if matches:
            shown = ", ".join(repr(match) for match in matches[:5])
            issues.append(Issue(rel, line_no, "mojibake", f"contains common mojibake fragment(s): {shown}"))

    return issues


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _has_encoding(node: ast.Call) -> bool:
    return any(keyword.arg == "encoding" for keyword in node.keywords)


def _is_binary_mode(node: ast.Call) -> bool:
    for arg in node.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and "b" in arg.value:
            return True
    for keyword in node.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
            value = keyword.value.value
            return isinstance(value, str) and "b" in value
    return False


def check_python_text_io(path: Path, text: str) -> list[Issue]:
    if path.suffix != ".py":
        return []

    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return []

    issues: list[Issue] = []
    rel = path.relative_to(ROOT)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name not in {"open", "read_text", "write_text"}:
            continue
        if _is_binary_mode(node):
            continue
        if _has_encoding(node):
            continue
        issues.append(Issue(rel, node.lineno, "missing_utf8_encoding", f"{name}() should pass encoding='utf-8'"))
    return issues


def run_checks(targets: Iterable[str] = DEFAULT_TARGETS) -> list[Issue]:
    issues: list[Issue] = []
    for path in sorted(set(iter_target_files(targets))):
        text, decode_issue = decode_utf8(path)
        if decode_issue is not None:
            issues.append(decode_issue)
            continue
        assert text is not None
        issues.extend(check_visible_text(path, text))
        issues.extend(check_python_text_io(path, text))
    return issues


def check_core_text_clean() -> list[Issue]:
    issues: list[Issue] = []
    for rel in CORE_TEXT_FILES:
        path = ROOT / rel
        if not path.exists():
            continue
        text, decode_issue = decode_utf8(path)
        if decode_issue is not None:
            issues.append(decode_issue)
            continue
        assert text is not None
        issues.extend(check_visible_text(path, text))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Check project text integrity.")
    parser.add_argument("targets", nargs="*", help="Optional paths relative to repository root.")
    args = parser.parse_args()

    issues = run_checks(args.targets or DEFAULT_TARGETS)
    if issues:
        print("Text integrity check failed:")
        for issue in issues:
            print(f"- {issue.format()}")
        return 1

    print("Text integrity check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
