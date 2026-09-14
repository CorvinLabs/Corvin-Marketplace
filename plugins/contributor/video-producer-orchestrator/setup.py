from setuptools import setup, find_packages

setup(
    name="corvin-video-producer-orchestrator",
    version="1.0.0",
    description="Generate professional demo videos from storyboards with quality gates and learning integration",
    author="CorvinOS Contributors",
    license="Apache-2.0",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "pillow>=9.0.0",
        "google-cloud-texttospeech>=2.14.0",
        "pydub>=0.25.0",
        "ffmpeg-python>=0.2.1",
        "numpy>=1.21.0",
        "scipy>=1.7.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.20.0",
            "pytest-cov>=4.0.0",
            "responses>=0.23.0",
            "black>=23.0.0",
            "pylint>=2.16.0",
            "mypy>=1.0.0",
        ],
        "piper": [
            "piper-tts>=1.2.0",
        ],
    },
    include_package_data=True,
    package_data={
        "src": ["design_system.json"],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
