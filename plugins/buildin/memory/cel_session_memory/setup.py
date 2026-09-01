"""Setup for cel_session_memory plugin."""

from setuptools import setup, find_packages

setup(
    name="cel_session_memory",
    version="1.0.0",
    description="CEL session memory provider",
    author="Anthropic PBC",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        # Add dependencies here
    ],
)
