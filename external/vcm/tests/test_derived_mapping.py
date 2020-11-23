import cftime
import numpy as np
import pytest
from typing import Mapping
import xarray as xr

from vcm import DerivedMapping

nt, nx, ny = 3, 2, 1
ds = xr.Dataset(
    {
        "lat": xr.DataArray(np.random.rand(ny, nx), dims=["y", "x"]),
        "lon": xr.DataArray(np.random.rand(ny, nx), dims=["y", "x"]),
        "T": xr.DataArray(
            np.random.rand(ny, nx, nt),
            dims=["y", "x", "time"],
            coords={"time": [cftime.DatetimeJulian(2016, 1, 1) for n in range(nt)]},
        ),
        "q": xr.DataArray(
            np.random.rand(ny, nx, nt),
            dims=["y", "x", "time"],
            coords={"time": [cftime.DatetimeJulian(2016, 1, 1) for n in range(nt)]},
        ),
        "dQu": xr.DataArray(
            np.ones((ny, nx, nt)),
            dims=["y", "x", "time"],
            coords={"time": [cftime.DatetimeJulian(2016, 1, 1) for n in range(nt)]},
        ),
    }
)


def test_wind_tendency_derived():
    # dQu/dQv must be calculated from dQxwind, dQywind
    rotation = {
        var: xr.DataArray(np.zeros((ny, nx)), dims=["y", "x"])
        for var in [
            "eastward_wind_u_coeff",
            "eastward_wind_v_coeff",
            "northward_wind_u_coeff",
            "northward_wind_v_coeff",
        ]
    }
    data = xr.Dataset(
        {
            "dQxwind": xr.DataArray(np.ones((ny + 1, nx)), dims=["y_interface", "x"]),
            "dQywind": xr.DataArray(np.ones((ny, nx + 1)), dims=["y", "x_interface"]),
            **rotation,
        }
    )

    derived_mapping = DerivedMapping(data)
    dQu = derived_mapping["dQu"]
    dQv = derived_mapping["dQv"]
    np.testing.assert_array_almost_equal(dQu, 0.0)
    np.testing.assert_array_almost_equal(dQv, 0.0)


def test_wind_tendency_nonderived():
    # dQu/dQv already exist in data
    derived_mapping = DerivedMapping(ds)
    dQu = derived_mapping["dQu"]
    np.testing.assert_array_almost_equal(dQu, 1.0)


def test_DerivedMapping():
    derived_state = DerivedMapping(ds)
    assert isinstance(derived_state["T"], xr.DataArray)


def test_DerivedMapping_cos_zenith():
    derived_state = DerivedMapping(ds)
    output = derived_state["cos_zenith_angle"]
    assert isinstance(output, xr.DataArray)


def test_DerivedMapping__data_arrays():
    derived_state = DerivedMapping(ds)
    keys = ["T", "q"]
    data_arrays = derived_state._data_arrays(keys)
    assert isinstance(data_arrays, Mapping)
    assert set(keys) == set(data_arrays.keys())


def test_DerivedMapping_dataset():
    derived_state = DerivedMapping(ds)
    keys = ["T", "q", "cos_zenith_angle"]
    ds_derived_state = derived_state.dataset(keys)
    assert isinstance(ds_derived_state, xr.Dataset)
    for existing_var in ["T", "q"]:
        np.testing.assert_array_almost_equal(
            ds_derived_state[existing_var], ds[existing_var]
        )


def test_DerivedMapping_unregistered():
    derived_state = DerivedMapping(ds)
    with pytest.raises(KeyError):
        derived_state["latent_heat_flux"]