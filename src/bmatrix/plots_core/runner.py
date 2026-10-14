"""Plotting and summary helpers for completed MPAS-JEDI/SABER B-matrix products."""
from __future__ import annotations

import csv
from dataclasses import asdict
import math
from pathlib import Path
import shutil
from typing import Iterable, Mapping, Sequence

from ..products import BMatrixProducts

DEFAULT_PLOT_VARIABLES: tuple[str, ...] = (
    "stream_function",
    "velocity_potential",
    "temperature",
    "spechum",
    "surface_pressure",
    "air_temperature",
    "air_pressure_at_surface",
    "water_vapor_mixing_ratio_wrt_moist_air",
)

CONTROL_LABELS = {
    "stream_function": r"$\psi$",
    "velocity_potential": r"$\chi_u$",
    "temperature": r"$T_u$",
    "spechum": r"$q$",
    "surface_pressure": r"$p_s$",
    "air_temperature": r"$T$",
    "air_pressure_at_surface": r"$p_s$",
    "water_vapor_mixing_ratio_wrt_moist_air": r"$q$",
}

VBAL_PAIRS: tuple[tuple[str, str], ...] = (
    ("stream_function-temperature", r"$T$ explicada por $\psi$"),
    ("stream_function-velocity_potential", r"$\chi$ explicada por $\psi$"),
    ("stream_function-surface_pressure", r"$p_s$ explicada por $\psi$"),
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "product",
    "path",
    "variable",
    "shape",
    "min",
    "max",
    "mean",
    "rms",
    "max_abs",
    "nonzero_count",
)

FG = "#1f2937"
MUTED = "#4b5563"
GRID = "#cbd5e1"
ACCENTS = ("#0099d7", "#00a98f", "#f17c0b", "#cf6ca7")


class PlotContext:
    """Runtime imports used by plotting helpers."""

    def __init__(self):
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import matplotlib.tri as mtri
            import netCDF4
            import numpy as np
        except ImportError as exc:  # pragma: no cover - depends on runtime environment
            raise RuntimeError("A etapa plots requer netCDF4, numpy e matplotlib.") from exc

        self.plt = plt
        self.mtri = mtri
        self.netcdf4 = netCDF4
        self.np = np


def plots_workspace_from_bflow(config: Mapping[str, object], bflow_workspace: str | Path) -> Path:
    """Return the deterministic plots workspace for a BFLOW workspace."""
    project = config.get("project", {})
    if not isinstance(project, Mapping):
        raise ValueError("Configuração inválida: seção project ausente.")
    work_root = Path(str(project.get("work_root", ".")))
    return work_root / "bmatrix" / "plots" / Path(bflow_workspace).name


def generate_plots(
    products: BMatrixProducts,
    workspace: str | Path,
    *,
    clean: bool = False,
    level: int = 30,
    dpi: int = 150,
    variables: Sequence[str] | None = None,
) -> dict[str, Path]:
    """Generate CSV summaries and presentation-style diagnostics.

    The scientific figures are intentionally local and read-only.  They do not
    submit PBS jobs and never modify B-matrix products.  The layout follows the
    compact diagnostics used in B.J.-style B-matrix presentations: latitude-level
    sections, balance explained variance and local DIRAC spatial response maps.
    """
    ctx = PlotContext()
    _style(ctx)

    root = Path(workspace)
    if clean and root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    selected = tuple(variables or DEFAULT_PLOT_VARIABLES)
    product_map = _product_map(products)
    summary_rows: list[dict[str, object]] = []
    figures: list[Path] = []

    for product_name, path in product_map.items():
        if not path.is_file():
            raise FileNotFoundError(f"Produto obrigatório ausente para plots: {path}")
        with ctx.netcdf4.Dataset(path) as dataset:
            summary_rows.extend(_summarize_dataset(product_name, path, dataset, ctx=ctx))

    figures.extend(_generate_presentation_figures(products, root, selected, level, dpi, ctx))

    # Keep small per-product quicklooks as a fallback/sanity check, but place them
    # after the scientific products so they do not dominate the output directory.
    figures.extend(_generate_quicklooks(product_map, root / "99_quicklook", selected, level, dpi, ctx))

    summary_csv = root / "summary.csv"
    _write_summary_csv(summary_csv, summary_rows)
    readme = root / "README.md"
    _write_readme(readme, products, summary_csv, figures, level=level, dpi=dpi)

    print("=== PLOTS validation ===")
    print(f"WORKSPACE={root}")
    print(f"SUMMARY={summary_csv}")
    print(f"FIGURES={len(figures)}")
    print("SUCCESS: PLOTS gerados.")
    return {"workspace": root, "summary": summary_csv, "readme": readme}


def validate_plots(workspace: str | Path) -> bool:
    """Validate a completed plots workspace."""
    root = Path(workspace)
    summary = root / "summary.csv"
    readme = root / "README.md"
    if not summary.is_file():
        raise FileNotFoundError(f"summary.csv ausente: {summary}")
    if not readme.is_file():
        raise FileNotFoundError(f"README.md ausente: {readme}")
    figures = sorted(root.glob("**/*.png"))
    if not figures:
        raise FileNotFoundError(f"Nenhuma figura PNG encontrada em {root}")
    print("=== PLOTS validation ===")
    print(f"WORKSPACE={root}")
    print(f"FIGURES={len(figures)}")
    print("SUCCESS: PLOTS validado.")
    return True


def _style(ctx: PlotContext) -> None:
    ctx.plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "axes.edgecolor": MUTED,
            "axes.labelcolor": FG,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "text.color": FG,
            "axes.titlecolor": FG,
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.titleweight": "bold",
            "axes.titlepad": 10,
            "grid.color": GRID,
            "grid.alpha": 0.9,
            "grid.linestyle": ":",
            "grid.linewidth": 0.8,
            "legend.edgecolor": GRID,
            "legend.labelcolor": FG,
        }
    )


def _generate_presentation_figures(
    products: BMatrixProducts,
    root: Path,
    selected: Sequence[str],
    level: int,
    dpi: int,
    ctx: PlotContext,
) -> list[Path]:
    figures: list[Path] = []
    figures.extend(_plot_presentation_set(products, root, selected, level, dpi, ctx))
    figures.extend(_plot_hdiag_latlev(products, root, selected, dpi, ctx))
    figures.extend(_plot_vbal(products, root, dpi, ctx))
    figures.extend(_plot_dirac(products, root, selected, level, dpi, ctx))
    figures.extend(_plot_spatial_fields(products, root, selected, level, dpi, ctx))
    return figures


