import logging
import logging.handlers
import os
from pathlib import Path


def setup_logging():
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    console_handler.setLevel(logging.INFO)

    file_handler = logging.handlers.RotatingFileHandler(
        filename=logs_dir / "bot.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.INFO)

    error_handler = logging.handlers.RotatingFileHandler(
        filename=logs_dir / "errors.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8"
    )
    error_handler.setFormatter(fmt)
    error_handler.setLevel(logging.ERROR)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)

    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.WARNING)
