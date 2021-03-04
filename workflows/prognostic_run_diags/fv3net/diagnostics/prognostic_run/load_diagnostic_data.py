import intake
import logging
import warnings
import os
import xarray as xr
from typing import List, Iterable, Mapping, Set, Sequence

import fsspec
import vcm

from fv3net.diagnostics.prognostic_run import add_derived
from fv3net.diagnostics.prognostic_run.constants import DiagArg

logger = logging.getLogger(__name__)

# desired name as keys with set containing sources to rename
# TODO: could this be tied to the registry?
DIM_RENAME_INVERSE_MAP = {
    "x": {"grid_xt", "grid_xt_coarse"},
    "y": {"grid_yt", "grid_yt_coarse"},
    "tile": {"rank"},
    "xb": {"grid_x", "grid_x_coarse", "x_interface"},
    "yb": {"grid_y", "grid_y_coarse", "y_interface"},
}
VARNAME_SUFFIX_TO_REMOVE = ["_coarse"]
_DIAG_OUTPUT_LOADERS = []
MASK_VARNAME = "SLMSKsfc"
GRID_ENTRIES = {48: "grid/c48", 96: "grid/c96"}


def _adjust_tile_range(ds: xr.Dataset) -> xr.Dataset:

    if "tile" in ds:
        tiles = ds.tile

        if tiles.isel(tile=-1) == 6:
            ds = ds.assign_coords({"tile": tiles - 1})

    return ds


def _rename_dims(
    ds: xr.Dataset, rename_inverse: Mapping[str, Set[str]] = DIM_RENAME_INVERSE_MAP
) -> xr.Dataset:

    varname_target_registry = {}
    for target_name, source_names in rename_inverse.items():
        varname_target_registry.update({name: target_name for name in source_names})

    vars_to_rename = {
        var: varname_target_registry[var]
        for var in ds.dims
        if var in varname_target_registry
    }
    ds = ds.rename(vars_to_rename)
    return ds


def _set_calendar_to_julian(ds, time_coord="time"):
    if time_coord in ds.coords:
        ds[time_coord].attrs["calendar"] = "julian"
    return ds


def _round_to_nearest_second(time: xr.DataArray) -> xr.DataArray:
    return time.dt.round("1S")


def _round_time_coord(ds, time_coord="time"):

    if time_coord in ds.coords:
        new_times = _round_to_nearest_second(ds[time_coord])
        ds = ds.assign_coords({time_coord: new_times})
    else:
        logger.debug(
            "Round time operation called on dataset missing a time coordinate."
        )

    return ds


def _set_missing_attrs(ds):

    for var in ds:
        da = ds[var]

        # True for some prognostic zarrs
        if "description" in da.attrs and "long_name" not in da.attrs:
            da.attrs["long_name"] = da.attrs["description"]

        if "long_name" not in da.attrs:
            da.attrs["long_name"] = var

        if "units" not in da.attrs:
            da.attrs["units"] = "unspecified"
    return ds


def _remove_name_suffix(ds):
    for target in VARNAME_SUFFIX_TO_REMOVE:
        replace_names = {
            vname: vname.replace(target, "")
            for vname in ds.data_vars
            if target in vname
        }

        warn_on_overwrite(ds.data_vars.keys(), replace_names.values())
        ds = ds.rename(replace_names)
    return ds


def warn_on_overwrite(old: Iterable, new: Iterable):
    """
    Warn if new data keys will overwrite names (e.g., in a xr.Dataset)
    via an overlap with old keys or from duplication in new keys.

    Args:
        old: Original keys to check against
        new: Incoming keys to check for duplicates or existence in old
    """
    duplicates = {item for item in new if list(new).count(item) > 1}
    overlap = set(old) & set(new)
    overwrites = duplicates | overlap
    if len(overwrites) > 0:
        warnings.warn(
            UserWarning(
                f"Overwriting keys detected. Overlap: {overlap}"
                f"  Duplicates: {duplicates}"
            )
        )


def standardize_gfsphysics_diagnostics(ds):

    for func in [
        _set_calendar_to_julian,
        xr.decode_cf,
        _adjust_tile_range,
        _rename_dims,
        _round_time_coord,
        _remove_name_suffix,
        _set_missing_attrs,
    ]:
        ds = func(ds)

    return ds


def _open_tiles(path):
    return xr.open_mfdataset(path + ".tile?.nc", concat_dim="tile", combine="nested")


def load_verification(catalog_keys: List[str], catalog: intake.Catalog,) -> xr.Dataset:

    """
    Load verification data sources from a catalog and combine for reporting.

    Args:
        catalog_keys: catalog sources to load as verification data
        catalog: Intake catalog of available data sources.

    Returns:
        All specified verification datasources standardized and merged

    """
    verif_data = []
    for dataset_key in catalog_keys:
        ds = catalog[dataset_key].to_dask()
        ds = standardize_gfsphysics_diagnostics(ds)
        verif_data.append(ds)

    return xr.merge(verif_data, join="outer")