def _plot_hdiag_latlev(
    products: BMatrixProducts,
    root: Path,
    selected: Sequence[str],
    dpi: int,
    ctx: PlotContext,
) -> list[Path]:
    datasets = (
        ("01_stddev", "stddev", products.stddev, "Desvio-padrão", "desvio-padrão", False),
        ("02_corr_horizontal", "cor_rh", products.cor_rh, "Escala horizontal", "km", True),
        ("03_corr_vertical", "cor_rv", products.cor_rv, "Escala vertical", "km", True),
    )
    figures: list[Path] = []
    for directory, product_name, path, title, unit_label, convert_km in datasets:
        outdir = root / directory
        outdir.mkdir(parents=True, exist_ok=True)
        with ctx.netcdf4.Dataset(path) as dataset:
            for name in _ordered_plot_variables(dataset.variables, selected):
                variable = dataset.variables[name]
                if not _is_numeric_variable(variable, ctx=ctx):
                    continue
                target_size = _latitude_target_size(variable, ctx=ctx)
                lat = _latitude_for_dataset(dataset, products, target_size=target_size, ctx=ctx)
                result = _lat_level_field(variable, lat, ctx=ctx)
                if result is None:
                    continue
                latlev, plot_lat = result
                if latlev is None or not ctx.np.isfinite(latlev).any():
                    continue
                if convert_km:
                    latlev = _as_km(latlev, getattr(variable, "units", ""), ctx=ctx)
                label = CONTROL_LABELS.get(name, name)

                if latlev.shape[1] == 1:
                    figure = outdir / f"{product_name}_{_safe_name(name)}_vertical_profile.png"
                    _plot_vertical_profile(latlev[:, 0], title, label, unit_label, figure, dpi, ctx)
                elif latlev.shape[0] == 1:
                    figure = outdir / f"{product_name}_{_safe_name(name)}_lat_profile.png"
                    _plot_lat_profile(latlev[0], plot_lat, title, label, unit_label, figure, dpi, ctx)
                else:
                    figure = outdir / f"{product_name}_{_safe_name(name)}_latlev.png"
                    _plot_latlev(latlev, plot_lat, title, label, unit_label, figure, dpi, ctx)
                figures.append(figure)
    return figures


def _plot_vbal(products: BMatrixProducts, root: Path, dpi: int, ctx: PlotContext) -> list[Path]:
    outdir = root / "04_vbal"
    outdir.mkdir(parents=True, exist_ok=True)
    figures: list[Path] = []
    lat = _latitudes_from_vbal(products.vbal, ctx)
    if lat is None:
        return figures
    order = ctx.np.argsort(lat)
    sorted_lat = lat[order]
    with ctx.netcdf4.Dataset(products.vbal) as dataset:
        figure = outdir / "vbal_explained_variance_by_stream_function.png"
        if _plot_vbal_explained(dataset, sorted_lat, order, figure, dpi, ctx):
            figures.append(figure)
        figure = outdir / "vbal_temperature_stream_function_regression.png"
        if _plot_vbal_regression(dataset, lat, target_lat=35.0, output=figure, dpi=dpi, ctx=ctx):
            figures.append(figure)
    return figures


def _plot_dirac(
    products: BMatrixProducts,
    root: Path,
    selected: Sequence[str],
    level: int,
    dpi: int,
    ctx: PlotContext,
) -> list[Path]:
    outdir = root / "05_dirac"
    outdir.mkdir(parents=True, exist_ok=True)
    figures: list[Path] = []
    with ctx.netcdf4.Dataset(products.dirac) as dataset:
        for name in _ordered_plot_variables(dataset.variables, selected):
            if name not in dataset.variables:
                continue
            variable = dataset.variables[name]
            if not _is_numeric_variable(variable, ctx=ctx):
                continue
            levels, fields = _spatial_levels(variable, level, ctx=ctx)
            if not fields:
                continue
            lon, lat = _coordinates_for_size(products, len(fields[0]), ctx=ctx, dataset=dataset)
            if lon is None or lat is None:
                continue
            figure = outdir / f"dirac_{_safe_name(name)}_spatial_response.png"
            _plot_dirac_spatial(name, lon, lat, levels, fields, figure, dpi, ctx)
            figures.append(figure)
    return figures


def _generate_quicklooks(
    product_map: Mapping[str, Path],
    root: Path,
    selected: Sequence[str],
    level: int,
    dpi: int,
    ctx: PlotContext,
) -> list[Path]:
    root.mkdir(parents=True, exist_ok=True)
    figures: list[Path] = []
    for product_name, path in product_map.items():
        with ctx.netcdf4.Dataset(path) as dataset:
            figures.extend(_plot_dataset(product_name, path, dataset, root, selected, level, dpi, ctx))
    return figures


def _plot_latlev(latlev, lat, title: str, label: str, unit: str, output: Path, dpi: int, ctx: PlotContext) -> None:
    values = ctx.np.asarray(latlev, dtype=float)
    lat = ctx.np.asarray(lat, dtype=float)
    finite = values[ctx.np.isfinite(values)]
    if finite.size == 0:
        return
    vmin = float(ctx.np.nanpercentile(finite, 2.0))
    vmax = float(ctx.np.nanpercentile(finite, 98.0))
    if not ctx.np.isfinite(vmin) or not ctx.np.isfinite(vmax) or vmin == vmax:
        vmin = float(ctx.np.nanmin(finite))
        vmax = float(ctx.np.nanmax(finite))
    levels = ctx.np.linspace(vmin, vmax, 17)

    fig, axis = ctx.plt.subplots(figsize=(8.4, 5.6))
    image = axis.contourf(
        lat,
        ctx.np.arange(values.shape[0]),
        ctx.np.ma.masked_invalid(values),
        levels=levels,
        cmap="viridis",
        extend="both",
    )
    lines = axis.contour(
        lat,
        ctx.np.arange(values.shape[0]),
        ctx.np.ma.masked_invalid(values),
        levels=levels[::4],
        colors="#334155",
        linewidths=0.45,
        alpha=0.5,
    )
    axis.clabel(lines, inline=True, fontsize=7, fmt="%.2g", colors="#475569")
    axis.set_title(f"{title} — {label}")
    axis.set_xlabel("Latitude (°)")
    axis.set_ylabel("Nível vertical")
    axis.grid(True)
    colorbar = fig.colorbar(image, ax=axis, pad=0.018, fraction=0.048)
    colorbar.set_label(unit)
    _finish(fig, output, dpi, ctx)


