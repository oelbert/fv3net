import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import os
from scipy.stats import binned_statistic_2d
import xarray as xr

from vcm.calc import r2_score
from vcm.calc.calc import local_time
from vcm.cubedsphere.constants import (
    INIT_TIME_DIM,
    COORD_X_CENTER,
    COORD_Y_CENTER,
    COORD_Z_CENTER,
    VAR_LAT_CENTER,
    PRESSURE_GRID,
)
from vcm.cubedsphere.regridz import regrid_to_common_pressure
from vcm.select import mask_to_surface_type
from vcm.calc.thermo import pressure_at_midpoint_log
from vcm.visualize import plot_cube, mappable_var

from vcm.visualize.plot_diagnostics import plot_diurnal_cycle
from fv3net.diagnostics.data_funcs import (
    merge_comparison_datasets,
    get_latlon_grid_coords_set,
    EXAMPLE_CLIMATE_LATLON_COORDS,
)
from fv3net.diagnostics.sklearn_model_performance.data_funcs_sklearn import (
    integrate_for_Q,
    lower_tropospheric_stability,
)

kg_m2s_to_mm_day = (1e3 * 86400) / 997.0
SEC_PER_DAY = 86400

SAMPLE_DIM = "sample"
STACK_DIMS = ["tile", INIT_TIME_DIM, COORD_X_CENTER, COORD_Y_CENTER]

DPI_FIGURES = {
    "LTS": 100,
    "Q2_pressure_profiles": 70,
    "R2_pressure_profiles": 70,
    "diurnal_cycle": 80,
    "map_plot_3col": 120,
}


