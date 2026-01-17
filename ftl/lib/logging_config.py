#!/usr/bin/env python3
"""Structured logging configuration for FTL.

Provides a consistent logging setup:
- Console handler: warnings and above
- File handler: debug and above to .ftl/ftl.log
"""

import logging
from pathlib import Path

FTL_LOG_FILE = Path(".ftl/ftl.log")

# Module-level logger cache
_loggers = {}


def get_logger(name: str = "ftl") -> logging.Logger:
    """Get a configured logger for FTL modules.

    Args:
        name: Logger name (typically module name like "ftl.memory")

    Returns:
        Configured logger instance
    """
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)

    # Only configure if not already configured
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)

        # Console handler: warnings and above
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_format = logging.Formatter(
            "[%(name)s] %(levelname)s: %(message)s"
        )
        console_handler.setFormatter(console_format)
        logger.addHandler(console_handler)

        # File handler: debug and above
        try:
            FTL_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(FTL_LOG_FILE)
            file_handler.setLevel(logging.DEBUG)
            file_format = logging.Formatter(
                "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            file_handler.setFormatter(file_format)
            logger.addHandler(file_handler)
        except (IOError, OSError):
            # Can't write to log file - continue with console only
            pass

        # Don't propagate to root logger
        logger.propagate = False

    _loggers[name] = logger
    return logger


def clear_log():
    """Clear the FTL log file."""
    if FTL_LOG_FILE.exists():
        FTL_LOG_FILE.unlink()


def get_log_contents(max_lines: int = 100) -> list[str]:
    """Get recent log file contents.

    Args:
        max_lines: Maximum number of lines to return

    Returns:
        List of log lines (most recent last)
    """
    if not FTL_LOG_FILE.exists():
        return []

    try:
        lines = FTL_LOG_FILE.read_text().strip().split("\n")
        return lines[-max_lines:]
    except (IOError, OSError):
        return []


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FTL logging utilities")
    subparsers = parser.add_subparsers(dest="command")

    # tail command
    t = subparsers.add_parser("tail", help="Show recent log entries")
    t.add_argument("-n", "--lines", type=int, default=20, help="Number of lines")

    # clear command
    subparsers.add_parser("clear", help="Clear log file")

    # test command
    subparsers.add_parser("test", help="Write test log entries")

    args = parser.parse_args()

    if args.command == "tail":
        lines = get_log_contents(args.lines)
        for line in lines:
            print(line)

    elif args.command == "clear":
        clear_log()
        print("Log cleared")

    elif args.command == "test":
        log = get_logger("ftl.test")
        log.debug("Debug message")
        log.info("Info message")
        log.warning("Warning message")
        log.error("Error message")
        print("Test entries written to log")

    else:
        parser.print_help()
