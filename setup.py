""" Setup config
"""

from setuptools import find_packages, setup

setup(
    name="bifrost",
    version="0.1",
    author="Andrew Berger",
    author_email="a5b@stanford.edu",
    description="Template building and cross-modal registration.",
    url="https://github.com/ClandininLab/bifrost",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "numpy",
        "scipy",
        "nibabel",
        "pynrrd",
        "Pillow",
        "antspyx",
        "scikit-learn",
        "scikit-image",
        "voxelmorph @ git+https://github.com/ClandininLab/voxelmorph.git@ed92ff23455c8b8942a0c38ee8988223b71410c5",
        "snakemake",
    ],
    entry_points={
        "console_scripts": [
            "bifrost=bifrost.cli.bifrost:main",
        ]
    },
)
