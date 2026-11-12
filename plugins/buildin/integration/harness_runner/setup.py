"""Wheel: corvin_harness_runner-0.1.0-py3-none-any.whl (stdlib only; needs a CorvinOS install at run time)."""
from setuptools import find_packages, setup

setup(
    name="corvin_harness_runner",
    version="0.1.0",
    description="Headless single-turn CorvinOS runner for benchmark harnesses",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.11",
    install_requires=[],
)
