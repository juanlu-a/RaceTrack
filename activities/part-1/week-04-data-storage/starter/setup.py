from setuptools import find_packages, setup

setup(
    name="week04-racetrack-starter",
    version="0.1.0",
    packages=find_packages(include=["repositories*"]),
    install_requires=["boto3>=1.28.0"],
)
