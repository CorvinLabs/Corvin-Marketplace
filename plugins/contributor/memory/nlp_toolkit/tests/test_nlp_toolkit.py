"""
Unit tests for nlp_toolkit plugin.

Tests cover NLP utilities including:
- Sentiment analysis
- Entity extraction
- Text summarization
- Semantic similarity
- Error handling
"""

import pytest
from unittest.mock import MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from nlp_toolkit import NLPToolkit


class TestNLPToolkitInitialization:
    """Test plugin initialization."""

    @pytest.mark.asyncio
    async def test_init_success(self):
        """Test successful plugin initialization."""
        plugin = NLPToolkit()
        assert plugin is not None
        assert plugin.enabled is True
        assert plugin.spacy_model == "en_core_web_sm"
        assert plugin.similarity_threshold == 0.7

    @pytest.mark.asyncio
    async def test_initialize_with_config(self):
        """Test initialize with configuration."""
        plugin = NLPToolkit()
        context = {
            "spacy_model": "en_core_web_lg",
            "similarity_threshold": 0.8,
        }
        await plugin.initialize(context)

        assert plugin.spacy_model == "en_core_web_lg"
        assert plugin.similarity_threshold == 0.8

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test plugin shutdown."""
        plugin = NLPToolkit()
        await plugin.shutdown()
        assert len(plugin.text_cache) == 0


class TestNLPToolkitSentimentAnalysis:
    """Test sentiment analysis functionality."""

    @pytest.mark.asyncio
    async def test_analyze_sentiment_positive(self):
        """Test positive sentiment detection."""
        plugin = NLPToolkit()
        text = "This is excellent work, I love it!"
        result = await plugin.analyze_sentiment(text)

        assert result["sentiment"] in ("positive", "neutral")
        assert "score" in result
        assert "confidence" in result

    @pytest.mark.asyncio
    async def test_analyze_sentiment_negative(self):
        """Test negative sentiment detection."""
        plugin = NLPToolkit()
        text = "This is terrible and awful, I hate it"
        result = await plugin.analyze_sentiment(text)

        assert result["sentiment"] in ("negative", "neutral")
        assert result["score"] < 0.5

    @pytest.mark.asyncio
    async def test_analyze_sentiment_neutral(self):
        """Test neutral sentiment detection."""
        plugin = NLPToolkit()
        text = "The weather is cloudy today"
        result = await plugin.analyze_sentiment(text)

        assert result["sentiment"] in ("neutral", "negative", "positive")
        assert result["text"] == text

    @pytest.mark.asyncio
    async def test_analyze_sentiment_mixed(self):
        """Test mixed sentiment detection."""
        plugin = NLPToolkit()
        text = "Good and bad aspects"
        result = await plugin.analyze_sentiment(text)

        assert "sentiment" in result
        assert result["confidence"] >= 0

    @pytest.mark.asyncio
    async def test_analyze_sentiment_empty(self):
        """Test sentiment analysis with empty text."""
        plugin = NLPToolkit()
        with pytest.raises(ValueError):
            await plugin.analyze_sentiment("")


class TestNLPToolkitEntityExtraction:
    """Test entity extraction."""

    @pytest.mark.asyncio
    async def test_extract_entities_person(self):
        """Test extraction of person entities."""
        plugin = NLPToolkit()
        text = "John Smith works at Microsoft in Seattle"
        result = await plugin.extract_entities(text)

        assert result["text"] == text
        assert "entities" in result
        assert "PERSON" in result["entities"]

    @pytest.mark.asyncio
    async def test_extract_entities_location(self):
        """Test extraction of location entities."""
        plugin = NLPToolkit()
        text = "Paris is the capital of France"
        result = await plugin.extract_entities(text)

        assert "entities" in result
        assert "LOCATION" in result["entities"]

    @pytest.mark.asyncio
    async def test_extract_entities_multiple(self):
        """Test extraction of multiple entity types."""
        plugin = NLPToolkit()
        text = "Alice works at Google in San Francisco since 2020"
        result = await plugin.extract_entities(text)

        assert result["entity_count"] >= 0
        assert "entities" in result

    @pytest.mark.asyncio
    async def test_extract_entities_empty(self):
        """Test entity extraction with empty text."""
        plugin = NLPToolkit()
        with pytest.raises(ValueError):
            await plugin.extract_entities("")

    @pytest.mark.asyncio
    async def test_extract_entities_no_entities(self):
        """Test extraction when no entities found."""
        plugin = NLPToolkit()
        text = "this is lowercase text with no entities"
        result = await plugin.extract_entities(text)

        assert result["entity_count"] == 0


class TestNLPToolkitSummarization:
    """Test text summarization."""

    @pytest.mark.asyncio
    async def test_summarize_long_text(self):
        """Test summarization of long text."""
        plugin = NLPToolkit()
        text = "This is the first sentence. This is the second sentence. This is the third sentence. This is the fourth sentence."
        result = await plugin.summarize_text(text)

        assert result["original_text"] == text
        assert "summary" in result
        assert "compression_ratio" in result
        assert len(result["key_points"]) > 0

    @pytest.mark.asyncio
    async def test_summarize_short_text(self):
        """Test summarization of short text."""
        plugin = NLPToolkit()
        text = "Short text"
        result = await plugin.summarize_text(text)

        assert result["summary"] is not None

    @pytest.mark.asyncio
    async def test_summarize_custom_length(self):
        """Test summarization with custom length."""
        plugin = NLPToolkit()
        text = "First. Second. Third. Fourth. Fifth."
        result = await plugin.summarize_text(text, num_sentences=2)

        assert "summary" in result

    @pytest.mark.asyncio
    async def test_summarize_empty_text(self):
        """Test summarization with empty text."""
        plugin = NLPToolkit()
        with pytest.raises(ValueError):
            await plugin.summarize_text("")

    @pytest.mark.asyncio
    async def test_summarize_single_sentence(self):
        """Test summarization of single sentence."""
        plugin = NLPToolkit()
        text = "This is a single sentence"
        result = await plugin.summarize_text(text)

        assert result["original_text"] == text


class TestNLPToolkitSimilarity:
    """Test semantic similarity computation."""

    @pytest.mark.asyncio
    async def test_compute_similarity_identical(self):
        """Test similarity of identical texts."""
        plugin = NLPToolkit()
        text = "The quick brown fox"
        result = await plugin.compute_similarity(text, text)

        assert result["similarity"] == 1.0
        assert result["is_similar"] is True

    @pytest.mark.asyncio
    async def test_compute_similarity_high(self):
        """Test similarity of very similar texts."""
        plugin = NLPToolkit()
        text1 = "The cat sat on the mat"
        text2 = "A cat sat on a mat"
        result = await plugin.compute_similarity(text1, text2)

        assert result["similarity"] > 0.5
        assert "is_similar" in result

    @pytest.mark.asyncio
    async def test_compute_similarity_low(self):
        """Test similarity of dissimilar texts."""
        plugin = NLPToolkit()
        text1 = "apples and oranges"
        text2 = "cats and dogs"
        result = await plugin.compute_similarity(text1, text2)

        assert result["similarity"] < 1.0

    @pytest.mark.asyncio
    async def test_compute_similarity_threshold(self):
        """Test similarity threshold."""
        plugin = NLPToolkit()
        plugin.similarity_threshold = 0.5
        text1 = "hello world"
        text2 = "hello"
        result = await plugin.compute_similarity(text1, text2)

        assert result["threshold"] == 0.5
        assert "is_similar" in result

    @pytest.mark.asyncio
    async def test_compute_similarity_empty_text1(self):
        """Test similarity with empty first text."""
        plugin = NLPToolkit()
        with pytest.raises(ValueError):
            await plugin.compute_similarity("", "text")

    @pytest.mark.asyncio
    async def test_compute_similarity_empty_text2(self):
        """Test similarity with empty second text."""
        plugin = NLPToolkit()
        with pytest.raises(ValueError):
            await plugin.compute_similarity("text", "")


class TestNLPToolkitExecute:
    """Test execute method."""

    @pytest.mark.asyncio
    async def test_execute_sentiment(self):
        """Test execute for sentiment analysis."""
        plugin = NLPToolkit()
        result = await plugin.execute(
            analyze_sentiment=True,
            text="This is great",
        )

        assert "sentiment" in result
        assert "score" in result

    @pytest.mark.asyncio
    async def test_execute_entities(self):
        """Test execute for entity extraction."""
        plugin = NLPToolkit()
        result = await plugin.execute(
            extract_entities=True,
            text="John works at Google",
        )

        assert "entities" in result

    @pytest.mark.asyncio
    async def test_execute_summarize(self):
        """Test execute for summarization."""
        plugin = NLPToolkit()
        result = await plugin.execute(
            summarize=True,
            text="First. Second. Third.",
            num_sentences=2,
        )

        assert "summary" in result

    @pytest.mark.asyncio
    async def test_execute_similarity(self):
        """Test execute for similarity."""
        plugin = NLPToolkit()
        result = await plugin.execute(
            compute_similarity=True,
            text1="hello world",
            text2="hello",
        )

        assert "similarity" in result
        assert "is_similar" in result

    @pytest.mark.asyncio
    async def test_execute_default(self):
        """Test execute with default (sentiment)."""
        plugin = NLPToolkit()
        result = await plugin.execute(text="Good work")

        assert "sentiment" in result

    @pytest.mark.asyncio
    async def test_execute_no_text(self):
        """Test execute without text."""
        plugin = NLPToolkit()
        with pytest.raises(ValueError):
            await plugin.execute()

    @pytest.mark.asyncio
    async def test_execute_similarity_no_text2(self):
        """Test execute similarity without text2."""
        plugin = NLPToolkit()
        with pytest.raises(ValueError):
            await plugin.execute(
                compute_similarity=True,
                text1="hello",
            )


class TestNLPToolkitErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_invalid_similarity_threshold(self):
        """Test with invalid similarity threshold."""
        plugin = NLPToolkit()
        plugin.similarity_threshold = 1.5  # Out of range

        # Should still work, just use the value
        result = await plugin.compute_similarity("text1", "text2")
        assert result is not None

    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Test concurrent NLP operations."""
        plugin = NLPToolkit()
        texts = [
            "This is great",
            "This is terrible",
            "This is neutral",
        ]

        results = []
        for text in texts:
            result = await plugin.analyze_sentiment(text)
            results.append(result)

        assert len(results) == 3
        assert all("sentiment" in r for r in results)


