"""Setup for semantic_context_retriever plugin."""

from setuptools import setup, find_packages

setup(
    name="semantic_context_retriever",
    version="0.1.0",
    description="BM25 context-selection provider (ADR-0599 context_retriever)",
    author="Anthropic PBC",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        # pure-python BM25 fallback; rank_bm25 optional
    ],
)
