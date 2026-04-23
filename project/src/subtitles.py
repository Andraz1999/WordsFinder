"""
subtitles.py
------------
Parse subtitle files and find vocabulary that is new to the learner.

Supported formats: .srt, .ass, .ssa  (via the ``srt`` library).

Results layout
~~~~~~~~~~~~~~
For each subtitle input folder a **results folder** is created under
``new_words_folder``, named after the input folder (e.g. ``MyShow/``).
Inside that folder two JSONL files are written:

* ``orth_base.jsonl`` – one record per unique ``orthBase`` form.
* ``lemma.jsonl``     – one record per unique ``lemma`` form.

Typical usage::

    from subtitles import load_subtitles, find_new_words

    subs   = load_subtitles(config)
    result = find_new_words(config, word_store, subs, tokenised_pairs)
    print(result)
"""

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import srt

from src.jp_tokenizer import WordPair
from src.word_store import WordStore


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Subtitle:
    """One subtitle line from a media file."""
    title:      str   # stem of the source file (e.g. "episode_01")
    start_time: str   # timedelta string from the parser
    end_time:   str
    text:       str   # raw subtitle text (not yet cleaned)


@dataclass
class NewWordRecord:
    """Aggregated information about one new word found in the subtitles."""
    word:        str
    count:       int       = 0
    titles:      list[str] = field(default_factory=list)
    start_times: list[str] = field(default_factory=list)
    end_times:   list[str] = field(default_factory=list)
    sentences:   list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "word":        self.word,
            "count":       self.count,
            "titles":      self.titles,
            "start_times": self.start_times,
            "end_times":   self.end_times,
            "sentences":   self.sentences,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "NewWordRecord":
        return NewWordRecord(
            word        = d["word"],
            count       = d.get("count",       0),
            titles      = d.get("titles",       []),
            start_times = d.get("start_times",  []),
            end_times   = d.get("end_times",    []),
            sentences   = d.get("sentences",    []),
        )


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_srt(path: Path) -> list[Subtitle]:
    """Parse a ``.srt`` file into a list of :class:`Subtitle` objects."""
    with open(path, "r", encoding="utf-8") as f:
        data = f.read()
    return [
        Subtitle(
            title      = path.stem,
            start_time = str(sub.start),
            end_time   = str(sub.end),
            text       = sub.content,
        )
        for sub in srt.parse(data)
    ]


def _strip_ass_tags(text: str) -> str:
    """Remove ASS/SSA override tags (``{\\an8}``, ``{\\blur4}``, …)."""
    return re.sub(r'\{[^}]*\}', '', text)


def _parse_ass(path: Path) -> list[Subtitle]:
    """Parse a ``.ass`` / ``.ssa`` file into :class:`Subtitle` objects."""
    subtitles: list[Subtitle] = []
    in_events = False
    format_cols: list[str] = []

    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.strip() == "[Events]":
                in_events = True
                continue
            if not in_events:
                continue
            if line.startswith("["):
                break
            if line.startswith("Format:"):
                format_cols = [c.strip() for c in line[7:].split(",")]
                continue
            if line.startswith("Dialogue:") and format_cols:
                values = line[9:].split(",", len(format_cols) - 1)
                row = dict(zip(format_cols, values))
                raw_text = _strip_ass_tags(row.get("Text", ""))
                subtitles.append(Subtitle(
                    title      = path.stem,
                    start_time = row.get("Start", ""),
                    end_time   = row.get("End",   ""),
                    text       = raw_text,
                ))
    return subtitles


_PARSERS = {
    ".srt": _parse_srt,
    ".ass": _parse_ass,
    ".ssa": _parse_ass,
}


# ---------------------------------------------------------------------------
# Public loading API
# ---------------------------------------------------------------------------

def load_subtitles(config: dict[str, Any]) -> list[Subtitle]:
    """Recursively load all supported subtitle files from the input folder.

    Args:
        config: Project config dict.

    Returns:
        All :class:`Subtitle` lines from every file found, in the order
        they are encountered.

    Raises:
        FileNotFoundError: If the input folder does not exist.
    """
    folder = Path(config["subtitles"]["input_folder"])
    if not folder.exists():
        raise FileNotFoundError(f"Subtitles input folder not found: {folder}")

    subtitles: list[Subtitle] = []
    for ext, parser in _PARSERS.items():
        for path in sorted(folder.rglob(f"*{ext}")):
            subtitles.extend(parser(path))
    return subtitles


