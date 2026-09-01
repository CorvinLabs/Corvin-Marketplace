"""Setup for slack_notifier plugin."""

from setuptools import setup, find_packages

setup(
    name="slack_notifier",
    version="1.0.0",
    description="Send notifications to Slack channels from Corvin tasks and workflows. Supports rich formatting, mentions, and threading.",
    author="Community Contributor (example.com)",
    license="MIT",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        "requests>=2.28.0",
    ],
)
