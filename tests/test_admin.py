"""Tests for the scriptable and interactive administration interface."""

import pytest

from intervals_mcp import admin, config, users


def test_add_prompts_for_missing_values(monkeypatch, tmp_path, capsys):
    path = tmp_path / "users.toml"
    answers = iter(["alex", "123"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr("getpass.getpass", lambda _: "private-key")

    admin.add(path, "mcp.example.com")

    saved = config.load_users(path)[0]
    assert saved.name == "alex"
    assert saved.athlete_id == "i123"
    output = capsys.readouterr().out
    assert saved.api_key not in output
    assert f"/{saved.token}/mcp" in output
    assert f"/{saved.token}/sse" in output


def test_list_never_prints_secrets(tmp_path, capsys):
    path = tmp_path / "users.toml"
    admin.add(path, "", name="alex", athlete_id="i123", api_key="private-key")
    capsys.readouterr()

    admin.list_users(path)

    output = capsys.readouterr().out
    assert "alex" in output
    assert "i123" in output
    assert "private-key" not in output
    assert config.load_users(path)[0].token not in output


def test_remove_requires_typed_confirmation(monkeypatch, tmp_path, capsys):
    path = tmp_path / "users.toml"
    admin.add(path, "", name="alex", athlete_id="i123", api_key="private-key")
    monkeypatch.setattr("builtins.input", lambda _: "wrong")

    admin.remove(path, "alex")

    assert path.exists()
    assert "cancelled" in capsys.readouterr().out.lower()


def test_remove_yes_skips_confirmation(tmp_path):
    path = tmp_path / "users.toml"
    admin.add(path, "", name="alex", athlete_id="i123", api_key="private-key")

    admin.remove(path, "alex", yes=True)

    assert not path.exists()


def test_initial_setup_creates_private_environment_and_user_files(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    users_path = tmp_path / "users.toml"
    monkeypatch.setattr(config, "DEFAULT_ENV_FILE", env_path)
    answers = iter(["mcp.example.com", "alex", "123", "n"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr("getpass.getpass", lambda _: "private-key")

    admin.initial_setup(users_path)

    assert "MCP_DOMAIN=mcp.example.com" in env_path.read_text()
    assert config.load_users(users_path)[0].athlete_id == "i123"
    assert (env_path.stat().st_mode & 0o777) == 0o600
    assert (users_path.stat().st_mode & 0o777) == 0o600


def test_menu_exits_without_running_an_action(monkeypatch, tmp_path):
    monkeypatch.setattr("builtins.input", lambda _: "0")

    assert admin.menu(tmp_path / "users.toml", "") == 0


def test_compose_explains_when_docker_is_missing(monkeypatch):
    monkeypatch.setattr(admin.shutil, "which", lambda _: None)

    with pytest.raises(users.UserError) as excinfo:
        admin._compose("ps")

    assert "Docker" in str(excinfo.value)
