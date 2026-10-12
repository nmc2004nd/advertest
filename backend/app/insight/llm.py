"""Client LLM theo API chuẩn OpenAI (`POST {base}/chat/completions`), mặc định DeepSeek.

Cấu hình qua biến môi trường: `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_TIMEOUT_S`. Không
có `LLM_API_KEY` thì tính năng nhận xét chi tiết tắt. Lỗi mạng, HTTP hay đầu ra không phải JSON
đều thành `LlmFailed`; chi tiết chỉ ghi log server (không lộ khóa hay nội dung phản hồi).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

from backend.app.services.errors import LlmFailed

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_TIMEOUT_S = 90.0
MAX_TOKENS = 2000


@dataclass(frozen=True)
class LlmClient:
    base_url: str
    model: str
    api_key: str
    timeout_s: float = DEFAULT_TIMEOUT_S
    transport: httpx.BaseTransport | None = None  # test thay bằng httpx.MockTransport

    def chat_json(self, system: str, user: str) -> dict[str, Any]:
        """Một lượt hỏi, yêu cầu trả một object JSON (`response_format: json_object`)."""
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
            "max_tokens": MAX_TOKENS,
            "stream": False,
        }
        try:
            with httpx.Client(timeout=self.timeout_s, transport=self.transport) as client:
                response = client.post(
                    f"{self.base_url.rstrip('/')}/chat/completions",
                    json=body,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
        except httpx.HTTPError as exc:
            logger.warning("Gọi LLM thất bại: %s", type(exc).__name__)
            raise LlmFailed("Không kết nối được tới LLM. Vui lòng thử lại sau.") from exc
        if response.status_code != 200:
            logger.warning("LLM trả HTTP %s", response.status_code)
            raise LlmFailed(f"LLM trả lỗi HTTP {response.status_code}. Vui lòng thử lại sau.")
        try:
            content = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            logger.warning("LLM trả nội dung không phải JSON hợp lệ")
            raise LlmFailed("LLM trả nội dung không đúng định dạng. Vui lòng thử lại.") from exc
        if not isinstance(parsed, dict):
            raise LlmFailed("LLM trả nội dung không đúng định dạng. Vui lòng thử lại.")
        return parsed


def client_from_env() -> LlmClient | None:
    """Client theo biến môi trường; None khi chưa đặt `LLM_API_KEY`."""
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        timeout = float(os.environ.get("LLM_TIMEOUT_S") or DEFAULT_TIMEOUT_S)
    except ValueError:
        timeout = DEFAULT_TIMEOUT_S
    return LlmClient(
        base_url=os.environ.get("LLM_BASE_URL", "").strip() or DEFAULT_BASE_URL,
        model=os.environ.get("LLM_MODEL", "").strip() or DEFAULT_MODEL,
        api_key=api_key,
        timeout_s=timeout,
    )