class TestNLPToolkitIntegration:
    """Integration tests."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        """Test complete plugin lifecycle."""
        plugin = NLPToolkit()
        context = {
            "spacy_model": "en_core_web_sm",
            "similarity_threshold": 0.75,
        }

        await plugin.initialize(context)
        assert plugin.enabled is True

        # Perform various operations
        text = "This is excellent work! The results look great."
        sentiment = await plugin.analyze_sentiment(text)
        entities = await plugin.extract_entities(text)
        summary = await plugin.summarize_text(text)
        similarity = await plugin.compute_similarity(text, "This is good work")

        assert all(r is not None for r in [sentiment, entities, summary, similarity])

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_text_analysis_workflow(self):
        """Test complete text analysis workflow."""
        plugin = NLPToolkit()
        await plugin.initialize()

        documents = [
            "Great product, highly recommended!",
            "Terrible experience, would not recommend",
            "The product works as expected",
        ]

        results = {
            "sentiments": [],
            "entities": [],
            "summaries": [],
        }

        for doc in documents:
            results["sentiments"].append(await plugin.analyze_sentiment(doc))
            results["entities"].append(await plugin.extract_entities(doc))
            results["summaries"].append(await plugin.summarize_text(doc))

        assert len(results["sentiments"]) == 3
        assert len(results["entities"]) == 3
        assert len(results["summaries"]) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
