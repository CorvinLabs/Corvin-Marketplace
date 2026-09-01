"""Setup for cowork_hub plugin."""

from setuptools import setup, find_packages

setup(
    name="cowork_hub",
    version="1.0.0",
    description="L4 multi-persona orchestration",
    author="Anthropic PBC",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        # Add dependencies here
    ],
)
