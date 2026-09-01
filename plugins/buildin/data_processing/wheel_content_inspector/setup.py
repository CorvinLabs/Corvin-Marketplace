"""Setup for wheel_content_inspector plugin."""

from setuptools import setup, find_packages

setup(
    name="wheel_content_inspector",
    version="1.0.0",
    description="Wheel content inspection",
    author="Anthropic PBC",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        # Add dependencies here
    ],
)
