"""Setup for consent_gate plugin."""

from setuptools import setup, find_packages

setup(
    name="consent_gate",
    version="1.0.0",
    description="L16 consent management gate",
    author="Anthropic PBC",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        # Add dependencies here
    ],
)
