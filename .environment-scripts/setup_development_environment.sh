#!/bin/bash
set -e

INSTALL_TYPE=$1
PLATFORM=$2
CLONE_PREFIX=$3
INSTALL_PREFIX=$4
FV3NET_DIR=$5
CALLPYFORT=$6
CONDA_ENV=$7

SCRIPTS=$FV3NET_DIR/.environment-scripts
PLATFORM_SCRIPTS=$SCRIPTS/$PLATFORM

source $PLATFORM_SCRIPTS/configuration_variables.sh

if [ "$INSTALL_TYPE" == "all" ] || [ "$INSTALL_TYPE" == "fv3gfs-fortran" ] || [ "$INSTALL_TYPE" == "wrapper" ];
then
    export NCEPLIBS_DIR=$INSTALL_PREFIX/NCEPlibs
    export ESMFMKFILE=$INSTALL_PREFIX/esmf/lib/esmf.mk
    export FMS_DIR=$FV3NET_DIR/external/fv3gfs-fortran/FMS
    export FV3_DIR=$FV3NET_DIR/external/fv3gfs-fortran/FV3
    SERIAL_DIR=$FV3NET_DIR/external/fv3gfs-fortran/serial
    if [ -n "${CALLPYFORT}" ];
    then
        export CALL_PY_FORT_DIR=$CLONE_PREFIX/call_py_fort
    fi
fi

if [ "$INSTALL_TYPE" == "all" ] || [ "$INSTALL_TYPE" == "fv3gfs-fortran" ];
then
    if [$PLATFORM==*"serialize"*];
    then
        echo -e ">>> preprocessing code for serialization"
        mkdir -p $SERIAL_DIR/FV3/atmos_cubed_sphere/model
        mkdir -p $SERIAL_DIR/FV3/atmos_cubed_sphere/driver/fvGFS
        mkdir -p $SERIAL_DIR/FV3/atmos_cubed_sphere/tools
	    mkdir -p $SERIAL_DIR/FV3/gfsphysics/GFS_layer

        python3 $PPSER_PY $PPSER_FLAGS  --output-dir=$SERIAL_DIR/FV3 $FV3_DIR/*.F90
        python3 $PPSER_PY $PPSER_FLAGS  --output-dir=$SERIAL_DIR/FV3/atmos_cubed_sphere/model $FV3_DIR/atmos_cubed_sphere/model/*.F90
        python3 $PPSER_PY $PPSER_FLAGS  --output-dir=$SERIAL_DIR/FV3/atmos_cubed_sphere/driver/fvGFS $FV3_DIR/atmos_cubed_sphere/driver/fvGFS/*.F90
        python3 $PPSER_PY $PPSER_FLAGS  --output-dir=$SERIAL_DIR/FV3/gfsphysics/GFS_layer $FV3_DIR/gfsphysics/GFS_layer/*.F90
        python3 $PPSER_PY $PPSER_FLAGS  --output-dir=$SERIAL_DIR/FV3/atmos_cubed_sphere/tools $FV3_DIR/atmos_cubed_sphere/tools/fv_grid_tools.F90
        python3 $PPSER_PY $PPSER_FLAGS  --output-dir=$SERIAL_DIR/FV3/atmos_cubed_sphere/tools $FV3_DIR/atmos_cubed_sphere/tools/fv_restart.F90
        python3 $PPSER_PY $PPSER_FLAGS  --output-dir=$SERIAL_DIR/FV3/atmos_cubed_sphere/tools $FV3_DIR/atmos_cubed_sphere/tools/test_cases.F90

        cp -r -u $SERIAL_DIR/FV3/* $FV3_DIR/

    fi
    CALLPYFORT=$CALLPYFORT bash "$SCRIPTS"/install_fv3gfs_fortran.sh "$FV3_DIR" "$FV3GFS_PLATFORM" "$INSTALL_PREFIX"
fi

if [ "$INSTALL_TYPE" == "all" ] || [ "$INSTALL_TYPE" == "python-requirements" ] || [ "$INSTALL_TYPE" == "fv3net-packages" ] || [ $INSTALL_TYPE == "wrapper" ];
then
    ACTIVATE_CONDA=$PLATFORM_SCRIPTS/activate_conda_environment.sh
    if [ -f "$ACTIVATE_CONDA" ];
    then
        source "$ACTIVATE_CONDA" "$CONDA_ENV"
    fi
fi

if [ "$INSTALL_TYPE" == "all" ] || [ "$INSTALL_TYPE" == "python-requirements" ];
then
    if [ "$PLATFORM" != "gnu_docker" ];
    then
        make -C "$FV3NET_DIR" docker/prognostic_run/requirements.txt
    fi
    CC="$MPI4PY_CC" MPICC="$MPI4PY_MPICC" pip install --no-cache-dir -r "$FV3NET_DIR"/docker/prognostic_run/requirements.txt
fi

if [ "$INSTALL_TYPE" == "all" ] || [ "$INSTALL_TYPE" == "wrapper" ];
then
    CC="$WRAPPER_CC" \
    LDSHARED="$WRAPPER_LDSHARED" \
    CALLPYFORT=$CALLPYFORT \
    bash "$SCRIPTS"/install_python_wrapper.sh "$FV3_DIR"
fi

if [ "$INSTALL_TYPE" == "all" ] || [ "$INSTALL_TYPE" == "fv3net-packages" ];
then
    bash "$SCRIPTS"/install_fv3net_packages.sh \
        "$FV3NET_DIR"/external/vcm \
        "$FV3NET_DIR"/external/artifacts \
        "$FV3NET_DIR"/external/loaders \
        "$FV3NET_DIR"/external/fv3fit \
        "$FV3NET_DIR"/external/fv3kube \
        "$FV3NET_DIR"/workflows/post_process_run \
        "$FV3NET_DIR"/workflows/prognostic_c48_run \
        "$FV3NET_DIR"/external/emulation \
        "$FV3NET_DIR"/external/radiation
fi
