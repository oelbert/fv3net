import logging
import os
import tempfile
from datetime import datetime
from functools import partial
from os.path import join

from vcm import fv3run
from vcm.cloud import gsutil

RESTART_DIR_PATTERN = (
    "gs://vcm-ml-data/"
    "2019-10-28-X-SHiELD-2019-10-05-multiresolution-extracted/"
    "restart/C48/{time}/rundir"
)
OUTPUT_DIR_PATTERN = (
    "gs://vcm-ml-data/"
    "2019-10-28-X-SHiELD-2019-10-05-multiresolution-extracted/"
    "one-step-run/C48/{time}/rundir"
)


def restart_dir(time):
    return RESTART_DIR_PATTERN.format(time=time)


def output(time):
    return OUTPUT_DIR_PATTERN.format(time=time)


def convert_timestamp_to_diag_table_time(time: str) -> str:
    date = datetime.strptime(time, "%Y%m%d.%H%M%S")
    date_string = date.strftime("%Y %m %d %H %M %S")
    return date_string


def patch_diag_table(dir, time):
    with open(join(dir, "rundir", "diag_table"), "w") as file:
        date_string = convert_timestamp_to_diag_table_time(time)
        file.write(f"20160801.00Z.C48.32bit.non-mono\n{date_string}")
        # add output of the grid spec for post-processing purposes (TODO
        # replace all this with fv3config)
        file.write(
            """
            #output files
            "grid_spec",              -1,  "months",   1, "days",  "time"
            ###
            # grid_spec
            ###
            "dynamics", "grid_lon", "grid_lon", "grid_spec", "all", .false.,  "none", 2,
            "dynamics", "grid_lat", "grid_lat", "grid_spec", "all", .false.,  "none", 2,
            "dynamics", "grid_lont", "grid_lont", "grid_spec", "all", .false.,  "none", 2,
            "dynamics", "grid_latt", "grid_latt", "grid_spec", "all", .false.,  "none", 2,
            "dynamics", "area",     "area",     "grid_spec", "all", .false.,  "none", 2,
            """  # noqa
        )


def main(time: str, rundir_transformations=(), key=None):
    """Run the FV3 C48 model one step forward for the run-directory for a specific time

    Args:
        time: the timestep YYYYMMDD.HHMMSS to run the model for
        rundir_transformations: a sequence of transformations (e.g. modifying the
           diag_table) to apply to the downloaded run directory before the FV3
           simulation.

    """
    if key is None:
        try:
            key = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
        except KeyError:
            pass
        else:
            gsutil.authenticate(key)

    elif key:
        gsutil.authenticate(key)

    with tempfile.TemporaryDirectory() as localdir:
        gsutil.copy(restart_dir(time), localdir)
        logging.info("running experiment")
        for transform in rundir_transformations:
            transform(localdir)
        try:
            fv3run.run_experiment(localdir)
        except Exception as e:
            logging.critical(
                "Experiment failed. Listing rundir for debugging purposes"
                f"{os.listdir(localdir)}"
            )
            raise e
        gsutil.copy(localdir + "/*", output(time))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("time")
    args = parser.parse_args()
    time = args.time

    main(args.time, rundir_transformations=[partial(patch_diag_table, time=time)])