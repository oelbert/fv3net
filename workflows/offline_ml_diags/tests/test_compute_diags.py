import logging
from dataclasses import dataclass
import tempfile
import os
from typing import Optional
from synth import (  # noqa: F401
    grid_dataset,
    grid_dataset_path,
    nudging_dataset_path,
    dataset_fixtures_dir,
)
from fv3fit._shared import load_data_sequence
from fv3fit._shared.config import ModelTrainingConfig
from fv3fit.keras import get_model
from fv3fit import Estimator
from offline_ml_diags.compute_diags import main

logger = logging.getLogger(__name__)


batch_kwargs = {
    "needs_grid": False,
    "res": "c8_random_values",
    "timesteps_per_batch": 1,
    "mapping_function": "open_merged_nudged",
    "timesteps": ["20160801.001500"],
    "mapping_kwargs": {
        "i_start": 0,
        "rename_vars": {
            "air_temperature_tendency_due_to_nudging": "dQ1",
            "specific_humidity_tendency_due_to_nudging": "dQ2",
        },
    },
}


train_config = ModelTrainingConfig(
    model_type="DenseModel",
    hyperparameters={"width": 3, "depth": 2},
    input_variables=["air_temperature", "specific_humidity"],
    output_variables=["dQ1", "dQ2"],
    batch_function="batches_from_geodata",
    batch_kwargs=batch_kwargs,
    scaler_type="standard",
    scaler_kwargs={},
    additional_variables=None,
    random_seed=0,
    validation_timesteps=None,
    data_path=nudging_dataset_path,
)


def model(training_batches) -> Estimator:
    model = get_model(
        "DenseModel",
        "sample",
        ["air_temperature", "specific_humidity"],
        ["dQ1", "dQ2"],
        width=3,
        depth=2,
    )
    model.fit(training_batches)
    return model


@dataclass
class Args:
    model_path: str
    output_path: str
    grid: str
    timesteps_n_samples: Optional[int] = 2
    data_path: Optional[str] = None
    config_yml: Optional[str] = None
    timesteps_file: Optional[str] = None
    training: Optional[bool] = False
    snapshot_time: Optional[str] = None


def test_offline_diags_integration(
    nudging_dataset_path, grid_dataset_path  # noqa: F811
):
    """
    Test the bash endpoint for computing offline diagnostics
    """
    training_batches = load_data_sequence(nudging_dataset_path, train_config)
    trained_model = model(training_batches)
    with tempfile.TemporaryDirectory() as tmpdir:
        model_dir = os.path.join(tmpdir, "trained_model")
        trained_model.dump(model_dir)
        train_config.data_path = nudging_dataset_path
        train_config.dump(model_dir)
        args = Args(model_dir, os.path.join(tmpdir, "offline_diags"), grid_dataset_path)
        main(args)