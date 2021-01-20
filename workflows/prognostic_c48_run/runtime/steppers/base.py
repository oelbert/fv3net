import logging
from typing import Sequence

import xarray as xr

from runtime.derived_state import DerivedFV3State
from runtime.names import PRECIP_RATE, SPHUM, DELP, AREA, TENDENCY_TO_STATE_NAME
from runtime.diagnostics.machine_learning import compute_baseline_diagnostics
from runtime.types import State, Diagnostics


logger = logging.getLogger(__name__)


class LoggingMixin:

    rank: int

    def _log_debug(self, message: str):
        if self.rank == 0:
            logger.debug(message)

    def _log_info(self, message: str):
        if self.rank == 0:
            logger.info(message)

    def _print(self, message: str):
        if self.rank == 0:
            print(message)


class Stepper:
    @property
    def _state(self):
        return DerivedFV3State(self._fv3gfs)

    def _compute_python_tendency(self) -> Diagnostics:
        return {}

    def _apply_python_to_dycore_state(self) -> Diagnostics:
        return {}

    def _apply_python_to_physics_state(self) -> Diagnostics:
        return {}


class BaselineStepper(Stepper):
    def __init__(self, fv3gfs, states_to_output: Sequence[str]):
        self._fv3gfs = fv3gfs
        self._states_to_output = states_to_output

    def _compute_python_tendency(self) -> Diagnostics:
        return {}

    def _apply_python_to_dycore_state(self) -> Diagnostics:

        state: State = {name: self._state[name] for name in [PRECIP_RATE, SPHUM, DELP]}
        diagnostics: Diagnostics = compute_baseline_diagnostics(state)
        diagnostics.update({name: self._state[name] for name in self._states_to_output})

        return {
            "area": self._state[AREA],
            "cnvprcp_after_python": self._fv3gfs.get_diagnostic_by_name(
                "cnvprcp"
            ).data_array,
            **diagnostics,
        }


def apply(state: State, tendency: State, dt: float) -> State:
    """Given state and tendency prediction, return updated state.
    Returned state only includes variables updated by ML model."""

    with xr.set_options(keep_attrs=True):
        updated = {}
        for name in tendency:
            state_name = TENDENCY_TO_STATE_NAME.get(name, name)
            updated[state_name] = state[state_name] + tendency[name] * dt
    return updated  # type: ignore


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