#!/bin/bash
#
#SBATCH --job-name=bifrost-controller
#
#SBATCH --time=7-00:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --partition=trc

# load environment, replace with appropriate incantations for your cluster
module load py-ants py-tensorflow/2.9.1_py39
source $GROUP_HOME/venvs/bifrost/bin/activate

# cd to a "workflow" directory, set appropriately
# the "workflow" directory must contain:
#  - a Snakefile
#  - a config.yaml file
#  - a cluster_profile directory containing a config.yaml (the cluster profile)
cd $GROUP_HOME/src/bifrost/pipeline

# submit tasks as jobs to the slurm scheduler
# log to stdout verbosely
# run no more than 100 jobs at the same time
# as described in the data requirements section of the readme
# use the cluster specific settings in the cluster profile
snakemake --slurm \
          --verbose \
          --jobs 100 \
          --directory /path/to/data/dir \
          --profile cluster_profile
