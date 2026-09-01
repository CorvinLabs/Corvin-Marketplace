"""Setup for nlp_toolkit plugin."""

from setuptools import setup, find_packages

setup(
    name="nlp_toolkit",
    version="2.0.0",
    description="Natural Language Processing utilities for text analysis, named entity recognition, sentiment analysis, and semantic similarity. Plugs into session memory for context enhancement.",
    author="Community Contributor (nlp-collective.io)",
    license="MIT",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        "spacy>=3.0.0",
        "nltk>=3.8.0",
        "transformers>=4.30.0",
    ],
)
