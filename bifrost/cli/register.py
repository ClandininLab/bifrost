""" Logic for full registration pipeline

Execute using the 'bifrost' executable installed by setuptools
"""

import logging
import os
import shutil
import sys
from pathlib import Path

import ants
import h5py
import numpy as np
import tensorflow as tf
import voxelmorph as vxm
from skimage.exposure import equalize_adapthist

from bifrost.io import download_weights, md5sum, write_affine, write_image
from bifrost.util import package_path, transpose_image, update_image_array

# hide GPUs
os.environ["CUDA_VISIBLE_DEVICES"] = ""
# suppress tensorflow import warnings
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"


TARGET_SHAPE = (160, 160, 192)
DEVICE = "/CPU:0"
MODEL_WEIGHTS_PATH = f"{package_path()}/weights/synthmorph_weights.h5"


def register(args):

    # ========================================================================== #
    #                      PARSE ARGS, CONFIGURE LOGGER                          #
    # ========================================================================== #

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    stdout_handler = logging.StreamHandler(stream=sys.stdout)
    # don't log errors, those get sent to stderr
    stdout_handler.addFilter(lambda x: x.levelno < logging.WARNING)
    logger.addHandler(stdout_handler)

    error_handler = logging.StreamHandler(stream=sys.stderr)
    error_handler.setLevel(logging.WARNING)
    logger.addHandler(error_handler)

    # ========================================================================== #
    #                        CONFIGURE LOGGING VERBOSITY                         #
    # ========================================================================== #

    if args.verbose:
        stdout_handler.setLevel(logging.INFO)
    else:
        stdout_handler.setLevel(logging.CRITICAL + 1)

    # ========================================================================== #
    #                              PATH LOGIC                                    #
    # ========================================================================== #

    assert os.path.exists(args.moving)

    results_dir = args.results_dir.rstrip("/")
    logger.info("Storing results in %s", results_dir)

    if os.path.exists(results_dir):
        if args.force:
            logger.info("Cleaning existing results directory")
            shutil.rmtree(results_dir)
            os.makedirs(results_dir)
        else:
            logger.warning(
                "Results directory already exists. Run again with -f or --force to override"
            )
            return
    else:
        os.makedirs(results_dir)

    if not os.path.exists(MODEL_WEIGHTS_PATH):
        logger.info("Downloading synthmorph weights to %s", MODEL_WEIGHTS_PATH)
        download_weights()

    # ========================================================================== #
    #                          INPUT VALIDATION                                  #
    # ========================================================================== #

    if args.skip_syn and args.skip_affine and args.skip_synthmorph:
        logger.warning(
            "All registration steps skipped. Run again with a registration step enabled"
        )
        return

    # ========================================================================== #
    #                      CONFIGURE LOG FILE HANDLER                            #
    # ========================================================================== #

    if args.log is None:
        result_name = args.results_dir.rstrip("/").split("/")[-1].split(".")[0]
        log_path = f"{results_dir}/{result_name}.log"
    else:
        log_path = args.log

    logger.info("Writing full logs to %s", log_path)

    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    logger.debug("Parsed args: %s", args)

    with h5py.File(f"{results_dir}/transform.h5", "w") as h5_handle:
        for arg_name, arg_val in vars(args).items():
            if arg_name != "func" and arg_val is not None:
                h5_handle.attrs[f"args.{arg_name}"] = arg_val

        # ========================================================================== #
        #                               LOAD IMAGES                                  #
        # ========================================================================== #

        logger.info("Loading moving image: %s", args.moving)
        moving_img = ants.image_read(args.moving)
        moving_md5sum = md5sum(args.moving)
        logger.info("Moving image hash: %s", moving_md5sum)
        logger.info("Moving image info: \n %s", repr(moving_img))

        h5_handle.attrs["moving.md5sum"] = moving_md5sum

        logger.info("Loading fixed image: %s", args.fixed)
        fixed_img = ants.image_read(args.fixed)
        fixed_md5sum = md5sum(args.fixed)
        logger.info("Fixed image hash: %s", fixed_md5sum)
        logger.info("Fixed image info: \n %s", repr(fixed_img))

        h5_handle.attrs["fixed.md5sum"] = fixed_md5sum

        # save fixed metadata, needed to define the physical to index transformation
        h5_handle.attrs["fixed.shape"] = fixed_img.shape
        h5_handle.attrs["fixed.origin"] = fixed_img.origin
        h5_handle.attrs["fixed.spacing"] = fixed_img.spacing
        h5_handle.attrs["fixed.direction"] = fixed_img.direction
        h5_handle.attrs["fixed.has_components"] = fixed_img.has_components

        synthmorph_mask = None

        if args.synthmorph_mask is not None:
            logger.info("Loading SynthMorph mask: %s", args.synthmorph_mask)
            synthmorph_mask = ants.image_read(args.synthmorph_mask)
            logger.info("SynthMorph mask hash: %s", md5sum(args.synthmorph_mask))

            if (
                not (
                    synthmorph_mask.shape == moving_img.shape
                    and synthmorph_mask.spacing == moving_img.spacing
                    and (synthmorph_mask.direction == moving_img.direction).all()
                )
                and args.downsample_to > 0
            ):
                logger.warning(
                    "Discrepancy between SynthMorph mask metadata and moving image metadata prior to resampling."
                )

            if args.downsample_to > 0:
                desired_spacing = (args.downsample_to,) * 3

                logger.info(
                    "Resampling moving SynthMorph mask. Current resolution: %s, Desired resolution: %s",
                    synthmorph_mask.spacing,
                    desired_spacing,
                )
                synthmorph_mask = ants.resample_image(
                    synthmorph_mask, desired_spacing, interp_type=3
                )

            if not (
                synthmorph_mask.shape == moving_img.shape
                and synthmorph_mask.spacing == moving_img.spacing
                and (synthmorph_mask.direction == moving_img.direction).all()
            ):
                logger.critical(
                    "Fatal discrepancy between SynthMorph mask metadata and moving image metadata."
                )
                raise RuntimeError(
                    "Fatal discrepancy between SynthMorph mask metadata and moving image metadata."
                )

            write_image(h5_handle, "/synthmorph_mask", synthmorph_mask)

        if args.downsample_to > 0:
            desired_spacing = (args.downsample_to,) * 3

            if moving_img.spacing != desired_spacing:
                logger.info(
                    "Resampling moving image. Current resolution: %s, Desired resolution: %s",
                    moving_img.spacing,
                    desired_spacing,
                )
                moving_img = ants.resample_image(
                    moving_img, desired_spacing, interp_type=3
                )

            if fixed_img.spacing != desired_spacing:
                logger.info(
                    "Resampling fixed image. Current resolution: %s, Desired resolution: %s",
                    fixed_img.spacing,
                    desired_spacing,
                )
                fixed_img = ants.resample_image(
                    fixed_img, desired_spacing, interp_type=3
                )

        # ========================================================================== #
        #                                  RESCALE                                   #
        # ========================================================================== #

        logger.info("Rescaling images")
        logger.info(
            "Moving intensity range: %s - %s", moving_img.min(), moving_img.max()
        )
        moving_img -= moving_img.min()
        moving_img /= moving_img.max()

        logger.info("Fixed intensity range: %s - %s", fixed_img.min(), fixed_img.max())
        fixed_img -= fixed_img.min()
        fixed_img /= fixed_img.max()

        # ========================================================================== #
        #                          HISTOGRAM EQUALIZATION                            #
        # ========================================================================== #

        if args.moving_clip_limit > 0:
            logger.info("Running moving CLAHE. Clip limit: %s", args.moving_clip_limit)

            moving_clahe = equalize_adapthist(
                moving_img.numpy(),
                kernel_size=args.clahe_kernel_size,
                clip_limit=args.moving_clip_limit,
            )

            moving_img = update_image_array(moving_img, moving_clahe)

        if args.fixed_clip_limit > 0:
            logger.info("Running fixed CLAHE. Clip limit: %s", args.fixed_clip_limit)

            fixed_clahe = equalize_adapthist(
                fixed_img.numpy(),
                kernel_size=args.clahe_kernel_size,
                clip_limit=args.fixed_clip_limit,
            )

            fixed_img = update_image_array(fixed_img, fixed_clahe)

        logger.debug("Histogram equalization complete")

        # ========================================================================== #
        #                                  AFFINE                                    #
        # ========================================================================== #

        if args.skip_affine:
            full_res_moving = moving_img
        else:

            logger.info("Running affine alignment")
            affine = ants.registration(
                fixed_img, moving_img, type_of_transform="Affine"
            )

            moving_img = affine["warpedmovout"]
            full_res_moving = moving_img

            if args.synthmorph_mask is not None:
                logger.info("Applying affine transform to SynthMorph mask")
                synthmorph_mask = ants.apply_transforms(
                    fixed_img, synthmorph_mask, transformlist=affine["fwdtransforms"]
                )

            # NOTE: for some inexplicable reason ants returns identical files
            # for forward and reverse transforms, so we need only store one
            # see: https://github.com/ANTsX/ANTsPy/issues/340
            write_affine(h5_handle, "/affine", affine["fwdtransforms"][0])

            # write intermediate result
            ants.image_write(moving_img, f"{results_dir}/registered.nii")
            logger.debug(
                "Wrote affine warpedmovout to %s", f"{results_dir}/registered.nii"
            )

            if args.keep_intermediates:
                shutil.copy(
                    f"{results_dir}/registered.nii", f"{results_dir}/affine.nii"
                )

        # ========================================================================== #
        #                           CALCULATE TRANSPOSITION                          #
        # ========================================================================== #

        assert moving_img.shape == fixed_img.shape

        optimal_transposition = np.argsort(moving_img.shape)
        inverse_transposition = np.argsort(optimal_transposition)
        transposed_shape = [moving_img.shape[idx] for idx in optimal_transposition]

        # ========================================================================== #
        #                              FIND MIRROR AXIS                              #
        # ========================================================================== #

        mirror_axis = None

        if args.mirror_warp:
            axis_rms = []

            for axis_idx in range(3):
                affine_img = moving_img.numpy()
                mirrored_img = np.flip(affine_img, axis_idx)

                axis_rms.append(np.sqrt(np.sum((affine_img - mirrored_img) ** 2)))

                logger.debug("Axis %s mirrored RMS: %s", axis_idx, axis_rms[-1])

            logger.info("Axis %s selected as mirror axis", np.argmin(axis_rms))

            transposed_axis_rms = [axis_rms[idx] for idx in optimal_transposition]
            mirror_axis = np.argmin(transposed_axis_rms)

        # ========================================================================== #
        #                        SYMMETRIC NORMALIZATION                             #
        # ========================================================================== #

        if not args.skip_syn:
            logger.info("Running SyN pre-registration")
            syn = ants.registration(fixed_img, moving_img, type_of_transform="SyN")

            moving_img = syn["warpedmovout"]
            full_res_moving = moving_img

            if args.synthmorph_mask is not None:
                logger.info("Applying SyN transform to SynthMorph mask")
                synthmorph_mask = ants.apply_transforms(
                    fixed_img, synthmorph_mask, transformlist=syn["fwdtransforms"]
                )

            h5_handle.create_group("/syn")

            # store affine alone to emphasize it's up you to compute it's inverse
            write_affine(h5_handle, "/syn/affine", syn["fwdtransforms"][1])

            write_image(h5_handle, "/syn/forward_warp", syn["fwdtransforms"][0])

            # write intermediate result, cleaning existing if it exists
            Path(f"{results_dir}/registered.nii").unlink(missing_ok=True)
            ants.image_write(moving_img, f"{results_dir}/registered.nii")
            logger.debug(
                "Wrote SyN warpedmovout to %s", f"{results_dir}/registered.nii"
            )

            if args.keep_intermediates:
                shutil.copy(f"{results_dir}/registered.nii", f"{results_dir}/syn.nii")

        # ========================================================================== #
        #                                SYNTHMORPH                                  #
        # ========================================================================== #

        if not args.skip_synthmorph:

            # ========================================================================== #
            #                                DOWNSAMPLE                                  #
            # ========================================================================== #

            logger.info(
                "Transposing moving from %s to %s", moving_img.shape, transposed_shape
            )
            moving_img = transpose_image(moving_img, optimal_transposition)

            logger.info(
                "Transposing fixed from %s to %s", fixed_img.shape, transposed_shape
            )
            fixed_img = transpose_image(fixed_img, optimal_transposition)

            logger.info(
                "Resampling moving from %s to %s", moving_img.shape, TARGET_SHAPE
            )
            moving_img = ants.resample_image(
                moving_img, TARGET_SHAPE, use_voxels=True, interp_type=3
            )

            logger.info("Resampling fixed from %s to %s", fixed_img.shape, TARGET_SHAPE)
            fixed_img = ants.resample_image(
                fixed_img, TARGET_SHAPE, use_voxels=True, interp_type=3
            )

            # ========================================================================== #
            #                                INFERENCE                                   #
            # ========================================================================== #

            logger.info("Starting downsampled inference")

            moving = moving_img.numpy().reshape((1,) + moving_img.shape + (1,))
            logger.debug("Moving shape: %s", moving.shape)

            fixed = fixed_img.numpy().reshape((1,) + fixed_img.shape + (1,))
            logger.debug("Fixed volfile shape: %s", fixed.shape)

            inshape = moving.shape[1:-1]
            nb_feats = moving.shape[-1]

            with tf.device(DEVICE):
                # load model
                model = vxm.networks.VxmDense.load(MODEL_WEIGHTS_PATH)

                logger.info("Running inference")

                # run inference
                warp = model.register(moving, fixed)

                # symmetrize warp
                if args.mirror_warp:
                    flipped_warp = np.flip(warp, mirror_axis + 1)
                    mirrored_warp = np.mean([warp, flipped_warp], axis=0)
                    mirrored_warp[:, :, :, :, mirror_axis] = np.mean(
                        [warp, -flipped_warp], axis=0
                    )[:, :, :, :, mirror_axis]
                    warp = mirrored_warp

                moved = vxm.networks.Transform(inshape, nb_feats=nb_feats).predict(
                    [moving, warp]
                )

                moving = moved

            # ========================================================================== #
            #                       UPSAMPLE WARP AND APPLY                              #
            # ========================================================================== #

            logger.info("Upsampling warp")

            warp = warp.squeeze()

            full_res_moving = transpose_image(full_res_moving, optimal_transposition)

            upsampled_warp = np.zeros(full_res_moving.shape + (3,))
            logger.debug("Upsampled warp shape: %s", upsampled_warp.shape)

            for idx in range(3):
                rescale_factor = full_res_moving.shape[idx] / TARGET_SHAPE[idx]
                upsampled_warp[:, :, :, idx] = (
                    ants.resample_image(
                        ants.from_numpy(warp[:, :, :, idx]),
                        full_res_moving.shape,
                        True,
                        0,
                    ).numpy()
                    * rescale_factor
                )

            h5_handle.create_dataset(
                "/synthmorph",
                data=upsampled_warp,
                chunks=True,
                compression="gzip",
                compression_opts=9,
                shuffle=True,
                fletcher32=True,
            )

            logger.info("Applying upsampled warp")

            with tf.device(DEVICE):
                transform = vxm.networks.Transform(full_res_moving.shape, nb_feats=1)
                warped = transform.predict(
                    [
                        full_res_moving.numpy().reshape(
                            (1,) + full_res_moving.shape + (1,)
                        ),
                        upsampled_warp.reshape((1,) + upsampled_warp.shape),
                    ]
                ).squeeze()

            if args.synthmorph_mask is not None:
                synthmorph_mask = (
                    transpose_image(synthmorph_mask, optimal_transposition).numpy() > 0
                )
                warped[synthmorph_mask] = full_res_moving[synthmorph_mask]

            warped = transpose_image(ants.from_numpy(warped), inverse_transposition)
            warped.set_spacing(full_res_moving.spacing)

            # write final result, removing the intermediate result if it exists
            Path(f"{results_dir}/registered.nii").unlink(missing_ok=True)
            ants.image_write(warped, f"{results_dir}/registered.nii")
            logger.debug(
                "Wrote final SynthMorph transformed image to %s",
                f"{results_dir}/registered.nii",
            )
