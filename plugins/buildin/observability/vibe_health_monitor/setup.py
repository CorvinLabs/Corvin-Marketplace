"""Setup for vibe_health_monitor plugin."""

from setuptools import setup, find_packages

setup(
    name="vibe_health_monitor",
    version="1.0.0",
    description="Monitors Vibe session health metrics, latency, and state transitions",
    author="Anthropic PBC",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        # Vibe/Brain plugin depends on core CorvinOS only
    ],
)
