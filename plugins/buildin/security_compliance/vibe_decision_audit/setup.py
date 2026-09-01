"""Setup for vibe_decision_audit plugin."""

from setuptools import setup, find_packages

setup(
    name="vibe_decision_audit",
    version="1.0.0",
    description="Audit trail for Vibe session decisions, routing, and state changes",
    author="Anthropic PBC",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        # Vibe/Brain plugin depends on core CorvinOS only
    ],
)
