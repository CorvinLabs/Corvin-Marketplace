"""Setup for learning_event_storage plugin."""

from setuptools import setup, find_packages

setup(
    name="learning_event_storage",
    version="1.0.0",
    description="Learning event storage backend",
    author="Anthropic PBC",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        # Add dependencies here
    ],
)
