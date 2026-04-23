"""
main.py
-------
Entry point for the Words Finder desktop app.

Running WITHOUT arguments:  launches the desktop GUI (pywebview + Flask)
Running WITH arguments:     uses CLI as before

Usage examples (CLI)::

    python main.py sync-anki
    python main.py scan-subs
    python main.py subtitle-stats MyShow
    python main.py kanji-stats
    python main.py kanji-stats --sort RTK
    python main.py mark-known 食べる
    python main.py remove-word MyShow 食べる
    python main.py delete-results MyShow
    python main.py reset
"""

import argparse
import json
import os
import shutil
import sys
import threading
from pathlib import Path

# ---------------------------------------------------------------------------
# Frozen / development path helpers
# ---------------------------------------------------------------------------

def _bundle_dir() -> Path:
    """Directory that contains the bundled files when frozen by PyInstaller,
    or the project root when running from source."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)          # type: ignore[attr-defined]
    return Path(__file__).parent


def _project_root() -> Path:
    """Writable project root.
    When frozen: the directory that contains the .exe/.app (i.e. dist/WordsFinder/).
    When running from source: the directory that contains main.py.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def _appdata_dir() -> Path:
    """
    Persistent, writable directory for WordsFinder data.

    Windows : %APPDATA%\\WordsFinder
    macOS   : ~/Library/Application Support/WordsFinder
    Linux   : ~/.local/share/WordsFinder
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        # Linux / other Unix
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

    d = base / "WordsFinder"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# First-run: seed writable data files from the bundle into AppData
# ---------------------------------------------------------------------------

def _seed_appdata() -> None:
    """
    Copy internal data files from the bundle to the user data directory on
    first run so the app can write to them freely.
    """
    bundle  = _bundle_dir()
    appdata = _appdata_dir()

    # ── kanji_static.json (bundled, read-only reference data) ─────────────
    _seed_file(
        bundle / "data" / "kanji" / "kanji_static.json",
        appdata / "data" / "kanji" / "kanji_static.json",
    )

    # ── data sub-folders that the app writes to ────────────────────────────
    for folder in [
        "data/kanji",
        "data/new_words",
    ]:
        (appdata / folder).mkdir(parents=True, exist_ok=True)

    # ── config.json ────────────────────────────────────────────────────────
    dest_config = appdata / "config.json"
    if not dest_config.exists():
        default_config = {
            "anki": {
                "connect_url": "http://localhost:8765",
                "decks_fields": [],
                "ignore_in_brackets": True,
                "last_retrieved": ""
            },
            "kanji": {
                "dynamic_path": str(appdata / "data" / "kanji" / "kanji_dynamic.json"),
                "sort": "grade",
                "static_path":  str(appdata / "data" / "kanji" / "kanji_static.json"),
            },
            "subtitles": {
                "input_folder": "",
                "max_sentences_per_word": 100,
                "new_words_folder": str(appdata / "data" / "new_words"),
                "output_folder": ""
            },
            "words": {
                "lemma_path":      str(appdata / "data" / "anki_words_lemma.jsonl"),
                "orth_base_path":  str(appdata / "data" / "anki_words_orth_base.jsonl"),
                "preferred_parsing": "orth_base",
                "sort": "descending"
            }
        }
        with open(dest_config, "w", encoding="utf-8") as f:
            json.dump(default_config, f, ensure_ascii=False, indent=4)


def _seed_file(src: Path, dest: Path) -> None:
    """Copy *src* to *dest* only if *dest* does not already exist."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() and src.exists():
        shutil.copy2(src, dest)


# ---------------------------------------------------------------------------
# Resolved runtime paths
# ---------------------------------------------------------------------------

def _config_path() -> Path:
    return _appdata_dir() / "config.json"


def _ui_config_path() -> Path:
    return _appdata_dir() / "ui_config.json"


def _ui_dir() -> Path:
    """UI directory — always read from the bundle (read-only assets)."""
    return _bundle_dir() / "UI"


# ---------------------------------------------------------------------------
# Patch UI/app.py paths before it is imported
# ---------------------------------------------------------------------------

def _patch_app_paths() -> None:
    """
    app.py uses __file__-relative paths for CONFIG_PATH and UI_CONFIG_PATH.
    When frozen those paths point inside the bundle (read-only).
    We monkey-patch them after import so the app writes to the correct
    user data directory on every platform.
    """
    import UI.app as ui_app          # type: ignore
    ui_app.CONFIG_PATH    = _config_path()
    ui_app.UI_CONFIG_PATH = _ui_config_path()


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------

