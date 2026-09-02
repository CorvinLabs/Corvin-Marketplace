"""
End-to-end tests for nlp_toolkit plugin.

Tests real plugin initialization, NLP workflows, and analysis flows.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from nlp_toolkit import NLPToolkit


class TestNLPToolkitE2E:
    """End-to-end tests for NLP Toolkit."""

    @pytest.mark.asyncio
    async def test_e2e_basic_analysis(self):
        """E2E test: Basic text analysis workflow."""
        plugin = NLPToolkit()
        context = {
            "spacy_model": "en_core_web_sm",
            "similarity_threshold": 0.7,
        }
        await plugin.initialize(context)

        # Analyze text
        text = "This is excellent work! I really appreciate the effort."
        result = await plugin.analyze_sentiment(text)

        # Verify
        assert result["text"] == text
        assert "sentiment" in result
        assert "score" in result
        assert "confidence" in result

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_full_analysis_pipeline(self):
        """E2E test: Full NLP analysis pipeline."""
        plugin = NLPToolkit()
        await plugin.initialize()

        text = "Alice Johnson works at Google in Mountain View and leads the AI research team."

        # Sentiment
        sentiment = await plugin.analyze_sentiment(text)
        assert "sentiment" in sentiment

        # Entities
        entities = await plugin.extract_entities(text)
        assert "entities" in entities
        assert entities["entity_count"] > 0

        # Summary
        summary = await plugin.summarize_text(text)
        assert "summary" in summary

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_sentiment_tracking(self):
        """E2E test: Track sentiment across multiple messages."""
        plugin = NLPToolkit()
        await plugin.initialize()

        messages = [
            "Great work today!",
            "The results are disappointing",
            "This is average",
            "Excellent progress!",
            "Terrible performance",
        ]

        sentiments = []
        for msg in messages:
            result = await plugin.analyze_sentiment(msg)
            sentiments.append(result)

        # Verify all were analyzed
        assert len(sentiments) == 5
        assert all("sentiment" in s for s in sentiments)

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_document_processing(self):
        """E2E test: Process multiple documents."""
        plugin = NLPToolkit()
        await plugin.initialize()

        documents = [
            "Customer feedback: The product is great but the delivery was slow.",
            "Internal memo: We need to improve our processes.",
            "Support ticket: User is very happy with our service.",
        ]

        results = {"sentiments": [], "entities": [], "summaries": []}

        for doc in documents:
            sentiment = await plugin.analyze_sentiment(doc)
            entities = await plugin.extract_entities(doc)
            summary = await plugin.summarize_text(doc)

            results["sentiments"].append(sentiment)
            results["entities"].append(entities)
            results["summaries"].append(summary)

        # Verify
        assert len(results["sentiments"]) == 3
        assert len(results["entities"]) == 3
        assert len(results["summaries"]) == 3

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_similarity_matching(self):
        """E2E test: Match similar documents."""
        plugin = NLPToolkit()
        plugin.similarity_threshold = 0.6
        await plugin.initialize()

        query = "How do I reset my password?"

        documents = [
            "Instructions to reset your password",
            "Forgot password? Click here",
            "What is your email?",
            "How to change security settings",
        ]

        similarities = []
        for doc in documents:
            result = await plugin.compute_similarity(query, doc)
            similarities.append(result)

        assert len(similarities) == 4
        assert all("is_similar" in s for s in similarities)

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_text_summarization(self):
        """E2E test: Summarize long documents."""
        plugin = NLPToolkit()
        await plugin.initialize()

        # Long document
        document = (
            "The new product launch was successful. "
            "We exceeded sales targets by 25 percent. "
            "Customer feedback has been very positive. "
            "The marketing campaign reached 2 million people. "
            "Social media engagement increased significantly."
        )

        # Summarize to 2 sentences
        result = await plugin.summarize_text(document, num_sentences=2)

        assert "summary" in result
        assert result["compression_ratio"] < 1.0
        assert len(result["key_points"]) > 0

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_multilingual_handling(self):
        """E2E test: Handle various text patterns."""
        plugin = NLPToolkit()
        await plugin.initialize()

        # Different types of text
        texts = [
            "URGENT: System down!",  # All caps
            "The quick brown fox jumps over the lazy dog",  # Standard
            "user@example.com called today",  # With email
            "Version 2.0.1 released",  # With numbers
        ]

        results = []
        for text in texts:
            sentiment = await plugin.analyze_sentiment(text)
            results.append(sentiment)

        assert len(results) == 4
        assert all("sentiment" in r for r in results)

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_feedback_analysis(self):
        """E2E test: Analyze customer feedback."""
        plugin = NLPToolkit()
        await plugin.initialize()

        feedbacks = [
            "Amazing product! Highly recommended.",
            "Not satisfied with the quality.",
            "It works as expected.",
            "Terrible customer service!",
            "Love this feature!",
        ]

        positive_count = 0
        negative_count = 0

        for feedback in feedbacks:
            result = await plugin.analyze_sentiment(feedback)
            if result["sentiment"] == "positive":
                positive_count += 1
            elif result["sentiment"] == "negative":
                negative_count += 1

        # Verify at least some classification worked
        assert positive_count + negative_count > 0

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_context_enrichment(self):
        """E2E test: Enrich context with NLP analysis."""
        plugin = NLPToolkit()
        await plugin.initialize()

        # User query to enhance
        query = "Tell me about John's achievements at Google"

        # Extract entities to understand query context
        entities = await plugin.extract_entities(query)

        # Summarize if needed
        summary = await plugin.summarize_text(query, num_sentences=1)

        # Compute similarity to known topics
        topics = [
            "Career achievements",
            "Company history",
            "Technology trends",
        ]

        similarities = []
        for topic in topics:
            sim = await plugin.compute_similarity(query, topic)
            similarities.append(sim)

        assert entities["entity_count"] > 0
        assert len(similarities) == 3

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_execute_interface(self):
        """E2E test: Using execute() method."""
        plugin = NLPToolkit()
        await plugin.initialize()

        # Test via execute
        result1 = await plugin.execute(
            analyze_sentiment=True,
            text="Excellent work!",
        )
        assert "sentiment" in result1

        result2 = await plugin.execute(
            extract_entities=True,
            text="Bob works at Microsoft",
        )
        assert "entities" in result2

        result3 = await plugin.execute(
            summarize=True,
            text="First sentence. Second sentence. Third sentence.",
            num_sentences=2,
        )
        assert "summary" in result3

        result4 = await plugin.execute(
            compute_similarity=True,
            text1="hello world",
            text2="hello",
        )
        assert "similarity" in result4

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_error_recovery(self):
        """E2E test: Error handling and recovery."""
        plugin = NLPToolkit()
        await plugin.initialize()

        # Try invalid analysis (should fail)
        try:
            await plugin.analyze_sentiment("")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass  # Expected

        # Continue with valid text
        result = await plugin.analyze_sentiment("Recovery successful")
        assert result["sentiment"] is not None

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_e2e_production_scenario(self):
        """E2E test: Realistic production scenario."""
        plugin = NLPToolkit()
        context = {
            "spacy_model": "en_core_web_sm",
            "similarity_threshold": 0.75,
        }
        await plugin.initialize(context)

        # Simulate customer support workflow

        # Step 1: Analyze incoming ticket
        ticket = "Your new product is amazing! When will it be available in my country?"

        sentiment = await plugin.analyze_sentiment(ticket)
        entities = await plugin.extract_entities(ticket)

        # Step 2: Match against FAQ
        faq = "What is the availability of new products?"
        match = await plugin.compute_similarity(ticket, faq)

        # Step 3: Summarize for agent
        summary = await plugin.summarize_text(ticket, num_sentences=1)

        # Verify all steps completed
        assert sentiment["sentiment"] is not None
        assert entities["entity_count"] >= 0
        assert match["similarity"] >= 0
        assert summary["summary"] is not None

        await plugin.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
