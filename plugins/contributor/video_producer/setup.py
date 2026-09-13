"""Setup for Video Producer plugin."""

from setuptools import setup, find_packages

setup(
    name="video-producer",
    version="1.0.0",
    description="Create CorvinOS marketing and explainer videos from PowerPoints, screenshots, and voice narration. Orchestrated multi-skill system with deep asset analysis.",
    author="CorvinOS Contributors",
    license="Apache-2.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        "corvinOS>=1.0.0",
        "python-pptx>=0.6.21",
        "openai>=1.0.0",
        "pydantic>=2.0.0",
        "requests>=2.31.0",
        "anthropic>=0.40.0",
        "gTTS>=2.5.0",
        "python-dotenv>=1.0.0",
        "Pillow>=10.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.0.0",
        ],
    },
)
