"""Setup for sql_expert plugin."""

from setuptools import setup, find_packages

setup(
    name="sql_expert",
    version="1.1.0",
    description="Advanced SQL query optimization and debugging. Analyzes execution plans, suggests indexes, and refactors complex queries for performance.",
    author="Community Contributor (db-community.org)",
    license="MIT",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        "sqlalchemy>=2.0.0",
        "psycopg2>=2.9.0",
    ],
)
