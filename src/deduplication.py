"""
Deduplication and clustering module for News Summarizer Agent.
Identifies duplicate URLs and near-duplicate titles in plain Python.
"""

import re
from typing import List, Dict, Any, Set


def normalize_title(title: str) -> Set[str]:
    """Tokenize and normalize a news title into meaningful lowercase words."""
    cleaned = re.sub(r"[^\w\s]", "", title.lower())
    stop_words = {
        "a", "an", "the", "in", "on", "at", "by", "for", "with", "about",
        "against", "between", "into", "through", "during", "before", "after",
        "above", "below", "to", "from", "up", "down", "is", "are", "was",
        "were", "be", "been", "being", "have", "has", "had", "and", "or"
    }
    tokens = {word for word in cleaned.split() if word and word not in stop_words}
    return tokens


def calculate_jaccard_similarity(tokens1: Set[str], tokens2: Set[str]) -> float:
    """Calculate Jaccard token similarity between two sets."""
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    return len(intersection) / len(union)


def deduplicate_stories(
    stories: List[Dict[str, Any]],
    similarity_threshold: float = 0.55
) -> List[Dict[str, Any]]:
    """
    Deduplicate stories based on URL equality and title token similarity.
    Keeps the highest quality / longest text entry when clustering.
    """
    unique_by_url: List[Dict[str, Any]] = []
    seen_urls: Set[str] = set()

    for story in stories:
        url = story.get("url", "").strip()
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_by_url.append(story)

    # Cluster by title similarity
    clustered_stories: List[Dict[str, Any]] = []
    token_cache = [normalize_title(s.get("title", "")) for s in unique_by_url]

    merged_indices: Set[int] = set()

    for i, story in enumerate(unique_by_url):
        if i in merged_indices:
            continue

        best_story = story
        tokens_i = token_cache[i]

        for j in range(i + 1, len(unique_by_url)):
            if j in merged_indices:
                continue

            tokens_j = token_cache[j]
            similarity = calculate_jaccard_similarity(tokens_i, tokens_j)

            if similarity >= similarity_threshold:
                merged_indices.add(j)
                # Keep the candidate with longer extracted text / summary
                text_len_best = len(best_story.get("summary", "") or best_story.get("text", ""))
                text_len_other = len(unique_by_url[j].get("summary", "") or unique_by_url[j].get("text", ""))
                if text_len_other > text_len_best:
                    best_story = unique_by_url[j]

        clustered_stories.append(best_story)

    return clustered_stories

