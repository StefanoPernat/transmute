import logging
import logging.config

from core.logging import build_logging_config, configure_logging


def test_build_logging_config_has_root():
    config = build_logging_config()
    assert "root" in config
    assert config["root"]["level"] == "INFO"
    assert "default" in config["root"]["handlers"]


def test_build_logging_config_does_not_disable_existing():
    config = build_logging_config()
    assert config["disable_existing_loggers"] is False


def test_build_logging_config_preserves_uvicorn_formatters():
    config = build_logging_config()
    assert "formatters" in config
    assert "default" in config["formatters"]


def test_configure_logging_applies():
    configure_logging()
    root = logging.getLogger()
    assert root.level <= logging.INFO
