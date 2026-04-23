"""
config_loader.py
----------------
Loads and validates config.json.
Import ``load_config()`` in any module that needs settings.

Internal keys (prefixed with ``_``) are stripped before validation and
before writing to disk, so callers may freely annotate the in-memory
config dict (e.g. ``config["_config_path"]``) without corrupting the file.
"""

import json
from pathlib import Path
from typing import Any

_REQUIRED_KEYS = {
    "anki": ["connect_url", "decks_fields", "last_retrieved", "ignore_in_brackets"],
    "kanji": ["static_path", "dynamic_path", "sort"],
    "words": ["orth_base_path", "lemma_path", "preferred_parsing", "sort"],
    "subtitles": ["input_folder", "output_folder", "new_words_folder", "max_sentences_per_word"]
}

_VALID_KANJI_SORT_VALUES       = ["grade", "RTK"]
_VALID_PREFFERED_PARSING_VALUES = ["orth_base", "lemma"]
_VALID_WORDS_SORT_VALUES        = ["ascending", "descending"]


def _strip_internal(config: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of *config* with all ``_``-prefixed keys removed.

    Keys like ``_config_path`` are runtime annotations added by app.py so
    that pipeline functions know where to save.  They must never be written
    to disk or passed to ``_validate``.
    """
    return {k: v for k, v in config.items() if not k.startswith("_")}


def load_config(config_path: str | Path = "config.json") -> dict[str, Any]:
    """Load and return the project config.

    Args:
        config_path: Path to the JSON config file.  Defaults to
            ``config.json`` in the current working directory.

    Returns:
        The parsed config dictionary.

    Raises:
        FileNotFoundError: If the config file does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    _validate(config)
    return config


def save_config(config: dict[str, Any], config_path: str | Path = "config.json") -> None:
    """Persist an updated config dict back to disk.

    Internal keys (those starting with ``_``) are stripped before writing
    so they never appear in the JSON file.

    Args:
        config:      The config dictionary to write.
        config_path: Destination path.  Defaults to ``config.json``.
    """
    clean = _strip_internal(config)
    _validate(clean)
    with open(Path(config_path), "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=4)


def _validate(config: dict[str, Any]) -> None:
    """Validate config structure and value constraints.

    Args:
        config: Config dict to validate (must already be stripped of
                internal ``_``-prefixed keys).

    Raises:
        ValueError: If required keys are missing or values are invalid.
    """
    for section, keys in _REQUIRED_KEYS.items():
        if section not in config:
            raise ValueError(f"Config missing section: '{section}'")
        for key in keys:
            if key not in config[section]:
                raise ValueError(f"Config missing key: '{section}.{key}'")

    if config["kanji"]["sort"] not in _VALID_KANJI_SORT_VALUES:
        raise ValueError(
            f"Invalid 'kanji.sort' - must be either "
            f"{_VALID_KANJI_SORT_VALUES[0]} or {_VALID_KANJI_SORT_VALUES[1]}"
        )
    if config["words"]["preferred_parsing"] not in _VALID_PREFFERED_PARSING_VALUES:
        raise ValueError(
            f"Invalid 'words.preferred_parsing' - must be either "
            f"{_VALID_PREFFERED_PARSING_VALUES[0]} or {_VALID_PREFFERED_PARSING_VALUES[1]}"
        )
    if config["words"]["sort"] not in _VALID_WORDS_SORT_VALUES:
        raise ValueError(
            f"Invalid 'words.sort' - must be either "
            f"{_VALID_WORDS_SORT_VALUES[0]} or {_VALID_WORDS_SORT_VALUES[1]}"
        )