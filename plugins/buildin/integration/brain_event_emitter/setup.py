"""Setup for brain_event_emitter plugin."""

from setuptools import setup, find_packages

setup(
    name="brain_event_emitter",
    version="1.0.0",
    description="Emit Brain subsystem events to event bus for downstream processing",
    author="Anthropic PBC",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        # Vibe/Brain plugin depends on core CorvinOS only
    ],
)
