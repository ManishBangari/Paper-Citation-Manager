import pytest

from app.config import settings


def test_no_browser_origin_is_allowed_by_default(client):
    res = client.options("/papers/", headers={"Origin": "https://evil.example",
                                              "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in res.headers


@pytest.mark.parametrize("value, expected", [
    ("", []),
    ("   ", []),
    ("https://ui.example.com", ["https://ui.example.com"]),
    ("https://a.example.com, https://b.example.com ,", ["https://a.example.com", "https://b.example.com"]),
])
def test_cors_origins_setting_is_parsed(monkeypatch, value, expected):
    monkeypatch.setattr(settings, "cors_origins", value)
    assert settings.cors_origin_list == expected
