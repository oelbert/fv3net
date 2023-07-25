#!/bin/bash
set -e

# Note if this script is modified, the base image will need to be rebuilt.

PLATFORM=$1
CLONE_PREFIX=$2
INSTALL_PREFIX=$3
FV3NET_DIR=$4
CALLPYFORT=$5
CONDA_ENV=$6


SCRIPTS=$FV3NET_DIR/.environment-scripts
PLATFORM_SCRIPTS=$SCRIPTS/$PLATFORM
NCEPLIBS_DIR=$INSTALL_PREFIX/NCEPlibs
ESMF_DIR=$INSTALL_PREFIX/esmf
FMS_DIR=$FV3NET_DIR/external/fv3gfs-fortran/FMS

source $PLATFORM_SCRIPTS/configuration_variables.sh

bash "$PLATFORM_SCRIPTS"/install_base_software.sh "$CLONE_PREFIX" "$INSTALL_PREFIX" "$CONDA_ENV" "$SCRIPTS"
# Provide an optional platform-specific way to modify the build environment;
# currently only used to manually add the `bats` utility to the search PATH on
# systems where it is installed manually.
if [ -f "$PLATFORM_SCRIPTS/patch_base_build_environment.sh" ];
then
    source "$PLATFORM_SCRIPTS/patch_base_build_environment.sh" "$CLONE_PREFIX"
fi
bash "$SCRIPTS"/install_nceplibs.sh "$CLONE_PREFIX"/NCEPlibs "$NCEPLIBS_DIR" "$NCEPLIBS_PLATFORM" "$NCEPLIBS_COMPILER"
bash "$SCRIPTS"/install_esmf.sh "$CLONE_PREFIX"/esmf "$ESMF_DIR" "$ESMF_OS" "$ESMF_COMPILER" "$ESMF_SITE" "$ESMF_COMM"

if [$PLATFORM==*"serialize"*];
then
    if [-z $SERIALBOX_ROOT];
    then
        bash "$SCRIPTS"/install_serialbox.sh "$CLONE_PREFIX"/serialbox
    fi
    export PPSER_PY="$SERIALBOX_ROOT/install/python/pp_ser/pp_ser.py"
    export PPSER_FLAGS= "--verbose --ignore-identical -m utils_ppser_kbuff"
fi

CC="$FMS_CC" \
FC="$FMS_FC" \
LDFLAGS="$FMS_LDFLAGS" \
LOG_DRIVER_FLAGS="$FMS_LOG_DRIVER_FLAGS" \
CPPFLAGS="$FMS_CPPFLAGS" \
FCFLAGS="$FMS_FCFLAGS" \
bash "$SCRIPTS"/install_fms.sh "$FMS_DIR" "$FMS_MAKE_OPTIONS"

if [ -n "${CALLPYFORT}" ];
then
    bash "$SCRIPTS"/install_call_py_fort.sh "$CLONE_PREFIX"/call_py_fort
fi
