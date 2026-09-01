"""Setup for self_repair_engine plugin."""

from setuptools import setup, find_packages

setup(
    name="self_repair_engine",
    version="1.0.0",
    description="Observes self-repair attempts and outcomes",
    author="Anthropic PBC",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        # Vibe/Brain plugin depends on core CorvinOS only
    ],
    extras_require={
        "dev": ["pytest", "pytest-asyncio"],
    },
)
