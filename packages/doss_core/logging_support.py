"""Shared application logging without exposing exception payloads or paths."""

import logging
import os
import re

_CAS = re.compile(r"[0-9]{2,7}-?[0-9]{2}-?[0-9]")


def get_logger(module: str) -> logging.Logger:
    parent = logging.getLogger("doss")
    level = os.environ.get("LOG_LEVEL", "INFO").strip().upper()
    levels = {"DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING,
              "ERROR": logging.ERROR, "CRITICAL": logging.CRITICAL}
    parent.setLevel(levels.get(level, logging.INFO))
    logging.basicConfig(format="%(levelname)s %(name)s %(message)s")
    return parent.getChild(module)


def cas_context(value: object) -> str:
    """Use a CAS-shaped value in logs; never echo arbitrary input."""
    return value if isinstance(value, str) and _CAS.fullmatch(value) else "invalid-or-missing"