sys.path.insert(0, str(_bundle_dir() / "src"))  # make src importable


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="jpvocab",
        description="Japanese vocabulary pipeline",
    )
    p.add_argument(
        "--config",
        default=str(_config_path()),
        metavar="PATH",
        help="Path to config.json",
    )

    sub = p.add_subparsers(dest="command", required=False)

    sub.add_parser("sync-anki",  help="Fetch new cards from Anki.")
    sub.add_parser("scan-subs",  help="Scan subtitle files for new words.")
    sub.add_parser("reset",      help="Delete word and kanji databases.")

    mk = sub.add_parser("mark-known", help="Mark a word as already known.")
    mk.add_argument("word")

    rw = sub.add_parser("remove-word", help="Remove a word from subtitle results.")
    rw.add_argument("folder")
    rw.add_argument("word")

    dr = sub.add_parser("delete-results", help="Delete a subtitle results folder.")
    dr.add_argument("folder")

    ss = sub.add_parser("subtitle-stats", help="Print comprehension stats.")
    ss.add_argument("folder")

    ks = sub.add_parser("kanji-stats", help="Print kanji statistics.")
    ks.add_argument("--sort", choices=["grade", "RTK"], default=None)

    return p


# ---------------------------------------------------------------------------
# GUI launcher
# ---------------------------------------------------------------------------

PORT = 5099   # internal Flask port


def _start_flask() -> None:
    """Start Flask in a background daemon thread."""
    sys.path.insert(0, str(_bundle_dir() / "UI"))
    _patch_app_paths()
    from UI.app import create_app
    flask_app = create_app()
    flask_app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)


def _determine_start_page() -> str:
    """Return the URL Flask should open on launch."""
    base = f"http://127.0.0.1:{PORT}"

    ui_cfg_path = _ui_config_path()
    if not ui_cfg_path.exists():
        return f"{base}/lang-select"

    if not _config_path().exists():
        return f"{base}/setup"

    with open(ui_cfg_path, "r", encoding="utf-8") as f:
        ui_cfg = json.load(f)

    if not ui_cfg.get("language"):
        return f"{base}/lang-select"

    try:
        with open(_config_path(), "r", encoding="utf-8") as f:
            config = json.load(f)
        if not config.get("anki", {}).get("decks_fields"):
            return f"{base}/setup"
    except Exception:
        return f"{base}/setup"

    return f"{base}/"


def _launch_gui() -> None:
    """Launch pywebview pointing at local Flask server."""
    # Icon: use .icns on macOS, .ico on Windows, .png on Linux
    if sys.platform == "darwin":
        icon_path = str(_ui_dir() / "icons" / "default_icon.png")
    elif sys.platform == "win32":
        icon_path = str(_ui_dir() / "icons" / "icon_2.ico")
    else:
        icon_path = str(_ui_dir() / "icons" / "default_icon.png")

    try:
        import webview
    except ImportError:
        print("pywebview not installed.  Install it with:  pip install pywebview")
        print("Falling back to browser mode (opening in default browser).")
        import webbrowser, time

        flask_thread = threading.Thread(target=_start_flask, daemon=True)
        flask_thread.start()
        time.sleep(1.5)

        url = _determine_start_page()
        webbrowser.open(url)
        print(f"App running at {url}")
        print("Press Ctrl+C to quit.")
        try:
            while True:
                flask_thread.join(1)
        except KeyboardInterrupt:
            pass
        return

    # Start Flask in background
    flask_thread = threading.Thread(target=_start_flask, daemon=True)
    flask_thread.start()

    # Wait for Flask to be ready
    import time, urllib.request
    base = f"http://127.0.0.1:{PORT}"
    for _ in range(20):
        try:
            urllib.request.urlopen(base + "/", timeout=1)
            break
        except Exception:
            time.sleep(0.25)

    url = _determine_start_page()

    window = webview.create_window(
        title     = "Words Finder",
        url       = url,
        width     = 1280,
        height    = 800,
        resizable = True,
        frameless = False,
        maximized = True,
    )
    webview.start(debug=False, icon=icon_path)


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def _run_cli(args) -> None:
    from src.config_loader import load_config
    import src.pipeline as pipeline

    config = load_config(args.config)
    # Stamp the resolved path so pipeline._save_config() always writes back
    # to the correct AppData location -- same as app.py's _load_config() does.
    config["_config_path"] = args.config

    if args.command == "sync-anki":
        pipeline.add_words_from_anki(config)

    elif args.command == "scan-subs":
        pipeline.get_new_words_from_subtitles(config)

    elif args.command == "reset":
        confirm = input("This will delete all word and kanji data. Type 'yes' to continue: ")
        if confirm.strip().lower() == "yes":
            pipeline.reset_databases(config)
        else:
            print("Aborted.")

    elif args.command == "mark-known":
        pipeline.mark_word_as_known(config, args.word)

    elif args.command == "remove-word":
        pipeline.remove_word_from_subtitle_results(config, args.folder, args.word)

    elif args.command == "delete-results":
        pipeline.delete_subtitle_results(config, args.folder)

    elif args.command == "subtitle-stats":
        pipeline.subtitle_stats(config, args.folder)

    elif args.command == "kanji-stats":
        if args.sort:
            config.setdefault("kanji", {})["sort"] = args.sort
        pipeline.kanji_stats(config)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    _seed_appdata()

    parser = _build_parser()
    args   = parser.parse_args()

    if not args.command:
        _launch_gui()
    else:
        _run_cli(args)


if __name__ == "__main__":
    main()