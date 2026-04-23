"""
jp_tokenizer.py
---------------
Extract and normalise Japanese content words from raw sentences.

Each word is represented as a ``WordPair`` named-tuple carrying both the
surface-level base form (``orth_base``) and the canonical dictionary form
(``lemma``).  Downstream code can choose which representation to use for
storage or display.

Typical usage::

    from jp_tokenizer import clean, tokenize, WordPair

    sentences  = clean(raw_sentences, ignore_brackets=True)
    word_lists = tokenize(sentences)           # list[list[WordPair]]
    flat_pairs = tokenize(sentences, flatten=True)  # list[WordPair]
"""

import re
from typing import NamedTuple

import fugashi

# ---------------------------------------------------------------------------
# Public data type
# ---------------------------------------------------------------------------

class WordPair(NamedTuple):
    """A single token's two most useful base forms.

    Attributes:
        orth_base: ``orthBase`` feature — the word as it would be written in
                   its base (dictionary-entry) spelling, preserving kanji /
                   kana choice from the original text.
        lemma:     ``lemma`` feature — the canonical lemma used by UniDic,
                   which normalises spelling variants to a single form.
    """
    orth_base: str
    lemma: str


# ---------------------------------------------------------------------------
# POS filtering constants
# ---------------------------------------------------------------------------

_KEEP_POS: set[str] = {
    "動詞",    # verbs
    "形容詞",  # i-adjectives
    "形状詞",  # na-adjectives / adjectival nouns
    "名詞",    # nouns  (further filtered below)
    "副詞",    # adverbs
    "感動詞",  # interjections / onomatopoeia
}

_EXCLUDE_NOUN_SUBTYPES: set[str] = {
    "固有名詞",  # proper nouns – names, places, titles
    "数詞",      # numerals
}

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def clean(sentences: list[str], ignore_brackets: bool = True) -> list[str]:
    """Strip non-Japanese characters from each sentence.

    Args:
        sentences:        Raw sentences to clean.
        ignore_brackets:  When ``True``, content inside ``()``, ``[]``,
                          ``{}``, and ``<>`` is removed before stripping.

    Returns:
        A new list of cleaned sentences (same length, same order).
    """
    results: list[str] = []
    for text in sentences:
        if ignore_brackets:
            text = re.sub(r'\([^)]*\)',   '', text)  # half-width ()
            text = re.sub(r'（[^）]*）',   '', text)  # full-width （）
            text = re.sub(r'\[[^\]]*\]',  '', text)  # half-width []
            text = re.sub(r'［[^］]*］',   '', text)  # full-width ［］
            text = re.sub(r'\{[^}]*\}',   '', text)  # half-width {}
            text = re.sub(r'｛[^｝]*｝',   '', text)  # full-width ｛｝
            text = re.sub(r'<[^>]*>',     '', text)  # half-width <>
            text = re.sub(r'＜[^＞]*＞',   '', text)  # full-width ＜＞
            #text = re.sub(r'【[^】]*】',   '', text)  # lenticular brackets 【】
            text = re.sub(r'〔[^〕]*〕',   '', text)  # tortoise-shell brackets 〔〕
            text = re.sub(r'〈[^〉]*〉',   '', text)  # angle brackets 〈〉
            text = re.sub(r'《[^》]*》',   '', text)  # double angle brackets 《》
            #text = re.sub(r'「[^」]*」',   '', text)  # corner brackets 「」
            #text = re.sub(r'『[^』]*』',   '', text)  # white corner brackets 『』

        # Remove all whitespace
        text = re.sub(r'[\s\u3000\u2000-\u200B\u00A0]+', '', text)

        # Keep hiragana, katakana, kanji, prolonged-sound mark
        text = re.sub(
            r'[^\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFFー\u3000]',
            ' ',
            text,
        )
        results.append(text.strip())
    return results


def tokenize(
    sentences: list[str],
    flatten: bool = False,
) -> list[list[WordPair]] | list[WordPair]:
    """Return content-word pairs (orth_base, lemma) from Japanese sentences.

    Particles, conjunctions, auxiliary verbs, proper nouns, and numerals
    are filtered out so the result is suitable for vocabulary study.

    A :class:`WordPair` is emitted only when **both** ``orthBase`` and
    ``lemma`` are available and non-empty; tokens missing either feature
    are silently skipped.

    Args:
        sentences: Pre-cleaned Japanese sentences.
        flatten:   When ``True``, return a single flat list instead of a
                   list-of-lists.

    Returns:
        ``list[list[WordPair]]`` grouped by sentence, or ``list[WordPair]``
        when *flatten* is ``True``.
    """
    tagger = fugashi.Tagger()
    results: list[list[WordPair]] = []

    for sentence in sentences:
        pairs: list[WordPair] = []
        for word in tagger(sentence):
            pos1      = word.feature.pos1
            pos2      = word.feature.pos2
            orth_base = word.feature.orthBase
            lemma     = word.feature.lemma

            if pos1 not in _KEEP_POS:
                continue

            if pos1 == "名詞" and pos2 in _EXCLUDE_NOUN_SUBTYPES:
                continue

            # Require both features to be present and meaningful
            if (
                orth_base and orth_base != "*"
                and lemma    and lemma    != "*"
            ):
                pairs.append(WordPair(orth_base=orth_base, lemma=lemma))

        results.append(pairs)

    if flatten:
        return [p for pair_list in results for p in pair_list]
    return results


def tokenize_sentence(sentence: str) -> list[WordPair]:
    """Convenience wrapper: tokenize a single sentence into a flat pair list.

    Args:
        sentence: A single (pre-cleaned) Japanese sentence.

    Returns:
        List of :class:`WordPair` objects for each content word found.
    """
    result = tokenize([sentence], flatten=True)
    return result  # type: ignore[return-value]