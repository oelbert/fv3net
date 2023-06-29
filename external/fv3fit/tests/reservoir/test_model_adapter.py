import numpy as np
import xarray as xr

from fv3fit.reservoir.transformers.transformer import Transformer
from fv3fit.reservoir.domain import RankDivider
from fv3fit.reservoir.readout import ReservoirComputingReadout
from fv3fit.reservoir import (
    Reservoir,
    ReservoirHyperparameters,
    HybridReservoirComputingModel,
)
from fv3fit.reservoir.model import HybridDatasetAdapter


class DoNothingAutoencoder(Transformer):
    def __init__(self, latent_dim_len):
        self._latent_dim_len = latent_dim_len
        self._array_feature_sizes = None

    @property
    def n_latent_dims(self):
        return self._latent_dim_len

    def encode(self, x):
        self._array_feature_sizes = [arr.shape[-1] for arr in x]
        return np.concatenate(x, -1)

    def decode(self, latent_x):
        if self._array_feature_sizes is None:
            raise ValueError("Must encode data before decoding.")

        split_indices = np.cumsum(self._array_feature_sizes)[:-1]
        return np.split(latent_x, split_indices, axis=-1)


def get_initialized_hybrid_model():
    # expects rank size (including halos) in latent space
    divider = RankDivider((2, 2), ["x", "y"], [8, 8], 2)
    autoencoder = DoNothingAutoencoder(6)
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

    result = model.predict(data)
    print(result, file=regtest)


def test_adapter_increment_state():
    hybrid_predictor = get_initialized_hybrid_model()
    data = get_single_rank_xarray_data()

    model = HybridDatasetAdapter(hybrid_predictor)
    model.reset_state()
    model.increment_state(data)
