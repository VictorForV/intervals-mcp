"""Tests for the add-user CLI.

Hand-editing users.toml is possible; this exists so a typo cannot produce a
duplicate token or a too-short one.
"""

import stat

import pytest

from intervals_mcp import adduser, config


class TestAddUser:
    def test_creates_the_file_with_the_first_user(self, tmp_path):
        path = tmp_path / "users.toml"

        token = adduser.add_user(path, name="alex", athlete_id="i111", api_key="k1")

        users = config.load_users(path)
        assert [u.name for u in users] == ["alex"]
        assert users[0].token == token

    def test_appends_without_disturbing_existing_users(self, tmp_path):
        path = tmp_path / "users.toml"
        first = adduser.add_user(path, name="alex", athlete_id="i111", api_key="k1")

        second = adduser.add_user(path, name="bob", athlete_id="i222", api_key="k2")

        users = config.load_users(path)
        assert [u.name for u in users] == ["alex", "bob"]
        assert users[0].token == first
        assert users[1].token == second

    def test_generates_a_distinct_secret_token_per_user(self, tmp_path):
        path = tmp_path / "users.toml"

        first = adduser.add_user(path, name="alex", athlete_id="i111", api_key="k1")
        second = adduser.add_user(path, name="bob", athlete_id="i222", api_key="k2")

        assert first != second
        assert len(first) >= config.MIN_TOKEN_LENGTH

    def test_normalises_a_bare_athlete_id(self, tmp_path):
        path = tmp_path / "users.toml"

        adduser.add_user(path, name="alex", athlete_id="111", api_key="k1")

        assert config.load_users(path)[0].athlete_id == "i111"

    def test_writes_the_file_owner_only(self, tmp_path):
        path = tmp_path / "users.toml"

        adduser.add_user(path, name="alex", athlete_id="i111", api_key="k1")

        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    def test_refuses_a_duplicate_name(self, tmp_path):
        path = tmp_path / "users.toml"
        adduser.add_user(path, name="alex", athlete_id="i111", api_key="k1")

        with pytest.raises(adduser.AddUserError) as excinfo:
            adduser.add_user(path, name="alex", athlete_id="i999", api_key="k9")

        assert "alex" in str(excinfo.value)

    def test_refuses_a_duplicate_athlete(self, tmp_path):
        path = tmp_path / "users.toml"
        adduser.add_user(path, name="alex", athlete_id="i111", api_key="k1")

        with pytest.raises(adduser.AddUserError) as excinfo:
            adduser.add_user(path, name="other", athlete_id="i111", api_key="k9")

        assert "i111" in str(excinfo.value)

    def test_rejects_a_blank_name(self, tmp_path):
        with pytest.raises(adduser.AddUserError):
            adduser.add_user(tmp_path / "users.toml", name="  ", athlete_id="i1", api_key="k")

    def test_rejects_a_blank_api_key(self, tmp_path):
        with pytest.raises(adduser.AddUserError):
            adduser.add_user(tmp_path / "users.toml", name="alex", athlete_id="i1", api_key="")

    def test_escapes_a_quote_in_a_value_rather_than_writing_broken_toml(self, tmp_path):
        path = tmp_path / "users.toml"

        adduser.add_user(path, name='we"ird', athlete_id="i111", api_key="k1")

        assert config.load_users(path)[0].name == 'we"ird'


class TestMain:
    def test_runs_end_to_end_without_a_host_configured(self, tmp_path, monkeypatch, capsys):
        """Regression test: main() builds its argparser at call time, and a
        missing `import os` there only shows up when main() actually runs -
        add_user() alone can't catch it."""
        monkeypatch.delenv("MCP_DOMAIN", raising=False)
        path = tmp_path / "users.toml"
        monkeypatch.setattr(
            "sys.argv",
            [
                "intervals-mcp-adduser",
                "--name",
                "alex",
                "--athlete-id",
                "i111",
                "--api-key",
                "k1",
                "--users-file",
                str(path),
            ],
        )

        assert adduser.main() == 0
        assert "token:" in capsys.readouterr().out


class TestConnectorUrl:
    def test_builds_the_sse_url_a_connector_expects(self):
        url = adduser.connector_url("example.com", "tok123")

        assert url == "https://example.com/tok123/sse"

    def test_accepts_a_host_given_with_a_scheme(self):
        assert adduser.connector_url("https://example.com", "tok") == "https://example.com/tok/sse"

    def test_accepts_a_host_given_with_a_trailing_slash(self):
        assert adduser.connector_url("example.com/", "tok") == "https://example.com/tok/sse"