# ---------------------------------------------------------------------------
# New-word detection
# ---------------------------------------------------------------------------

def find_new_words(
    config:     dict[str, Any],
    word_store: WordStore,
    subtitles:  list[Subtitle],
    pair_lists: list[list[WordPair]],
) -> dict[str, Any]:
    """Identify vocabulary in *subtitles* that is not in *word_store*.

    For each subtitle input folder a results folder is created under
    ``new_words_folder``.  Inside it two files are written:
    ``orth_base.jsonl`` and ``lemma.jsonl``.

    Each representation is checked independently against its own database:
    an orth-base form is only recorded as new if it is absent from the
    orth-base DB, and likewise for lemma.

    Args:
        config:     Project config dict.
        word_store: Populated :class:`~word_store.WordStore` instance.
        subtitles:  Subtitle lines (same order / length as *pair_lists*).
        pair_lists: :class:`~jp_tokenizer.WordPair` lists for each subtitle
                    line.  Must have the same length as *subtitles*.

    Returns:
        Dict with ``folder_name`` and stats of the new words:
        (``*_new_unique``, ``*_new_count``, ``all_words_count``), 
        where * is either ``orth_base`` or ``lemma``.

    Raises:
        ValueError: If *subtitles* and *pair_lists* have different lengths.
    """
    if len(subtitles) != len(pair_lists):
        raise ValueError(
            f"subtitles ({len(subtitles)}) and pair_lists ({len(pair_lists)}) "
            "must have the same length."
        )

    # Separate accumulators for the two representations
    new_orth:  dict[str, NewWordRecord] = {}
    new_lemma: dict[str, NewWordRecord] = {}

    orth_new_unique  = 0
    orth_new_count   = 0
    lemma_new_unique = 0
    lemma_new_count  = 0
    all_words_count  = 0

    for sub, pairs in zip(subtitles, pair_lists):
        for pair in pairs:
            all_words_count += 1

            # --- orth_base accumulator ---
            ob = pair.orth_base
            if not word_store.is_known_orth(ob):
                orth_new_count += 1
                if ob in new_orth:
                    r = new_orth[ob]
                    r.count += 1
                    if r.count <= config["subtitles"]["max_sentences_per_word"]:
                        r.titles.append(sub.title)
                        r.start_times.append(sub.start_time)
                        r.end_times.append(sub.end_time)
                        r.sentences.append(sub.text)
                else:
                    orth_new_unique += 1
                    new_orth[ob] = NewWordRecord(
                        word        = ob,
                        count       = 1,
                        titles      = [sub.title],
                        start_times = [sub.start_time],
                        end_times   = [sub.end_time],
                        sentences   = [sub.text],
                    )

            # --- lemma accumulator ---
            lm = pair.lemma
            if not word_store.is_known_lemma(lm):
                lemma_new_count += 1
                if lm in new_lemma:
                    r = new_lemma[lm]
                    r.count += 1
                    if r.count <= config["subtitles"]["max_sentences_per_word"]:
                        r.titles.append(sub.title)
                        r.start_times.append(sub.start_time)
                        r.end_times.append(sub.end_time)
                        r.sentences.append(sub.text)
                else:
                    lemma_new_unique += 1
                    new_lemma[lm] = NewWordRecord(
                        word        = lm,
                        count       = 1,
                        titles      = [sub.title],
                        start_times = [sub.start_time],
                        end_times   = [sub.end_time],
                        sentences   = [sub.text],
                    )


    
    orth_stats  = {"new_unique_words": orth_new_unique,  "new_words_count": orth_new_count,  "all_words_count": all_words_count, "path": config["subtitles"]["input_folder"]}
    lemma_stats = {"new_unique_words": lemma_new_unique, "new_words_count": lemma_new_count, "all_words_count": all_words_count, "path": config["subtitles"]["input_folder"]}
    
    folder_name = _folder_name(config)
    
    sorted_orth_base = sorted(list(new_orth.values()), key=lambda x: x.count, reverse=True)
    sorted_lemma = sorted(list(new_lemma.values()), key=lambda x: x.count, reverse=True)
    
    _save_new_words(
        config, folder_name,
        sorted_orth_base,  orth_stats,
        sorted_lemma, lemma_stats,
    )

    return {
        "folder_name": folder_name,
        "orth":  orth_stats,
        "lemma": lemma_stats,
    }


