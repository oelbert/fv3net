import xarray as xr
import logging
from typing import Hashable, Mapping
import vcm
from runtime.types import State, Diagnostics
from runtime.names import (
    TEMP,
    SPHUM,
    DELP,
    PHYSICS_PRECIP_RATE,
    TENDENCY_TO_STATE_NAME,
    STATE_NAME_TO_TENDENCY,
)

logger = logging.getLogger(__name__)

cp = 1004
KG_PER_M2_PER_M = 1000.0


def precipitation_sum(
    physics_precip: xr.DataArray, column_dq2: xr.DataArray, dt: float
) -> xr.DataArray:
    """Return sum of physics precipitation and ML-induced precipitation. Output is
    thresholded to enforce positive precipitation.

    Args:
        physics_precip: precipitation from physics parameterizations [m]
        column_dq2: column-integrated moistening from ML [kg/m^2/s]
        dt: physics timestep [s]

    Returns:
        total precipitation [m]"""
    m_per_mm = 1 / 1000
    ml_precip = -column_dq2 * dt * m_per_mm  # type: ignore
    total_precip = physics_precip + ml_precip
    total_precip = total_precip.where(total_precip >= 0, 0)
    total_precip.attrs["units"] = "m"
    return total_precip


def precipitation_accumulation(
    precipitation_rate: xr.DataArray, dt: float
) -> xr.DataArray:
    """Return precipitation accumulation from precipitation rate and timestep

    Args:
        precipitation_rate: precipitation rate [kg/m^s/s]
        dt: timestep over which accumulation occurred [s]

    Returns:
        precipitation accumulation [m]"""
    precipitation_accumulation: xr.DataArray = precipitation_rate * dt / KG_PER_M2_PER_M
    precipitation_accumulation.attrs["units"] = "m"
    return precipitation_accumulation


def precipitation_rate(
    precipitation_accumulation: xr.DataArray, dt: float
) -> xr.DataArray:
    """Return precipitation rate from a precipitation accumulation and timestep

    Args:
        precipitation_accumulation: precipitation accumulation [m]
        dt: timestep over which accumulation occurred [s]

    Returns:
        precipitation rate [kg/m^s/s]"""

    precipitation_rate: xr.DataArray = (
        KG_PER_M2_PER_M * precipitation_accumulation / dt  # type: ignore
    )
    precipitation_rate.attrs["units"] = "kg/m^2/s"
    return precipitation_rate


def compute_diagnostics(
    state: State, tendency: State, label: str, hydrostatic: bool
) -> Diagnostics:
    delp = state[DELP]
    temperature_tendency_name = "dQ1"
    humidity_tendency_name = "dQ2"

    temperature_tendency = tendency.get(temperature_tendency_name, xr.zeros_like(delp))
    humidity_tendency = tendency.get(humidity_tendency_name, xr.zeros_like(delp))

    # compute column-integrated diagnostics
    if hydrostatic:
        net_heating = vcm.column_integrated_heating_from_isobaric_transition(
            temperature_tendency, delp, "z"
        )
    else:
        net_heating = vcm.column_integrated_heating_from_isochoric_transition(
            temperature_tendency, delp, "z"
        )
    diags: Diagnostics = {
        f"net_moistening_due_to_{label}": vcm.mass_integrate(
            humidity_tendency, delp, dim="z"
        ).assign_attrs(
            units="kg/m^2/s",
            description=f"column integrated moisture tendency due to {label}",
        ),
        f"column_heating_due_to_{label}": net_heating.assign_attrs(
            units="W/m^2"
        ).assign_attrs(description=f"column integrated heating due to {label}"),
    }
    delp_tendency = STATE_NAME_TO_TENDENCY[DELP]
    if delp_tendency in tendency:
        net_mass_tendency = vcm.mass_integrate(
            xr.ones_like(tendency[delp_tendency]), tendency[delp_tendency], dim="z"
        ).assign_attrs(
            units="kg/m^2/s",
            description=f"column-integrated mass tendency due to {label}",
        )
        diags[f"net_mass_tendency_due_to_{label}"] = net_mass_tendency

    # add 3D tendencies to diagnostics
    if label == "nudging":
        diags_3d: Mapping[Hashable, xr.DataArray] = {
            f"{TENDENCY_TO_STATE_NAME[k]}_tendency_due_to_nudging": v
            for k, v in tendency.items()
        }
    elif label == "machine_learning":
        diags_3d = {
            "dQ1": temperature_tendency.assign_attrs(units="K/s").assign_attrs(
                description=f"air temperature tendency due to {label}"
            ),
            "dQ2": humidity_tendency.assign_attrs(units="kg/kg/s").assign_attrs(
                description=f"specific humidity tendency due to {label}"
            ),
        }
    diags.update(diags_3d)

    # add 3D state to diagnostics for backwards compatibility
    diags.update({TEMP: state[TEMP], SPHUM: state[SPHUM], DELP: state[DELP]})

    return diags


def compute_ml_momentum_diagnostics(state: State, tendency: State) -> Diagnostics:
    delp = state[DELP]

    dQu = tendency.get("dQu", xr.zeros_like(delp))
    dQv = tendency.get("dQv", xr.zeros_like(delp))
    column_integrated_dQu = vcm.mass_integrate(dQu, delp, "z")
    column_integrated_dQv = vcm.mass_integrate(dQv, delp, "z")
    return dict(
        dQu=dQu.assign_attrs(units="m s^-2").assign_attrs(
            description="zonal wind tendency due to ML"
        ),
        dQv=dQv.assign_attrs(units="m s^-2").assign_attrs(
            description="meridional wind tendency due to ML"
        ),
        column_integrated_dQu_stress=column_integrated_dQu.assign_attrs(
            units="Pa", description="column integrated zonal wind tendency due to ML",
        ),
        column_integrated_dQv_stress=column_integrated_dQv.assign_attrs(
            units="Pa",
            description="column integrated meridional wind tendency due to ML",
        ),
    )


def rename_diagnostics(diags: Diagnostics):
    """Postfix ML output names with _diagnostic and create zero-valued outputs in
    their stead. Function operates in place."""
    ml_tendencies = {
        "net_moistening_due_to_machine_learning",
        "net_heating_due_to_machine_learning",
        "column_integrated_dQu",
        "column_integrated_dQv",
        "override_for_time_adjusted_total_sky_downward_shortwave_flux_at_surface",
        "override_for_time_adjusted_total_sky_net_shortwave_flux_at_surface",
        "override_for_time_adjusted_total_sky_downward_longwave_flux_at_surface",
    }
    ml_tendencies_in_diags = ml_tendencies & set(diags)
    for variable in ml_tendencies_in_diags:
        attrs = diags[variable].attrs
        diags[f"{variable}_diagnostic"] = diags[variable].assign_attrs(
            description=attrs.get("description", "") + " (diagnostic only)"
        )
        diags[variable] = xr.zeros_like(diags[variable]).assign_attrs(attrs)


def compute_baseline_diagnostics(state: State) -> Diagnostics:

    return dict(
        water_vapor_path=vcm.mass_integrate(state[SPHUM], state[DELP], dim="z")
        .assign_attrs(units="mm")
        .assign_attrs(description="column integrated water vapor"),
        physics_precip=(state[PHYSICS_PRECIP_RATE])
        .assign_attrs(units="kg/m^2/s")
        .assign_attrs(
            description="surface precipitation rate due to parameterized physics"
        ),
    )
