"""Tests for loading the multi-user configuration.

A bad users file must stop the server rather than quietly serve a partial
configuration, so most of these assert on failure.
"""

import pytest

from intervals_mcp import config

VALID = """
[[users]]
name = "alex"
athlete_id = "i123456"
api_key = "key-alex"
token = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

[[users]]
name = "bob"
athlete_id = "i999999"
api_key = "key-bob"
token = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
"""


def write(tmp_path, text: str):
    path = tmp_path / "users.toml"
    path.write_text(text)
    return path


class TestLoadUsers:
    def test_reads_every_user(self, tmp_path):
        users = config.load_users(write(tmp_path, VALID))

        assert [u.name for u in users] == ["alex", "bob"]
        assert users[0].athlete_id == "i123456"
        assert users[0].api_key == "key-alex"
        assert users[1].token == "b" * 32

    def test_normalises_an_athlete_id_without_the_i_prefix(self, tmp_path):
        users = config.load_users(
            write(
                tmp_path,
                """
[[users]]
name = "alex"
athlete_id = "123456"
api_key = "k"
token = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
""",
            )
        )

        assert users[0].athlete_id == "i123456"

    def test_does_not_expose_api_keys_in_reprs(self, tmp_path):
        users = config.load_users(write(tmp_path, VALID))

        assert "key-alex" not in repr(users[0])
        assert "key-alex" not in repr(users)


class TestRejectsBadConfiguration:
    def test_missing_file(self, tmp_path):
        with pytest.raises(config.ConfigError) as excinfo:
            config.load_users(tmp_path / "nope.toml")

        assert "nope.toml" in str(excinfo.value)

    def test_no_users_at_all(self, tmp_path):
        with pytest.raises(config.ConfigError) as excinfo:
            config.load_users(write(tmp_path, "# empty\n"))

        assert "no users" in str(excinfo.value).lower()

    def test_duplicate_tokens_would_collide_on_one_route(self, tmp_path):
        text = VALID.replace("b" * 32, "a" * 32)

        with pytest.raises(config.ConfigError) as excinfo:
            config.load_users(write(tmp_path, text))

        assert "token" in str(excinfo.value).lower()
        assert "a" * 32 not in str(excinfo.value), "the message must not leak the token"

    def test_duplicate_names(self, tmp_path):
        text = VALID.replace('name = "bob"', 'name = "alex"')

        with pytest.raises(config.ConfigError) as excinfo:
            config.load_users(write(tmp_path, text))

        assert "alex" in str(excinfo.value)

    def test_a_token_too_short_to_be_secret(self, tmp_path):
        text = VALID.replace("b" * 32, "short")

        with pytest.raises(config.ConfigError) as excinfo:
            config.load_users(write(tmp_path, text))

        message = str(excinfo.value)
        assert "bob" in message
        assert "20" in message, "the message should state the minimum length"

    def test_missing_field(self, tmp_path):
        with pytest.raises(config.ConfigError) as excinfo:
            config.load_users(
                write(
                    tmp_path,
                    """
[[users]]
name = "alex"
api_key = "k"
token = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
""",
                )
            )

        assert "athlete_id" in str(excinfo.value)

    def test_blank_value(self, tmp_path):
        text = VALID.replace('api_key = "key-bob"', 'api_key = "   "')

        with pytest.raises(config.ConfigError) as excinfo:
            config.load_users(write(tmp_path, text))

        assert "api_key" in str(excinfo.value)

    def test_malformed_toml(self, tmp_path):
        with pytest.raises(config.ConfigError) as excinfo:
            config.load_users(write(tmp_path, "[[users]\nname = "))

        assert "users.toml" in str(excinfo.value)


class TestSingleUserFallback:
    def test_falls_back_to_the_env_athlete_when_no_users_file_exists(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INTERVALS_API_KEY", "envkey")
        monkeypatch.setenv("INTERVALS_ATHLETE_ID", "i123")
        monkeypatch.setenv("INTERVALS_MCP_TOKEN", "t" * 32)
        monkeypatch.setattr(config, "DEFAULT_ENV_FILE", None)

        users = config.resolve_users(users_file=tmp_path / "absent.toml")

        assert len(users) == 1
        assert users[0].athlete_id == "i123"
        assert users[0].token == "t" * 32

    def test_prefers_the_users_file_when_it_exists(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INTERVALS_API_KEY", "envkey")
        monkeypatch.setenv("INTERVALS_ATHLETE_ID", "i123")
        monkeypatch.setenv("INTERVALS_MCP_TOKEN", "t" * 32)
        monkeypatch.setattr(config, "DEFAULT_ENV_FILE", None)

        users = config.resolve_users(users_file=write(tmp_path, VALID))

        assert [u.name for u in users] == ["alex", "bob"]

    def test_explains_itself_when_neither_source_is_configured(self, tmp_path, monkeypatch):
        monkeypatch.delenv("INTERVALS_API_KEY", raising=False)
        monkeypatch.delenv("INTERVALS_MCP_TOKEN", raising=False)
        monkeypatch.setattr(config, "DEFAULT_ENV_FILE", None)

        with pytest.raises(config.ConfigError) as excinfo:
            config.resolve_users(users_file=tmp_path / "absent.toml")

        message = str(excinfo.value)
        assert "absent.toml" in message, "should name the file it looked for"
        assert "INTERVALS_API_KEY" in message, "should offer the single-athlete route too"
