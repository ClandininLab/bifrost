""" Dispatch logic for all BIFROST tools

Execute using the 'bifrost' executable installed by setuptools
"""

import argparse
import sys

from bifrost.util import SubcommandHelpFormatter


def main():
    parser = argparse.ArgumentParser(
        description="BIFROST: template building and cross-modal registration",
        epilog="If you find this tool useful, please cite the BIFROST paper",
        formatter_class=SubcommandHelpFormatter,
    )
    subparsers = parser.add_subparsers(
        required=True, title="available commands", metavar="\b"
    )

    parser_register = subparsers.add_parser(
        "register",
        description="register two images and save the transform",
        help="cross-modal image registration",
        epilog="If you find this tool useful, please cite [INSERT FINAL CITATION]",
    )
    parser_register.set_defaults(func=register_dispatch)

    parser_transform = subparsers.add_parser(
        "transform",
        description="applies a transform computed by the 'bifrost register' command",
        help="apply bifrost transform",
        epilog="If you find this tool useful, please cite [INSERT FINAL CITATION]",
    )
    parser_transform.set_defaults(func=transform_dispatch)

    parser_build_template = subparsers.add_parser(
        "build_template",
        description="computes a statistically representative template from a series of structural images",
        help="average several images into a representative template",
        epilog="If you find this tool useful, please cite [INSERT FINAL CITATION]",
    )
    parser_build_template.set_defaults(func=build_template_dispatch)

    # ======================================= #
    #              REGISTER ARGS            = #
    # ======================================= #

    moving_help = "Absolute path to moving image"
    parser_register.add_argument("moving", help=moving_help)

    fixed_help = "Absolute path to fixed image"
    parser_register.add_argument("fixed", help=fixed_help)

    results_dir_help = "Absolute path to write results"
    parser_register.add_argument("results_dir", help=results_dir_help)

    clahe_kernel_size_help = (
        "Kernel size for contrast-limited adaptive histogram equalization. "
        "See https://scikit-image.org/docs/stable/api/skimage.exposure.html#skimage.exposure.equalize_hist for details"
    )
    parser_register.add_argument(
        "--clahe_kernel_size", help=clahe_kernel_size_help, default=None, type=int
    )

    fixed_clip_limit_help = (
        "Clip limit for fixed image CLAHE. Higher values giver more contrast. "
        "By default, CLAHE is not run on the fixed image. \n"
        "See https://scikit-image.org/docs/stable/api/skimage.exposure.html#skimage.exposure.equalize_hist for details"
    )
    parser_register.add_argument(
        "--fixed_clip_limit", help=fixed_clip_limit_help, default=-1, type=float
    )

    moving_clip_limit_help = (
        "Clip limit for moving image CLAHE. Higher values giver more contrast. "
        "Set to -1 to disable \n"
        "See https://scikit-image.org/docs/stable/api/skimage.exposure.html#skimage.exposure.equalize_hist for details"
    )
    parser_register.add_argument(
        "--moving_clip_limit", help=moving_clip_limit_help, default=0.03, type=float
    )

    skip_syn_help = "Skip symmetric normalization pre-registration"
    parser_register.add_argument("--skip_syn", help=skip_syn_help, action="store_true")

    skip_affine_help = "Skip affine, images must be pre-aligned. Ignored if affine initialization is enabled"
    parser_register.add_argument(
        "--skip_affine", help=skip_affine_help, action="store_true"
    )

    skip_synthmorph_help = "Skip synthmorph inference"
    parser_register.add_argument(
        "--skip_synthmorph", help=skip_synthmorph_help, action="store_true"
    )

    downsample_to_help = "Isotropic resolution to downsample full-res to, before doing anything. Microns. "
    parser_register.add_argument(
        "--downsample_to", help=downsample_to_help, default=-1, type=float
    )

    synthmorph_mask_help = "Path to SynthMorph warp mask, of same shape as moving"
    parser_register.add_argument("--synthmorph_mask", help=synthmorph_mask_help)

    mirror_help = "Mirror warp. Axis selected automatically based on similarity"
    parser_register.add_argument("--mirror_warp", help=mirror_help, action="store_true")

    keep_intermediates_help = (
        "Keep intermediate results. By default only the final template is retained. "
        "Useful for diagnosing registration problems."
    )
    parser_register.add_argument(
        "--keep_intermediates", help=keep_intermediates_help, action="store_true"
    )

    force_help = "Force override of results directory, if it already exists"
    parser_register.add_argument("-f", "--force", help=force_help, action="store_true")

    log_help = "Desired log file. By default logs are written to output directory"
    parser_register.add_argument("-l", "--log", help=log_help, default=None)

    verbose_help = "Print info to stdout. By default, only errors are emitted."
    parser_register.add_argument(
        "-v", "--verbose", help=verbose_help, action="store_true"
    )

    # ======================================= #
    #              TRANSFORM ARGS           = #
    # ======================================= #

    alignment_path_help = 'Absolute path to BIFROST registration RESULTS_DIR. Must contain a "transform.h5" file'
    parser_transform.add_argument("alignment_path", help=alignment_path_help)

    image_path_help = "Absolute path to image to transform"
    parser_transform.add_argument("image_path", help=image_path_help)

    label_image_help = "Set if image is a label image (ROIs). Uses interpolation methods that preserve labels"
    parser_transform.add_argument(
        "--label_image", help=label_image_help, action="store_true"
    )

    apply_preprocessing_help = (
        "Set this to exactly reproduce the net result of the original registration. "
        "By default only the spatial transformation is applied, setting this option includes the preprocessing steps."
    )
    parser_transform.add_argument(
        "--apply_preprocessing", help=apply_preprocessing_help, action="store_true"
    )

    result_name_help = (
        "Overrides default result name if specified. "
        "Interpreted as path if prefixed with `\\` or `.\\`, "
        "otherwise interpreted as name and written to ALIGNMENT_PATH"
    )
    parser_transform.add_argument("--result_name", help=result_name_help, type=str)

    log_help = "Desired log file. By default logs are written to output directory."
    parser_transform.add_argument("-l", "--log", help=log_help, default=None)

    verbose_help = "Print info to stdout. By default, only errors are emitted."
    parser_transform.add_argument(
        "-v", "--verbose", help=verbose_help, action="store_true"
    )

    # ======================================= #
    #            BUILD TEMPLATE ARGS        = #
    # ======================================= #

    input_path_help = "Absolute path(s) to structural images or directorie(s) containing them. NIfTIs only"
    parser_build_template.add_argument(
        "--input", help=input_path_help, required=True, nargs="+"
    )

    output_path_help = "Absolute path to output directory, created"
    parser_build_template.add_argument("--output", help=output_path_help, required=True)

    reference_image_help = (
        "Absolute path to reference image used as fixed for the first alignment step. "
        "Should be symmetrical across the x axis. Thereafter the mean from the previous step is used as fixed. "
        "If not specified an image is chosen arbitarily."
    )
    parser_build_template.add_argument("--reference_image", help=reference_image_help)

    affine_steps_help = "Number of affine alignment steps"
    parser_build_template.add_argument(
        "--affine_steps", help=affine_steps_help, default=1, type=int
    )

    syn_steps_help = "Number of SyN alignment steps"
    parser_build_template.add_argument(
        "--syn_steps", help=syn_steps_help, default=3, type=int
    )

    gradient_step_help = "Shape update gradient step size."
    parser_build_template.add_argument(
        "--gradient_step", help=gradient_step_help, default=0.1, type=float
    )

    preprocessing_help = "Preprocessing steps to perform. Insensitive to argument order"
    parser_build_template.add_argument(
        "--preprocessing",
        help=preprocessing_help,
        action="extend",
        nargs="+",
        choices=["CLAHE", "legacy"],
        type=str,
    )

    mode_group = parser_build_template.add_mutually_exclusive_group()

    force_help = "Force override of output directory, if it already exists"
    mode_group.add_argument("-f", "--force", help=force_help, action="store_true")

    resume_help = "Don't clean results directory and resume existing work. Useful when running on a preemptible node."
    mode_group.add_argument("--preemptible", help=resume_help, action="store_true")

    mirror_help = "Mirror input images across the x axis."
    parser_build_template.add_argument(
        "--mirror", help=mirror_help, action="store_true"
    )

    keep_intermediates_help = (
        "Keep intermediate results. By default only the final template is retained."
    )
    parser_build_template.add_argument(
        "--keep_intermediates", help=keep_intermediates_help, action="store_true"
    )

    log_help = "Desired log file. By default logs are written to output directory"
    parser_build_template.add_argument("-l", "--log", help=log_help, default=None)

    verbose_help = "Print info to stdout. By default, only errors are emitted."
    parser_build_template.add_argument(
        "-v", "--verbose", help=verbose_help, action="store_true"
    )

    # ======================================= #
    #           PARSE ARGS, DISPATCH        = #
    # ======================================= #

    if len(sys.argv) == 1:
        parser.print_help()
    else:
        args = parser.parse_args()

        args.func(args)


def register_dispatch(args):
    from bifrost.cli.register import register

    register(args)


def transform_dispatch(args):
    from bifrost.cli.apply_transform import transform

    transform(args)


def build_template_dispatch(args):
    from bifrost.cli.build_template import build_template

    build_template(args)
