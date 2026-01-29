import logging
from types import FrameType
from typing import override

from loguru import logger


class InterceptHandler(logging.Handler):
    """
    Standard Loguru interceptor. Routes standard logging to Loguru
    while preserving the original caller's file and line number.
    """

    @override
    def emit(self, record: logging.LogRecord) -> None:
        # 1. Map standard logging levels to Loguru levels
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # 2. Safely downgrade SQLAlchemy INFO logs
        if record.name == "sqlalchemy.engine.Engine" and record.levelno == logging.INFO:
            # MUST be the string "DEBUG" so Loguru knows which formatting to apply
            level = "DEBUG"

            # 3. The standard Loguru stack-depth calculator
        frame: FrameType | None = logging.currentframe()
        depth: int = 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        # 4. Fire the log into Loguru
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )
