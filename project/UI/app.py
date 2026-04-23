"""
app.py
------
Flask server that powers the Words Finder desktop UI.
Serves all pages and exposes API routes consumed by the frontend JS.
Launch via main.py (python main.py) — do NOT run this file directly.

PATH RULES (important for frozen / installed builds):
  CONFIG_PATH and UI_CONFIG_PATH are intentionally set to None here.
  main.py monkey-patches them to the correct AppData paths before
  calling create_app(), so every route always reads/writes AppData —
  never the read-only bundle or Program Files directory.
"""

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_from_directory

# ---------------------------------------------------------------------------
# Path setup — resolve UI dir so templates/static work when frozen
# ---------------------------------------------------------------------------

# When frozen by PyInstaller, __file__ is inside sys._MEIPASS.
# We only use UI_DIR for read-only assets (templates, static, icons, text).
# All writable paths (config, ui_config) come from main.py via monkey-patch.
if getattr(sys, "frozen", False):
    UI_DIR = Path(sys._MEIPASS) / "UI"          # type: ignore[attr-defined]
else:
    UI_DIR = Path(__file__).parent

sys.path.insert(0, str(UI_DIR.parent))

from src.config_loader import load_config, save_config
import src.pipeline as pipeline
from src.word_store import WordStore

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
app = Flask(
    __name__,
    template_folder=str(UI_DIR / "templates"),
    static_folder=str(UI_DIR / "static"),
)

# These are patched by main.py before create_app() is called.
# They must NOT be derived from __file__ or PROJECT_ROOT here,
# because that would point into the read-only bundle / Program Files.
CONFIG_PATH:    Path | None = None
UI_CONFIG_PATH: Path | None = None

UI_TEXT_PATH = UI_DIR / "ui_text.json"   # read-only asset — bundle path is fine


# ---------------------------------------------------------------------------
# Path accessors — always read the (possibly patched) module variables
# ---------------------------------------------------------------------------

def _config_path() -> Path:
    if CONFIG_PATH is None:
        raise RuntimeError(
            "CONFIG_PATH has not been set. "
            "Ensure main.py patches app.CONFIG_PATH before calling create_app()."
        )
    return CONFIG_PATH


