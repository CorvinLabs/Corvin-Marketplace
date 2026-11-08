from setuptools import find_packages, setup

setup(
    name="corvin-project-templates",
    version="1.0.0",
    description="Project templates (feature fragments) for CorvinOS projects",
    license="Apache-2.0",
    packages=find_packages(include=["src*"]),
    package_data={"src": ["fragments/*/*.yaml", "fragments/*/files/*", "templates/*.yaml"]},
    install_requires=["pyyaml"],
    python_requires=">=3.11",
)
