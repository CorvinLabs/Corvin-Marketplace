"""Setup for path_gate plugin."""

from setuptools import setup, find_packages

setup(
    name="path_gate",
    version="1.0.0",
    description="L10 filesystem write protection",
    author="Anthropic PBC",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        # Add dependencies here
    ],
)