def _ui_config_path() -> Path:
    if UI_CONFIG_PATH is None:
        raise RuntimeError(
            "UI_CONFIG_PATH has not been set. "
            "Ensure main.py patches app.UI_CONFIG_PATH before calling create_app()."
        )
    return UI_CONFIG_PATH


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_ui_config() -> dict[str, Any]:
    p = _ui_config_path()
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_ui_config(data: dict[str, Any]) -> None:
    with open(_ui_config_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_ui_text() -> dict[str, Any]:
    with open(UI_TEXT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_text(lang: str | None = None) -> dict[str, Any]:
    ui_cfg = _load_ui_config()
    language = lang or ui_cfg.get("language", "en")
    texts = _load_ui_text()
    return texts.get(language, texts["en"])


def _load_config() -> dict[str, Any]:
    config = load_config(_config_path())
    # Stamp the resolved AppData path so pipeline functions that internally
    # need to save config always write to AppData, never to Program Files.
    config["_config_path"] = str(_config_path())
    return config


def _save_config(config: dict[str, Any]) -> None:
    """Always save to the patched AppData path, never to a path in config."""
    save_config(config, _config_path())


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    ui_cfg = _load_ui_config()
    text = _get_text()
    config = _load_config()
    return render_template("main.html", text=text, ui_cfg=ui_cfg, config=config)


@app.route("/subs/<folder_name>")
def subs_page(folder_name: str):
    ui_cfg = _load_ui_config()
    text = _get_text()
    return render_template("subs.html", text=text, ui_cfg=ui_cfg, folder_name=folder_name)


@app.route("/kanji")
def kanji_page():
    ui_cfg = _load_ui_config()
    text = _get_text()
    return render_template("kanji.html", text=text, ui_cfg=ui_cfg)


@app.route("/words")
def words_page():
    ui_cfg = _load_ui_config()
    text = _get_text()
    return render_template("words.html", text=text, ui_cfg=ui_cfg)


@app.route("/setup")
def setup_page():
    ui_cfg = _load_ui_config()
    text = _get_text()
    config = _load_config()
    return render_template("setup.html", text=text, ui_cfg=ui_cfg, config=config)


@app.route("/settings")
def settings_page():
    ui_cfg = _load_ui_config()
    text = _get_text()
    config = _load_config()
    return render_template("settings.html", text=text, ui_cfg=ui_cfg, config=config)


@app.route("/lang-select")
def lang_select_page():
    texts = _load_ui_text()
    return render_template("lang_select.html", texts=texts)


# ---------------------------------------------------------------------------
# Static icons / UI assets
# ---------------------------------------------------------------------------

@app.route("/icons/<path:filename>")
def serve_icon(filename: str):
    return send_from_directory(UI_DIR / "icons", filename)


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(UI_DIR / "icons", "default_icon.png", mimetype="image/png")


@app.route("/bg/<path:filename>")
def serve_bg(filename: str):
    """Serve a background image from the configured bg folder."""
    ui_cfg = _load_ui_config()
    bg_folder = ui_cfg.get("background_folder", "")
    if bg_folder and Path(bg_folder).exists():
        return send_from_directory(bg_folder, filename)
    return "", 404


# ---------------------------------------------------------------------------
# API — UI config
# ---------------------------------------------------------------------------

@app.route("/api/ui-config", methods=["GET"])
def api_get_ui_config():
    return jsonify(_load_ui_config())


@app.route("/api/ui-config", methods=["POST"])
def api_save_ui_config():
    data = request.get_json()
    _save_ui_config(data)
    return jsonify({"ok": True})


@app.route("/api/ui-config/exists", methods=["GET"])
def api_ui_config_exists():
    return jsonify({"exists": _ui_config_path().exists()})


# ---------------------------------------------------------------------------
# API — App config
# ---------------------------------------------------------------------------

@app.route("/api/config", methods=["GET"])
def api_get_config():
    try:
        return jsonify(_load_config())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/config", methods=["POST"])
def api_save_config():
    try:
        data = request.get_json()
        _save_config(data)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ---------------------------------------------------------------------------
# API — Main panel data
# ---------------------------------------------------------------------------

def _get_all_result_stats(config: dict[str, Any]) -> list[dict]:
    """Same as subtitles.get_all_result_stats but tolerates missing new_words folder."""
    from src.subtitles import get_all_result_stats
    try:
        return get_all_result_stats(config)
    except Exception:
        return []


@app.route("/api/results", methods=["GET"])
def api_results():
    try:
        config = _load_config()
        results = _get_all_result_stats(config)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/results-stats", methods=["GET"])
def api_results_stats():
    try:
        config  = _load_config()
        results = _get_all_result_stats(config)
        ui_cfg  = _load_ui_config()
        bg_folder = ui_cfg.get("background_folder", "")
        for r in results:
            name = r.get("name", "")
            bg_path = Path(bg_folder) / name if bg_folder else None
            has_bg = False
            if bg_path:
                for ext in (".jpg", ".jpeg", ".png", ".webp"):
                    if (bg_path.parent / (name + ext)).exists():
                        has_bg = True
                        r["bg_image"] = f"/bg/{name}{ext}"
                        break
            if not has_bg:
                r["bg_image"] = "/icons/default_icon.png"
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# API — Anki sync
# ---------------------------------------------------------------------------

@app.route("/api/sync-anki", methods=["POST"])
def api_sync_anki():
    try:
        config = _load_config()
        result = pipeline.add_words_from_anki(config)
        # pipeline.add_words_from_anki updates config["anki"]["last_retrieved"]
        # and calls save_config internally — but that save_config call in
        # pipeline.py must also target AppData, so we re-save here to be safe.
        _save_config(config)
        return jsonify(result)
    except Exception as e:
        err_str = str(e)
        if "ConnectionError" in err_str or "Connection refused" in err_str or "connect" in err_str.lower():
            return jsonify({"error": "anki_not_open"}), 503
        return jsonify({"error": err_str}), 500


# ---------------------------------------------------------------------------
# API — Scan subtitles
# ---------------------------------------------------------------------------

@app.route("/api/scan-subs", methods=["POST"])
def api_scan_subs():
    try:
        data   = request.get_json() or {}
        config = _load_config()
        path   = data.get("path", "").strip()
        if path:
            config["subtitles"]["input_folder"] = path
            _save_config(config)
        result = pipeline.get_new_words_from_subtitles(config)
        pref  = config["words"]["preferred_parsing"]
        label = "orth" if pref == "orth_base" else "lemma"
        s = result.get(label, {})
        return jsonify({
            "unique":        s.get("unique", 0),
            "comprehension": s.get("comprehension", 0),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# API — Subs panel
# ---------------------------------------------------------------------------

@app.route("/api/subs/<folder_name>", methods=["GET"])
def api_subs_data(folder_name: str):
    try:
        config = _load_config()
        data   = pipeline.get_new_words_from_file(config, folder_name)
        stats  = data["stats"]
        words  = data["words"]

        flat_words = []
        for w in words:
            titles      = w.get("titles", [])
            start_times = w.get("start_times", [])
            sentences   = w.get("sentences", [])
            end_times   = w.get("end_times", [])
            for i in range(len(titles)):
                flat_words.append({
                    "word":       w["word"],
                    "count":      w["count"],
                    "title":      titles[i] if i < len(titles) else "",
                    "start_time": start_times[i] if i < len(start_times) else "",
                    "end_time":   end_times[i] if i < len(end_times) else "",
                    "sentence":   sentences[i] if i < len(sentences) else "",
                })

        return jsonify({"stats": stats, "words": flat_words})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/subs/<folder_name>/scan", methods=["POST"])
def api_subs_scan(folder_name: str):
    try:
        config = _load_config()
        original_input = config["subtitles"]["input_folder"]
        stats = pipeline.get_new_words_from_file(config, folder_name)["stats"]
        new_path = stats.get("path", original_input)
        config["subtitles"]["input_folder"] = new_path
        pipeline.get_new_words_from_subtitles(config)
        config["subtitles"]["input_folder"] = original_input
        _save_config(config)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/subs/<folder_name>/remove-word", methods=["POST"])
def api_remove_word(folder_name: str):
    try:
        data   = request.get_json()
        config = _load_config()
        pipeline.remove_word_from_subtitle_results(config, folder_name, data["word"])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/subs/<folder_name>/mark-known", methods=["POST"])
def api_mark_known(folder_name: str):
    try:
        data   = request.get_json()
        config = _load_config()
        pipeline.mark_word_as_known(config, data["word"])
        pipeline.remove_word_from_subtitle_results(config, folder_name, data["word"])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/subs/<folder_name>/add-line", methods=["POST"])
def api_add_line(folder_name: str):
    try:
        from src.subtitles import Subtitle
        data   = request.get_json()
        config = _load_config()
        sub = Subtitle(
            title      = data["title"],
            start_time = data["start_time"],
            end_time   = data.get("end_time", ""),
            text       = data["sentence"],
        )
        pipeline.write_subtitle_line_to_output(config, sub)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# API — Delete subtitle result
# ---------------------------------------------------------------------------

@app.route("/api/results/<folder_name>", methods=["DELETE"])
def api_delete_result(folder_name: str):
    try:
        config = _load_config()
        pipeline.delete_subtitle_results(config, folder_name)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# API — Kanji
# ---------------------------------------------------------------------------

@app.route("/api/kanji", methods=["GET"])
def api_kanji():
    try:
        config = _load_config()
        stats  = pipeline.kanji_stats(config)
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/kanji/sort", methods=["POST"])
def api_kanji_sort():
    try:
        data   = request.get_json()
        config = _load_config()
        config["kanji"]["sort"] = data["sort"]
        _save_config(config)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# API — Words
# ---------------------------------------------------------------------------

@app.route("/api/words", methods=["GET"])
def api_words():
    try:
        config = _load_config()
        store  = WordStore(config)
        words  = store.get_words(config)
        return jsonify(words)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/words/sort", methods=["POST"])
def api_words_sort():
    try:
        data   = request.get_json()
        config = _load_config()
        config["words"]["sort"] = data["sort"]
        _save_config(config)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# API — Reset databases
# ---------------------------------------------------------------------------

@app.route("/api/reset", methods=["POST"])
def api_reset():
    try:
        config = _load_config()
        pipeline.reset_databases(config)
        # reset_databases sets config["anki"]["last_retrieved"] = ""
        # in memory — persist that change to AppData now.
        _save_config(config)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# API — Browse folder (webview only, graceful fallback in browser)
# ---------------------------------------------------------------------------

@app.route("/api/browse-folder", methods=["POST"])
def api_browse_folder():
    """Ask pywebview to open a folder dialog. Returns chosen path."""
    try:
        import webview
        windows = webview.windows
        if windows:
            result = windows[0].create_file_dialog(webview.FOLDER_DIALOG)
            if result:
                return jsonify({"path": result[0]})
        return jsonify({"path": ""})
    except Exception as e:
        return jsonify({"path": "", "error": str(e)})


# ---------------------------------------------------------------------------
# Expose app for main.py
# ---------------------------------------------------------------------------

def create_app() -> Flask:
    return app