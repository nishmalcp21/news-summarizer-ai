"""
Story Follow-Up Q&A Engine (PRD Section 13).
Allows users to ask follow-up questions about specific stories or the overall digest.
Grounds answers strictly in fetched article text to prevent hallucination.
"""

from typing import List, Dict, Any, Optional
import re
from src.config import config
from src.logger import logger


class StoryQAEngine:
    """Answers follow-up questions grounded strictly in extracted article text."""

    def __init__(self, llm_client=None):
        self.llm = llm_client

    def answer_question(
        self,
        question: str,
        articles: List[Dict[str, Any]],
        story_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Answers a question using provided articles.
        Returns:
            {"answer": str, "cited_sources": List[str], "confidence": str}
        """
        clean_q = question.strip()
        if not clean_q:
            return {"answer": "Please provide a valid question.", "cited_sources": [], "confidence": "none"}

        # Filter to target story if specified
        target_articles = articles
        if story_id:
            target_articles = [a for a in articles if a.get("story_id") == story_id]
            if not target_articles:
                target_articles = articles

        # Build context from article data
        context_chunks: List[str] = []
        sources: List[str] = []

        for a in target_articles:
            url = a.get("url", "")
            title = a.get("title", "")
            text = a.get("text", "") or a.get("snippet", "")
            sources.append(url)
            context_chunks.append(f"Title: {title}\nURL: {url}\nContent: {text[:2500]}")

        combined_context = "\n---\n".join(context_chunks)

        # Keyword matching / mock fallback if no live LLM
        if not self.llm or not hasattr(self.llm, "_call_completion"):
            return self._heuristic_answer(clean_q, target_articles)

        # Live LLM prompt
        prompt = (
            f"You are a strict, factual Q&A assistant answering questions about news articles.\n"
            f"CRITICAL RULE: Answer the question using ONLY the provided article context. "
            f"If the answer cannot be found in the context, explicitly state: 'The provided news sources do not contain this information.' "
            f"Never speculate or hallucinate outside the text.\n\n"
            f"Context:\n{combined_context}\n\n"
            f"Question: {clean_q}\n\n"
            f"Answer:"
        )

        try:
            messages = [
                {"role": "system", "content": "You are a factual, grounded news assistant."},
                {"role": "user", "content": prompt}
            ]
            ans = self.llm._call_completion(messages, temperature=0.1)
            return {
                "answer": ans.strip(),
                "cited_sources": [s for s in sources if s],
                "confidence": "high"
            }
        except Exception as e:
            logger.log_error(0, "qa_engine", f"Q&A LLM invocation failed: {e}")
            return self._heuristic_answer(clean_q, target_articles)

    def _heuristic_answer(self, question: str, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Grounded plain Python heuristic search over article text for mock/offline mode."""
        q_words = {w.lower() for w in re.findall(r"\w+", question) if len(w) > 3}
        if not q_words:
            return {
                "answer": "The provided news sources do not contain specific information regarding this question.",
                "cited_sources": [],
                "confidence": "low"
            }

        best_sentence = ""
        best_source = ""
        best_score = 0

        asking_person = any(w in question.lower() for w in ["who", "ceo", "leader", "founder", "author"])

        for a in articles:
            text = a.get("text", "") or a.get("snippet", "")
            sentences = re.split(r"(?<=[.!?]) +", text)
            for s in sentences:
                s_words = {w.lower() for w in re.findall(r"\w+", s)}
                overlap = len(q_words.intersection(s_words))
                if overlap > best_score:
                    if asking_person and overlap < 2:
                        continue
                    best_score = overlap
                    best_sentence = s.strip()
                    best_source = a.get("source") or a.get("url", "")

        min_required_overlap = 2 if len(q_words) >= 3 else 1
        if best_score >= min_required_overlap and len(best_sentence) > 15:
            return {
                "answer": f"According to {best_source}: \"{best_sentence}\"",
                "cited_sources": [best_source] if best_source else [],
                "confidence": "grounded"
            }
        else:
            return {
                "answer": "The provided news sources do not contain specific information regarding this question.",
                "cited_sources": [],
                "confidence": "low"
            }
