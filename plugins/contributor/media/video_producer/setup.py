"""Video Producer — Setup configuration.

ADR-0953 Phase E: install_requires corrected to match what the live path
(src/models.py, storage.py, skill.py, async_runner.py, __init__.py) actually
imports — see requirements.txt for the verification method. entry_points
removed: both pointed at modules deleted in ADR-0953 Phase C
(video_producer.__main__, video_producer.plugin) and neither was ever read
by any CorvinOS loader (the console route imports src/__init__.py directly
by file path; the real plugin-lifecycle entry point is provider.py, loaded
via corvin_plugins.bootstrap, which uses no setuptools entry_point group at
all). There is no console-script CLI on the live path.
"""

from setuptools import setup, find_packages

setup(
    name="corvinos-video-producer",
    version="1.3.0",
    description="Create narrated MP4s with animated web slides: LLM storyboard, OpenAI TTS narration, deterministic Chromium rendering, ffmpeg assembly",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Corvin Labs",
    license="Apache-2.0",
    # src/ IS the package root (src/__init__.py, no further nesting since
    # ADR-0953 removed the src/video_producer/ sub-package) -- find_packages()
    # only finds subdirectories containing __init__.py, so it would find
    # nothing here; this tells setuptools "the package is named
    # corvinos_video_producer, its code lives in src/".
    package_dir={"corvinos_video_producer": "src"},
    packages=["corvinos_video_producer"],
    python_requires=">=3.9",
    install_requires=[
        "anthropic>=0.40.0",
        "requests>=2.31.0",
        "gTTS>=2.5.0",
        "Pillow>=10.0.0",
    ],
    extras_require={
        "dev": ["pytest>=7.0", "pytest-cov>=4.0"],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Multimedia :: Video :: Video Production",
    ],
)
