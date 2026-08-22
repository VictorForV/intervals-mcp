"""Tests for safe athlete lifecycle management."""

import stat

import pytest

from intervals_mcp import config, users


def seed(path):
    return users.add_user(path, "alex", "i111", "secret-one")


def test_add_creates_a_valid_owner_only_file(tmp_path):
    path = tmp_path / "users.toml"

    added = seed(path)

    assert config.load_users(path)[0].name == "alex"
    assert added.token
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_add_refuses_duplicate_names_and_athletes(tmp_path):
    path = tmp_path / "users.toml"
    seed(path)

    with pytest.raises(users.UserError):
        users.add_user(path, "alex", "i222", "secret-two")
    with pytest.raises(users.UserError):
        users.add_user(path, "bob", "i111", "secret-two")


def test_update_preserves_unspecified_secrets(tmp_path):
    path = tmp_path / "users.toml"
    original = seed(path)

    updated = users.update_user(path, "alex", name="alexander", athlete_id="222")

    assert updated.name == "alexander"
    assert updated.athlete_id == "i222"
    assert updated.api_key == "secret-one"
    assert updated.token == original.token


def test_update_can_replace_key_and_rotate_token(tmp_path):
    path = tmp_path / "users.toml"
    original = seed(path)

    updated = users.update_user(path, "alex", api_key="secret-two", rotate_token=True)

    assert updated.api_key == "secret-two"
    assert updated.token != original.token


def test_update_refuses_collisions(tmp_path):
    path = tmp_path / "users.toml"
    seed(path)
    users.add_user(path, "bob", "i222", "secret-two")

    with pytest.raises(users.UserError):
        users.update_user(path, "bob", name="alex")
    with pytest.raises(users.UserError):
        users.update_user(path, "bob", athlete_id="i111")


def test_remove_keeps_other_users(tmp_path):
    path = tmp_path / "users.toml"
    seed(path)
    users.add_user(path, "bob", "i222", "secret-two")

    removed = users.remove_user(path, "alex")

    assert removed.name == "alex"
    assert [user.name for user in config.load_users(path)] == ["bob"]


def test_remove_last_user_removes_the_secret_file(tmp_path):
    path = tmp_path / "users.toml"
    seed(path)

    users.remove_user(path, "alex")

    assert not path.exists()


def test_missing_user_operations_fail_cleanly(tmp_path):
    path = tmp_path / "users.toml"
    seed(path)

    with pytest.raises(users.UserError):
        users.find_user(path, "missing")
    with pytest.raises(users.UserError):
        users.update_user(path, "missing", name="new")
    with pytest.raises(users.UserError):
        users.remove_user(path, "missing")


def test_endpoint_urls_include_both_transports():
    result = users.endpoint_urls("https://mcp.example.com/", "secret-token")

    assert result == {
        "http": "https://mcp.example.com/secret-token/mcp",
        "sse": "https://mcp.example.com/secret-token/sse",
    }


def test_endpoint_urls_require_a_host():
    with pytest.raises(users.UserError):
        users.endpoint_urls("", "secret-token")
