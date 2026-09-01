"""Setup for error_healing plugin."""

from setuptools import setup, find_packages

setup(
    name="error_healing",
    version="1.0.0",
    description="Error detection and healing",
    author="Anthropic PBC",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        # Add dependencies here
    ],
)
