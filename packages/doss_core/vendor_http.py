"""Bounded, best-effort HTTP access to public vendor SDS services."""

import time
from collections.abc import Callable

import requests

from packages.doss_core.logging_support import get_logger

logger = get_logger(__name__)
_TRANSIENT = {500, 502, 503, 504}


def get_vendor_response(
    url: str,
    *,
    vendor: str,
    headers: dict[str, str],
    throttle: Callable[[], None],
    timeout: tuple[float, float],
) -> tuple[int, bytes, str]:
    """Return the status, body, and content type; never retry a forbidden response."""
    for attempt in range(3):
        throttle()
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt < 2:
                logger.debug("vendor_http_retry vendor=%s error_type=%s attempt=%d",
                             vendor, type(exc).__name__, attempt + 1)
            else:
                logger.warning("vendor_http_degraded vendor=%s error_type=%s",
                               vendor, type(exc).__name__)
                return 0, b"", ""
        except requests.RequestException as exc:
            logger.warning("vendor_http_degraded vendor=%s error_type=%s",
                           vendor, type(exc).__name__)
            return 0, b"", ""
        else:
            status = response.status_code
            if status == 403:
                logger.warning("vendor_http_degraded vendor=%s status=403 reason=access_denied_or_bot_protection", vendor)
            if status not in _TRANSIENT or attempt == 2:
                if status in _TRANSIENT:
                    logger.warning("vendor_http_degraded vendor=%s status=%d", vendor, status)
                if status >= 400:
                    # Preserve prior HTTPError contract. An error page is never an SDS.
                    return status, response.content, ""
                return status, response.content, response.headers.get("Content-Type", "").lower()
            logger.debug("vendor_http_retry vendor=%s status=%d attempt=%d",
                         vendor, status, attempt + 1)
        time.sleep(0.5 * (2 ** attempt))
    return 0, b"", ""
