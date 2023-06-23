""" Logic for template building

Execute using the 'bifrost' executable installed by setuptools
"""

import logging
import os
import shutil
import sys
from glob import glob

import ants
import numpy as np
import scipy
from skimage.exposure import equalize_adapthist
from skimage.filters import threshold_triangle as triangle
from sklearn.preprocessing import quantile_transform

from bifrost.util import update_image_array


def build_template(args):

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

    try:

        # ========================================================================== #
        #                              PATH LOGIC                                    #
        # ========================================================================== #

        input_paths = []

        for input_path in args.input:
            assert os.path.exists(input_path)

            if os.path.isdir(input_path):
                input_paths.extend(
                    [
                        f"{input_path}/{input_file}"
                        for input_file in os.listdir(input_path)
                    ]
                )
            else:
                input_paths.append(input_path)

        logger.debug("Parsed input files: %s", input_paths)

        if args.reference_image is not None:
            assert os.path.exists(args.reference_image)

        if os.path.exists(args.output):
            if args.force:
                logger.info("Cleaning existing results directory")
                shutil.rmtree(args.output)
            elif args.preemptible:
                logger.info("Resuming existing work")
            else:
                logger.warning(
                    "Results directory already exists. Run again with --force to override or --preemptible to resume"
                )
                return

        os.makedirs(args.output, exist_ok=True)
        os.makedirs(f"{args.output}/preprocessed", exist_ok=True)
        os.makedirs(f"{args.output}/templates", exist_ok=True)
        os.makedirs(f"{args.output}/scratch", exist_ok=True)

        # ========================================================================== #
        #                      CONFIGURE LOG FILE HANDLER                            #
        # ========================================================================== #

        if args.log is None:
            log_path = f"{args.output}/build_template.log"
        else:
            log_path = args.log

        logger.info("Writings logs to %s", log_path)

        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)

        logger.addHandler(file_handler)

        logger.debug("Parsed args: %s", args)

        # ==================================================================== #
        #                             PREPROCESSING                            #
        # ==================================================================== #

        logger.info(
            "Preprocessing flies: %s",
            [os.path.basename(input_path) for input_path in input_paths],
        )

        for input_path in input_paths:
            name = os.path.basename(input_path).split(".")[0]
            output_path = f"{args.output}/preprocessed/{name}.nii"

            if not os.path.exists(output_path):
                logger.info("Preprocessing %s", name)
                preprocess(args, input_path, output_path)
            else:
                logger.info("%s already preprocessed", name)

        # ========================================================================== #
        #                                  AFFINE                                    #
        # ========================================================================== #

        if args.reference_image is not None:
            initial_image = args.reference_image
        else:
            initial_image = input_paths[0]

        logger.info("Starting affine step 0")
        alignment_iteration(
            args,
            moving_dir=f"{args.output}/preprocessed",
            step_name="affine_0",
            fixed_path=initial_image,
            type_of_transform="Affine",
            transform_avg=False,
            mirror=args.mirror,
        )

        for affine_step in range(1, args.affine_steps):
            logger.info("Starting affine step %s", affine_step)

            alignment_iteration(
                args,
                moving_dir=f"{args.output}/scratch/affine_{affine_step - 1}",
                step_name=f"affine_{affine_step}",
                fixed_path=f"{args.output}/templates/affine_{affine_step - 1}.nii",
                type_of_transform="Affine",
                transform_avg=False,
                mirror=False,
            )

        # ========================================================================== #
        #                                    SyN                                     #
        # ========================================================================== #

        logger.info("Starting SyN step 0")

        alignment_iteration(
            args,
            moving_dir=f"{args.output}/scratch/affine_{args.affine_steps - 1}",
            step_name="syn_0",
            fixed_path=f"{args.output}/templates/affine_{args.affine_steps - 1}.nii",
            type_of_transform="SyN",
            transform_avg=True,
            mirror=False,
        )

        for syn_step in range(1, args.syn_steps):
            logger.info("Starting SyN step %s", syn_step)

            alignment_iteration(
                args,
                moving_dir=f"{args.output}/scratch/syn_{syn_step - 1}",
                step_name=f"syn_{syn_step}",
                fixed_path=f"{args.output}/templates/syn_{syn_step - 1}.nii",
                type_of_transform="SyN",
                transform_avg=True,
                mirror=False,
            )

        logger.info("Cleaning up")

        shutil.move(
            f"{args.output}/templates/syn_{args.syn_steps - 1}.nii",
            f"{args.output}/template.nii",
        )

        if args.keep_intermediates:
            # add back symlink for the final result which was moved
            os.symlink(
                f"{args.output}/template.nii",
                f"{args.output}/templates/syn_{args.syn_steps}.nii",
            )
        else:
            shutil.rmtree(f"{args.output}/preprocessed")
            shutil.rmtree(f"{args.output}/templates")

        logger.info("Template generation complete")

    except:
        logger.exception("Caught general exception")
        raise

    finally:
        logger.info("Exiting, cleaning scratch")
        shutil.rmtree(f"{args.output}/scratch")


