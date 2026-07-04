"""Minimal LLM connectivity check.

Run from project root:
    python scripts/test_llm_connection.py
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
from backend.core.llm import get_llm


def _mask_key(key: str) -> str:
    if not key:
        return "<missing>"
    if len(key) <= 8:
        return "<present: short key hidden>"
    return f"{key[:4]}...{key[-4:]}"


def main() -> None:
    print("LLM connection test")
    print(f"base_url: {OPENAI_BASE_URL}")
    print(f"model: {OPENAI_MODEL}")
    print(f"api_key: {_mask_key(OPENAI_API_KEY)}")
    print(f"api_key_exists: {bool(OPENAI_API_KEY)}")
    print()

    try:
        llm = get_llm(temperature=0.0)
        response = llm.invoke("你好")
        content = response.content if hasattr(response, "content") else str(response)
        print("SUCCESS: LLM responded.")
        # 强制 ASCII 编码打印，避免 GBK 终端下 emoji 报错
        safe = content.encode("ascii", errors="backslashreplace").decode("ascii")
        print(f"response ({len(content)} chars): {safe[:200]}{'...' if len(safe) > 200 else ''}")
    except Exception:
        print("FAILED: LLM connection or invocation failed.")
        print("Full traceback:")
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
