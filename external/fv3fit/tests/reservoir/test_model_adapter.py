import numpy as np
import pytest
import xarray as xr

from fv3fit.reservoir.transformers.transformer import DoNothingAutoencoder
from fv3fit.reservoir.domain import RankDivider
from fv3fit.reservoir.readout import ReservoirComputingReadout
from fv3fit.reservoir import (
    Reservoir,
    ReservoirHyperparameters,
    HybridReservoirComputingModel,
)
from fv3fit.reservoir.model import HybridDatasetAdapter, _transpose_xy_dims


@pytest.mark.parametrize(
    "original_dims, reordered_dims",
    [
        (["time", "x", "y", "z"], ["time", "x", "y", "z"]),
        (["time", "y", "x", "z"], ["time", "x", "y", "z"]),
    ],
)
def test__transpose_xy_dims(original_dims, reordered_dims):
    da = xr.DataArray(np.random.rand(5, 7, 7, 8), dims=original_dims)
    assert list(_transpose_xy_dims(da, rank_dims=["x", "y"]).dims) == reordered_dims


def get_initialized_hybrid_model():
    # expects rank size (including halos) in latent space
    divider = RankDivider((2, 2), ["x", "y"], [8, 8], 2)
    autoencoder = DoNothingAutoencoder([3, 3])
    input_size = 6 * 6 * autoencoder.n_latent_dims  # overlap subdomain in latent space
    hybrid_input_size_per_subdomain = (
        divider.subdomain_xy_size_without_overlap ** 2 * autoencoder.n_latent_dims
    )  # no overlap subdomain in latent space
    output_size = (
        hybrid_input_size_per_subdomain  # no overlap subdomain in latent space
    )

    state_size = 25
    hyperparameters = ReservoirHyperparameters(
        state_size=state_size,
        adjacency_matrix_sparsity=0.0,
        spectral_radius=1.0,
        input_coupling_sparsity=1,
    )
    reservoir = Reservoir(hyperparameters, input_size=input_size)

    # multiplied by the number of subdomains since it's a combined readout
    readout = ReservoirComputingReadout(
        coefficients=np.random.rand(
            state_size * 4 + hybrid_input_size_per_subdomain * 4, output_size * 4
        ),
        intercepts=np.random.rand(output_size * 4),
    )

    hybrid_predictor = HybridReservoirComputingModel(
        input_variables=["a", "b"],
        output_variables=["a", "b"],
        hybrid_variables=["a", "b"],
        reservoir=reservoir,
        readout=readout,
        rank_divider=divider,
        autoencoder=autoencoder,
    )
    hybrid_predictor.reset_state()

    return hybrid_predictor


def get_single_rank_xarray_data():
    rng = np.random.RandomState(0)
    a = rng.randn(8, 8, 3)  # two variables concatenated to form size 6 latent space
    b = rng.randn(8, 8, 3)

    return xr.Dataset(
        {
            "a": xr.DataArray(a, dims=["x", "y", "z"]),
            "b": xr.DataArray(b, dims=["x", "y", "z"]),
        }
    )


def test_adapter_predict(regtest):
    hybrid_predictor = get_initialized_hybrid_model()
    data = get_single_rank_xarray_data()

    model = HybridDatasetAdapter(hybrid_predictor)
    nhalo = model.model.rank_divider.overlap
    data_without_overlap = data.isel(
        {"x": slice(nhalo, -nhalo), "y": slice(nhalo, -nhalo)}
    )
    result = model.predict(data_without_overlap)
    print(result, file=regtest)


def test_adapter_increment_state():
    hybrid_predictor = get_initialized_hybrid_model()
    data = get_single_rank_xarray_data()

    model = HybridDatasetAdapter(hybrid_predictor)
    model.reset_state()
    model.increment_state(data)
