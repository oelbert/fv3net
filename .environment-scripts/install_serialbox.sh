#!/bin/bash
set -e

CLONE_PREFIX=$1

export SERIALBOX_ROOT=$CLONE_PREFIX
export SERIALBOX_APP=$CLONE_PREFIX

# needs gnu compilers, boost, and cmake

git clone https://github.com/eth-cscs/serialbox2.git $SERIALBOX_ROOT
cd $SERIALBOX_ROOT
mkdir build
cd build
cmake -DSERIALBOX_USE_NETCDF=ON -DSERIALBOX_ENABLE_FORTRAN=ON -DSERIALBOX_TESTING=ON -DSERIALBOX_EXAMPLES=OFF ../
make && make install
