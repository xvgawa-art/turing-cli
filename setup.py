#!/usr/bin/env python3
"""
Turing CLI setup script

用于将 CLI 工具安装为系统命令
"""

from setuptools import setup, find_packages
from pathlib import Path

# 读取 README.md
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding='utf-8') if (this_directory / "README.md").exists() else ""

setup(
    name="turing-cli",
    version="1.0.0",
    author="Turing Team",
    author_email="team@turing.ai",
    description="代码漏洞审计工具 CLI",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your-org/turing-cli",
    packages=find_packages(exclude=["tests", "tests.*"]),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.10",
    install_requires=[
        "click>=8.0.0",
        "gitpython>=3.1.0",
        "pydantic>=2.0.0",
        "httpx>=0.24.0",
    ],
    extras_require={
        "opencode": ["opencode-ai>=0.1.0a36"],
    },
    entry_points={
        "console_scripts": [
            "turing=turing_cli.main:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
