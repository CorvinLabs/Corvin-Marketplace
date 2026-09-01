"""Setup for vibe_context_telemetry plugin."""

from setuptools import setup, find_packages

setup(
    name="vibe_context_telemetry",
    version="1.0.0",
    description="Collects Vibe context engineering metrics (preservation, additive model)",
    author="Anthropic PBC",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        # Vibe/Brain plugin depends on core CorvinOS only
    ],
)
