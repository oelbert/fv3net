#!/bin/bash

CONDA_ENV=$1
CONDA_BASE=$(conda info --base)

conda env create -n $CONDA_ENV -f environment.yml  2> /dev/null || \
	echo "Conda env already exists proceeding to VCM package installation"

source activate $CONDA_ENV

local_packages_to_install=(. external/fv3config external/vcm external/vcm/external/mappm)
for package  in ${local_packages_to_install[@]}
do
  pip install --no-deps -e $package
done