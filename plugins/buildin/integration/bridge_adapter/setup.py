"""Setup for bridge_adapter plugin."""

from setuptools import setup, find_packages

setup(
    name="bridge_adapter",
    version="1.0.0",
    description="Bridge adapter framework",
    author="Anthropic PBC",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        # Add dependencies here
    ],
)
