import dataclasses
import datetime
import logging
from typing import Optional

import cftime
import dacite
import yaml
from emulation._emulate.microphysics import (
    MicrophysicsHook,
    IntervalSchedule,
    Mask,
    TimeMask,
    always_right,
)
from emulation._monitor.monitor import StorageConfig, StorageHook
from emulation._time import from_datetime

logger = logging.getLogger("emulation")


def do_nothing(state):
    pass


@dataclasses.dataclass
class ModelConfig:
    """

    Attributes:
        path: path to a saved tensorflow model
        online_schedule: an object controlling when to use the emulator instead
            of the fortran model. Only supports scheduling by an interval.
            The physics is used for the first half of the interval, and the ML
            for the second half.
    """

    path: str
    online_schedule: Optional[IntervalSchedule] = None

    def build(self) -> MicrophysicsHook:
        return MicrophysicsHook(self.path, mask=self._build_mask())

    def _build_mask(self) -> Mask:
        if self.online_schedule:
            return TimeMask(self.online_schedule)
        else:
            return always_right


@dataclasses.dataclass
class EmulationConfig:
    model: Optional[ModelConfig] = None
    gscond: Optional[ModelConfig] = None
    storage: Optional[StorageConfig] = None

    @staticmethod
    def _build_model(model: ModelConfig):
        if model is None:
            logger.info("No model configured.")
            return do_nothing
        else:
            return model.build().microphysics

    def build_model_hook(self):
        return self._build_model(self.model)

    def build_gscond_hook(self):
        return self._build_model(self.gscond)

    def build_storage_hook(self):
        if self.storage is None:
            logger.info("No storage configured.")
            return do_nothing
        else:
            return StorageHook(**dataclasses.asdict(self.storage)).store

    @staticmethod
    def from_dict(config: dict) -> "EmulationConfig":
        return dacite.from_dict(
            EmulationConfig,
            config,
            config=dacite.Config(
                type_hooks={
                    cftime.DatetimeJulian: from_datetime,
                    datetime.timedelta: (lambda x: datetime.timedelta(seconds=x)),
                }
            ),
        )


def get_hooks():
    path = "fv3config.yml"
    config_key = "zhao_carr_emulation"
    try:
        with open(path) as f:
            dict_ = yaml.safe_load(f)
    except FileNotFoundError:
        logging.warn("Config not found...using defaults.")
        dict_ = {}
    config = EmulationConfig.from_dict(dict_.get(config_key, {}))

    return (
        config.build_gscond_hook(),
        config.build_model_hook(),
        config.build_storage_hook(),
    )
