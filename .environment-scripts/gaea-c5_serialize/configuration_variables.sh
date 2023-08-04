#!/bin/bash

# NCEPlibs arguments
NCEPLIBS_PLATFORM=gaea
NCEPLIBS_COMPILER=gnu

# ESMF arguments and environment variables
ESMF_OS=Unicos
ESMF_COMPILER=gfortran
ESMF_SITE=default
ESMF_CC=cc
ESMF_COMM=mpiuni

# FMS environment variables
FMS_CC=mpicc
FMS_FC=mpif90
FMS_LDFLAGS=
FMS_LOG_DRIVER_FLAGS=
FMS_CPPFLAGS='-Duse_LARGEFILE -DMAXFIELDMETHODS_=500 -DGFS_PHYS'
FMS_FCFLAGS='-FR -i4 -r8 -fopenmp'
FMS_MAKE_OPTIONS=

# fv3gfs-fortran arguments
FV3GFS_PLATFORM=gaea-c5_serialize

# Python requirements environment variables
MPI4PY_CC=mpicc
MPI4PY_MPICC=mpicc

# Python wrapper environment variables
WRAPPER_CC=cc
WRAPPER_LDSHARED='cc -shared'