def make_all_plots(ds_pred, ds_target, ds_hires, grid, output_dir):
    """ Makes figures for predictions on test data

    Args:
        ds_pred: unstacked dataset of prediction on test set
        ds_target: unstacked test data with target values
        ds_hires: unstacked coarsened high res diagnostic data
        grid: grid spec
        output_dir: location to write figures to

    Returns:
        dict of header keys and image path list values for passing to the html
        report template
    """
    for ds in [ds_pred, ds_target, ds_hires]:
        if not set(STACK_DIMS).issubset(ds.dims):
            raise ValueError(
                f"Make sure all datasets are unstacked,"
                "i.e. have original dimensions {STACK_DIMS}."
            )
    report_sections = {}

    # for convenience, separate the land/sea data
    slmsk = ds_target.isel({COORD_Z_CENTER: -1, INIT_TIME_DIM: 0}).slmsk
    ds_pred_sea = mask_to_surface_type(xr.merge([ds_pred, slmsk]), "sea").drop("slmsk")
    ds_target_sea = mask_to_surface_type(xr.merge([ds_target, slmsk]), "sea").drop(
        "slmsk"
    )
    ds_pred_land = mask_to_surface_type(xr.merge([ds_pred, slmsk]), "land").drop(
        "slmsk"
    )
    ds_target_land = mask_to_surface_type(xr.merge([ds_target, slmsk]), "land").drop(
        "slmsk"
    )
    ds_pe = merge_comparison_datasets(
        "P-E",
        [ds_pred, ds_target, ds_hires],
        ["prediction", "target C48", "coarsened high res"],
        grid,
        slmsk,
    )
    ds_heating = merge_comparison_datasets(
        "heating",
        [ds_pred, ds_target, ds_hires],
        ["prediction", "target C48", "coarsened high res"],
        grid,
        slmsk,
    )

    # LTS
    PE_pred = (
        mask_to_surface_type(ds_pe.sel(dataset="prediction"), "sea")["P-E"]
        .squeeze()
        .drop("dataset")
    )
    PE_hires = (
        mask_to_surface_type(ds_pe.sel(dataset="coarsened high res"), "sea")["P-E"]
        .squeeze()
        .drop("dataset")
    )
    _plot_lower_troposphere_stability(
        xr.merge([grid, ds_target_sea]),
        PE_pred,
        PE_hires,
        mask_to_surface_type(ds_pe.sel(dataset="coarsened high res"), "sea")["P-E"],
    ).savefig(os.path.join(output_dir, "LTS_vs_Q.png"), dpi=DPI_FIGURES["LTS"])
    report_sections["Lower tropospheric stability vs humidity"] = ["LTS_vs_Q.png"]

    # Vertical Q2 profiles over land and ocean
    _make_vertical_profile_plots(
        ds_pred_land, ds_target_land, "Q2", "[kg/kg/day]", "global Q2 vertical profile"
    ).savefig(os.path.join(output_dir, "vertical_profile_Q2_land.png"))
    _make_vertical_profile_plots(
        ds_pred_sea, ds_target_sea, "Q2", "[kg/kg/day]", "global Q2 vertical profile"
    ).savefig(
        os.path.join(output_dir, "vertical_profile_Q2_sea.png"),
        dpi=DPI_FIGURES["Q2_pressure_profiles"],
    )
    report_sections["Q2 pressure level profiles"] = [
        "vertical_profile_Q2_land.png",
        "vertical_profile_Q2_sea.png",
    ]

    # R^2 vs pressure plots
    _make_r2_plot(ds_pred, ds_target, ["Q1", "Q2"], title="$R^2$, global").savefig(
        os.path.join(output_dir, "r2_vs_pressure_level_global.png")
    )
    _make_land_sea_r2_plot(
        ds_pred_sea, ds_pred_land, ds_target_sea, ds_target_land, vars=["Q1", "Q2"]
    ).savefig(
        os.path.join(output_dir, "r2_vs_pressure_level_landsea.png"),
        dpi=DPI_FIGURES["R2_pressure_profiles"],
    )
    report_sections["R^2 vs pressure levels"] = [
        "r2_vs_pressure_level_global.png",
        "r2_vs_pressure_level_landsea.png",
    ]

    # plot P-E across the diurnal cycle
    local_coords = get_latlon_grid_coords_set(grid, EXAMPLE_CLIMATE_LATLON_COORDS)
    ds_pe["local_time"] = local_time(ds_pe)
    ds_heating["local_time"] = local_time(ds_heating)
    plot_diurnal_cycle(
        mask_to_surface_type(ds_pe, "sea"), "P-E", title="ocean"
    ).savefig(
        os.path.join(output_dir, "diurnal_cycle_P-E_sea.png"),
        dpi=DPI_FIGURES["diurnal_cycle"],
    )
    plot_diurnal_cycle(
        mask_to_surface_type(ds_pe, "land"), "P-E", title="land"
    ).savefig(
        os.path.join(output_dir, "diurnal_cycle_P-E_land.png"),
        dpi=DPI_FIGURES["diurnal_cycle"],
    )
    for location_name, coords in local_coords.items():
        plot_diurnal_cycle(
            ds_pe.sel(coords), "P-E", title=location_name, ylabel="P-E [mm]"
        ).savefig(
            os.path.join(output_dir, f"diurnal_cycle_P-E_{location_name}.png"),
            dpi=DPI_FIGURES["diurnal_cycle"],
        )
    report_sections["Diurnal cycle, P-E"] = [
        "diurnal_cycle_P-E_sea.png",
        "diurnal_cycle_P-E_land.png",
    ] + [f"diurnal_cycle_P-E_{location_name}.png" for location_name in local_coords]

    # plot column heating across the diurnal cycle
    plot_diurnal_cycle(
        mask_to_surface_type(ds_heating, "sea"), "heating", title="sea"
    ).savefig(
        os.path.join(output_dir, "diurnal_cycle_heating_sea.png"),
        dpi=DPI_FIGURES["diurnal_cycle"],
    )
    plot_diurnal_cycle(
        mask_to_surface_type(ds_heating, "land"), "heating", title="land"
    ).savefig(
        os.path.join(output_dir, "diurnal_cycle_heating_land.png"),
        dpi=DPI_FIGURES["diurnal_cycle"],
    )

    for location_name, coords in local_coords.items():
        plot_diurnal_cycle(
            ds_heating.sel(coords),
            "heating",
            title=location_name,
            ylabel="heating [W/m$^2$]",
        ).savefig(
            os.path.join(output_dir, f"diurnal_cycle_heating_{location_name}.png"),
            dpi=DPI_FIGURES["diurnal_cycle"],
        )
    report_sections["Diurnal cycle, heating"] = [
        "diurnal_cycle_heating_sea.png",
        "diurnal_cycle_heating_land.png",
    ] + [f"diurnal_cycle_heating_{location_name}.png" for location_name in local_coords]

    # map plot variables and compare across prediction/ C48 /coarsened high res data
    _plot_comparison_maps(
        ds_pe,
        "P-E",
        time_index_selection=None,
        plot_cube_kwargs={"cbar_label": "time avg, P-E [mm/day]"},
    ).savefig(
        os.path.join(output_dir, "P-E_time_avg.png"), dpi=DPI_FIGURES["map_plot_3col"]
    )
    _plot_comparison_maps(
        ds_pe,
        "P-E",
        time_index_selection=[0, 2],
        plot_cube_kwargs={"cbar_label": "timestep snapshot, P-E [mm/day]"},
    ).savefig(
        os.path.join(output_dir, "P-E_time_snapshots.png"),
        dpi=DPI_FIGURES["map_plot_3col"],
    )
    report_sections["P-E"] = ["P-E_time_avg.png", "P-E_time_snapshots.png"]

    _plot_comparison_maps(
        ds_heating,
        "heating",
        time_index_selection=None,
        plot_cube_kwargs={"cbar_label": "time avg, column heating [W/m$^2$]"},
    ).savefig(
        os.path.join(output_dir, "column_heating_time_avg.png"),
        dpi=DPI_FIGURES["map_plot_3col"],
    )
    _plot_comparison_maps(
        ds_heating,
        "heating",
        time_index_selection=[0, -1],
        plot_cube_kwargs={"cbar_label": "timestep snapshot, column heating [W/m$^2$]"},
    ).savefig(
        os.path.join(output_dir, "column_heating_snapshots.png"),
        dpi=DPI_FIGURES["map_plot_3col"],
    )
    report_sections["Column heating"] = [
        "column_heating_time_avg.png",
        "column_heating_snapshots.png",
    ]

    return report_sections


