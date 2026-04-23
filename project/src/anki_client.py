"""
anki_client.py
--------------
Thin wrapper around the AnkiConnect HTTP API.

Typical usage::

    from anki_client import fetch_sentences
    sentences = fetch_sentences(config)
"""

from typing import Any

import requests


# ---------------------------------------------------------------------------
# Low-level transport
# ---------------------------------------------------------------------------

BATCH_SIZE = 500


def _request(connect_url: str, action: str, **params: Any) -> Any:
    """Send one AnkiConnect request and return its ``result`` field.

    Args:
        connect_url: AnkiConnect base URL (e.g. ``http://localhost:8765``).
        action:      AnkiConnect action name.
        **params:    Action-specific parameters.

    Returns:
        The ``result`` value from AnkiConnect's JSON response.

    Raises:
        requests.HTTPError: On non-2xx HTTP status.
        RuntimeError:       If AnkiConnect returns an error string.
    """
    payload = {"action": action, "version": 6, "params": params}
    resp = requests.post(connect_url, json=payload, timeout=120)
    resp.raise_for_status()
    body = resp.json()
    if body.get("error"):
        raise RuntimeError(f"AnkiConnect error [{action}]: {body['error']}")
    return body["result"]


def _fetch_cards_info_batch(connect_url: str, batch: list[int]) -> list[dict]:
    """Fetch cardsInfo for a single batch of card IDs."""
    return _request(connect_url, "cardsInfo", cards=batch)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_sentences(config: dict[str, Any]) -> list[tuple[str, int]]:
    url = config["anki"]["connect_url"]
    result: list[tuple[str, int]] = []
    last = config["anki"].get("last_retrieved", "")

    for entry in config["anki"]["decks_fields"]:
        deck = entry["deck"]
        searched_fields = entry["fields"]

        all_ids = _request(url, "findCards", query=f'deck:"{deck}"')
        filtered_ids = [i for i in all_ids if last == "" or str(i) > last]
        if not filtered_ids:
            continue

        # Fetch cardsInfo in parallel batches
        batches = [
            filtered_ids[i : i + BATCH_SIZE]
            for i in range(0, len(filtered_ids), BATCH_SIZE)
        ]

        all_cards: list[dict] = []
        for batch in batches:
            all_cards.extend(_fetch_cards_info_batch(url, batch))
        print(len(all_cards))

        # Extract sentences
        for card in all_cards:
            card_fields = card.get("fields", {})
            card_id = card["cardId"]

            for field in searched_fields:
                field_data = card_fields.get(field)
                if not field_data:
                    continue
                result.append((field_data["value"], card_id))

    return result