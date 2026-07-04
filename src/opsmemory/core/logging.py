"""Structured logging configuration for the platform."""

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging for the application.

    Uses a concise single-line format suitable both for local development
    and for container log collectors.

    Args:
        level: Logging level name, e.g. ``"INFO"`` or ``"DEBUG"``.
    """
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        stream=sys.stdout,
        force=True,
    )
    # Reduce noise from third-party libraries at default level.
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger for a module.

    Args:
        name: Logger name, conventionally ``__name__`` of the caller.
    """
    return logging.getLogger(name)
