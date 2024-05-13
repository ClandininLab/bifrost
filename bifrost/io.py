"""
Module for I/O related methods
"""

import hashlib
import os
import urllib

import ants
import h5py
import numpy as np

from bifrost.util import package_path


def write_affine(h5_handle, name, transform):
    """Write ANTs affine transform to h5

    Args:
      h5_handle: open file handle - h5py.File
      name: name of group to create, absolute path - str
      transform: if str interpreted as path to .mat file - ANTsTransform or str
    """
    assert isinstance(h5_handle, h5py.File)
    assert isinstance(transform, (ants.ANTsTransform, str))

    if isinstance(transform, str):
        transform = ants.read_transform(transform)

    h5_handle.create_group(name)
    h5_handle.create_dataset(f"{name}/parameters", data=transform.parameters)
    h5_handle.create_dataset(
        f"{name}/fixed_parameters", data=transform.fixed_parameters
    )


def read_affine(h5_handle, name, directory=None):
    """Read ANTs affine transform from h5
    If directory is not None, writes to a file and returns absolute path
    This allows use with ants.apply_transforms which demands files


    Args:
      h5_handle: open file handle - h5py.File
      name: name of group, absolute path - str
      directory: absolute path to (presumably temporary) directory to write result to

    Returns:
      transform: path or transform object
    """
    assert isinstance(h5_handle, h5py.File)

    transform = ants.create_ants_transform()
    transform.set_parameters(h5_handle[f"{name}/parameters"][:])
    transform.set_fixed_parameters(h5_handle[f"{name}/fixed_parameters"][:])

    if directory is None:
        return transform

    transform_path = f"{directory}/aff.mat"

    assert not os.path.exists(transform_path)

    ants.write_transform(transform, transform_path)

    return transform_path


def write_image(h5_handle, name, image):
    """Writes ANTs image to h5

    Args:
      h5_handle: open file handle - h5py.File
      name: name of dataset to create, absolute path - str
      image: if str interpreted as path to image file - ANTsImage or str
    """
    assert isinstance(h5_handle, h5py.File)
    assert isinstance(image, (ants.ANTsImage, str))

    if isinstance(image, str):
        image = ants.image_read(image)

    image_arr = image.numpy()

    h5_handle.create_dataset(
        name,
        data=image_arr,
        chunks=True,
        compression="gzip",
        compression_opts=9,
        shuffle=True,
        fletcher32=True,
    )

    h5_handle[name].attrs["origin"] = image.origin
    h5_handle[name].attrs["spacing"] = image.spacing
    h5_handle[name].attrs["direction"] = image.direction
    h5_handle[name].attrs["has_components"] = image.has_components


def read_image(h5_handle, name, directory=None):
    """Reads ANTs image from h5
    If directory is not None, writes to a file and returns absolute path
    This allows use with ants.apply_transforms which demands files


    Args:
      h5_handle: open file handle - h5py.File
      name: name of dataset, absolute path - str
      directory: absolute path to (presumably temporary) directory to write result to

    Returns:
      image - ants.ANTs.Image
    """
    assert isinstance(h5_handle, h5py.File)

    image = ants.from_numpy(
        h5_handle[name][:],
        origin=tuple(h5_handle[name].attrs["origin"]),
        spacing=tuple(h5_handle[name].attrs["spacing"]),
        direction=h5_handle[name].attrs["direction"],
        has_components=h5_handle[name].attrs["has_components"],
    )

    if directory is None:
        return image

    img_path = f"{directory}/img.nii"

    assert not os.path.exists(img_path)

    ants.image_write(image, img_path)

    return img_path


def md5sum(filename):
    """Compute the md5sum of a file

    Args:
      filename - str

    Returns:
      file_hash - str
    """
    file_hash = hashlib.md5()

    with open(filename, "rb") as file_handle:
        chunk = file_handle.read(8192)

        while chunk:
            file_hash.update(chunk)
            chunk = file_handle.read(8192)

    return file_hash.hexdigest()


def download_weights(shapes=True):
    """Download synthmorph weights. By default the 'shapes' weights are downloaded"""
    if shapes:
        weights_url = "https://surfer.nmr.mgh.harvard.edu/ftp/data/voxelmorph/synthmorph/shapes-dice-vel-3-res-8-16-32-256f.h5"
    else:
        weights_url = "https://surfer.nmr.mgh.harvard.edu/ftp/data/voxelmorph/synthmorph/brains-dice-vel-0.5-res-16-256f.h5"

    weight_dir = f"{package_path()}/weights"

    os.makedirs(weight_dir, exist_ok=True)

    urllib.request.urlretrieve(weights_url, f"{weight_dir}/synthmorph_weights.h5")
