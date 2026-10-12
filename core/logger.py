import logging
from config.settings import settings


def setup_logging():
    settings.setup_logging()


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)