# ---------------------------------------------------------------------------
# SRT output
# ---------------------------------------------------------------------------

def _timedelta_str_to_srt(time_str: str) -> str:
    """Convert a :class:`datetime.timedelta` string to SRT timestamp format.

    Timedelta ``__str__`` produces strings like ``"0:16:33.158000"`` or
    ``"1:04:07.000000"``.  SRT requires ``"HH:MM:SS,mmm"``.

    Args:
        time_str: A timedelta string such as ``"0:16:33.158000"``.

    Returns:
        An SRT-formatted timestamp such as ``"00:16:33,158"``.
    """
    # Split off the fractional-seconds part (may be absent for whole seconds)
    if "." in time_str:
        main, frac = time_str.split(".")
        millis = int(frac[:3].ljust(3, "0"))   # keep only milliseconds
    else:
        main, millis = time_str, 0

    parts = main.split(":")
    # timedelta str can be H:MM:SS or HH:MM:SS — normalise to three parts
    if len(parts) == 2:          # M:SS  (rare but possible for short clips)
        h, m, s = 0, int(parts[0]), int(parts[1])
    else:
        h, m, s = int(parts[0]), int(parts[1]), int(parts[2])

    return f"{h:02d}:{m:02d}:{s:02d},{millis:03d}"


def write_subtitle_line(config: dict[str, Any], subtitle: Subtitle) -> bool:
    """Append a subtitle line to the corresponding ``.srt`` output file.

    The output file is::

        <config["subtitles"]["output_folder"]> / <subtitle.title>.srt

    The file is created if it does not exist. Lines are kept sorted by
    start time.
    
    Args: 
        config: Project config dict. Must contain `config["subtitles"]["output_folder"]. 
        subtitle: The :class:Subtitle to persist.

    Returns:
        True if the subtitle was added, False if it was skipped due to duplication.
    """
    out_folder = Path(config["subtitles"]["output_folder"])
    out_folder.mkdir(parents=True, exist_ok=True)
    out_path = out_folder / f"{subtitle.title}.srt"

    start_srt = _timedelta_str_to_srt(subtitle.start_time)
    end_srt   = _timedelta_str_to_srt(subtitle.end_time)

    # ------------------------------------------------------------------
    # Read existing entries (if any)
    # ------------------------------------------------------------------
    existing: list[srt.Subtitle] = []
    if out_path.exists():
        with open(out_path, "r", encoding="utf-8") as f:
            existing = list(srt.parse(f.read()))

    # ------------------------------------------------------------------
    # Duplicate check
    # ------------------------------------------------------------------
    new_text_stripped = subtitle.text.strip()
    for entry in existing:
        if (
            _timedelta_str_to_srt(str(entry.start)) == start_srt
            and _timedelta_str_to_srt(str(entry.end))   == end_srt
            and entry.content.strip()                    == new_text_stripped
        ):
            return False  # duplicate

    # ------------------------------------------------------------------
    # Build new entry and re-sort by start time
    # ------------------------------------------------------------------
    import datetime

    def _parse_srt_ts(ts: str) -> datetime.timedelta:
        h, m, rest = ts.split(":")
        s, ms = rest.split(",")
        return datetime.timedelta(
            hours=int(h), minutes=int(m), seconds=int(s), milliseconds=int(ms)
        )

    new_entry = srt.Subtitle(
        index   = 0,
        start   = _parse_srt_ts(start_srt),
        end     = _parse_srt_ts(end_srt),
        content = subtitle.text.strip(),
    )

    all_entries = existing + [new_entry]
    all_entries.sort(key=lambda e: e.start)

    for idx, entry in enumerate(all_entries, start=1):
        entry.index = idx

    # ------------------------------------------------------------------
    # Write back
    # ------------------------------------------------------------------
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(srt.compose(all_entries))

    return True


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _folder_name(config: dict[str, Any]) -> str:
    """Return the results sub-folder name for the current subtitle input folder."""
    return Path(config["subtitles"]["input_folder"]).name or "subtitles"


