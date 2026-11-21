"""Entry point: start the local backend, then show the UI in its own window."""

from __future__ import annotations

import logging
import secrets
import socket
import sys
import threading
import time
import webbrowser

import uvicorn

from . import APP_NAME_AR, config
from .server import create_app

WEBVIEW2_CLIENT = r"Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _has_webview2() -> bool:
    """Without the WebView2 runtime pywebview would fall back to the old IE
    engine, which cannot render this UI. In that case use the browser."""
    if sys.platform != "win32":
        return False
    import winreg

    for hive, prefix in (
        (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\WOW6432Node\\"),
        (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\"),
        (winreg.HKEY_CURRENT_USER, "Software\\"),
    ):
        try:
            with winreg.OpenKey(hive, prefix + WEBVIEW2_CLIENT) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
                if version and version != "0.0.0.0":
                    return True
        except OSError:
            continue
    return False


def main() -> None:
    if "--biit-acl-helper" in sys.argv:
        from .protection import run_helper
        try:
            index = sys.argv.index("--biit-acl-helper")
            raise SystemExit(run_helper(sys.argv[index + 1]))
        except (IndexError, OSError):
            raise SystemExit(2)
    logging.basicConfig(
        filename=str(config.user_dir() / "biit.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )
    log = logging.getLogger("biit")

    stop = threading.Event()
    runtime = {"mode": "window"}
    port = _free_port()
    app = create_app(secrets.token_urlsafe(24), runtime, on_shutdown=stop.set)

    # log_config=None: the windowed exe has no console, uvicorn's default
    # logging setup would crash on the missing stdout.
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, log_config=None,
        http="h11", ws="none", loop="asyncio", lifespan="off",
    ))
    threading.Thread(target=server.run, daemon=True).start()

    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        log.error("backend did not start")
        sys.exit(1)

    url = f"http://127.0.0.1:{port}/"
    shown = False
    if _has_webview2():
        try:
            import webview

            webview.create_window(APP_NAME_AR, url, width=1240, height=800, min_size=(980, 640))
            webview.start(gui="edgechromium")
            shown = True
        except Exception:  # noqa: BLE001 - any GUI failure falls back to the browser
            log.exception("window mode failed, falling back to the browser")

    if not shown:
        runtime["mode"] = "browser"
        # On Windows 10 without WebView2, notify once then open the browser
        if sys.platform == "win32":
            import ctypes
            import winreg
            try:
                ver = winreg.QueryValueEx(
                    winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion"),
                    "CurrentBuildNumber",
                )[0]
                is_win10 = int(ver) < 22000  # builds < 22000 are Windows 10
            except Exception:
                is_win10 = False
            if is_win10:
                log.info("Windows 10 detected – WebView2 missing, using browser mode")
                ctypes.windll.user32.MessageBoxW(
                    0,
                    "BiTT Assistant يعمل الآن في المتصفح.\n\n"
                    "لتشغيله كنافذة مستقلة، ثبّت WebView2 Runtime من:\n"
                    "https://developer.microsoft.com/en-us/microsoft-edge/webview2/\n"
                    "(اختر Evergreen Bootstrapper)",
                    "BiTT Assistant – وضع المتصفح",
                    0x40,  # MB_ICONINFORMATION
                )
        webbrowser.open(url)
        try:
            stop.wait()  # until the user presses "إغلاق التطبيق"
            time.sleep(0.3)  # let the shutdown response reach the page
        except KeyboardInterrupt:
            pass

    server.should_exit = True


if __name__ == "__main__":
    main()
