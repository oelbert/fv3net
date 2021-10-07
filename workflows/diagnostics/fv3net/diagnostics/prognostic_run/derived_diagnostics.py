from typing import Sequence, Tuple

import xarray as xr

import vcm

from fv3net.diagnostics._shared.registry import Registry


def merge_derived(diags: Sequence[Tuple[str, xr.DataArray]]) -> xr.Dataset:
    out = xr.Dataset()
    for name, da in diags:
        out[name] = da
    return out


# all functions added to this registry must take a single xarray Dataset as
# input and return a single xarray DataArray
derived_registry = Registry(merge_derived)


@derived_registry.register("mass_streamfunction_pressure_level_zonal_time_mean")
def psi_value(diags: xr.Dataset) -> xr.DataArray:
    if "northward_wind_pressure_level_zonal_time_mean" not in diags:
        return xr.DataArray()
    northward_wind = diags["northward_wind_pressure_level_zonal_time_mean"]
    return vcm.mass_streamfunction(northward_wind)


@derived_registry.register("mass_streamfunction_pressure_level_zonal_bias")
def psi_bias(diags: xr.Dataset) -> xr.DataArray:
    if "northward_wind_pressure_level_zonal_bias" not in diags:
        return xr.DataArray()
    northward_wind_bias = diags["northward_wind_pressure_level_zonal_bias"]
    return vcm.mass_streamfunction(northward_wind_bias)


@derived_registry.register("mass_streamfunction_300_700_zonal_and_time_mean")
def psi_value_mid_troposphere(diags: xr.Dataset) -> xr.DataArray:
    if "northward_wind_pressure_level_zonal_time_mean" not in diags:
        return xr.DataArray()
    northward_wind = diags["northward_wind_pressure_level_zonal_time_mean"]
    psi = vcm.mass_streamfunction(northward_wind).sel(pressure=slice(30000, 70000))
    psi_mid_trop = psi.weighted(psi.pressure).mean("pressure")
    return psi_mid_trop.assign_attrs(
        long_name="mass streamfunction 300-700hPa average", units="Gkg/s"
    )


@derived_registry.register("mass_streamfunction_300_700_zonal_bias")
def psi_bias_mid_troposphere(diags: xr.Dataset) -> xr.DataArray:
    if "northward_wind_pressure_level_zonal_bias" not in diags:
        return xr.DataArray()
    northward_wind_bias = diags["northward_wind_pressure_level_zonal_bias"]
    psi = vcm.mass_streamfunction(northward_wind_bias).sel(pressure=slice(30000, 70000))
    psi_mid_trop = psi.weighted(psi.pressure).mean("pressure")
    return psi_mid_trop.assign_attrs(
        long_name="mass streamfunction 300-700hPa average", units="Gkg/s"
    )