def preprocess(args, input_path, output_path):
    """Runs all preprocessing"""
    image = ants.image_read(input_path)

    if args.preprocessing is None:
        shutil.copy(input_path, output_path)
        return

    if "legacy" in args.preprocessing:
        image = __legacy_preprocess(image)

    if "CLAHE" in args.preprocessing:
        image -= image.min()
        image /= image.max()

        image = update_image_array(
            image, equalize_adapthist(image.numpy(), kernel_size=64, clip_limit=0.03)
        )

    ants.image_write(image, output_path)


def __legacy_preprocess(image):
    """Legacy preprocessing"""

    image_arr = image.numpy()

    # Blur brain and mask small values
    image_copy = image_arr.copy().astype("float32")
    image_copy = scipy.ndimage.gaussian_filter(image_copy, sigma=10)
    threshold = triangle(image_copy)
    image_copy[np.where(image_copy < threshold / 2)] = 0

    # Remove blobs outside contiguous brain
    labels, label_nb = scipy.ndimage.label(image_copy)
    image_label = np.bincount(labels.flatten())[1:].argmax() + 1
    image_copy = image_arr.copy().astype("float32")
    image_copy[np.where(labels != image_label)] = np.nan

    # Perform quantile normalization
    image_copy = quantile_transform(
        image_copy.flatten().reshape(-1, 1), n_quantiles=500, random_state=0
    )
    image_copy = image_copy.reshape(image_arr.shape)

    return update_image_array(image, np.nan_to_num(image_copy))


def generate_template(args, step_name, output_path, transform_avg):
    """Generates template from registration results

    Depending on the experiment type this either averages the images directly or 'averages' their transformations
    """
    logger = logging.getLogger(__name__)
    __retries = 0

    assert output_path.endswith(".nii")

    while True:
        try:
            input_path = f"{args.output}/scratch/{step_name}"

            # 'average' transformations
            #
            # NOTE: a shortcoming of this method is that the affine transform is assumed to be nearly the identity
            #  ie, it is ignored entirely
            # there doesn't seem to be a well defined method to average affine transformations
            # however, much work has been done on averaging quaternions
            # it is also unclear whether averaging the 'diffeomorphic' warp is well-defined
            # it is, at least, a crude hack as implemented (https://github.com/ANTsX/ANTsPy/issues/125)
            #
            if transform_avg:
                transform_dir = f"{args.output}/scratch/{step_name}_transform"

                if os.path.exists(f"{transform_dir}/transform.nii"):
                    logger.info("%s: found existing inverse average transform")
                    avg_img = __average_images(f"{input_path}/*.nii")
                else:
                    os.makedirs(transform_dir, exist_ok=True)

                    avg_img = __average_images(f"{input_path}/*.nii")
                    avg_transform = __average_images(f"{input_path}/*.nii.gz")

                    # this could only ever be construed as an inverse if you squint, a lot
                    inv_avg_transform = avg_transform * -1 * args.gradient_step

                    ants.image_write(
                        inv_avg_transform, f"{transform_dir}/transform.nii"
                    )

                template = ants.apply_transforms(
                    avg_img, avg_img, f"{transform_dir}/transform.nii"
                )

                ants.image_write(template, output_path)

            # average images directly
            else:
                template = __average_images(f"{input_path}/*.nii")
                ants.image_write(template, output_path)

            break
        except Exception as exc:
            if __retries < 2:
                logger.exception("Caught exception, retrying")

                __clean_template(output_path)
                __retries += 1
            else:
                logger.exception("Caught exception, max retries reached")
                raise exc


