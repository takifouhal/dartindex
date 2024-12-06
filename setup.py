from setuptools import setup, find_packages

setup(
    name="dartindex",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "click>=8.0.0",
        "protobuf>=4.21.0",
    ],
    entry_points={
        "console_scripts": [
            "dartindex=cli.main:cli",
        ],
    },
) 