"""Loopback-only launcher for the optional StatConvert browser UI."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import socket
from threading import Thread
from time import monotonic, sleep
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser

from statconvert.exceptions import StatConvertError

from .dependencies import ensure_ui_dependencies


DEFAULT_UI_HOST = "127.0.0.1"
DEFAULT_UI_PORT = 8765
FRIENDLY_UI_HOST = "statconvert.localhost"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
UI_READINESS_TIMEOUT_SECONDS = 10.0


class WebUiLaunchError(StatConvertError):
    """The local browser UI cannot be started safely."""


def validate_host(host: str) -> str:
    """Return a normalized loopback host or reject non-local binding."""

    if not isinstance(host, str) or not host.strip():
        raise WebUiLaunchError("The UI host must be a non-empty loopback host.")
    normalized = host.strip().casefold()
    if normalized not in LOOPBACK_HOSTS:
        raise WebUiLaunchError(
            f"StatConvert 1.1.1 is local-only and cannot bind to host '{host}'.",
            suggestion="Use --host 127.0.0.1 or --host localhost.",
        )
    return normalized


def validate_port(port: int) -> int:
    """Return a valid TCP port."""

    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise WebUiLaunchError("The UI port must be an integer from 1 through 65535.")
    return port


def build_local_url(host: str, port: int) -> str:
    """Build the browser URL for one validated loopback address."""

    validated_host = validate_host(host)
    validated_port = validate_port(port)
    display_host = f"[{validated_host}]" if validated_host == "::1" else validated_host
    return f"http://{display_host}:{validated_port}"


def resolve_open_url(
    host: str,
    port: int,
    *,
    friendly_available: bool = True,
) -> str:
    """Prefer the friendly local alias for the default IPv4 loopback bind."""

    bound_url = build_local_url(host, port)
    if validate_host(host) != DEFAULT_UI_HOST:
        return bound_url
    if friendly_available:
        return f"http://{FRIENDLY_UI_HOST}:{port}"
    return bound_url


def launch_ui(
    *,
    host: str = DEFAULT_UI_HOST,
    port: int = DEFAULT_UI_PORT,
    open_browser: bool = True,
    static_dir: str | Path | None = None,
    on_start: Callable[[str, str], None] | None = None,
) -> None:
    """Validate, create, and run the optional local UI server."""

    validated_host = validate_host(host)
    validated_port = validate_port(port)
    _ensure_port_available(validated_host, validated_port)
    ensure_ui_dependencies()

    import uvicorn

    from .server import create_app

    bound_url = build_local_url(validated_host, validated_port)
    open_url = resolve_open_url(validated_host, validated_port)
    application = create_app(
        host=validated_host,
        port=validated_port,
        open_url=open_url,
        static_dir=static_dir,
    )
    if on_start is not None:
        on_start(open_url, f"{validated_host}:{validated_port}")
    if open_browser:
        Thread(
            target=_open_browser_when_ready,
            args=(bound_url, open_url),
            daemon=True,
            name="statconvert-ui-browser",
        ).start()

    uvicorn.run(
        application,
        host=validated_host,
        port=validated_port,
        log_level="info",
    )


def _ensure_port_available(host: str, port: int) -> None:
    bind_host = "127.0.0.1" if host == "localhost" else host
    family = socket.AF_INET6 if bind_host == "::1" else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as check_socket:
            check_socket.bind((bind_host, port))
    except OSError as exc:
        raise WebUiLaunchError(
            f"The StatConvert UI cannot use {host}:{port} because the port is busy.",
            suggestion="Choose another local port with --port.",
        ) from exc


def _open_browser_when_ready(readiness_url: str, open_url: str) -> None:
    health_url = f"{readiness_url}/api/health"
    deadline = monotonic() + UI_READINESS_TIMEOUT_SECONDS
    while monotonic() < deadline:
        try:
            with urlopen(health_url, timeout=0.5) as response:
                if response.status == 200:
                    opened = webbrowser.open(open_url)
                    if not opened and open_url != readiness_url:
                        webbrowser.open(readiness_url)
                    return
        except (OSError, URLError):
            sleep(0.1)
