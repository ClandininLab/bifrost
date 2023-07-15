# bifrost

Template building and multi-modal registration

# System Requirements

## Hardware Requirements

Image registration is a memory-intensive computation, with memory
requirements scaling roughly linearly with the number of voxels in your image.
For example, 128 GB of memory is sufficient for 32-bit images of shape (1652,
768, 479).

`bifrost` makes use of all available cores. Note that determinism is only
guaranteed when running in single-threaded mode.

## Software requirements

`bifrost` fully supports *nix and was tested on CentOS 7 running Python 3.9.0.
Windows and MacOS are not officially supported, although it is likely possible
to install `bifrost` on these platforms. A
[docker](https://docs.docker.com/get-started/) image is provided which can be
used on all platforms.

Python >=3.8  is required.

Refer to `setup.py` for a full list of dependencies.

# Installation

```
pip install git+ssh://git@github.com/ClandininLab/bifrost.git
```

Installation takes about two minutes on a computer with a fast internet
connection and an empty `pip` cache.

# Docker

Build the BIFROST docker image by running

```
docker build /path/to/bifrost-repo --tag bifrost:latest
```

You can then drop into a shell in a ready to go environment with

```
docker run --name bifrost --rm -it bifrost:latest bash
```

# Usage

We provide a `bifrost` executable providing direct access to our tooling and a
[Snakemake](https://snakemake.readthedocs.io/en/stable/) workflow which
implements the BIFROST pipeline, handling plumbing and distributed execution.

## Using the executable

The `bifrost` executable, which is installed by `pip`, provides interfaces to all BIFROST logic.
There are  three subcommands:

- `bifrost register`
- `bifrost transform`
- `bifrost build_template`

`bifrost register` computes the transformation between two
images using SynthMorph and uses it to register them. `bifrost transform`
applies that transform to other images. `bifrost build_template` builds a
statistically representative "mean image" from a series of individual images
which often registers more accurately to a reference template than the
individual images.

See the interactive help for each subcommand for detailed usage intructions.

## The BIFROST pipeline

The BIFROST pipeline registers images from a dataset of $N$ samples with $M$
channels and an arbitrary number of timepoints into the space of the Functional
Drosophila Atlas (FDA) which was published as part of the BIFROST paper. We provide an
implementation of the BIFROST pipeline in the form of an easy to use
[Snakemake](https://snakemake.readthedocs.io/en/stable/) workflow that
transparently scales from single-node to cluster execution.

The BIFROST pipeline consists of the following steps:

1. A representative "mean" template is created from the structural images of each sample
2. Each structural image is independently registered to the template, producing a transform from each sample to the shared template
3. The template is registered to the FDA, producing a transform from the shared template to the FDA
4. Each dependent image for each sample is transformed in sequence into the space of the shared template and then FDA using the transforms computed in the previous two steps

Steps which do not depend on each other proceed in parallel so long as
sufficient resources are available.

A toy dataset with two samples, a single channel and a single dependent image for each sample has the following dependency graph:

![The dependency DAG for this dataset](assets/simple_dag.svg)

In this example a maximum of three steps execute simultaneously.


The degree of parallelism increases dramatically for more realistic datasets. For instance, this is the dependency graph for the (still unrealistically small) demo dataset:

![The dependency DAG for the demo dataset](assets/demo_dag.svg)

For a dataset with $N$ samples, $M$ channels each of which has $K$ dependent
images there are $2 + N + 2 N K M$ steps in the pipelin. Up to $1 + N K M$ steps
can proceed in parallel. As each step can take on the order of an hour to
complete, serial execution would be prohibitively slow. The beauty of Snakemake
is that it transparently orchestrates the distributed execution of the pipeline
on your favorite cluster/cloud platform.


### Data requirements

You must provide your data as NIfTI images with accurate metadata. NIfTI
metadata includes a specification of the transformation between voxel-space and
anatomical space, which is used during registration. In our experience the vast
majority of registration falures are caused by incorrect metadata.

In order to be correctly parsed by the Snakemake workflow you must follow a
prescribed directory structure. Under your top-level dataset directory there
must be a directory named `templates` containing only the FDA and a directory
`data`. `data` contains $N$ arbitrarily named directories, one for each sample.
Each sample directory must contain a structural image file
`structural_image.nii` and can contain any number of arbitrarily named channel
directories. Each channel directory can contain any number of arbitrarily named
NIfTI images (the `.nii` suffix is mandatory).

The channel images are dependent upon the structural image and assumed to be
motion-corrected and perfectly aligned to it.

Some examples:


The toy dataset used to generate the first image:
```
toy_dataset
├── data
│   ├── sample_1
│   │   ├── channel_1
│   │   │   └── dependent_image.nii
│   │   └── structural_image.nii
│   └── sample_2
│       ├── channel_1
│       │   └── dependent_image.nii
│       └── structural_image.nii
└── templates
    └── FDA.nii
```

The demo dataset:
```
demo_dataset
├── data
│   ├── fly_1
│   │   ├── green
│   │   │   └── lc11.nii
│   │   └── structural_image.nii
│   ├── fly_2
│   │   ├── green
│   │   │   └── lc11.nii
│   │   └── structural_image.nii
│   ├── fly_3
│   │   ├── green
│   │   │   └── lc11.nii
│   │   └── structural_image.nii
│   ├── fly_4
│   │   ├── green
│   │   │   └── lc11.nii
│   │   └── structural_image.nii
│   ├── fly_5
│   │   ├── green
│   │   │   └── lc11.nii
│   │   └── structural_image.nii
│   ├── fly_6
│   │   ├── green
│   │   │   └── lc11.nii
│   │   └── structural_image.nii
│   ├── fly_7
│   │   ├── green
│   │   │   └── lc11.nii
│   │   └── structural_image.nii
│   ├── fly_8
│   │   ├── green
│   │   │   └── lc11.nii
│   │   └── structural_image.nii
│   └── fly_9
│       ├── green
│       │   └── lc11.nii
│       └── structural_image.nii
└── templates
    └── FDA.nii
```

Channel and images names are arbitrary and not shared across samples:

```
example
├── data
│   ├── foo
│   │   ├── channel_bar
│   │   │   ├── img_1.nii
│   │   │   └── img_2.nii
│   │   ├── channel_foo
│   │   │   ├── image_1.nii
│   │   │   ├── image_2.nii
│   │   │   └── image_3.nii
│   │   └── structural_image.nii
│   ├── bar
│   │   ├── qux
│   │   │   ├── image_1.nii
│   │   │   └── image_2.nii
│   │   └── structural_image.nii
│   └── baz
│       └── structural_image.nii
└── templates
    └── FDA.nii
```

### Usage

To use the pipeline you must install the `bifrost` using `pip` _and_ clone this
repository to a location of your choice. This is because `snakemake` must be
executed from within a directory containing a `Snakefile`.

#### Single-node execution

To run the pipeline in single-node mode using up to 16 cores, run the following command
from within the `pipeline` directory of this repo.

```
snakemake --cores 16 --directory /path/to/your/dataset
```

#### Distributed execution

To execute the pipeline on a Slurm cluster modify the `MAX_THREADS` value in
`pipeline/Snakefile` and the account, partition and memory values in
`pipeline/cluster_profile/config.yaml` as needed.

The pipeline can then be executed using at most 64 jobs in parallel by running the following command from within
the `pipeline` directory of this repo

```
snakemake --slurm --jobs 64 --profile cluster_profile --directory /path/to/your/dataset
```

You can submit an unlimited number of jobs in parallel by setting `--jobs all`
if you dare tempt the wrath of your cluster admin.

Please refer to the Snakemake docs for instructions on how to execute the
pipeline on
[cloud](https://snakemake.readthedocs.io/en/stable/executing/cloud.html)
resources and other
[cluster](https://snakemake.readthedocs.io/en/stable/executing/cluster.html)
scheduling systems.


# Demo

The demo dataset is included in this repository. Install [git
lfs](https://git-lfs.com/) prior to cloning this repository to download it, or
install it and run `git lfs pull` if you have already cloned the repo.

Once you have unpacked `demo_dataset.tar.gz` to a location of your choice, you
can run the demo by `cd`ing to `pipeline/` and running

```
snakemake --cores all --directory /path/to/demo_dataset
```

This takes about 3 minutes to run on a node with 16 cores.

If all went well, the output of `tree /path/to/demo_dataset` will be

```
demo_dataset
├── data
│   ├── fly_1
│   │   ├── green
│   │   │   └── lc11.nii
│   │   └── structural_image.nii
│   ├── fly_2
│   │   ├── green
│   │   │   └── lc11.nii
│   │   └── structural_image.nii
│   ├── fly_3
│   │   ├── green
│   │   │   └── lc11.nii
│   │   └── structural_image.nii
│   ├── fly_4
│   │   ├── green
│   │   │   └── lc11.nii
│   │   └── structural_image.nii
│   ├── fly_5
│   │   ├── green
│   │   │   └── lc11.nii
│   │   └── structural_image.nii
│   ├── fly_6
│   │   ├── green
│   │   │   └── lc11.nii
│   │   └── structural_image.nii
│   ├── fly_7
│   │   ├── green
│   │   │   └── lc11.nii
│   │   └── structural_image.nii
│   ├── fly_8
│   │   ├── green
│   │   │   └── lc11.nii
│   │   └── structural_image.nii
│   └── fly_9
│       ├── green
│       │   └── lc11.nii
│       └── structural_image.nii
├── logs
│   ├── build_template.log
│   ├── register_structural_images_to_template_fly_1.log
│   ├── register_structural_images_to_template_fly_2.log
│   ├── register_structural_images_to_template_fly_3.log
│   ├── register_structural_images_to_template_fly_4.log
│   ├── register_structural_images_to_template_fly_5.log
│   ├── register_structural_images_to_template_fly_6.log
│   ├── register_structural_images_to_template_fly_7.log
│   ├── register_structural_images_to_template_fly_8.log
│   ├── register_structural_images_to_template_fly_9.log
│   ├── register_template_to_fda.log
│   ├── transform_dependent_images_to_fda_fly_1_green_lc11.log
│   ├── transform_dependent_images_to_fda_fly_2_green_lc11.log
│   ├── transform_dependent_images_to_fda_fly_3_green_lc11.log
│   ├── transform_dependent_images_to_fda_fly_4_green_lc11.log
│   ├── transform_dependent_images_to_fda_fly_5_green_lc11.log
│   ├── transform_dependent_images_to_fda_fly_6_green_lc11.log
│   ├── transform_dependent_images_to_fda_fly_7_green_lc11.log
│   ├── transform_dependent_images_to_fda_fly_8_green_lc11.log
│   ├── transform_dependent_images_to_fda_fly_9_green_lc11.log
│   ├── transform_dependent_images_to_template_fly_1_green_lc11.log
│   ├── transform_dependent_images_to_template_fly_2_green_lc11.log
│   ├── transform_dependent_images_to_template_fly_3_green_lc11.log
│   ├── transform_dependent_images_to_template_fly_4_green_lc11.log
│   ├── transform_dependent_images_to_template_fly_5_green_lc11.log
│   ├── transform_dependent_images_to_template_fly_6_green_lc11.log
│   ├── transform_dependent_images_to_template_fly_7_green_lc11.log
│   ├── transform_dependent_images_to_template_fly_8_green_lc11.log
│   └── transform_dependent_images_to_template_fly_9_green_lc11.log
├── results
│   ├── template.nii
│   ├── template_to_fda
│   │   ├── registered.nii
│   │   └── transform.h5
│   └── transformed_images
│       ├── fly_1
│       │   └── green
│       │       └── lc11.nii
│       ├── fly_2
│       │   └── green
│       │       └── lc11.nii
│       ├── fly_3
│       │   └── green
│       │       └── lc11.nii
│       ├── fly_4
│       │   └── green
│       │       └── lc11.nii
│       ├── fly_5
│       │   └── green
│       │       └── lc11.nii
│       ├── fly_6
│       │   └── green
│       │       └── lc11.nii
│       ├── fly_7
│       │   └── green
│       │       └── lc11.nii
│       ├── fly_8
│       │   └── green
│       │       └── lc11.nii
│       └── fly_9
│           └── green
│               └── lc11.nii
└── templates
    └── FDA.nii

42 directories, 60 files
```

# Reference

If you found this tool useful lease cite the BIFROST paper.