def _results_dir(config: dict[str, Any], folder_name: str) -> Path:
    """Return (and create) the results directory for *folder_name*.

    Structure: ``<new_words_folder>/<folder_name>/``
    """
    out = Path(config["subtitles"]["new_words_folder"]) / folder_name
    out.mkdir(parents=True, exist_ok=True)
    return out


def _orth_path(results_dir: Path) -> Path:
    return results_dir / "orth_base.jsonl"


def _lemma_path(results_dir: Path) -> Path:
    return results_dir / "lemma.jsonl"


def _write_jsonl(
    path:    Path,
    records: list[NewWordRecord],
    stats:   dict[str, int | str],
) -> None:
    """Write *records* to *path* as JSONL.

    The first line is a ``_stats`` header record so that summary numbers
    can be read back cheaply without scanning the whole file::

        {"_stats": true, "new_unique_words": 42, "new_words_count": 105, "all_words_count": 300, "path": "subtitles"}

    Subsequent lines are word records sorted by count descending.
    """
    sorted_records = sorted(records, key=lambda r: r.count, reverse=True)
    with open(path, "w", encoding="utf-8") as f:
        header = {"_stats": True, **stats}
        f.write(json.dumps(header, ensure_ascii=False) + "\n")
        for rec in sorted_records:
            f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")


def _save_new_words(
    config:        dict[str, Any],
    folder_name:   str,
    orth_records:  list[NewWordRecord],
    orth_stats:    dict[str, int | str],
    lemma_records: list[NewWordRecord],
    lemma_stats:   dict[str, int | str],
) -> None:
    """Persist both record lists (with their stats headers) into the results folder."""
    rdir = _results_dir(config, folder_name)
    _write_jsonl(_orth_path(rdir),  orth_records,  orth_stats)
    _write_jsonl(_lemma_path(rdir), lemma_records, lemma_stats)


def _load_jsonl(path: Path, to_dict: bool = False) -> list[NewWordRecord] | list[dict[str, Any]]:
    """Load a JSONL file into a list of :class:`NewWordRecord` objects or its dict form.

    The first line is a ``_stats`` header and is silently skipped.
    """
    if not path.exists():
        return []
    records: list[NewWordRecord] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("_stats"):   # skip the header record
                continue
            if to_dict:
                records.append(obj)
            else:
                records.append(NewWordRecord.from_dict(obj))
    return records


def load_results(
    config: dict[str, Any],
    folder_name: str,
) -> list[dict[str, Any]]:
    """Load previously saved new-words files for *folder_name*.

    Args:
        config:      Project config dict.
        folder_name: Name of the results sub-folder (no extension).

    Returns:
        ``orth_records`` or ``lemma_records`` — depends on config.preffered_parsing
    """
    rdir = Path(config["subtitles"]["new_words_folder"]) / folder_name
    if (config["words"]["preferred_parsing"] == "orth_base"):
        return _load_jsonl(_orth_path(rdir), True)
    elif (config["words"]["preferred_parsing"] == "lemma"):
        return _load_jsonl(_lemma_path(rdir), True)


def _read_stats_header(path: Path) -> dict[str, int | str] | None:
    """Read the ``_stats`` header from the first line of a results JSONL file.

    Returns ``None`` if the file does not exist or has no header.
    """
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        first = f.readline().strip()
    if not first:
        return None
    obj = json.loads(first)
    if not obj.get("_stats"):
        return None
    return {
        "new_unique_words": obj["new_unique_words"],
        "new_words_count":  obj["new_words_count"],
        "all_words_count":  obj["all_words_count"],
        "path":             obj["path"]
    }


def subtitle_stats(
    config:      dict[str, Any],
    folder_name: str,
) -> dict[str, int] | None:
    """Return the saved scan stats for a results folder without re-scanning.

    Reads only the first line of each JSONL file, so this is very cheap.

    Args:
        config:      Project config dict.
        folder_name: Name of the results sub-folder to inspect.

    Returns:
        Dict, with keys (``new_unique_words``, ``new_words_count``,
        ``all_words_count``, ``path``) or ``None`` if that file does not exist yet.
    """
    rdir = Path(config["subtitles"]["new_words_folder"]) / folder_name
    if (config["words"]["preferred_parsing"] == "orth_base"):
        return _read_stats_header(_orth_path(rdir))
    elif (config["words"]["preferred_parsing"] == "lemma"):
        return _read_stats_header(_lemma_path(rdir))

    

