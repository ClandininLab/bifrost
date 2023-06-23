""" Misc. utility methods
"""

import argparse
import inspect
import os

import numpy as np

import bifrost

SYNTHMORPH_SHAPE = (160, 160, 192)


def update_image_array(image, updated):
    """Update ANTs.Image image array but preserve metadata

    Args:
      image - ants.ANTsImage
      updated: array to replace image data with - np.ndarray

    Returns:
      updated_image - ants.ANTsImage
    """
    import ants

    assert isinstance(image, ants.ANTsImage)
    assert image.numpy().shape == updated.shape

    updated_image = ants.from_numpy(
        updated,
        origin=image.origin,
        spacing=image.spacing,
        direction=image.direction,
        has_components=image.has_components,
    )

    return updated_image


def threshold_image(image, threshold):
    """Set intensity values below threshold to 0

    Args:
      image - ants.ANTsImage
      threshold - float

    Returns:
      thresholded_img - ants.ANTsImage
    """
    import ants

    assert isinstance(image, ants.ANTsImage)

    image_arr = image.numpy()

    image_arr[image_arr <= threshold] = 0

    thresholded_image = ants.from_numpy(
        image_arr,
        origin=image.origin,
        spacing=image.spacing,
        direction=image.direction,
        has_components=image.has_components,
    )

    return thresholded_image


def transpose_image(image, transposition):
    """Transpose the axes of an image, preserve metadata

    Args:
      image - ants.ANTsImage
      transposition: permutation of axes, same format as np.transpose

    Returns:
      transposed_image
    """
    import ants

    assert sorted(transposition) == list(range(len(transposition)))

    def _permute(arr):
        return [arr[idx] for idx in transposition]

    image_arr = image.numpy()

    image_arr = np.transpose(image_arr, transposition)

    transposed_image = ants.from_numpy(
        image_arr,
        origin=_permute(image.origin),
        spacing=_permute(image.spacing),
        direction=np.stack(_permute(image.direction)),
        has_components=image.has_components,
    )

    return transposed_image


def dice_coefficient(image_1, image_2, exclude_labels=[0]):
    """Computes the mean Sørensen–Dice coefficient across labels for two images
    Also returns per label dice coefficients

    Args:
      image_1 - np.ndarray
      image_2 - np.ndarray
      exclude_labels: (optional) list of labels to exclude, say the background - list

    Returns:
      mean_coeff - float
      label_coeffs: map of label to dice coeff - dict
    """
    assert image_1.shape == image_2.shape
    assert isinstance(image_1, np.ndarray)
    assert isinstance(image_2, np.ndarray)

    labels = np.unique(image_1)
    assert all(labels == np.unique(image_2))

    label_coeffs = {}

    for label in labels:
        assert float(label).is_integer()

        if label not in exclude_labels:
            mask_1 = image_1 == label
            mask_2 = image_2 == label

            label_coeffs[int(label)] = (
                2 * np.sum(mask_1 * mask_2) / (np.sum(mask_1) + np.sum(mask_2))
            )

    mean_coeff = np.mean(list(label_coeffs.values()))

    return mean_coeff, label_coeffs


def package_path():
    """Returns the absolute path to this package base directory"""
    return os.path.dirname(inspect.getfile(bifrost))


class SubcommandHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Adapted from https://stackoverflow.com/questions/13423540/argparse-subparser-hide-metavar-in-command-listing"""

    def _format_action(self, action):
        parts = super(argparse.RawDescriptionHelpFormatter, self)._format_action(action)
        if action.nargs == argparse.PARSER:
            parts = "\n".join(parts.split("\n")[1:])
        return parts
