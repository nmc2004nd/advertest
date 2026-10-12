"""Nhận xét chi tiết bằng LLM: client chuẩn OpenAI (DeepSeek) và kiểm đầu ra, không cần DB."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from advertest_contracts.models import MAX_NARRATIVE_ITEMS
from backend.app.insight.llm import DEFAULT_BASE_URL, DEFAULT_MODEL, LlmClient, client_from_env
from backend.app.insight.narrative import parse_content
from backend.app.services.errors import LlmFailed


def _client(handler: Any) -> LlmClient:
    return LlmClient(
        base_url="https://llm.test/",
        model="deepseek-chat",
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
    )


def _reply(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_chat_json_sends_openai_request() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return _reply('{"summary": "ok"}')

    assert _client(handler).chat_json("hệ thống", "dữ liệu") == {"summary": "ok"}
    assert seen["url"] == "https://llm.test/chat/completions"
    assert seen["auth"] == "Bearer sk-test"
    body = seen["body"]
    assert body["model"] == "deepseek-chat"
    assert body["response_format"] == {"type": "json_object"}
    assert [msg["role"] for msg in body["messages"]] == ["system", "user"]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text="lỗi"),
        httpx.Response(401, json={"error": "bad key"}),
        _reply("không phải json"),
        _reply("[1, 2]"),
        httpx.Response(200, json={"choices": []}),
    ],
)
def test_chat_json_errors_are_llm_failed(response: httpx.Response) -> None:
    with pytest.raises(LlmFailed):
        _client(lambda _: response).chat_json("s", "u")


def test_network_error_is_llm_failed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    with pytest.raises(LlmFailed) as info:
        _client(handler).chat_json("s", "u")
    assert "sk-test" not in str(info.value)


def test_client_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "LLM_TIMEOUT_S"):
        monkeypatch.delenv(name, raising=False)
    assert client_from_env() is None
    monkeypatch.setenv("LLM_API_KEY", "sk-x")
    client = client_from_env()
    assert client is not None
    assert (client.base_url, client.model) == (DEFAULT_BASE_URL, DEFAULT_MODEL)
    monkeypatch.setenv("LLM_MODEL", "deepseek-reasoner")
    monkeypatch.setenv("LLM_TIMEOUT_S", "abc")
    client = client_from_env()
    assert client is not None and client.model == "deepseek-reasoner"


def test_parse_content_clips_lists_and_text() -> None:
    raw = {
        "summary": "  Tóm tắt  ",
        "findings": [{"title": f"t{i}", "detail": "d" * 3000} for i in range(8)]
        + [{"title": "", "detail": "bỏ"}, "sai kiểu"],
        "next_steps": ["a", " ", "b", "c", "d", "e", "f"],
    }
    content = parse_content(raw)
    assert content["summary"] == "Tóm tắt"
    assert len(content["findings"]) == MAX_NARRATIVE_ITEMS
    assert len(content["findings"][0]["detail"]) == 2000
    assert content["next_steps"] == ["a", "b", "c", "d", "e"]


@pytest.mark.parametrize("raw", [{}, {"summary": ""}, {"summary": "x", "findings": 3}])
def test_parse_content_rejects_bad_shape(raw: dict[str, Any]) -> None:
    with pytest.raises(LlmFailed):
        parse_content(raw)
