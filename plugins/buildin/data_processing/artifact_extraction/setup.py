"""Setup for artifact_extraction plugin."""

from setuptools import setup, find_packages

setup(
    name="artifact_extraction",
    version="1.0.0",
    description="Artifact extraction from sessions",
    author="Anthropic PBC",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        # Add dependencies here
    ],
)