# Below are plotting functions specific to this diagnostic workflow


def _make_r2_plot(ds_pred, ds_target, vars, sample_dim=SAMPLE_DIM, title=None):
    plt.clf()
    fig = plt.figure()
    if isinstance(vars, str):
        vars = [vars]
    x = np.array(PRESSURE_GRID) / 100
    for var in vars:
        y = r2_score(
            regrid_to_common_pressure(ds_target[var], ds_target["delp"]).stack(
                sample=STACK_DIMS
            ),
            regrid_to_common_pressure(ds_pred[var], ds_pred["delp"]).stack(
                sample=STACK_DIMS
            ),
            sample_dim,
        ).values
        plt.plot(x, y, label=var)
    plt.legend()
    plt.xlabel("pressure [HPa]")
    plt.ylabel("$R^2$")
    if title:
        plt.title(title)
    plt.show()
    return fig


def _make_land_sea_r2_plot(
    ds_pred_sea, ds_pred_land, ds_target_sea, ds_target_land, vars
):
    plt.clf()
    fig = plt.figure()
    x = np.array(PRESSURE_GRID) / 100
    colors = ["blue", "orange"]
    for color, var in zip(colors, vars):
        y_sea = r2_score(
            regrid_to_common_pressure(ds_target_sea[var], ds_target_sea["delp"]).stack(
                sample=STACK_DIMS
            ),
            regrid_to_common_pressure(ds_pred_sea[var], ds_pred_sea["delp"]).stack(
                sample=STACK_DIMS
            ),
            SAMPLE_DIM,
        ).values
        y_land = r2_score(
            regrid_to_common_pressure(
                ds_target_land[var], ds_target_land["delp"]
            ).stack(sample=STACK_DIMS),
            regrid_to_common_pressure(ds_pred_land[var], ds_pred_land["delp"]).stack(
                sample=STACK_DIMS
            ),
            SAMPLE_DIM,
        ).values
        plt.plot(x, y_sea, color=color, alpha=0.7, label=f"{var}, sea", linestyle="--")
        plt.plot(x, y_land, color=color, alpha=0.7, label=f"{var}, land", linestyle=":")
    plt.legend()
    plt.xlabel("pressure [HPa]")
    plt.ylabel("$R^2$")
    plt.show()
    return fig


def _plot_comparison_maps(
    ds_merged, var, time_index_selection=None, plot_cube_kwargs=None
):
    # map plot a variable and compare across prediction/ C48 /coarsened high res data
    matplotlib.rcParams["figure.dpi"] = 200
    plt.clf()
    plot_cube_kwargs = plot_cube_kwargs or {}

    if not time_index_selection:
        map_var = mappable_var(ds_merged.mean(INIT_TIME_DIM), var)
    else:
        map_var = mappable_var(
            ds_merged.isel({INIT_TIME_DIM: time_index_selection}), var
        )
        plot_cube_kwargs["row"] = INIT_TIME_DIM
    fig = plot_cube(map_var, col="dataset", **plot_cube_kwargs)[0]
    if isinstance(time_index_selection, int):
        time_label = (
            ds_merged[INIT_TIME_DIM]
            .values[time_index_selection]
            .strftime("%Y-%m-%d, %H:%M:%S")
        )
        plt.suptitle(time_label)
    plt.show()
    return fig