def alignment_iteration(
    args,
    moving_dir,
    step_name,
    fixed_path,
    type_of_transform,
    transform_avg,
    mirror,
):
    logger = logging.getLogger(__name__)
    __retries = 0

    step_dir = f"{args.output}/scratch/{step_name}"
    os.makedirs(step_dir, exist_ok=True)

    if os.path.exists(f"{args.output}/templates/{step_name}.nii"):
        logger.info(f"{step_name} template already exists")
        return

    fixed = ants.image_read(fixed_path)

    for input_path in glob(f"{moving_dir}/*.nii"):
        input_name = None

        while True:
            try:
                input_name = input_path.split("/")[-1].split(".")[0]

                if __step_output_exists(input_name, step_dir, transform_avg, False):
                    logger.info(
                        "%s: found existing work for %s ", step_name, input_name
                    )
                else:
                    logger.info("%s: processing %s", step_name, input_name)

                    moving = ants.image_read(input_path)

                    registration = ants.registration(
                        fixed, moving, type_of_transform=type_of_transform
                    )

                    __write_step_output(
                        registration,
                        input_name,
                        step_dir,
                        write_transform=transform_avg,
                        mirror=False,
                    )

                if mirror:
                    if __step_output_exists(input_name, step_dir, transform_avg, True):
                        logger.info(
                            "%s: found existing work for input %s mirror",
                            step_name,
                            input_name,
                        )
                    else:
                        logger.info(
                            "%s: processing input %s mirror", step_name, input_name
                        )

                        moving_mirror = update_image_array(moving, moving[::-1])

                        registration_mirror = ants.registration(
                            fixed, moving_mirror, type_of_transform=type_of_transform
                        )

                        __write_step_output(
                            registration_mirror,
                            input_name,
                            step_dir,
                            write_transform=transform_avg,
                            mirror=True,
                        )
                break
            except Exception as exc:
                if __retries < 2:
                    logger.exception(
                        "Caught exception processing input %s, retrying", input_name
                    )

                    __clean_step_output(input_name, step_dir, mirror)
                    __retries += 1
                else:
                    logger.exception(
                        "Caught exception processing input %s, max retries reached",
                        input_name,
                    )
                    raise exc

    logger.info("Generating new template for  %s", step_name)
    generate_template(
        args,
        step_name=step_name,
        output_path=f"{args.output}/templates/{step_name}.nii",
        transform_avg=transform_avg,
    )

    logger.info("Finished %s", step_name)


def __average_images(pattern):
    img_paths = glob(pattern)

    img_0 = ants.image_read(img_paths[0])
    avg_img = img_0.numpy() / len(img_paths)

    for img_path in img_paths[1:]:
        avg_img += ants.image_read(img_path).numpy() / len(img_paths)

    return update_image_array(img_0, avg_img)


def __write_step_output(registration, input_name, step_dir, write_transform, mirror):
    suffix = ""
    if mirror:
        suffix = "_m"

    ants.image_write(
        registration["warpedmovout"],
        f"{step_dir}/{input_name}{suffix}.nii",
    )

    if write_transform:
        shutil.copy(
            registration["fwdtransforms"][0],
            f"{step_dir}/{input_name}{suffix}_t.nii.gz",
        )


def __step_output_exists(input_name, step_dir, write_transform, mirror):
    suffix = ""
    if mirror:
        suffix = "_m"

    if not os.path.exists(f"{step_dir}/{input_name}{suffix}.nii"):
        return False

    if write_transform and not os.path.exists(
        f"{step_dir}/{input_name}{suffix}_t.nii.gz"
    ):
        return False

    return True


def __clean_step_output(input_name, step_dir, mirror):
    suffix = ""
    if mirror:
        suffix = "_m"

    try:
        os.remove(f"{step_dir}/{input_name}{suffix}.nii")
    except FileNotFoundError:
        pass

    try:
        os.remove(f"{step_dir}/{input_name}{suffix}_t.nii.gz")
    except FileNotFoundError:
        pass


def __clean_template(template_path):
    try:
        os.remove(template_path)
    except FileNotFoundError:
        pass
