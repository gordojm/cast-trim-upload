"""Command line entry point: ``cast-trim-upload [serve|setup|login|doctor]``."""

import argparse
import asyncio
import logging
import threading
import webbrowser

from .config import get_settings


def _already_running(url: str) -> bool:
    import httpx

    try:
        return httpx.get(f"{url}/api/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


def _serve(args: argparse.Namespace) -> None:
    import uvicorn

    settings = get_settings()
    url = f"http://{settings.host}:{settings.port}"
    open_browser = settings.open_browser and not args.no_browser
    if _already_running(url):
        # Started twice (e.g. start.bat double-clicked again): just show the app.
        print(f"cast-trim-upload is already running at {url}")
        if open_browser:
            webbrowser.open(url)
        return
    if open_browser:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    print(f"cast-trim-upload running at {url}  (Ctrl+C to stop)")
    uvicorn.run("cast_trim_upload.main:app", host=settings.host, port=settings.port,
                reload=args.reload, log_level="info")


def _setup(args: argparse.Namespace) -> None:
    from . import tools

    status = tools.setup(get_settings(), update=args.update)
    _print_status(status)


def _login(_: argparse.Namespace) -> None:
    from .spotify.uploader import SpotifyUploader

    settings = get_settings()
    settings.ensure_dirs()
    print("A browser window will open. Log in to Spotify for Creators there.")
    asyncio.run(SpotifyUploader(settings).login())
    print("Logged in. The session is saved in", settings.browser_profile_dir)


def _doctor(_: argparse.Namespace) -> None:
    from . import tools

    settings = get_settings()
    tools.add_tools_to_path(settings)
    _print_status(tools.tool_status(settings))


def _print_status(status) -> None:
    rows = [
        ("ffmpeg", status.ffmpeg),
        ("TwitchDownloaderCLI", status.twitch_cli),
        ("JS runtime (YouTube)", status.js_runtime),
        ("Playwright Chromium", "installed" if status.chromium else None),
        ("yt-dlp", status.yt_dlp_version),
    ]
    for name, value in rows:
        print(f"  {'OK ' if value else 'MISSING'}  {name:<22} {value or ''}")
    if not status.ok:
        print("\nSomething is missing. Run: cast-trim-upload setup"
              + ("" if status.js_runtime else "  (and install Node.js or Deno for YouTube)"))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(prog="cast-trim-upload")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Start the web app (default)")
    serve.add_argument("--no-browser", action="store_true", help="Don't open the browser")
    serve.add_argument("--reload", action="store_true", help="Auto-reload on code changes (dev)")
    serve.set_defaults(func=_serve)

    setup = sub.add_parser("setup", help="Download TwitchDownloaderCLI, ffmpeg and Chromium")
    setup.add_argument("--update", action="store_true", help="Also update tools and yt-dlp")
    setup.set_defaults(func=_setup)

    sub.add_parser("login", help="Log in to Spotify for Creators").set_defaults(func=_login)
    sub.add_parser("doctor", help="Check that all tools are installed").set_defaults(func=_doctor)

    args = parser.parse_args()
    if not args.command:
        args = parser.parse_args(["serve"])
    args.func(args)


if __name__ == "__main__":
    main()
