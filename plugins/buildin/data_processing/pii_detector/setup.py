"""Setup for pii_detector plugin."""

from setuptools import setup, find_packages

setup(
    name="pii_detector",
    version="1.0.0",
    description="PII detection and masking",
    author="Anthropic PBC",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        # Add dependencies here
    ],
)
