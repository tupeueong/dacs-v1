import re

WORD_RE = re.compile(r"[0-9A-Za-zÀ-ỹĐđ]+", re.UNICODE)

def vi_legal_tokenize(text: str) -> list[str]:
    words = [token.casefold() for token in WORD_RE.findall(text)]
    bigrams = [f"{left}_{right}" for left, right in zip(words, words[1:])]
    return words + bigrams
