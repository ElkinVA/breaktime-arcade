"""Malformed Content-Length must be a client error, not a 500 (§6 item 9)."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from django.test import RequestFactory

from apps.gameplay.api.views import (
    MAX_RESULT_BODY_BYTES,
    SessionResultView,
    _content_length,
)


def _request(content_length: str):
    request = RequestFactory().post(
        "/api/v1/sessions/x/result",
        data="{}",
        content_type="application/json",
    )
    request.META["CONTENT_LENGTH"] = content_length
    return request


def test_non_numeric_content_length_returns_400() -> None:
    response = SessionResultView().post(_request("not-a-number"), uuid4())

    assert response.status_code == 400
    assert response.data["code"] == "E_INVALID_REQUEST"


def test_negative_content_length_returns_400() -> None:
    response = SessionResultView().post(_request("-10"), uuid4())

    assert response.status_code == 400
    assert response.data["code"] == "E_INVALID_REQUEST"


def test_oversized_content_length_returns_413() -> None:
    response = SessionResultView().post(_request(str(MAX_RESULT_BODY_BYTES + 1)), uuid4())

    assert response.status_code == 413
    assert response.data["code"] == "E_PAYLOAD_TOO_LARGE"


def test_content_length_parser_handles_missing_empty_zero_and_boundary() -> None:
    assert _content_length(SimpleNamespace(META={})) == 0
    assert _content_length(SimpleNamespace(META={"CONTENT_LENGTH": ""})) == 0
    assert _content_length(SimpleNamespace(META={"CONTENT_LENGTH": "0"})) == 0
    assert (
        _content_length(SimpleNamespace(META={"CONTENT_LENGTH": str(MAX_RESULT_BODY_BYTES)}))
        == MAX_RESULT_BODY_BYTES
    )
    assert _content_length(SimpleNamespace(META={"CONTENT_LENGTH": "9" * 5000})) is None
