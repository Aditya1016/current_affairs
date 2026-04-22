"""Tests for app/config.py — settings parsing helpers."""
import os

from app.config import _parse_csv_env


class TestParseCsvEnv:
    def test_returns_default_when_env_not_set(self):
        default = ["a", "b", "c"]
        os.environ.pop("_TEST_CSV_VAR", None)
        result = _parse_csv_env("_TEST_CSV_VAR", default)
        assert result == default

    def test_returns_default_when_env_is_empty_string(self, monkeypatch):
        monkeypatch.setenv("_TEST_CSV_VAR", "")
        result = _parse_csv_env("_TEST_CSV_VAR", ["default"])
        assert result == ["default"]

    def test_parses_single_value(self, monkeypatch):
        monkeypatch.setenv("_TEST_CSV_VAR", "https://feed.example.com")
        result = _parse_csv_env("_TEST_CSV_VAR", [])
        assert result == ["https://feed.example.com"]

    def test_parses_multiple_values(self, monkeypatch):
        monkeypatch.setenv("_TEST_CSV_VAR", "a,b,c")
        result = _parse_csv_env("_TEST_CSV_VAR", [])
        assert result == ["a", "b", "c"]

    def test_strips_whitespace_around_entries(self, monkeypatch):
        monkeypatch.setenv("_TEST_CSV_VAR", " a , b , c ")
        result = _parse_csv_env("_TEST_CSV_VAR", [])
        assert result == ["a", "b", "c"]

    def test_ignores_empty_entries(self, monkeypatch):
        monkeypatch.setenv("_TEST_CSV_VAR", "a,,b,  ,c")
        result = _parse_csv_env("_TEST_CSV_VAR", [])
        assert result == ["a", "b", "c"]
