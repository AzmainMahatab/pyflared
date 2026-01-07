import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from platformdirs import user_log_dir
from rich.logging import RichHandler

from pyflared.log.cli_config import AUTHOR
from pyflared.log.context_logger import ContextualLogger
from pyflared.shared.contants import APP_NAME

logger = logging.getLogger("pyflared")

# We must set the logger's level to the LOWEST level we intend to capture
# (DEBUG) so that it passes messages to the handlers. The handlers will
# then filter based on their own levels.
logger.setLevel(logging.DEBUG)

# class _ContextAwareHandler(logging.StreamHandler):
#     def filter(self, record):
#         pass
#
#     def setLevel(self, level):


# 1. Create the Common Formatter for the file
# file_formatter = logging.Formatter(
#     fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
#     datefmt="%Y-%m-%d %H:%M:%S"
# )

# 2. Setup Console Handler (Rich)
# Level: ERROR (Quiet)
console_handler = RichHandler(
    level=logging.DEBUG,
    markup=True,
    show_path=False,
    rich_tracebacks=True
)
contextual_logger = ContextualLogger(console_handler)
logger.addHandler(console_handler)

# 3. Setup File Handler (Rotating)
# Level: DEBUG (Loud)
log_dir = Path(user_log_dir(APP_NAME, AUTHOR))
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "tunnel.log"
file_handler = RotatingFileHandler(
    filename=log_file,
    mode="a",
    maxBytes=5_242_880,  # 5 MB
    backupCount=3,
    encoding="utf-8"
)
file_handler.setLevel(logging.DEBUG)
logger.addHandler(file_handler)

# file_handler.setFormatter(file_formatter)

# 4. Configure the Specific Logger


# Prevent duplicate logs if this function is called multiple times

# Propagate = False
logger.propagate = False

# class ContextAwareFilter(logging.Filter):
#     """
#     A custom filter that rejects log records based on the current context's
#     verbosity level, rather than the global logger's level.
#     """
#
#     def filter(self, record: logging.LogRecord) -> bool:
#         # Get the threshold required for the current running task
#         threshold = _verbosity_context.get()
#         # Allow the log only if its level is greater than or equal to the threshold
#         return record.levelno >= threshold
#
#
# logger.addHandler(_ContextAwareHandler())
#
# console_handler.addFilter(ContextAwareFilter)
# console_handler.setLevel(ContextAwareFilter)
#
#
# class ScopedLogger:
#     """
#     Manages a logger that supports context-aware (task-local) verbosity levels.
#     """
#
#     def __init__(self, name: str = "app", default_level: int = logging.INFO):
#         # 1. Create a private ContextVar specific to this instance
#         self._verbosity_var: ContextVar[int] = ContextVar(
#             f"verbosity_{name}", default=default_level
#         )
#
#         # 2. Initialize the logger
#         self.logger = logging.getLogger(name)
#         self._setup_logging()
#
#     def _setup_logging(self) -> None:
#         """Configures the physical handler and attaches the context filter."""
#         # Clean up existing handlers to avoid duplicates during re-runs
#         if self.logger.hasHandlers():
#             self.logger.handlers.clear()
#
#         # The handler must allow EVERYTHING physically (DEBUG)
#         handler = logging.StreamHandler(sys.stdout)
#         handler.setLevel(logging.DEBUG)
#
#         # Attach our custom filter that uses THIS instance's ContextVar
#         handler.addFilter(self._create_filter())
#
#         # The logical logger must also allow everything
#         self.logger.setLevel(logging.DEBUG)
#         self.logger.addHandler(handler)
#         self.logger.propagate = False
#
#     def _create_filter(self) -> logging.Filter:
#         """Creates a closure-based filter or inner-class filter."""
#
#         # We use an inner class to keep it neat and access internal state safely
#         class _ContextFilter(logging.Filter):
#             def __init__(self, context_var: ContextVar[int]):
#                 super().__init__()
#                 self._context_var = context_var
#
#             def filter(self, record: logging.LogRecord) -> bool:
#                 # Compare record level against the current context level
#                 return record.levelno >= self._context_var.get()
#
#         return _ContextFilter(self._verbosity_var)
#
#     @contextmanager
#     def scope(self, verbose: bool):
#         """
#         Context manager to set verbosity for the current block/task.
#         Automatically resets context on exit.
#         """
#         target_level = logging.DEBUG if verbose else logging.INFO
#         token = self._verbosity_var.set(target_level)
#         try:
#             yield
#         finally:
#             self._verbosity_var.reset(token)
#
#
# class SL2:
#     context_var: ContextVar[int] = ContextVar("verbosity", default=logging.INFO)
#
#     class _ContextFilter(logging.Filter):
#         def filter(self, record: logging.LogRecord) -> bool:
#             # Compare record level against the current context level
#             return record.levelno >= self.context_var.get()
#
#     def add_to_handle(self, handler: logging.Handler):
#         handler.addFilter(
#             _ContextFilter()
#         )
