# NLP Toolkit Plugin

Natural Language Processing utilities for text analysis and session memory enhancement.

## Description

The NLP Toolkit plugin provides:
- Sentiment analysis
- Named entity recognition
- Text summarization
- Semantic similarity computation

Perfect for text understanding, content analysis, and context enhancement.

## Installation

```bash
pip install -e .
```

Or via Corvin-Marketplace:
```bash
corvin plugin install nlp_toolkit
```

## Configuration

The plugin accepts configuration for NLP models:

```json
{
  "spacy_model": "en_core_web_sm",
  "similarity_threshold": 0.7
}
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `spacy_model` | string | `en_core_web_sm` | Spacy model for NER and POS tagging |
| `similarity_threshold` | number | `0.7` | Threshold for semantic similarity (0.0-1.0) |

## Usage

### Sentiment Analysis

```python
plugin = NLPToolkit()
await plugin.initialize()

result = await plugin.analyze_sentiment("This is excellent work!")
# Returns: { sentiment: "positive", score: 0.85, confidence: 0.9 }
```

### Entity Extraction

```python
result = await plugin.extract_entities("John Smith works at Microsoft in Seattle")
# Returns: { entities: { PERSON: ["John"], LOCATION: ["Seattle"], ... }, entity_count: 2 }
```

### Text Summarization

```python
text = "This is the first sentence. This is the second sentence. This is the third sentence."
result = await plugin.summarize_text(text, num_sentences=2)
# Returns: { summary: "...", compression_ratio: 0.6, key_points: [...] }
```

### Semantic Similarity

```python
result = await plugin.compute_similarity("hello world", "hello there")
# Returns: { similarity: 0.75, is_similar: True, threshold: 0.7 }
```

### Via execute() Method

```python
# Sentiment
result = await plugin.execute(analyze_sentiment=True, text="Great work!")

# Entities
result = await plugin.execute(extract_entities=True, text="John works at Google")

# Summarize
result = await plugin.execute(summarize=True, text="...", num_sentences=3)

# Similarity
result = await plugin.execute(
    compute_similarity=True,
    text1="hello world",
    text2="hello"
)
```

## Architecture

```
┌──────────────────────┐
│   Input Text         │
│  (user query/doc)    │
└──────────┬───────────┘
           │
   ┌───────▼────────┐
   │  Preprocessing │
   │  - Tokenize    │
   │  - Normalize   │
   └───────┬────────┘
           │
   ┌───────┴──────────────────┐
   │                          │
┌──▼────────┐  ┌────▼──────┐ │
│ Sentiment  │  │  Entity   │ │
│ Analyzer   │  │ Extractor │ │
└──┬────────┘  └────┬──────┘ │
   │                │        │
   │ ┌──────────────┘        │
   │ │                       │
   │ │  ┌──────────────────┐ │
   │ │  │ Text             │ │
   │ │  │ Summarization    │ │
   │ │  └────────┬─────────┘ │
   │ │           │           │
   └─┼───────────┼───────────┘
     │           │
     │  ┌────────▼─────────┐
     │  │  Similarity      │
     │  │  Computation     │
     │  └────────┬─────────┘
     │           │
     └───────────┼────────┐
                 │        │
          ┌──────▼──┐  ┌──▼────┐
          │ Results │  │ Cache │
          └─────────┘  └───────┘
```

## Features

- **Sentiment Analysis**: Detect positive, negative, or neutral sentiment with confidence scores
- **Entity Extraction**: Identify PERSON, LOCATION, ORGANIZATION, DATE, QUANTITY entities
- **Text Summarization**: Extract key sentences and generate text summaries
- **Similarity Scoring**: Compute semantic similarity between text pairs with configurable threshold
- **Async Processing**: Non-blocking NLP operations
- **Configurable Models**: Support for different Spacy models and thresholds

## Sentiment Scores

| Range | Interpretation |
|-------|-----------------|
| -1.0 to -0.5 | Strongly negative |
| -0.5 to 0.0 | Somewhat negative |
| 0.0 to 0.5 | Somewhat positive |
| 0.5 to 1.0 | Strongly positive |

## Entity Types

- **PERSON**: People names
- **LOCATION**: Geographical locations
- **ORGANIZATION**: Companies, organizations
- **DATE**: Date references
- **QUANTITY**: Numbers and measurements

## Testing

Run unit tests:

```bash
pytest tests/test_nlp_toolkit.py -v
```

Run E2E tests:

```bash
pytest tests/e2e_test_nlp_toolkit.py -v
```

## Limitations

- **Heuristic-based**: Current version uses simplified pattern matching
- **English Only**: Optimized for English language content
- **No Model Download**: Requires pre-installed Spacy models
- **Single-Document**: Processes one document at a time

## Performance

- **Sentiment**: <10ms per text
- **Entities**: <50ms per text
- **Summarization**: <100ms per text
- **Similarity**: <5ms per pair

## Requirements

- Python 3.8+
- spacy >= 3.0.0
- nltk >= 3.8.0
- transformers >= 4.30.0

## Spacy Model Setup

```bash
python -m spacy download en_core_web_sm
```

## Author

Community Contributor (nlp-collective.io)

## License

MIT - See LICENSE file

## Support

For issues, feature requests, or contributions, visit:
https://github.com/community-plugin/nlp-toolkit