def delete_orth_base_from_results(
    config:      dict[str, Any],
    folder_name: str,
    word:        str,
) -> bool:
    """Remove a word from the orth-base results folder.

    ``word`` is removed from ``orth_base.jsonl``.

    Args:
        config:      Project config dict.
        folder_name: Results sub-folder name (no extension).
        word:        str to remove.

    Returns:
        ``True`` if the wird was found and removed from ``orth_base.jsonl``,
        ``False`` if it was absent.
    """
    rdir = Path(config["subtitles"]["new_words_folder"]) / folder_name
    if not rdir.exists():
        return False

    removed = False

    orth_records  = _load_jsonl(_orth_path(rdir))

    orth_filtered = []
    deleted_word = {}
    for r in orth_records:
        if r.word != word:
            orth_filtered.append(r)
        else:
            deleted_word = r
    
    stats = _read_stats_header(_orth_path(rdir))
    
    stats["new_unique_words"] -= 1
    stats["new_words_count"] -= deleted_word.count
    stats["all_words_count"] -= deleted_word.count
        
    if len(orth_filtered) < len(orth_records):
        _write_jsonl(_orth_path(rdir), orth_filtered, stats)
        removed = True

    return removed   
    


def delete_lemma_from_results(
    config:      dict[str, Any],
    folder_name: str,
    word:        str,
) -> bool:
    """Remove a word from the orth-base results folder.

    ``word`` is removed from ``lemma.jsonl``.

    Args:
        config:      Project config dict.
        folder_name: Results sub-folder name (no extension).
        word:        str to remove.

    Returns:
        ``True`` if the wird was found and removed from ``lemma.jsonl``,
        ``False`` if it was absent.
    """
    
    rdir = Path(config["subtitles"]["new_words_folder"]) / folder_name
    if not rdir.exists():
        return False

    removed = False
    
    lemma_records  = _load_jsonl(_lemma_path(rdir))
    #lemma_filtered = [r for r in lemma_records if r.word != word]
    
    lemma_filtered = []
    deleted_word = {}
    for r in lemma_records:
        if r.word != word:
            lemma_filtered.append(r)
        else:
            deleted_word = r
            
    stats = _read_stats_header(_orth_path(rdir))
    
    stats["new_unique_words"] -= 1
    stats["new_words_count"] -= deleted_word.count
    stats["all_words_count"] -= deleted_word.count
    
    
    if len(lemma_filtered) < len(lemma_records):
        _write_jsonl(_lemma_path(rdir), lemma_filtered, stats)
        removed = True
        
    return removed


def delete_results_folder(config: dict[str, Any], folder_name: str) -> bool:
    """Delete the entire results folder for *folder_name*.

    Args:
        config:      Project config dict.
        folder_name: Results sub-folder name to delete.

    Returns:
        ``True`` if the folder existed and was deleted, ``False`` otherwise.
    """
    rdir = Path(config["subtitles"]["new_words_folder"]) / folder_name
    if rdir.exists() and rdir.is_dir():
        shutil.rmtree(rdir)
        return True
    return False

# ---

def _get_sorted_folder_names(config: dict[str, Any]) -> list[str]:
    """ Return the names of all folder names with new words sorted by 'last_modefied'"""
    folder_path = Path(config["subtitles"]["new_words_folder"])
    
    folders = [f for f in folder_path.iterdir() if f.is_dir()]
    folders.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    
    return [f.name for f in folders]

def get_all_result_stats(
    config: dict[str, Any]
) -> list[dict[str, str | int]]:
    """ Return a list of dicts with keys 
    (``name``, ``new_unique_words``, ``new_words_count``,
        ``all_words_count``, ``path``)
    """
    folder_names = _get_sorted_folder_names(config)
    result = []
    for folder_name in folder_names:
        entry = subtitle_stats(config, folder_name)
        entry["name"] = folder_name
        result.append(entry)
    return result
        