import logging
from contextlib import contextmanager, AbstractContextManager
from contextvars import ContextVar


# _verbosity_level: ContextVar[int] = ContextVar("verbosity_level", default=logging.NOTSET)
#
#
# class ContextLevelFilter(logging.Filter):
#     def filter(self, record: logging.LogRecord) -> bool:
#         return record.levelno >= _verbosity_level.get()
#
#
# @contextmanager
# def context_locked_logging(level: int):
#     """
#     Sets the log level for the current context only.
#     """
#     token = _verbosity_level.set(level)
#     try:
#         yield
#     finally:
#         _verbosity_level.reset(token)


# @dataclass
# class ContextedLogger:
#     _verbosity_level: ContextVar[int] = ContextVar("verbosity_level", default=logging.NOTSET)
#
#

class ContextualLogger:

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= self._verbosity_level.get()

    def __init__(self, handler: logging.Handler, *handlers: logging.Handler, default_level: int = logging.WARNING):
        self._verbosity_level: ContextVar[int] = ContextVar("verbosity_level", default=default_level)
        self.add_handlers(handler, *handlers)

    def add_handlers(self, *handlers: logging.Handler):
        for handler in handlers:
            handler.addFilter(self.filter)

    def contextual(self, level: int) -> AbstractContextManager[None]:
        """
        Sets the log level for the current context only.
        """

        @contextmanager
        def _manager():
            token = self._verbosity_level.set(level)
            try:
                yield
            finally:
                self._verbosity_level.reset(token)

        return _manager()

    def __call__(self, level: int):
        return self.contextual(level=level)
