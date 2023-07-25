#!/bin/bash

# NCEPlibs arguments
NCEPLIBS_PLATFORM=gaea
NCEPLIBS_COMPILER=gcc

# ESMF arguments and environment variables
ESMF_OS=Unicos
ESMF_COMPILER=gcc
ESMF_SITE=default
ESMF_CC=cc
ESMF_COMM=mpiuni

# FMS environment variables
FMS_CC=cc
FMS_FC=ftn
FMS_LDFLAGS=
FMS_LOG_DRIVER_FLAGS=
FMS_CPPFLAGS='-Duse_LARGEFILE -DMAXFIELDMETHODS_=500 -DGFS_PHYS'
FMS_FCFLAGS='-FR -i4 -r8'
FMS_MAKE_OPTIONS=

# fv3gfs-fortran arguments
FV3GFS_PLATFORM=gaea-c5_serialize

# Python requirements environment variables
MPI4PY_CC=cc
MPI4PY_MPICC=cc

# Python wrapper environment variables
WRAPPER_CC=cc
WRAPPER_LDSHARED='cc -shared'
