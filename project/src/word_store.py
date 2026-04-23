"""
word_store.py
-------------
Manages the Anki-derived word database.

Two parallel JSONL files are maintained so that every known word can be
looked up by either its ``orth_base`` (surface spelling) or its ``lemma``
(canonical UniDic form):

* ``<anki_words_orth_base>``  – keyed by ``orthBase``
* ``<anki_words_lemma>``      – keyed by ``lemma``

Each record has the shape::

    {"word": "食べる", "count": 3, "known": false}

``known=True`` marks words the user has explicitly flagged as already
known; they are treated the same as Anki words and excluded from the
"new words" search in subtitles.

Typical usage::

    from jp_tokenizer import WordPair
    store = WordStore(config)
    store.update([WordPair("食べる", "食べる"), WordPair("飲む", "飲む")])
    store.mark_known(WordPair("食べる", "食べる"))
    print(store.is_known_orth("食べる"))  # True
    store.save()
"""

import json
from pathlib import Path
from typing import Any

from src.jp_tokenizer import WordPair



class WordStore:
    """In-memory word database backed by two parallel JSONL files.

    Args:
        config: The project config dict.
                ``config["paths"]["anki_words_orth_base"]`` and
                ``config["paths"]["anki_words_lemma"]`` must point to the
                two JSONL storage files.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._path_orth  = Path(config["words"]["orth_base_path"])
        self._path_lemma = Path(config["words"]["lemma_path"])
        self._db_orth:  dict[str, dict[str, Any]] = self._load(self._path_orth)
        self._db_lemma: dict[str, dict[str, Any]] = self._load(self._path_lemma)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load(path: Path, to_list: bool = False) -> dict[str, dict[str, Any]] | list[dict[str, Any]]:
        """Read a JSONL file into an in-memory dict keyed by ``word``."""
        db: dict[str, dict[str, Any]] = {}
        words_list = []
        if not path.exists():
            return db
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    obj = json.loads(line)
                    db[obj["word"]] = obj
                    words_list.append(obj)
        if to_list:
            return words_list
        else:
            return db

    @staticmethod
    def _save_db(db: dict[str, dict[str, Any]], path: Path) -> None:
        """Persist one in-memory dict to a JSONL file, sorted by count desc."""
        path.parent.mkdir(parents=True, exist_ok=True)
        sorted_items = sorted(db.values(), key=lambda x: x["count"], reverse=True)
        with open(path, "w", encoding="utf-8") as f:
            for record in sorted_items:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def is_known_orth(self, orth_base: str) -> bool:
        """Return ``True`` if *orth_base* is in the orth-base database.

        Args:
            orth_base: The ``orthBase`` form to look up.
        """
        return orth_base in self._db_orth

    def is_known_lemma(self, lemma: str) -> bool:
        """Return ``True`` if *lemma* is in the lemma database.

        Args:
            lemma: The lemma form to look up.
        """
        return lemma in self._db_lemma

    def is_manually_known(self, pair: WordPair) -> bool:
        """Return ``True`` only if *either* form was manually marked as known.

        Args:
            pair: A :class:`~jp_tokenizer.WordPair` to look up.
        """
        orth_entry  = self._db_orth.get(pair.orth_base)
        lemma_entry = self._db_lemma.get(pair.lemma)
        return (
            (orth_entry  is not None and orth_entry.get("known",  False)) or
            (lemma_entry is not None and lemma_entry.get("known", False))
        )

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def update(self, pairs: list[WordPair]) -> int:
        """Add new word pairs (or increment counts of existing ones).

        Each :class:`~jp_tokenizer.WordPair` updates *both* JSONL files
        independently: the ``orth_base`` value goes into the orth-base DB
        and the ``lemma`` value goes into the lemma DB.

        Args:
            pairs: Flat list of :class:`~jp_tokenizer.WordPair` objects.

        Returns:
            Number of *new* orth-base entries that were not previously in
            the database (used as a proxy for "new words seen").
        """
        count = 0
        for pair in pairs:
            ob = pair.orth_base
            lm = pair.lemma

            # --- orth-base DB ---
            if ob in self._db_orth:
                self._db_orth[ob]["count"] += 1
            else:
                self._db_orth[ob] = {"word": ob, "count": 1, "known": False}
                count += 1

            # --- lemma DB ---
            if lm in self._db_lemma:
                self._db_lemma[lm]["count"] += 1
            else:
                self._db_lemma[lm] = {"word": lm, "count": 1, "known": False}

        return count

    def mark_known_orth_base(self, word: str) -> None:
        """Flag a word in orth-base database manually known.

        ``word`` is written to the orth-base database and
        If an entry already exists its ``known`` flag is set to ``True`` (count is
        unchanged).

        Args:
            word: A :str: to mark.
            
        Returns:
            ``True`` iff the word has not been marked or in the database yet,
            ``False`` otherwise.
        """
        
        if word in self._db_orth:
            self._db_orth[word]["known"] = True
            return False
        else:
            self._db_orth[word] = {"word": word, "count": 0, "known": True}
            return True
            
    def mark_known_lemma(self, word: str) -> None:
        """Flag a word in lemma database manually known.

        ``word`` is written to the lemma database and
        If an entry already exists its ``known`` flag is set to ``True`` (count is
        unchanged).

        Args:
            word: A :str: to mark.
            
        Returns:
            ``True`` iff the word has not been marked or in the database yet,
            ``False`` otherwise.
        """
        
        if word in self._db_lemma:
            self._db_lemma[word]["known"] = True
        else:
            self._db_lemma[word] = {"word": word, "count": 0, "known": True}

    def save(self) -> None:
        """Persist both in-memory databases to disk."""
        self._save_db(self._db_orth,  self._path_orth)
        self._save_db(self._db_lemma, self._path_lemma)

    def reset(self) -> None:
        """Delete both JSONL files and clear the in-memory databases."""
        for path in (self._path_orth, self._path_lemma):
            if path.exists():
                path.unlink()
        self._db_orth  = {}
        self._db_lemma = {}
        
    def get_words(self, config: dict[str, Any]) ->list[dict[str, Any]]:
        path = ""
        if (config["words"]["preferred_parsing"] == "orth_base"):
            path = self._path_orth
        elif (config["words"]["preferred_parsing"] == "lemma"):
            path = self._path_lemma
        return self._load(path, to_list = True)
        