def _plot_lat_profile(profile, lat, title: str, label: str, unit: str, output: Path, dpi: int, ctx: PlotContext) -> None:
    fig, axis = ctx.plt.subplots(figsize=(8.2, 4.6))
    axis.plot(lat, profile, color=ACCENTS[0], linewidth=2.8)
    axis.fill_between(lat, 0.0, profile, color=ACCENTS[0], alpha=0.12)
    axis.set_title(f"{title} — {label}")
    axis.set_xlabel("Latitude (°)")
    axis.set_ylabel(unit)
    axis.grid(True)
    _finish(fig, output, dpi, ctx)


def _plot_vertical_profile(profile, title: str, label: str, unit: str, output: Path, dpi: int, ctx: PlotContext) -> None:
    values = ctx.np.asarray(profile, dtype=float)
    levels = ctx.np.arange(values.size)
    finite = ctx.np.isfinite(values)
    if not finite.any():
        return
    fig, axis = ctx.plt.subplots(figsize=(6.4, 5.8))
    axis.plot(values[finite], levels[finite], color=ACCENTS[0], linewidth=2.8)
    axis.set_title(f"{title} — {label}")
    axis.set_xlabel(unit)
    axis.set_ylabel("Nível vertical")
    axis.grid(True)
    _finish(fig, output, dpi, ctx)


def _plot_vbal_explained(dataset, lat, order, output: Path, dpi: int, ctx: PlotContext) -> bool:
    levels_fill = ctx.np.linspace(0.0, 1.0, 11)
    levels_line = ctx.np.linspace(0.1, 0.9, 5)
    fig, axes = ctx.plt.subplots(1, 3, figsize=(15.8, 5.9), sharey=False)
    fig.suptitle("Matriz B — componente de variância explicada pelo balanço", fontsize=17)
    plotted = False
    for axis, (pair, label) in zip(axes, VBAL_PAIRS):
        try:
            _, variable = _group_variable(dataset, pair, "explained_var")
            values = _lat_level_from_values(_clean(variable[:], ctx=ctx), lat, ctx=ctx)[:, order]
        except (KeyError, ValueError):
            axis.set_axis_off()
            axis.set_title(f"{label}\nindisponível")
            continue
        if pair.endswith("surface_pressure"):
            valid = ctx.np.where(ctx.np.isfinite(values).any(axis=1))[0]
            if not valid.size:
                axis.set_axis_off()
                continue
            row = valid[int(ctx.np.argmax(ctx.np.nanmean(ctx.np.abs(values[valid]), axis=1)))]
            profile = values[row]
            axis.plot(lat, profile, color=ACCENTS[0], linewidth=3.0)
            axis.fill_between(lat, 0.0, profile, color=ACCENTS[0], alpha=0.12)
            axis.set_ylim(0.0, 1.02)
            axis.set_ylabel("Fração da variância")
            axis.text(
                0.03,
                0.92,
                f"campo de superfície (nível {row})",
                transform=axis.transAxes,
                color=MUTED,
                fontsize=9.5,
                ha="left",
                va="top",
            )
            axis.grid(True)
        else:
            masked = ctx.np.ma.masked_invalid(values)
            filled = axis.contourf(
                lat,
                ctx.np.arange(values.shape[0]),
                masked,
                levels=levels_fill,
                cmap="RdYlBu_r",
                extend="neither",
                antialiased=True,
            )
            lines = axis.contour(
                lat,
                ctx.np.arange(values.shape[0]),
                masked,
                levels=levels_line,
                colors="#334155",
                linewidths=0.55,
                alpha=0.55,
            )
            axis.clabel(lines, inline=True, fontsize=7, fmt="%.1f", colors="#475569")
            axis.set_ylabel("Nível vertical")
            colorbar = fig.colorbar(filled, ax=axis, pad=0.015, fraction=0.046)
            colorbar.set_label("Fração da variância")
            colorbar.set_ticks(ctx.np.linspace(0.0, 1.0, 6))
        axis.set_title(label)
        axis.set_xlabel("Latitude (°)")
        plotted = True
    _finish(fig, output, dpi, ctx)
    return plotted


def _plot_vbal_regression(dataset, lat, target_lat: float, output: Path, dpi: int, ctx: PlotContext) -> bool:
    try:
        _, variable = _group_variable(dataset, "stream_function-temperature", "reg")
    except KeyError:
        return False
    values = _clean(variable[:], ctx=ctx)
    if values.ndim != 3:
        return False
    index = int(ctx.np.nanargmin(ctx.np.abs(lat - target_lat)))
    if values.shape[-1] == lat.size:
        matrix = values[:, :, index]
    elif values.shape[0] == lat.size:
        matrix = values[index, :, :]
    else:
        return False
    finite = ctx.np.abs(matrix[ctx.np.isfinite(matrix)])
    if finite.size == 0:
        return False
    amplitude = float(ctx.np.nanpercentile(finite, 98.0))
    if not ctx.np.isfinite(amplitude) or amplitude <= 0.0:
        amplitude = float(ctx.np.nanmax(finite))
    levels_fill = ctx.np.linspace(-amplitude, amplitude, 17)
    levels_line = ctx.np.linspace(-amplitude, amplitude, 9)

    fig = ctx.plt.figure(figsize=(8.8, 6.8))
    grid = fig.add_gridspec(1, 2, width_ratios=[1.0, 0.055], wspace=0.08)
    axis = fig.add_subplot(grid[0, 0])
    colorbar_axis = fig.add_subplot(grid[0, 1])
    fig.suptitle(rf"Regressão vertical $T \leftarrow \psi$ — {lat[index]:.1f}°", fontsize=17)
    x = ctx.np.arange(matrix.shape[1])
    y = ctx.np.arange(matrix.shape[0])
    filled = axis.contourf(x, y, matrix, levels=levels_fill, cmap="coolwarm", extend="both")
    contour_levels = levels_line[ctx.np.abs(levels_line) > max(amplitude * 0.05, ctx.np.finfo(float).eps)]
    if contour_levels.size:
        lines = axis.contour(x, y, matrix, levels=contour_levels, colors="#334155", linewidths=0.45, alpha=0.45)
        axis.clabel(lines, inline=True, fontsize=6, fmt="%.1e", colors="#475569")
    axis.contour(x, y, matrix, levels=[0.0], colors=FG, linewidths=1.0, alpha=0.75)
    axis.set_xlabel(r"Nível de $\psi$")
    axis.set_ylabel(r"Nível de $T$")
    colorbar = fig.colorbar(filled, cax=colorbar_axis)
    colorbar.set_label("Coeficiente de regressão", labelpad=12)
    _finish(fig, output, dpi, ctx)
    return True


