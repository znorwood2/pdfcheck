"""Dependency-free guess at a document's main language from function words."""
from __future__ import annotations

import re

# Short, very frequent words that rarely appear in the other listed languages.
_FUNCTION_WORDS = {
    "en": "the and of to is in that it for with as are this was be by on not or have from which an".split(),
    "es": "el la los las de que y en un una por con para es del se al lo como más pero sus".split(),
    "fr": "le la les de des et est que une un pour dans qui pas sur au aux ce sont avec du".split(),
    "de": "der die das und ist nicht ein eine zu den von mit sich des auf für im dem auch".split(),
    "it": "il di che la per non una sono del della gli le con da si nel alla anche questo".split(),
    "pt": "o a os as de que e do da em um uma para com não por se mais ao dos das".split(),
    "nl": "de het een van en is dat op te zijn voor met niet aan er maar ook als bij".split(),
}

_BCP47 = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8})*$")

MIN_HITS = 20


def is_valid_language_tag(tag: str) -> bool:
    """Shape check only: a 2-3 letter primary subtag and well-formed subtags."""
    return bool(_BCP47.match(tag.strip()))


def primary_subtag(tag: str) -> str:
    return tag.strip().split("-")[0].lower()


def detect_language(text: str) -> str | None:
    """Return a supported language code when the evidence is clear, else None."""
    words = re.findall(r"[^\W\d_]+", text.lower())
    scores = {code: sum(1 for w in words if w in set(vocab)) for code, vocab in _FUNCTION_WORDS.items()}
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    (best, best_hits), (_, second_hits) = ranked[0], ranked[1]
    if best_hits < MIN_HITS or best_hits < 2 * second_hits:
        return None
    return best
