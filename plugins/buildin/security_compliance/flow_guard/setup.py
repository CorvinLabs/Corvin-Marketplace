"""Setup for flow_guard plugin."""

from setuptools import setup, find_packages

setup(
    name="flow_guard",
    version="1.0.0",
    description="L34 data flow guard",
    author="Anthropic PBC",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        # Add dependencies here
    ],
)