def _plot_dirac_spatial(
    name: str,
    lon,
    lat,
    levels: Sequence[int],
    fields: Sequence[object],
    output: Path,
    dpi: int,
    ctx: PlotContext,
) -> None:
    np = ctx.np
    center_field = np.asarray(fields[len(fields) // 2], dtype=float)
    peak = int(np.nanargmax(np.abs(center_field)))
    lon0 = float(lon[peak])
    lat0 = float(lat[peak])
    local_lon = ((lon - lon0 + 180.0) % 360.0) - 180.0
    maximum = max(float(np.nanmax(np.abs(field))) for field in fields)
    if not np.isfinite(maximum) or maximum <= 0.0:
        maximum = 1.0
    dlon = 38.0
    dlat = 28.0
    local = (np.abs(local_lon) <= dlon) & (lat >= lat0 - dlat) & (lat <= lat0 + dlat)

    fig = ctx.plt.figure(figsize=(16.8, 5.9))
    grid = fig.add_gridspec(1, len(levels) + 1, width_ratios=[1.0] * len(levels) + [0.055], wspace=0.10)
    axes = [fig.add_subplot(grid[0, index]) for index in range(len(levels))]
    colorbar_axis = fig.add_subplot(grid[0, -1])
    label = CONTROL_LABELS.get(name, name)
    fig.suptitle(f"Resposta espacial da B: {label} a um impulso em $T_u$ (DIRAC)", fontsize=17)
    norm = ctx.plt.Normalize(vmin=-maximum, vmax=maximum)
    artist = None
    for axis, field, item in zip(axes, fields, levels):
        local_field = np.asarray(field, dtype=float)
        signal = local & np.isfinite(local_field)
        artist = _spatial_artist(axis, local_lon[signal], lat[signal], local_field[signal], norm, ctx)
        axis.scatter([0.0], [lat0], marker="x", s=105, color=FG, linewidths=2.2, zorder=3)
        axis.set_title("2D/superfície" if item is None else f"Nível {item}")
        axis.set_xlabel("Longitude relativa ao impulso (°)")
        axis.set_xlim(-dlon, dlon)
        axis.set_ylim(lat0 - dlat, lat0 + dlat)
        axis.grid(True)
    axes[0].set_ylabel("Latitude (°)")
    colorbar = fig.colorbar(artist, cax=colorbar_axis)
    colorbar.set_label(f"Resposta em {label}", labelpad=12)
    fig.text(0.01, 0.035, f"Impulso: {lat0:.1f}°, {lon0:.1f}°", fontsize=8, color=MUTED, ha="left", va="bottom")
    _finish(fig, output, dpi, ctx)


def _spatial_artist(axis, x, y, values, norm, ctx: PlotContext):
    if len(values) >= 20:
        try:
            triangulation = ctx.mtri.Triangulation(x, y)
            return axis.tricontourf(triangulation, values, levels=17, cmap="coolwarm", norm=norm, extend="both")
        except (ValueError, RuntimeError):
            pass
    axis.scatter(x, y, s=6, color=GRID, alpha=0.18, linewidths=0, zorder=1)
    return axis.scatter(x, y, c=values, s=28, cmap="coolwarm", norm=norm, linewidths=0, zorder=2)


def _plot_presentation_set(
    products: BMatrixProducts,
    root: Path,
    selected: Sequence[str],
    level: int,
    dpi: int,
    ctx: PlotContext,
) -> list[Path]:
    """Recreate the compact presentation figure set from the old branch."""
    outdir = root / "00_presentation"
    outdir.mkdir(parents=True, exist_ok=True)
    figures: list[Path] = []

    lat = _latitudes_from_vbal(products.vbal, ctx)
    if lat is not None and Path(products.vbal).is_file():
        order = ctx.np.argsort(lat)
        sorted_lat = lat[order]
        with ctx.netcdf4.Dataset(products.vbal) as dataset:
            figure = outdir / "01_bmatrix_balance_explained_variance.png"
            if _plot_vbal_explained(dataset, sorted_lat, order, figure, dpi, ctx):
                figures.append(figure)

            figure = outdir / "02_bmatrix_temperature_psi_regression.png"
            if _plot_vbal_regression(dataset, lat, target_lat=35.0, output=figure, dpi=dpi, ctx=ctx):
                figures.append(figure)

    figure = outdir / "03_bmatrix_stddev_and_correlation_scales.png"
    if _plot_hdiag_profile_summary(products, figure, selected, dpi, ctx):
        figures.append(figure)

    if Path(products.dirac).is_file():
        with ctx.netcdf4.Dataset(products.dirac) as dataset:
            for candidate in ("temperature", "air_temperature", "stream_function", "velocity_potential", "spechum"):
                if candidate not in dataset.variables:
                    continue
                variable = dataset.variables[candidate]
                levels, fields = _spatial_levels(variable, level, ctx=ctx)
                if not fields:
                    continue
                lon, lat = _coordinates_for_size(products, len(fields[0]), ctx=ctx, dataset=dataset)
                if lon is None or lat is None:
                    continue
                figure = outdir / f"04_bmatrix_dirac_{_safe_name(candidate)}_response.png"
                _plot_dirac_spatial(candidate, lon, lat, levels, fields, figure, dpi, ctx)
                figures.append(figure)
                break

    return figures


def _plot_hdiag_profile_summary(
    products: BMatrixProducts,
    output: Path,
    selected: Sequence[str],
    dpi: int,
    ctx: PlotContext,
) -> bool:
    sources = (
        (products.stddev, "Desvio-padrão", "desvio-padrão", False),
        (products.cor_rh, "Escala horizontal", "km", True),
        (products.cor_rv, "Escala vertical", "km", True),
    )
    fig, axes = ctx.plt.subplots(1, 3, figsize=(16.2, 6.1), sharey=True)
    fig.suptitle("Matriz B — amplitude e escalas de correlação diagnosticadas", fontsize=17)
    plotted = False

    variables = tuple(selected or DEFAULT_PLOT_VARIABLES)
    for axis, (path, title, xlabel, convert_km) in zip(axes, sources):
        if not Path(path).is_file():
            axis.set_axis_off()
            continue
        with ctx.netcdf4.Dataset(path) as dataset:
            names = _ordered_plot_variables(dataset.variables, variables)
            for color, name in zip(ACCENTS * 4, names):
                if name not in dataset.variables:
                    continue
                profile = _vertical_profile(dataset.variables[name], ctx=ctx)
                if profile is None or not ctx.np.isfinite(profile).any():
                    continue
                if convert_km:
                    profile = _as_km(profile, getattr(dataset.variables[name], "units", ""), ctx=ctx)
                axis.plot(
                    profile,
                    ctx.np.arange(profile.size),
                    color=color,
                    linewidth=2.4,
                    label=CONTROL_LABELS.get(name, name),
                )
                plotted = True
        axis.set_title(title)
        axis.set_xlabel(xlabel)
        axis.grid(True)
        axis.legend(loc="best", fontsize=9)

    axes[0].set_ylabel("Nível vertical")

    if plotted:
        _finish(fig, output, dpi, ctx)
    else:
        ctx.plt.close(fig)
    return plotted


def _vertical_profile(variable, *, ctx: PlotContext):
    values, dims = _variable_values_and_dims(variable, ctx=ctx)
    if "nVertLevels" not in dims:
        return None
    level_axis = dims.index("nVertLevels")
    values = ctx.np.moveaxis(values, level_axis, 0)
    return ctx.np.nanmean(values.reshape(values.shape[0], -1), axis=1)


def _plot_spatial_fields(
    products: BMatrixProducts,
    root: Path,
    selected: Sequence[str],
    level: int,
    dpi: int,
    ctx: PlotContext,
) -> list[Path]:
    """Generate global spatial maps for each product/variable where coordinates exist."""
    outdir = root / "06_spatial_fields"
    outdir.mkdir(parents=True, exist_ok=True)
    figures: list[Path] = []

    product_map = {
        "stddev": products.stddev,
        "cor_rh": products.cor_rh,
        "cor_rv": products.cor_rv,
        "nicas_norm": products.nicas_norm,
        "dirac_nicas": products.dirac_nicas,
        "dirac": products.dirac,
    }

    for product_name, product_path in product_map.items():
        product_path = Path(product_path)
        if not product_path.is_file():
            continue
        with ctx.netcdf4.Dataset(product_path) as dataset:
            for name in _ordered_plot_variables(dataset.variables, selected):
                if name not in dataset.variables:
                    continue
                variable = dataset.variables[name]
                if not _is_numeric_variable(variable, ctx=ctx):
                    continue
                levels, fields = _spatial_levels(variable, level, ctx=ctx)
                if not fields:
                    continue
                for item, field in zip(levels, fields):
                    lon, lat = _coordinates_for_size(products, len(field), ctx=ctx, dataset=dataset)
                    if lon is None or lat is None:
                        continue
                    level_name = "surface" if item is None else f"lev{item:02d}"
                    figure = outdir / f"{product_name}_{_safe_name(name)}_{level_name}_spatial.png"
                    _plot_global_spatial(product_name, name, lon, lat, field, item, figure, dpi, ctx)
                    figures.append(figure)

    return figures


def _plot_global_spatial(
    product_name: str,
    variable_name: str,
    lon,
    lat,
    field,
    level: int | None,
    output: Path,
    dpi: int,
    ctx: PlotContext,
) -> None:
    values = ctx.np.asarray(field, dtype=float).ravel()
    lon = ctx.np.asarray(lon, dtype=float).ravel()
    lat = ctx.np.asarray(lat, dtype=float).ravel()

    finite = ctx.np.isfinite(values) & ctx.np.isfinite(lon) & ctx.np.isfinite(lat)
    if not finite.any():
        return

    finite_values = values[finite]
    vmin = float(ctx.np.nanpercentile(finite_values, 2.0))
    vmax = float(ctx.np.nanpercentile(finite_values, 98.0))
    if not ctx.np.isfinite(vmin) or not ctx.np.isfinite(vmax) or vmin == vmax:
        vmin = float(ctx.np.nanmin(finite_values))
        vmax = float(ctx.np.nanmax(finite_values))

    if vmin < 0.0 < vmax:
        amplitude = max(abs(vmin), abs(vmax))
        vmin, vmax = -amplitude, amplitude
        cmap = "coolwarm"
    else:
        cmap = "viridis"
    norm = ctx.plt.Normalize(vmin=vmin, vmax=vmax)

    fig, axis = ctx.plt.subplots(figsize=(10.8, 5.4))
    try:
        triangulation = ctx.mtri.Triangulation(lon[finite], lat[finite])
        artist = axis.tricontourf(
            triangulation,
            finite_values,
            levels=21,
            cmap=cmap,
            norm=norm,
            extend="both",
        )
    except (ValueError, RuntimeError):
        artist = axis.scatter(lon[finite], lat[finite], c=finite_values, s=4, cmap=cmap, norm=norm)

    label = CONTROL_LABELS.get(variable_name, variable_name)
    level_label = "2D/superfície" if level is None else f"nível {level}"
    axis.set_title(f"{product_name} — {label} — {level_label}")
    axis.set_xlabel("Longitude (°)")
    axis.set_ylabel("Latitude (°)")
    axis.set_xlim(-180.0, 180.0)
    axis.set_ylim(-90.0, 90.0)
    axis.grid(True)

    colorbar = fig.colorbar(artist, ax=axis, pad=0.018, fraction=0.045)
    colorbar.set_label(label)

    _finish(fig, output, dpi, ctx)


def _spatial_levels(variable, level: int, *, ctx: PlotContext):
    values, dims = _variable_values_and_dims(variable, ctx=ctx)

    if "nCells" in dims and "nVertLevels" in dims:
        nlevels = values.shape[dims.index("nVertLevels")]
        center = max(0, min(int(level), nlevels - 1))
        levels = sorted(set((max(0, center - 5), center, min(nlevels - 1, center + 5))))
        fields = [_field_level_from_values(values, dims, item, ctx=ctx) for item in levels]
        return levels, fields

    if "nCells" in dims:
        if dims.index("nCells") != 0:
            values = ctx.np.moveaxis(values, dims.index("nCells"), 0)
        return [None], [values.reshape(values.shape[0], -1)[:, 0]]

    if values.ndim == 1:
        return [None], [values]

    return [], []


def _coordinates_for_size(
    products: BMatrixProducts,
    size: int,
    *,
    ctx: PlotContext,
    dataset=None,
):
    if dataset is not None:
        lon, lat = _coordinates(dataset, ctx=ctx)
        if lon is not None and lat is not None and lon.size == size and lat.size == size:
            return lon, lat

    for candidate in _coordinate_candidates(products):
        try:
            with ctx.netcdf4.Dataset(candidate) as other:
                lon, lat = _coordinates(other, ctx=ctx)
        except OSError:
            continue
        if lon is not None and lat is not None and lon.size == size and lat.size == size:
            return lon, lat

    return None, None


def _coordinate_candidates(products: BMatrixProducts) -> list[Path]:
    roots: list[Path] = []
    product_paths = [Path(value) for value in asdict(products).values()]

    for product in product_paths:
        roots.append(product.parent)
        roots.append(product.parent.parent)
        if product.parent.name in {"HDIAG", "VBAL", "merge"}:
            roots.append(product.parent.parent)

    dirac_root = Path(products.dirac).parent
    run_id = dirac_root.name
    covariance_root = dirac_root.parent.parent if dirac_root.parent.name == "dirac" else None
    if covariance_root is not None:
        for stage in ("hdiag", "nicas", "dirac", "so", "vbal"):
            roots.append(covariance_root / stage / run_id)
            roots.append(covariance_root / stage / run_id / stage.upper())
            roots.append(covariance_root / stage / run_id / "HDIAG")
            roots.append(covariance_root / stage / run_id / "merge")

    candidates: list[Path] = []
    candidates.extend(product_paths)

    for root in roots:
        candidates.extend(
            [
                root / "bg.nc",
                root / "bg_so.nc",
                root / "mpas.dirac.nc",
                root / "template.nc",
            ]
        )
        candidates.extend(sorted(root.glob("*invariant*.nc")))
        candidates.extend(sorted(root.glob("templateFields*.nc")))
        candidates.extend(sorted(root.glob("*.nc")))

    unique: list[Path] = []
    seen: set[Path] = set()
    for item in candidates:
        if item in seen or not item.is_file():
            continue
        seen.add(item)
        unique.append(item)
    return unique


def _product_map(products: BMatrixProducts) -> dict[str, Path]:
    return {key: Path(value) for key, value in asdict(products).items()}


def _summarize_dataset(product_name: str, path: Path, dataset, *, ctx: PlotContext) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for group_name, group in _groups(dataset):
        for name, variable in group.variables.items():
            if not _is_numeric_variable(variable, ctx=ctx):
                continue
            label = f"{group_name}/{name}" if group_name else name
            values = _clean(variable[:], ctx=ctx).ravel()
            finite = values[ctx.np.isfinite(values)]
            if finite.size == 0:
                vmin = vmax = mean = rms = max_abs = float("nan")
                nonzero_count = 0
            else:
                vmin = float(ctx.np.min(finite))
                vmax = float(ctx.np.max(finite))
                mean = float(ctx.np.mean(finite))
                rms = float(ctx.np.sqrt(ctx.np.mean(finite * finite)))
                max_abs = float(ctx.np.max(ctx.np.abs(finite)))
                nonzero_count = int(ctx.np.count_nonzero(finite))
            rows.append(
                {
                    "product": product_name,
                    "path": str(path),
                    "variable": label,
                    "shape": "x".join(str(size) for size in variable.shape) or "scalar",
                    "min": _format_number(vmin),
                    "max": _format_number(vmax),
                    "mean": _format_number(mean),
                    "rms": _format_number(rms),
                    "max_abs": _format_number(max_abs),
                    "nonzero_count": nonzero_count,
                }
            )
    return rows


def _plot_dataset(
    product_name: str,
    path: Path,
    dataset,
    root: Path,
    selected: Sequence[str],
    level: int,
    dpi: int,
    ctx: PlotContext,
) -> list[Path]:
    figures: list[Path] = []
    x, y = _coordinates(dataset, ctx=ctx)
    outdir = root / _safe_name(product_name)
    outdir.mkdir(parents=True, exist_ok=True)

    for name in _ordered_plot_variables(dataset.variables, selected):
        variable = dataset.variables[name]
        if not _is_numeric_variable(variable, ctx=ctx):
            continue
        values = _select_plot_values(variable, level=level, ctx=ctx)
        if values is None:
            continue
        values = ctx.np.asarray(values, dtype=float).ravel()
        finite = ctx.np.isfinite(values)
        if not finite.any():
            continue
        fig, axis = ctx.plt.subplots(figsize=(8, 4.8))
        if x is not None and y is not None and len(x) == len(values) and len(y) == len(values):
            artist = axis.scatter(x[finite], y[finite], c=values[finite], s=4)
            axis.set_xlabel("longitude")
            axis.set_ylabel("latitude")
            axis.set_title(f"{product_name}: {name}")
            fig.colorbar(artist, ax=axis, label=name)
        else:
            axis.plot(ctx.np.arange(values.size)[finite], values[finite], linewidth=0.8)
            axis.set_xlabel("index")
            axis.set_ylabel(name)
            axis.set_title(f"{product_name}: {name}")
        figure = outdir / f"{_safe_name(name)}.png"
        _finish(fig, figure, dpi, ctx)
        figures.append(figure)
    return figures


def _ordered_plot_variables(available, selected: Sequence[str]) -> list[str]:
    ordered: list[str] = []
    for name in selected:
        if name in available and name not in ordered:
            ordered.append(name)
    if not ordered:
        for name in available:
            if name not in {"latCell", "lonCell", "latitude", "longitude", "lat_c2", "lon_c2"}:
                ordered.append(name)
            if len(ordered) >= 3:
                break
    return ordered


def _select_plot_values(variable, *, level: int, ctx: PlotContext):
    values, dims = _variable_values_and_dims(variable, ctx=ctx)
    if values.ndim == 0:
        return None
    if values.ndim == 1:
        return values
    if "nCells" in dims and "nVertLevels" in dims:
        level_axis = dims.index("nVertLevels")
        lev = max(0, min(int(level), values.shape[level_axis] - 1))
        values = ctx.np.take(values, indices=lev, axis=level_axis)
        dims = tuple(dim for dim in dims if dim != "nVertLevels")
        if dims.index("nCells") != 0:
            values = ctx.np.moveaxis(values, dims.index("nCells"), 0)
        return values.reshape(values.shape[0], -1)[:, 0]
    if values.ndim == 2:
        lev = max(0, min(int(level), values.shape[-1] - 1))
        return values[:, lev]
    reshaped = values.reshape(values.shape[0], -1)
    return reshaped[:, 0]



def _latitude_target_size(variable, *, ctx: PlotContext) -> int | None:
    values, dims = _variable_values_and_dims(variable, ctx=ctx)
    if "nCells" in dims:
        return int(values.shape[dims.index("nCells")])
    if values.ndim == 1:
        return int(values.size)
    if values.ndim >= 2:
        return int(max(values.shape))
    return None


def _lat_level_field(variable, lat, *, ctx: PlotContext):
    values, dims = _variable_values_and_dims(variable, ctx=ctx)
    lat = None if lat is None else ctx.np.asarray(lat, dtype=float).ravel()

    if values.ndim == 1:
        if lat is not None and values.size == lat.size:
            binned, binned_lat = _bin_latitude(values[:, None], lat, ctx=ctx)
            return binned.T, binned_lat
        return values[None, :], ctx.np.arange(values.size, dtype=float)

    if "nCells" in dims and "nVertLevels" in dims:
        cell_axis = dims.index("nCells")
        level_axis = dims.index("nVertLevels")
        values = ctx.np.moveaxis(values, (cell_axis, level_axis), (0, 1))
        matrix = values.reshape(values.shape[0], values.shape[1], -1)[:, :, 0]
        if lat is not None and matrix.shape[0] == lat.size:
            binned, binned_lat = _bin_latitude(matrix, lat, ctx=ctx)
            return binned.T, binned_lat
        return ctx.np.nanmean(matrix, axis=0)[:, None], ctx.np.array([0.0])

    if values.ndim == 2:
        if lat is not None:
            result = _lat_level_from_2d(values, lat, ctx=ctx)
            if result is not None:
                return result
        if values.shape[0] <= values.shape[1]:
            profile = ctx.np.nanmean(values, axis=1)
        else:
            profile = ctx.np.nanmean(values, axis=0)
        return profile[:, None], ctx.np.array([0.0])

    reshaped = values.reshape(values.shape[0], -1)
    profile = ctx.np.nanmean(reshaped, axis=1)
    return profile[:, None], ctx.np.array([0.0])


def _lat_level_from_values(values, lat, *, ctx: PlotContext):
    """Return a 2-D field oriented as level x latitude for VBAL products."""
    values = ctx.np.asarray(values, dtype=float)
    lat = ctx.np.asarray(lat, dtype=float).ravel()
    if values.ndim != 2:
        raise ValueError(f"Expected a 2-D product, got {values.shape}")
    if values.shape[1] == lat.size:
        return values
    if values.shape[0] == lat.size:
        return values.T
    raise ValueError(f"Latitude length {lat.size} is incompatible with {values.shape}")


def _lat_level_from_2d(values, lat, *, ctx: PlotContext):
    values = ctx.np.asarray(values, dtype=float)
    lat = ctx.np.asarray(lat, dtype=float).ravel()
    if values.shape[0] == lat.size:
        binned, binned_lat = _bin_latitude(values, lat, ctx=ctx)
        return binned.T, binned_lat
    if values.shape[1] == lat.size:
        binned, binned_lat = _bin_latitude(values.T, lat, ctx=ctx)
        return binned.T, binned_lat
    return None


def _bin_latitude(values, lat, *, ctx: PlotContext):
    values = ctx.np.asarray(values, dtype=float)
    lat = ctx.np.asarray(lat, dtype=float).ravel()
    order = ctx.np.argsort(lat)
    lat = lat[order]
    values = values[order]
    bins = ctx.np.linspace(-90.0, 90.0, 91)
    centers = 0.5 * (bins[:-1] + bins[1:])
    result = ctx.np.full((centers.size, values.shape[1]), ctx.np.nan)
    for index in range(centers.size):
        mask = (lat >= bins[index]) & (lat < bins[index + 1])
        if mask.any():
            result[index] = ctx.np.nanmean(values[mask], axis=0)
    good = ctx.np.isfinite(result).any(axis=1)
    if good.any():
        return result[good], centers[good]
    return values, lat


def _latitude_for_dataset(
    dataset,
    products: BMatrixProducts,
    *,
    target_size: int | None = None,
    ctx: PlotContext,
):
    _, lat = _coordinates(dataset, ctx=ctx)
    if lat is not None and (target_size is None or lat.size == target_size):
        return lat

    candidates = (
        products.dirac,
        products.dirac_nicas,
        products.nicas_norm,
        products.nicas,
        products.sampling,
        products.vbal,
        products.stddev,
        products.cor_rh,
        products.cor_rv,
    )
    seen: set[Path] = set()
    for candidate in candidates:
        candidate = Path(candidate)
        if candidate in seen or not candidate.is_file():
            continue
        seen.add(candidate)
        try:
            with ctx.netcdf4.Dataset(candidate) as other:
                _, candidate_lat = _coordinates(other, ctx=ctx)
        except OSError:
            continue
        if candidate_lat is not None and (target_size is None or candidate_lat.size == target_size):
            return candidate_lat

    vbal_lat = _latitudes_from_vbal(products.vbal, ctx)
    if vbal_lat is not None and (target_size is None or vbal_lat.size == target_size):
        return vbal_lat

    return None


def _latitudes_from_vbal(path: Path, ctx: PlotContext):
    candidates = [path, path.parent / "mpas_sampling.nc", path.parent / "VBAL" / "mpas_sampling.nc"]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        with ctx.netcdf4.Dataset(candidate) as dataset:
            for name in ("lat_c2", "latCell", "latitude", "lat"):
                if name in dataset.variables:
                    return _degrees(dataset.variables[name][:], ctx=ctx)
    return None


def _coordinates(dataset, *, ctx: PlotContext):
    lon = _maybe_coord(dataset, ("lonCell", "longitude", "lon", "lon_c2"), ctx=ctx)
    lat = _maybe_coord(dataset, ("latCell", "latitude", "lat", "lat_c2"), ctx=ctx)
    if lon is None or lat is None:
        return None, None
    lon = _degrees(lon, ctx=ctx).ravel()
    lat = _degrees(lat, ctx=ctx).ravel()
    lon = ((lon + 180.0) % 360.0) - 180.0
    return lon, lat


def _maybe_coord(dataset, names: Iterable[str], *, ctx: PlotContext):
    for name in names:
        if name in dataset.variables:
            return ctx.np.ma.asarray(dataset.variables[name][:], dtype=float).filled(ctx.np.nan)
    return None

def _dirac_levels(variable, level: int, *, ctx: PlotContext):
    values, dims = _variable_values_and_dims(variable, ctx=ctx)
    if "nCells" not in dims or "nVertLevels" not in dims:
        return [], []
    nlevels = values.shape[dims.index("nVertLevels")]
    center = max(0, min(int(level), nlevels - 1))
    levels = sorted(set((max(0, center - 5), center, min(nlevels - 1, center + 5))))
    fields = [_field_level_from_values(values, dims, item, ctx=ctx) for item in levels]
    return levels, fields


def _field_level_from_values(values, dims, level: int, *, ctx: PlotContext):
    values = ctx.np.take(values, level, axis=dims.index("nVertLevels"))
    dims = tuple(dim for dim in dims if dim != "nVertLevels")
    if dims.index("nCells") != 0:
        values = ctx.np.moveaxis(values, dims.index("nCells"), 0)
    return values.reshape(values.shape[0], -1)[:, 0]


def _variable_values_and_dims(variable, *, ctx: PlotContext):
    values = _clean(variable[:], ctx=ctx)
    dims = tuple(getattr(variable, "dimensions", ()))
    while values.ndim > 0 and values.shape[0] == 1 and (not dims or dims[0].lower() in {"time", "date"}):
        values = values[0]
        dims = dims[1:]
    return values, dims


def _groups(group, prefix: str = ""):
    yield prefix, group
    for name, child in group.groups.items():
        child_prefix = f"{prefix}/{name}" if prefix else name
        yield from _groups(child, child_prefix)


def _group_variable(dataset, group_name: str, prefix: str):
    for name, group in _groups(dataset):
        if name == group_name:
            for variable_name, variable in group.variables.items():
                if variable_name.startswith(prefix):
                    return variable_name, variable
    raise KeyError(f"No '{prefix}*' variable in group '{group_name}'")


def _as_km(values, units: str, *, ctx: PlotContext):
    values = ctx.np.asarray(values, dtype=float)
    finite = ctx.np.abs(values[ctx.np.isfinite(values)])
    if "km" in (units or "").lower():
        return values
    if "m" in (units or "").lower() or (finite.size and ctx.np.nanmedian(finite) > 1.0e5):
        return values / 1000.0
    return values


def _clean(values, *, ctx: PlotContext):
    array = ctx.np.ma.asarray(values, dtype=float).filled(ctx.np.nan)
    array = ctx.np.asarray(array, dtype=float)
    array[ctx.np.abs(array) > 1.0e30] = ctx.np.nan
    return array


def _degrees(values, *, ctx: PlotContext):
    array = _clean(values, ctx=ctx).ravel()
    finite = ctx.np.abs(array[ctx.np.isfinite(array)])
    if finite.size and ctx.np.nanmax(finite) <= 2.0 * math.pi + 0.1:
        array = ctx.np.degrees(array)
    return array


def _is_numeric_variable(variable, *, ctx: PlotContext) -> bool:
    return ctx.np.issubdtype(ctx.np.dtype(variable.dtype), ctx.np.number)


def _write_summary_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _write_readme(
    path: Path,
    products: BMatrixProducts,
    summary_csv: Path,
    figures: Sequence[Path],
    *,
    level: int,
    dpi: int,
) -> None:
    product_lines = "\n".join(f"- `{name}`: `{value}`" for name, value in asdict(products).items())
    figure_lines = "\n".join(f"- `{figure.relative_to(path.parent)}`" for figure in figures[:300])
    if len(figures) > 300:
        figure_lines += f"\n- ... mais {len(figures) - 300} figuras"
    text = f"""# B-matrix plots

Resumo e figuras gerados a partir dos produtos finais da matriz B.

## Organização

- `00_presentation/`: conjunto compacto no estilo das figuras de apresentação.
- `01_stddev/`: seções latitude × nível do desvio-padrão diagnosticado.
- `02_corr_horizontal/`: seções latitude × nível da escala horizontal.
- `03_corr_vertical/`: seções latitude × nível da escala vertical.
- `04_vbal/`: variância explicada pelo balanço e regressão vertical.
- `05_dirac/`: resposta espacial local da B a impulsos DIRAC por variável.
- `06_spatial_fields/`: mapas espaciais globais por produto/variável.
- `99_quicklook/`: figuras simples de inspeção rápida por produto.

## Configuração

- nível vertical usado para DIRAC/quicklook: `{level}`
- DPI: `{dpi}`
- resumo CSV: `{summary_csv.name}`

## Produtos lidos

{product_lines}

## Figuras

{figure_lines or "- nenhuma figura gerada"}
"""
    path.write_text(text)


def _finish(fig, output: Path, dpi: int, ctx: PlotContext) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.94) if fig._suptitle else None)
    fig.savefig(output, dpi=dpi, bbox_inches="tight")
    ctx.plt.close(fig)


def _format_number(value: float) -> str:
    if math.isnan(value):
        return "nan"
    return f"{value:.12g}"


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in value)

