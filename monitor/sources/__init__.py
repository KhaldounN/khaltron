"""Readers: each turns one kind of background work (files on disk, processes) into Job rows. They only read."""


def pretty_book(name: str | None) -> str:
    """'war_and_peace.txt' -> 'War and peace'."""
    if not name:
        return "a book"
    stem = name.rsplit(".", 1)[0] if name.endswith(".txt") else name
    words = stem.replace("_", " ").strip()
    return words[:1].upper() + words[1:]