def _make_vertical_profile_plots(ds_pred, ds_target, var, units, title=None):
    """Creates vertical profile plots of Q2 for drying/moistening columns

    Args:
        ds_pred (xr dataset): [description]
        ds_target (xr dataset): [description]
        var (str): [description]
        units (str): [description]
        output_dir (str): [description]
        plot_filename (str, optional): [description].
             Defaults to f"vertical_profile.png".
        title (str, optional): [description]. Defaults to None.
    """

    plt.clf()
    fig = plt.figure()
    pos_mask, neg_mask = ds_target["P-E"] > 0, ds_target["P-E"] < 0
    ds_pred = regrid_to_common_pressure(ds_pred[var], ds_pred["delp"])
    ds_target = regrid_to_common_pressure(ds_target[var], ds_target["delp"])

    ds_pred_pos_PE = ds_pred.where(pos_mask)
    ds_pred_neg_PE = ds_pred.where(neg_mask)
    ds_target_pos_PE = ds_target.where(pos_mask)
    ds_target_neg_PE = ds_target.where(neg_mask)

    pressure = ds_pred.pressure.values / 100.0
    profiles_kwargs = zip(
        [ds_pred_pos_PE, ds_target_pos_PE, ds_pred_neg_PE, ds_target_neg_PE],
        [
            {"label": "P-E > 0, prediction", "color": "blue", "linestyle": "-"},
            {"label": "P-E > 0, target", "color": "blue", "linestyle": "--"},
            {"label": "P-E < 0, prediction", "color": "orange", "linestyle": "-"},
            {"label": "P-E < 0, target", "color": "orange", "linestyle": "--"},
        ],
    )

    for data, kwargs in profiles_kwargs:
        stack_dims = [dim for dim in STACK_DIMS if dim in data.dims]
        data_mean = np.mean(np.nan_to_num(data.stack(sample=stack_dims).values), axis=1)
        plt.plot(pressure, data_mean, **kwargs)

    plt.xlabel("Pressure [HPa]")
    plt.ylabel(units)
    if title:
        plt.title(title)
    plt.legend()
    plt.show()
    return fig


def _plot_lower_troposphere_stability(ds, PE_pred, PE_hires, lat_max=20):
    lat_mask = abs(ds[VAR_LAT_CENTER]) < lat_max
    PE_pred = PE_pred.rename("PE_pred")
    PE_hires = PE_hires.rename("PE_hires")
    ds = (
        xr.merge([ds, PE_pred, PE_hires])
        .where(lat_mask)
        .stack(sample=STACK_DIMS)
        .dropna("sample")
    )

    ds["pressure"] = pressure_at_midpoint_log(ds["delp"])
    Q = [
        integrate_for_Q(p, qt)
        for p, qt in zip(ds["pressure"].values.T, ds["sphum"].values.T)
    ]
    LTS = lower_tropospheric_stability(ds)

    fig = plt.figure(figsize=(16, 4))

    ax1 = fig.add_subplot(131)
    hist = ax1.hist2d(LTS.values, Q)
    cbar1 = fig.colorbar(hist[3], ax=ax1)
    cbar1.set_label("count")
    ax1.set_xlabel("LTS [K]")
    ax1.set_ylabel("Q [mm]")

    ax2 = fig.add_subplot(132)
    bin_values_pred, x_edge, y_edge, _ = binned_statistic_2d(
        LTS.values, Q, ds["PE_pred"].values, statistic="mean", bins=20
    )
    X, Y = np.meshgrid(x_edge, y_edge)
    PE = ax2.pcolormesh(X, Y, bin_values_pred.T, vmin=-10, vmax=100)
    cbar2 = fig.colorbar(PE, ax=ax2)
    cbar2.set_label("P-E [mm/d]")
    ax2.set_xlabel("LTS [K]")
    ax2.set_ylabel("Q [mm]")
    ax2.set_title("Avg predicted P-E")

    ax3 = fig.add_subplot(133)
    bin_values_hires, x_edge, y_edge, _ = binned_statistic_2d(
        LTS.values, Q, ds["PE_hires"].values, statistic="mean", bins=20
    )
    bin_error = bin_values_pred - bin_values_hires
    PE_err = ax3.pcolormesh(X, Y, bin_error.T)
    cbar3 = fig.colorbar(PE_err, ax=ax3)
    cbar3.set_label("P-E [mm/d]")
    ax3.set_xlabel("LTS [K]")
    ax3.set_ylabel("Q [mm]")
    ax3.set_title("Avg P-E error (predicted - high res)")
    plt.show()
    return fig