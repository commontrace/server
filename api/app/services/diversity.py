"""Search result diversity service (Principle 13 — Anti-Monoculture).

MMR-inspired diversity: ensures search results don't all converge on
the same solution approach. If a candidate is too similar (cosine > 0.85)
to any already-selected result AND a dissimilar alternative exists lower
in the ranking, swaps them.

Uses pure Python cosine similarity — only runs on <= 50 results so
numpy is unnecessary.
"""

import math
import uuid
from typing import Optional


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors in pure Python."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def apply_diversity_sampling(
    results: list,
    embedding_lookup: dict[uuid.UUID, list[float]],
    similarity_threshold: float = 0.85,
) -> list:
    """Apply MMR-inspired diversity re-ranking to search results.

    Always keeps result[0] (best match). For each subsequent slot,
    if the candidate is too similar to any selected result AND a
    dissimilar alternative exists later in the ranking, swaps them.

    Args:
        results: Ranked search results (TraceSearchResult objects with .id)
        embedding_lookup: dict mapping trace UUID to embedding vector
        similarity_threshold: Maximum cosine similarity before considering swap

    Returns:
        Re-ordered results list with improved diversity
    """
    if len(results) < 3 or not embedding_lookup:
        return results

    selected: list = [results[0]]
    remaining = list(results[1:])

    while remaining and len(selected) < len(results):
        best_idx = 0
        best_candidate = remaining[0]

        # Check if best candidate is too similar to any selected result
        candidate_emb = embedding_lookup.get(best_candidate.id)
        if candidate_emb is not None:
            too_similar = False
            for sel in selected:
                sel_emb = embedding_lookup.get(sel.id)
                if sel_emb is not None:
                    sim = _cosine_similarity(candidate_emb, sel_emb)
                    if sim > similarity_threshold:
                        too_similar = True
                        break

            if too_similar:
                # Find first dissimilar alternative in remaining
                for alt_idx in range(1, len(remaining)):
                    alt = remaining[alt_idx]
                    alt_emb = embedding_lookup.get(alt.id)
                    if alt_emb is None:
                        continue

                    alt_too_similar = False
                    for sel in selected:
                        sel_emb = embedding_lookup.get(sel.id)
                        if sel_emb is not None:
                            sim = _cosine_similarity(alt_emb, sel_emb)
                            if sim > similarity_threshold:
                                alt_too_similar = True
                                break

                    if not alt_too_similar:
                        best_idx = alt_idx
                        break

        selected.append(remaining.pop(best_idx))

    return selected