def _load_standardized(path):
    logger.info(f"Loading and standardizing {path}")
    m = fsspec.get_mapper(path)
    ds = xr.open_zarr(m, consolidated=True, decode_times=False)
    return standardize_gfsphysics_diagnostics(ds)


def _load_prognostic_run_physics_output(url):
    """Load, standardize and merge prognostic run physics outputs"""
    # values euqal to zero in diags.zarr get interpreted as nans by xarray, so fix here
    diagnostic_data = [
        _load_standardized(os.path.join(url, "diags.zarr")).fillna(0.0),
        _load_standardized(os.path.join(url, "sfc_dt_atmos.zarr")),
    ]

    return xr.merge(diagnostic_data, join="inner")


def _coarsen(ds: xr.Dataset, area: xr.DataArray, coarsening_factor: int) -> xr.Dataset:
    return vcm.cubedsphere.weighted_block_average(
        ds, area, coarsening_factor, x_dim="x", y_dim="y"
    )


def _get_coarsening_args(
    ds: xr.Dataset, target_res: int, grid_entries: Mapping[int, str] = GRID_ENTRIES
) -> (str, int):
    """Given input dataset and target resolution, return catalog entry for input grid
    and coarsening factor"""
    input_res = ds.sizes["x"]
    if input_res % target_res != 0:
        raise ValueError("Target resolution must evenly divide input resolution")
    coarsening_factor = int(input_res / target_res)
    if input_res not in grid_entries:
        raise KeyError(f"No grid defined in catalog for c{input_res} resolution")
    return grid_entries[input_res], coarsening_factor


def load_dycore(
    url: str, verification_entries: Sequence[str], catalog: intake.Catalog
) -> DiagArg:
    """Open data required for dycore plots.

    Args:
        url: path to prognostic run directory
        verification_entries: catalog entries for verification dycore data
        catalog: Intake catalog of available data sources

    Returns:
        tuple of prognostic run data, verification data and grid variables all at
        coarsened resolution. Prognostic and verification data contain variables output
        by the dynamical core.
    """
    logger.info(f"Processing dycore data from run directory at {url}")

    # open grid
    logger.info("Opening Grid Spec")
    grid_c48 = standardize_gfsphysics_diagnostics(catalog["grid/c48"].to_dask())
    ls_mask = standardize_gfsphysics_diagnostics(catalog["landseamask/c48"].to_dask())
    grid_c48 = xr.merge([grid_c48, ls_mask])

    # open verification
    logger.info("Opening verification data")
    verification_c48 = load_verification(verification_entries, catalog)

    # open prognostic run data
    path = os.path.join(url, "atmos_dt_atmos.zarr")
    logger.info(f"Opening prognostic run data at {path}")
    ds = _load_standardized(path)
    input_grid, coarsening_factor = _get_coarsening_args(ds, 48)
    area = catalog[input_grid].to_dask()["area"]
    ds = _coarsen(ds, area, coarsening_factor)

    return ds, verification_c48, grid_c48


def load_physics(
    url: str, verification_entries: Sequence[str], catalog: intake.Catalog
) -> DiagArg:
    """Open data required for physics plots.

    Args:
        url: path to prognostic run directory
        verification_entries: catalog entries for verification physics data
        catalog: Intake catalog of available data sources

    Returns:
        tuple of prognostic run data, verification data and grid variables all at
        coarsened resolution. Prognostic and verification data contain variables
        output by the physics routines.
    """
    logger.info(f"Processing physics data from run directory at {url}")

    # open grid
    logger.info("Opening Grid Spec")
    grid_c48 = standardize_gfsphysics_diagnostics(catalog["grid/c48"].to_dask())
    ls_mask = standardize_gfsphysics_diagnostics(catalog["landseamask/c48"].to_dask())
    grid_c48 = xr.merge([grid_c48, ls_mask])

    # open verification
    verification_c48 = load_verification(verification_entries, catalog)
    verification_c48 = add_derived.physics_variables(verification_c48)

    # open prognostic run data
    logger.info(f"Opening prognostic run data at {url}")
    prognostic_output = _load_prognostic_run_physics_output(url)
    input_grid, coarsening_factor = _get_coarsening_args(prognostic_output, 48)
    area = catalog[input_grid].to_dask()["area"]
    prognostic_output = _coarsen(prognostic_output, area, coarsening_factor)
    prognostic_output = add_derived.physics_variables(prognostic_output)

    return prognostic_output, verification_c48, grid_c48