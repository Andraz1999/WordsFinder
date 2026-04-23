"""
pipeline.py
-----------
High-level orchestration layer.  Every public function here corresponds
to one user-facing operation exposed by ``main.py``.

All functions accept the project ``config`` dict as their first argument.

Changes vs original:
  - add_words_from_anki  now returns {"new_sentences": int, "new_words": int}
  - get_new_words_from_subtitles now returns the full stats dict
  Both functions still print to stdout for CLI compatibility.

  - save_config() is always called with an explicit path taken from the
    config dict itself, so it always writes to AppData — never to the
    bundle or Program Files directory.
"""

from typing import Any
from pathlib import Path

from src.config_loader import save_config as _save_config_to_file
from src.anki_client   import fetch_sentences
from src.jp_tokenizer  import clean, tokenize
from src.kanji_store   import KanjiStore
from src.word_store    import WordStore
from src.subtitles     import (
    load_subtitles,
    find_new_words,
    subtitle_stats as _subtitle_stats_from_file,
    delete_orth_base_from_results,
    delete_lemma_from_results,
    delete_results_folder,
    write_subtitle_line,
    Subtitle,
    load_results,
    _folder_name,
)


def _save_config(config: dict[str, Any]) -> None:
    """Save config to the path recorded inside the config dict.

    The config dict's path is set by main.py/_seed_appdata() to the
    correct AppData location, so this always writes to AppData regardless
    of where the exe lives.
    """
    # config_loader.save_config signature: save_config(config, path)
    # We derive the path from the config dict's own "config_path" key if
    # present (set by load_config), otherwise fall back to the caller
    # supplying it.  app.py always calls _save_config(config) via its own
    # wrapper that already knows the path — but pipeline functions that
    # mutate config and save themselves also need a path.
    path = config.get("_config_path")
    if path:
        _save_config_to_file(config, Path(path))
    else:
        # Fallback: let config_loader handle it (should not happen in normal use)
        _save_config_to_file(config)


# ---------------------------------------------------------------------------
# 1. Populate databases from Anki
# ---------------------------------------------------------------------------

def add_words_from_anki(config: dict[str, Any]) -> dict[str, int]:
    """Connect to Anki, extract new sentences, and update both databases.

    Returns:
        {"new_sentences": int, "new_words": int}
    """
    last = config["anki"].get("last_retrieved", "")

    raw_cards = fetch_sentences(config)
    new_cards = [
        (sentence, card_id)
        for sentence, card_id in raw_cards
        if last == "" or str(card_id) > last
    ]

    new_sents = len(new_cards)
    print(f"{new_sents} new sentence(s) found in Anki.")

    if not new_cards:
        return {"new_sentences": 0, "new_words": 0}

    sentences = [sentence for sentence, _ in new_cards]
    cleaned   = clean(sentences, ignore_brackets=config["anki"].get("ignore_in_brackets", True))

    # --- kanji ---
    kanji_store = KanjiStore(config)
    new_kanji   = kanji_store.update(cleaned)
    kanji_store.save()
    print(f"{new_kanji} new kanji added.")

    # --- words ---
    flat_pairs = tokenize(cleaned, flatten=True)
    word_store = WordStore(config)
    new_words  = word_store.update(flat_pairs)
    word_store.save()
    print(f"{new_words} new word(s) added.")

    # Persist the highest card_id seen as the new watermark.
    # _save_config is called here so both CLI and app persist last_retrieved.
    # app.py's api_sync_anki may also call _save_config afterwards — that is
    # a harmless double-write.
    max_id = str(max(card_id for _, card_id in new_cards))
    config["anki"]["last_retrieved"] = max_id
    _save_config(config)

    return {"new_sentences": new_sents, "new_words": new_words}


# ---------------------------------------------------------------------------
# 2. Find new words in subtitle files
# ---------------------------------------------------------------------------

def get_new_words_from_subtitles(config: dict[str, Any]) -> dict[str, Any]:
    """Parse subtitle files and report words not yet in the word database.

    Returns:
        {
            "orth": {"unique": int, "comprehension": float, ...},
            "lemma": {"unique": int, "comprehension": float, ...},
        }
    """
    word_store = WordStore(config)
    subtitles  = load_subtitles(config)

    raw_texts  = [sub.text for sub in subtitles]
    cleaned    = clean(raw_texts, ignore_brackets=config["anki"].get("ignore_in_brackets", True))
    pair_lists = tokenize(cleaned, flatten=False)

    raw_stats  = find_new_words(config, word_store, subtitles, pair_lists)
    result     = {}

    for label, s in (("orth", raw_stats["orth"]), ("lemma", raw_stats["lemma"])):
        unique   = s["new_unique_words"]
        new_tok  = s["new_words_count"]
        total    = s["all_words_count"]
        known    = total - new_tok
        coverage = (known / total * 100) if total else 0.0
        print(
            f"[{label}]  {unique} unique new word(s).  "
            f"Comprehension: {coverage:.1f}%  ({known}/{total} tokens known)."
        )
        result[label] = {
            "unique":         unique,
            "comprehension":  round(coverage, 1),
            "new_words":      new_tok,
            "all_words":      total,
        }

    return result


# ---------------------------------------------------------------------------
# 3. Reset all databases
# ---------------------------------------------------------------------------

