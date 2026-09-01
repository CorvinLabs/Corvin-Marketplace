"""Setup for stt_provider plugin."""

from setuptools import setup, find_packages

setup(
    name="stt_provider",
    version="1.0.0",
    description="CorvinOS buildin plugin",
    author="Anthropic PBC",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        # Add dependencies here
    ],
)
