"""Video Producer Skill 2.0 — Setup configuration"""

from setuptools import setup, find_packages

setup(
    name="video-producer-orchestrator",
    version="2.0.0",
    description="Orchestrated video production: PPT → professional video",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Corvin Labs",
    license="Apache-2.0",
    packages=find_packages(),
    python_requires=">=3.9",
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
        "google-api-python-client>=2.0",
        "google-auth-oauthlib>=1.0",
        "cairosvg>=2.5.0",
        "ffmpeg-python>=0.2.1",
    ],
    extras_require={
        "dev": ["pytest>=7.0", "pytest-cov>=4.0"],
        "blender": ["blender>=3.0.0"],
        "imagemagick": ["imagemagick>=7.0.0"],
    },
    entry_points={
        "console_scripts": [
            "video-producer = video_producer.__main__:main",
        ],
        "corvin.skills": [
            "video_producer = video_producer.plugin:VideoProducerPlugin",
        ],
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
