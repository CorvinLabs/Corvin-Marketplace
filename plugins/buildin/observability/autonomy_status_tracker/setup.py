"""Setup for autonomy_status_tracker plugin."""

from setuptools import setup, find_packages

setup(
    name="autonomy_status_tracker",
    version="1.0.0",
    description="Tracks autonomous session status, hardening state, and error recovery",
    author="Anthropic PBC",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        # Vibe/Brain plugin depends on core CorvinOS only
    ],
)
