"""
kanji_store.py
--------------
Manages the kanji database:

* ``kanji_static.json``  – read-only reference data (Joyo/RTK grades).
* ``kanji_dynamic.json`` – mutable file tracking which kanji the user
  has encountered (``common`` = in the static list, ``rare`` = not).

Typical usage::

    store = KanjiStore(config)
    store.update(["今日は良い天気ですね"])
    stats = store.stats()
    store.save()
"""

import json
import re
from pathlib import Path
from typing import Any


class KanjiStore:
    """In-memory kanji database backed by two JSON files.

    Args:
        config: Project config dict.  Reads paths from
                ``config["kanji"]["static_path"]`` and
                ``config["kanji"]["dynamic_path"]``.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._static_path  = Path(config["kanji"]["static_path"])
        self._dynamic_path = Path(config["kanji"]["dynamic_path"])
        self._static:  dict[str, dict[str, Any]] = self._load_static()
        self._common:  set[str] = set()
        self._rare:    set[str] = set()
        self._load_dynamic()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_static(self) -> dict[str, dict[str, Any]]:
        if not self._static_path.exists():
            raise FileNotFoundError(
                f"kanji_static.json not found: {self._static_path}"
            )
        with open(self._static_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_dynamic(self) -> None:
        if not self._dynamic_path.exists():
            return
        with open(self._dynamic_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._common = set(data.get("common", []))
        self._rare   = set(data.get("rare",   []))

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def update(self, sentences: list[str]) -> int:
        """Scan *sentences* for kanji and add new ones to the database.

        Kanji found in ``kanji_static`` go into the ``common`` bucket;
        everything else goes into ``rare``.

        Args:
            sentences: Raw or cleaned Japanese sentences.

        Returns:
            Number of kanji that were not previously recorded.
        """
        count = 0
        for sentence in sentences:
            for kanji in re.findall(r'[\u4E00-\u9FFF]', sentence):
                if kanji in self._static:
                    if kanji not in self._common:
                        self._common.add(kanji)
                        count += 1
                else:
                    if kanji not in self._rare:
                        self._rare.add(kanji)
                        count += 1
        return count

    def save(self) -> None:
        """Write the dynamic database to disk."""
        self._dynamic_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._dynamic_path, "w", encoding="utf-8") as f:
            json.dump(
                {"common": sorted(self._common), "rare": sorted(self._rare)},
                f,
                ensure_ascii=False,
                indent=2,
            )

    def reset(self) -> None:
        """Delete the dynamic file and clear the in-memory sets."""
        if self._dynamic_path.exists():
            self._dynamic_path.unlink()
        self._common = set()
        self._rare   = set()

    # ------------------------------------------------------------------
    # Queries / statistics
    # ------------------------------------------------------------------

    def stats(self, sort_by: str = "grade") -> dict[str, Any]:
        """Return a rich statistics dict about kanji knowledge.

        The returned dict has the shape::

            {
                "sort_by": "grade",
                "sorted_kanji": [
                    {"kanji": "一", "rtk_order": 1, "joyo_order": 1},
                    ...
                ],
                "known_list": [True, False, ...],
                "joyo":          {"total": 2136, "known": 120},
                "rtk1":          {"total": 2200, "known": 118},
                "rtk3":          {"total":  800, "known":  42},
                "rare":          {"total":   15, "kanji": ["亜", ...]},
                "by_joyo_grade": {1: {"total": 80, "known": 60}, ...}
            }

        Args:
            sort_by: ``"grade"`` (Joyo grade first, then RTK) or ``"RTK"``.

        Returns:
            Statistics dictionary described above.

        Raises:
            ValueError: If ``sort_by`` is not ``"grade"`` or ``"RTK"``.
        """
        if sort_by not in ("grade", "RTK"):
            raise ValueError("sort_by must be 'grade' or 'RTK'.")

        if sort_by == "grade":
            key_fn = lambda item: (
                item[1].get("Joyo_order", 9999),
                item[1].get("RTK_order",  9999),
            )
        else:
            key_fn = lambda item: item[1].get("RTK_order", 9999)

        sorted_entries = sorted(self._static.items(), key=key_fn)

        sorted_kanji: list[dict[str, Any]] = []
        known_list:   list[bool]           = []

        joyo_total = joyo_known = 0
        rtk1_total = rtk1_known = 0
        rtk3_total = rtk3_known = 0
        by_grade: dict[int, dict[str, int]] = {}

        RTK1_MAX = 2200
        RTK3_MAX = 3000

        for kanji, data in sorted_entries:
            joyo  = data.get("Joyo_order")
            rtk   = data.get("RTK_order")
            known = kanji in self._common

            sorted_kanji.append({
                "kanji":      kanji,
                "rtk_order":  rtk,
                "joyo_order": joyo,
            })
            known_list.append(known)

            if joyo < 50: # Joyo kanji have order <= 7
                joyo_total += 1
                if known:
                    joyo_known += 1

            if rtk is not None:
                if rtk <= RTK1_MAX:
                    rtk1_total += 1
                    if known:
                        rtk1_known += 1
                elif rtk <= RTK3_MAX:
                    rtk3_total += 1
                    if known:
                        rtk3_known += 1

            if joyo is not None and 1 <= joyo <= 7:
                grade_stats = by_grade.setdefault(joyo, {"total": 0, "known": 0})
                grade_stats["total"] += 1
                if known:
                    grade_stats["known"] += 1

        return {
            "sort_by":       sort_by,
            "sorted_kanji":  sorted_kanji,
            "known_list":    known_list,
            "joyo":          {"total": joyo_total, "known": joyo_known},
            "rtk1":          {"total": rtk1_total, "known": rtk1_known},
            "rtk3":          {"total": rtk3_total, "known": rtk3_known},
            "rare":          {"total": len(self._rare), "kanji": sorted(self._rare)},
            "by_joyo_grade": dict(sorted(by_grade.items())),
        }