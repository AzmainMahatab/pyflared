from pathlib import Path

from pyflared.log.logging_type import LoggingConfig
from platformdirs import user_log_dir

APP_NAME = "pyflared"
AUTHOR = "Azmain"

# Calculate the dynamic path
log_dir = Path(user_log_dir(APP_NAME, AUTHOR))
log_dir.mkdir(parents=True, exist_ok=True)
log_file_path = str(log_dir / "tunnel.log")

CONFIG: LoggingConfig = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "file_format": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S"
        }
    },
    "handlers": {
        "console": {
            "class": "rich.logging.RichHandler",
            "level": "ERROR",  # Default quiet
            "markup": True,
            "show_path": False,
            "rich_tracebacks": True
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",  # Always loud
            "formatter": "file_format",
            "filename": log_file_path,  # <--- INJECTED HERE
            "maxBytes": 5_242_880,  # 5 MB
            "backupCount": 3,
            "encoding": "utf-8"
        }
    },
    "loggers": {
        "pyflared": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": False
        }
    }
}
