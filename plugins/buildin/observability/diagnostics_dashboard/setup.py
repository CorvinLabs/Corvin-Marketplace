"""Setup for diagnostics_dashboard plugin."""

from setuptools import setup, find_packages

setup(
    name="diagnostics_dashboard",
    version="1.0.0",
    description="Diagnostics and health dashboard",
    author="Anthropic PBC",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        # Add dependencies here
    ],
)
