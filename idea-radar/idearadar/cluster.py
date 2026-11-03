import re

STOP = set("""a an the and or but of to in on for with is are was were be been it this that i you we they my our your
der die das und oder aber von zu in auf für mit ist sind war waren ein eine einen ich du wir sie mein unser dein nicht
auch wie wenn dass es im am bei""".split())


def tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zäöüß0-9]{3,}", text.lower()) if w not in STOP}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cluster(items: list[tuple[int, str]], threshold: float = 0.35) -> list[list[int]]:
    """Greedy single-pass clustering on token overlap; deterministic and dependency-free.
    Swap in embeddings later without changing the interface."""
    clusters: list[tuple[set[str], list[int]]] = []
    for item_id, text in items:
        toks = tokens(text)
        best, best_sim = None, 0.0
        for c in clusters:
            sim = jaccard(toks, c[0])
            if sim > best_sim:
                best, best_sim = c, sim
        if best is not None and best_sim >= threshold:
            best[1].append(item_id)
            best[0].update(toks)
        else:
            clusters.append((set(toks), [item_id]))
    return [c[1] for c in clusters]
