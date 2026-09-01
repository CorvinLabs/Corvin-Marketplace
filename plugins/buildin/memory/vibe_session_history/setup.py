"""Setup for vibe_session_history plugin."""

from setuptools import setup, find_packages

setup(
    name="vibe_session_history",
    version="1.0.0",
    description="Persistent history of Vibe sessions (decisions, context snapshots, outcomes)",
    author="Anthropic PBC",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        # Vibe/Brain plugin depends on core CorvinOS only
    ],
)
