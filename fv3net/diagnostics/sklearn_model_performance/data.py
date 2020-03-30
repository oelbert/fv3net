import os
from scipy.interpolate import UnivariateSpline
import xarray as xr

import fv3net
from ..data import net_heating_from_dataset
from fv3net.pipelines.create_training_data import (
    SUFFIX_COARSE_TRAIN_DIAG,
    VAR_Q_HEATING_ML,
    VAR_Q_MOISTENING_ML,
)
import vcm
from vcm.cloud.fsspec import get_fs
from vcm.convenience import round_time
from vcm.cubedsphere.constants import (
    INIT_TIME_DIM,
    COORD_X_CENTER,
    COORD_Y_CENTER,
    COORD_Z_CENTER,
    TILE_COORDS,
)
from vcm.regrid import regrid_to_shared_coords
from vcm.constants import (
    kg_m2s_to_mm_day,
    kg_m2_to_mm,
    SPECIFIC_HEAT_CONST_PRESSURE,
    GRAVITY,
)

SAMPLE_DIM = "sample"
STACK_DIMS = ["tile", INIT_TIME_DIM, COORD_X_CENTER, COORD_Y_CENTER]

THERMO_DATA_VAR_ATTRS = {
    "net_precipitation": {"long_name": "net column precipitation", "units": "mm/day"},
    "net_heating": {"long_name": "net column heating", "units": "W/m^2"},
    "net_precipitation_ml": {
        "long_name": "residual P-E predicted by ML model",
        "units": "mm/day",
    },
    "net_heating_ml": {
        "long_name": "residual heating predicted by ML model",
        "units": "W/m^2",
    },
}


def predict_on_test_data(
    test_data_path,
    model_path,
    num_test_zarrs,
    model_type="rf",
    downsample_time_factor=1,
):
    if model_type == "rf":
        from fv3net.regression.sklearn.test import (
            load_test_dataset,
            load_model,
            predict_dataset,
        )

        ds_test = load_test_dataset(
            test_data_path, num_test_zarrs, downsample_time_factor
        )
        sk_wrapped_model = load_model(model_path)
        ds_pred = predict_dataset(sk_wrapped_model, ds_test)
        return ds_test.unstack(), ds_pred
    else:
        raise ValueError(
            "Cannot predict using model type {model_type},"
            "only 'rf' is currently implemented."
        )


def load_high_res_diag_dataset(coarsened_hires_diags_path, init_times):
    fs = get_fs(coarsened_hires_diags_path)
    ds_hires = xr.open_zarr(
        # fs.get_mapper functions like a zarr store
        fs.get_mapper(
            os.path.join(coarsened_hires_diags_path, fv3net.COARSENED_DIAGS_ZARR_NAME)
        ),
        consolidated=True,
    ).rename({"time": INIT_TIME_DIM})
    ds_hires = ds_hires.assign_coords(
        {
            INIT_TIME_DIM: [round_time(t) for t in ds_hires[INIT_TIME_DIM].values],
            "tile": TILE_COORDS,
        }
    )
    ds_hires = ds_hires.sel({INIT_TIME_DIM: list(set(init_times))})
    if set(ds_hires[INIT_TIME_DIM].values) != set(init_times):
        raise ValueError(
            f"Timesteps {set(init_times)-set(ds_hires[INIT_TIME_DIM].values)}"
            f"are not matched in high res dataset."
        )

    ds_hires["net_precipitation"] = vcm.net_precipitation(
        ds_hires[f"LHTFLsfc_coarse"], ds_hires[f"PRATEsfc_coarse"]
    )
    ds_hires["net_heating"] = net_heating_from_dataset(ds_hires, suffix="coarse")

    return ds_hires


def add_column_heating_moistening(ds):
    """ Integrates column dQ1, dQ2 and sum with model's heating/moistening to calculate
    heating and P-E. Modifies in place.
    
    Args:
        ds (xarray dataset): train/test or prediction dataset
            that has dQ1, dQ2, delp, precip and LHF data variables
    """

    ds["net_precipitation_ml"] = (
        vcm.mass_integrate(-ds[VAR_Q_MOISTENING_ML], ds.delp) * kg_m2s_to_mm_day
    )
    ds["net_precipitation_physics"] = vcm.net_precipitation(
        ds[f"LHTFLsfc_{SUFFIX_COARSE_TRAIN_DIAG}"],
        ds[f"PRATEsfc_{SUFFIX_COARSE_TRAIN_DIAG}"],
    )

    ds["net_precipitation"] = (
        ds["net_precipitation_ml"] + ds["net_precipitation_physics"]
    )

    ds["net_heating_ml"] = SPECIFIC_HEAT_CONST_PRESSURE * vcm.mass_integrate(
        ds[VAR_Q_HEATING_ML], ds.delp
    )
    ds["net_heating_physics"] = net_heating_from_dataset(
        ds, suffix=SUFFIX_COARSE_TRAIN_DIAG
    )
    ds["net_heating"] = ds["net_heating_ml"] + ds["net_heating_physics"]
    for data_var, data_attrs in THERMO_DATA_VAR_ATTRS.items():
        ds[data_var].attrs = data_attrs


def integrate_for_Q(P, sphum, lower_bound=55000, upper_bound=85000):
    spline = UnivariateSpline(P, sphum)
    return (spline.integral(lower_bound, upper_bound) / GRAVITY) * kg_m2_to_mm


def lower_tropospheric_stability(ds):
    pressure = vcm.pressure_at_midpoint_log(ds.delp)
    T_at_700mb = (
        regrid_to_shared_coords(
            ds["T"],
            [70000],
            pressure,
            regrid_dim_name="p700mb",
            replace_dim_name=COORD_Z_CENTER,
        )
        .squeeze()
        .drop("p700mb")
    )
    theta_700mb = vcm.potential_temperature(70000, T_at_700mb)
    return theta_700mb - ds["tsea"]