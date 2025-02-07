from fv3fit.tfdataset import tfdataset_from_batches
from fv3fit.reservoir.train import train_reservoir_model
from fv3fit.reservoir.config import (
    ReservoirTrainingConfig,
    CubedsphereSubdomainConfig,
    ReservoirHyperparameters,
    BatchLinearRegressorHyperparameters,
)
from tests.training.test_train import (
    get_dataset_default,
    get_uniform_sample_func,
)


def test_train_reservoir():
    n_sample = 10
    n_tile, nx, ny, nz = 1, 12, 12, 5
    sample_func = get_uniform_sample_func(size=(n_sample, n_tile, nx, ny, nz))
    _, _, train_dataset = get_dataset_default(sample_func)
    _, _, test_dataset = get_dataset_default(sample_func)
    train_dataset = (
        train_dataset.unstack()
        .squeeze()
        .drop("tile")
        .rename({"sample": "time"})
        .transpose("time", "x", "y", "z")
    )
    test_dataset = (
        test_dataset.unstack()
        .squeeze()
        .drop("tile")
        .rename({"sample": "time"})
        .transpose("time", "x", "y", "z")
    )
    train_tfdataset = tfdataset_from_batches([train_dataset for _ in range(4)])
    val_tfdataset = tfdataset_from_batches([test_dataset])
    variables = ["var_in_3d", "var_in_2d"]

    subdomain_config = CubedsphereSubdomainConfig(
        layout=[2, 2], overlap=2, rank_dims=["x", "y"],
    )
    reservoir_config = ReservoirHyperparameters(
        state_size=100,
        adjacency_matrix_sparsity=0.95,
        spectral_radius=0.5,
        seed=0,
        input_coupling_scaling=0.0,
    )
    reg_config = BatchLinearRegressorHyperparameters(
        l2=0.0, use_least_squares_solve=True
    )
    hyperparameters = ReservoirTrainingConfig(
        input_variables=variables,
        output_variables=variables,
        subdomain=subdomain_config,
        reservoir_hyperparameters=reservoir_config,
        readout_hyperparameters=reg_config,
        n_batches_burn=2,
        input_noise=0.01,
    )
    model = train_reservoir_model(hyperparameters, train_tfdataset, val_tfdataset)
    model.reset_state()

    assert model.predict()[0].shape == (
        *model.rank_divider.rank_extent_without_overlap,
        nz,
    )
    assert model.predict()[1].shape == (
        *model.rank_divider.rank_extent_without_overlap,
        1,
    )
