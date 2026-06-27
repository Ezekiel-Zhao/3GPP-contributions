import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

PLOTS_DIR = Path(__file__).parent.parent / "plots"
PLOTS_DIR.mkdir(exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 150,
    "font.size": 11,
    "axes.grid": True,
    "grid.alpha": 0.3,
})


def plot_sampling_comparison(original: np.ndarray, sampled: np.ndarray,
                             dist: dict, label: str, name: str):
    bins = dist["bins"]
    bin_size = dist["bin_size"]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    nonzero = dist["probs"] > 0
    axes[0, 0].bar(
        bins[:-1][nonzero], dist["probs"][nonzero] * 100,
        width=bin_size, alpha=0.7, color="steelblue",
        edgecolor="black", linewidth=0.3, align="edge",
    )
    axes[0, 0].set_xlabel(f"{label} (tokens)")
    axes[0, 0].set_ylabel("Probability (%)")
    axes[0, 0].set_title(f"Binned Distribution (bin size = {bin_size})")

    axes[0, 1].hist(original, bins=bins, density=True, alpha=0.5,
                    color="steelblue", label="Original", edgecolor="black", linewidth=0.3)
    axes[0, 1].hist(sampled, bins=bins, density=True, alpha=0.5,
                    color="coral", label="Sampled", edgecolor="black", linewidth=0.3)
    axes[0, 1].set_xlabel(f"{label} (tokens)")
    axes[0, 1].set_ylabel("Density")
    axes[0, 1].set_title("Original vs Sampled (overlaid)")
    axes[0, 1].legend()

    axes[1, 0].hist(original, bins=bins, density=True, alpha=0.5,
                    color="steelblue", label="Original", edgecolor="black", linewidth=0.3)
    axes[1, 0].hist(sampled, bins=bins, density=True, alpha=0.5,
                    color="coral", label="Sampled", edgecolor="black", linewidth=0.3)
    axes[1, 0].set_xlabel(f"{label} (tokens)")
    axes[1, 0].set_ylabel("Density")
    axes[1, 0].set_title("Full range")
    axes[1, 0].legend()

    sorted_orig = np.sort(original)
    sorted_samp = np.sort(sampled)
    n_orig = len(sorted_orig)
    n_samp = len(sorted_samp)
    axes[1, 1].plot(
        sorted_orig, 1 - np.arange(1, n_orig + 1) / n_orig,
        color="steelblue", linewidth=1.5, label="Original",
    )
    axes[1, 1].plot(
        sorted_samp, 1 - np.arange(1, n_samp + 1) / n_samp,
        color="coral", linewidth=1.5, linestyle="--", label="Sampled",
    )
    axes[1, 1].set_xlabel(f"{label} (tokens)")
    axes[1, 1].set_ylabel("CCDF")
    axes[1, 1].set_title("CCDF Comparison")
    axes[1, 1].set_xscale("log")
    axes[1, 1].set_yscale("log")
    axes[1, 1].legend()

    plt.tight_layout()
    filepath = PLOTS_DIR / f"{name}_sampling.png"
    plt.savefig(filepath, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {filepath}")
