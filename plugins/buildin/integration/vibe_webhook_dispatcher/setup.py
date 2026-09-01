"""Setup for vibe_webhook_dispatcher plugin."""

from setuptools import setup, find_packages

setup(
    name="vibe_webhook_dispatcher",
    version="1.0.0",
    description="Dispatch Vibe session events to external webhooks (lifecycle, errors, milestones)",
    author="Anthropic PBC",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        # Vibe/Brain plugin depends on core CorvinOS only
    ],
)
