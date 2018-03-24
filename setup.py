import os

from setuptools import setup


def rel(*xs):
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), *xs)


with open(rel("fargate_scraper.py"), "r") as f:
    version_marker = "__version__ = "
    for line in f:
        if line.startswith(version_marker):
            _, version = line.split(version_marker)
            version = version.strip().strip('"')
            break
    else:
        raise RuntimeError("Version marker not found.")


setup(
    name="fargate_scraper",
    version=version,
    description="A CLI utility for scraping metrics endpoints from AWS Fargate.",
    long_description="Visit https://github.com/Bogdanp/fargate_scraper for more information.",
    packages=[],
    py_modules=["fargate_scraper"],
    install_requires=["boto3"],
    python_requires=">=3.5",
    entry_points={
        "console_scripts": [
            "fargate-scraper = fargate_scraper:main",
        ],
    },
    include_package_data=True,
)
