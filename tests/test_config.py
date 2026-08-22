import pytest

from intervals_mcp import config


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """Read configuration from the environment only, never the project's real .env."""
    monkeypatch.setattr(config, "DEFAULT_ENV_FILE", None)


class TestLoadConfig:
    def test_reads_key_and_athlete_from_environment(self, monkeypatch):
        monkeypatch.setenv("INTERVALS_API_KEY", "abc123")
        monkeypatch.setenv("INTERVALS_ATHLETE_ID", "i999")

        result = config.load_config()

        assert result.api_key == "abc123"
        assert result.athlete_id == "i999"

    def test_normalises_an_athlete_id_given_without_the_i_prefix(self, monkeypatch):
        monkeypatch.setenv("INTERVALS_API_KEY", "abc123")
        monkeypatch.setenv("INTERVALS_ATHLETE_ID", "123456")

        assert config.load_config().athlete_id == "i123456"

    def test_explains_what_to_do_when_the_key_is_missing(self, monkeypatch):
        monkeypatch.delenv("INTERVALS_API_KEY", raising=False)
        monkeypatch.setenv("INTERVALS_ATHLETE_ID", "i999")

        with pytest.raises(config.ConfigError) as excinfo:
            config.load_config()

        assert "INTERVALS_API_KEY" in str(excinfo.value)
        assert ".env" in str(excinfo.value)

    def test_explains_what_to_do_when_the_athlete_id_is_missing(self, monkeypatch):
        monkeypatch.setenv("INTERVALS_API_KEY", "abc123")
        monkeypatch.delenv("INTERVALS_ATHLETE_ID", raising=False)

        with pytest.raises(config.ConfigError) as excinfo:
            config.load_config()

        assert "INTERVALS_ATHLETE_ID" in str(excinfo.value)

    def test_treats_a_blank_key_as_missing(self, monkeypatch):
        monkeypatch.setenv("INTERVALS_API_KEY", "   ")
        monkeypatch.setenv("INTERVALS_ATHLETE_ID", "i999")

        with pytest.raises(config.ConfigError):
            config.load_config()

    def test_does_not_expose_the_key_in_its_repr(self, monkeypatch):
        monkeypatch.setenv("INTERVALS_API_KEY", "supersecret")
        monkeypatch.setenv("INTERVALS_ATHLETE_ID", "i999")

        assert "supersecret" not in repr(config.load_config())