def reset_databases(config: dict[str, Any]) -> None:
    """Delete both word JSONL files, the kanji-dynamic file, and reset the watermark."""
    WordStore(config).reset()
    KanjiStore(config).reset()

    config["anki"]["last_retrieved"] = ""
    _save_config(config)
    print("Databases reset.")


# ---------------------------------------------------------------------------
# 4. Manually mark a word as already known
# ---------------------------------------------------------------------------

def mark_word_as_known(config: dict[str, Any], word: str) -> None:
    """Add *word* to the database specified in config and flag it as manually known."""
    store = WordStore(config)
    is_now_marked = False
    if config["words"]["preferred_parsing"] == "orth_base":
        is_now_marked = store.mark_known_orth_base(word)
    elif config["words"]["preferred_parsing"] == "lemma":
        is_now_marked = store.mark_known_lemma(word)
    store.save()
    if is_now_marked:
        print(f"'{word}' marked as known.")
    else:
        print(f"'{word}' was already marked as known.")


# ---------------------------------------------------------------------------
# 5. Remove a word from a subtitle results folder
# ---------------------------------------------------------------------------

def remove_word_from_subtitle_results(
    config:      dict[str, Any],
    folder_name: str,
    word:        str,
) -> None:
    """Delete *word* from the appropriate JSONL file in the results folder."""
    removed = False
    if config["words"]["preferred_parsing"] == "orth_base":
        removed = delete_orth_base_from_results(config, folder_name, word)
    elif config["words"]["preferred_parsing"] == "lemma":
        removed = delete_lemma_from_results(config, folder_name, word)

    if removed:
        print(f"{word} removed from '{folder_name}' results.")
    else:
        print(f"{word} was not found in '{folder_name}' results.")


# ---------------------------------------------------------------------------
# 6. Delete a subtitle results folder
# ---------------------------------------------------------------------------

def delete_subtitle_results(config: dict[str, Any], folder_name: str) -> None:
    """Delete the entire results folder for the specified subtitle source."""
    deleted = delete_results_folder(config, folder_name)
    if deleted:
        print(f"Subtitle results folder '{folder_name}' deleted.")
    else:
        print(f"No subtitle results folder '{folder_name}' found.")


# ---------------------------------------------------------------------------
# 7. Subtitle scan statistics
# ---------------------------------------------------------------------------

def subtitle_stats(config: dict[str, Any], folder_name: str) -> dict[str, Any]:
    """Print and return the saved scan statistics for a subtitle results folder."""
    stats = _subtitle_stats_from_file(config, folder_name)

    for label, s in (("orth_base", stats["orth"]), ("lemma", stats["lemma"])):
        if s is None:
            print(f"[{label}]  No results file found for '{folder_name}'.")
            continue
        unique   = s["new_unique_words"]
        new_tok  = s["new_words_count"]
        total    = s["all_words_count"]
        known    = total - new_tok
        coverage = (known / total * 100) if total else 0.0
        print(
            f"[{label}]  {unique} unique new word(s).  "
            f"Comprehension: {coverage:.1f}%  ({known}/{total} tokens known)."
        )

    return stats


# ---------------------------------------------------------------------------
# 8. Add a subtitle line
# ---------------------------------------------------------------------------

def write_subtitle_line_to_output(config: dict[str, Any], subtitle: Subtitle) -> None:
    """Write a subtitle line and print the result."""
    added = write_subtitle_line(config, subtitle)

    start_srt = subtitle.start_time
    end_srt   = subtitle.end_time
    text      = subtitle.text.strip()
    filename  = f"{subtitle.title}.srt"

    if added:
        print(
            f"[subtitles] Written to '{filename}': "
            f"{start_srt} --> {end_srt} | {text!r}"
        )
    else:
        print(
            f"[subtitles] Duplicate line skipped in '{filename}': "
            f"{start_srt} --> {end_srt} | {text!r}"
        )


# ---------------------------------------------------------------------------
# 9. Kanji statistics
# ---------------------------------------------------------------------------

def kanji_stats(config: dict[str, Any]) -> dict[str, Any]:
    """Return detailed kanji knowledge statistics and print a summary."""
    sort_by = config.get("kanji", {}).get("sort", "grade")
    store   = KanjiStore(config)
    stats   = store.stats(sort_by=sort_by)

    joyo = stats["joyo"]
    rtk1 = stats["rtk1"]
    rtk3 = stats["rtk3"]
    rare = stats["rare"]

    print(f"Joyo kanji:    {joyo['known']}/{joyo['total']}")
    print(f"RTK-1 kanji:   {rtk1['known']}/{rtk1['total']}")
    print(f"RTK-3 kanji: {rtk3['known']}/{rtk3['total']}")
    print(f"Rare kanji:    {rare['total']}")
    print("By Joyo grade:")
    for grade, gs in stats["by_joyo_grade"].items():
        print(f"  Grade {grade}: {gs['known']}/{gs['total']}")

    return stats


# ---------------------------------------------------------------------------
# 10. Subs
# ---------------------------------------------------------------------------

def get_new_words_from_file(config: dict[str, Any], folder_name: str) -> dict[str, Any]:
    """Return stats and new words from the folder.

    Args:
        config (dict[str, Any]):
        folder_name (str): name of the folder where the new words are

    Returns:
        dict[str, Any]: with keys (``stats``, ``words``)
    """
    return {
        "stats": _subtitle_stats_from_file(config, folder_name),
        "words": load_results(config, folder_name),
    }