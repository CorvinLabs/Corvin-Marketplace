"""
NLP Toolkit plugin - Natural Language Processing utilities.

Provides text analysis, named entity recognition, sentiment analysis,
and semantic similarity for session memory enhancement.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple


logger = logging.getLogger(__name__)


class NLPToolkit:
    """Natural Language Processing utilities plugin."""

    def __init__(self):
        """Initialize the NLP Toolkit plugin."""
        self.enabled = True
        self.spacy_model = "en_core_web_sm"
        self.similarity_threshold = 0.7
        self.text_cache = {}

    async def initialize(self, context: Optional[Dict[str, Any]] = None):
        """Initialize plugin with NLP configuration."""
        if context:
            self.spacy_model = context.get("spacy_model", "en_core_web_sm")
            self.similarity_threshold = context.get("similarity_threshold", 0.7)

        logger.info(
            "NLPToolkit initialized with spacy_model=%s, threshold=%.2f",
            self.spacy_model,
            self.similarity_threshold,
        )

    async def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """
        Analyze sentiment of text.

        Args:
            text: Text to analyze

        Returns:
            Dict with sentiment label and scores
        """
        if not text:
            raise ValueError("text cannot be empty")

        # Simple heuristic-based sentiment (demo)
        text_lower = text.lower()
        positive_words = ["good", "great", "excellent", "amazing", "love"]
        negative_words = ["bad", "terrible", "awful", "hate", "poor"]

        pos_count = sum(1 for w in positive_words if w in text_lower)
        neg_count = sum(1 for w in negative_words if w in text_lower)

        if pos_count > neg_count:
            sentiment = "positive"
            score = min(0.5 + (pos_count * 0.1), 1.0)
        elif neg_count > pos_count:
            sentiment = "negative"
            score = max(-0.5 - (neg_count * 0.1), -1.0)
        else:
            sentiment = "neutral"
            score = 0.0

        return {
            "text": text,
            "sentiment": sentiment,
            "score": score,
            "confidence": 0.85 if (pos_count + neg_count) > 0 else 0.5,
        }

    async def extract_entities(self, text: str) -> Dict[str, Any]:
        """
        Extract named entities from text.

        Args:
            text: Text to analyze

        Returns:
            Dict with entities grouped by type
        """
        if not text:
            raise ValueError("text cannot be empty")

        # Simple pattern-based entity extraction (demo)
        entities = {
            "PERSON": [],
            "LOCATION": [],
            "ORGANIZATION": [],
            "DATE": [],
            "QUANTITY": [],
        }

        # Mock entity detection
        words = text.split()
        if len(words) >= 2:
            # First capitalized word -> PERSON
            for word in words:
                if word and word[0].isupper():
                    entities["PERSON"].append(word)
                    break

        return {
            "text": text,
            "entities": entities,
            "entity_count": sum(len(v) for v in entities.values()),
        }

    async def summarize_text(self, text: str, num_sentences: int = 3) -> Dict[str, Any]:
        """
        Summarize text to a few key sentences.

        Args:
            text: Text to summarize
            num_sentences: Number of sentences in summary

        Returns:
            Dict with summary and key points
        """
        if not text:
            raise ValueError("text cannot be empty")

        # Simple sentence-based summary (demo)
        sentences = text.split(".")
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) <= num_sentences:
            summary = text
        else:
            # Take first and last sentences (naive summarization)
            summary_sents = (
                [sentences[0]]
                + sentences[1 : num_sentences - 1]
                + [sentences[-1]]
            )
            summary = ". ".join(summary_sents) + "."

        return {
            "original_text": text,
            "summary": summary,
            "compression_ratio": len(summary) / len(text) if text else 0,
            "key_points": sentences[:num_sentences],
        }

    async def compute_similarity(self, text1: str, text2: str) -> Dict[str, Any]:
        """
        Compute semantic similarity between two texts.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Dict with similarity score and match status
        """
        if not text1 or not text2:
            raise ValueError("Both texts are required")

        # Simple word overlap similarity (demo)
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            similarity = 0.0
        else:
            overlap = len(words1 & words2)
            union = len(words1 | words2)
            similarity = overlap / union if union > 0 else 0.0

        return {
            "text1": text1,
            "text2": text2,
            "similarity": similarity,
            "is_similar": similarity >= self.similarity_threshold,
            "threshold": self.similarity_threshold,
        }

    async def execute(self, *args, **kwargs) -> Dict[str, Any]:
        """
        Execute NLP task.

        Supported kwargs:
        - analyze_sentiment: if True, analyze sentiment
        - extract_entities: if True, extract entities
        - summarize: if True, summarize text
        - compute_similarity: if True, compute similarity
        - text: input text (required)
        - text1, text2: for similarity
        - num_sentences: for summarization
        """
        text = kwargs.get("text")

        if kwargs.get("analyze_sentiment"):
            if not text:
                raise ValueError("text is required for sentiment analysis")
            return await self.analyze_sentiment(text)
        elif kwargs.get("extract_entities"):
            if not text:
                raise ValueError("text is required for entity extraction")
            return await self.extract_entities(text)
        elif kwargs.get("summarize"):
            if not text:
                raise ValueError("text is required for summarization")
            num_sentences = kwargs.get("num_sentences", 3)
            return await self.summarize_text(text, num_sentences)
        elif kwargs.get("compute_similarity"):
            text1 = kwargs.get("text1")
            text2 = kwargs.get("text2")
            if not text1 or not text2:
                raise ValueError("text1 and text2 are required for similarity")
            return await self.compute_similarity(text1, text2)
        else:
            # Default: sentiment analysis
            if not text:
                raise ValueError("text is required")
            return await self.analyze_sentiment(text)

    async def shutdown(self):
        """Shutdown the plugin gracefully."""
        self.text_cache.clear()
        logger.info("NLPToolkit shutdown complete")
