import numpy as np
from scipy import stats
from pathlib import Path

RESULTS_DIR = Path(__file__).parent.parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def build_empirical_distribution(lengths: np.ndarray, bin_size: int) -> dict:
    max_val = int(np.ceil(lengths.max() / bin_size) * bin_size)
    bins = np.arange(0, max_val + bin_size, bin_size)

    counts, _ = np.histogram(lengths, bins=bins)
    probs = counts / counts.sum()

    nonzero_mask = probs > 0
    n_nonzero = nonzero_mask.sum()

    print(f"  Bin size: {bin_size}")
    print(f"  Total bins: {len(bins) - 1}")
    print(f"  Non-empty bins: {n_nonzero}")

    return {
        "bins": bins,
        "probs": probs,
        "counts": counts,
        "bin_size": bin_size,
        "n_nonzero": n_nonzero,
    }


def sample_from_distribution(n_samples: int, bins: np.ndarray, probs: np.ndarray, bin_size: int) -> np.ndarray:
    sampled_bins = np.random.choice(len(bins) - 1, size=n_samples, p=probs)
    sampled_values = bins[sampled_bins] + np.random.uniform(0, bin_size, n_samples)
    sampled_values = sampled_values.astype(int)
    sampled_values = np.clip(sampled_values, 1, int(bins[-1]))
    return sampled_values


def validate_sampling(original: np.ndarray, sampled: np.ndarray) -> dict:
    ks_stat, ks_pvalue = stats.ks_2samp(original, sampled)

    result = {
        "ks_stat": ks_stat,
        "ks_pvalue": ks_pvalue,
        "original_mean": float(original.mean()),
        "sampled_mean": float(sampled.mean()),
        "original_median": float(np.median(original)),
        "sampled_median": float(np.median(sampled)),
        "original_std": float(original.std()),
        "sampled_std": float(sampled.std()),
    }

    print(f"\n  === Validation ===")
    print(f"  Original: mean={result['original_mean']:.1f}, "
          f"median={result['original_median']:.0f}, std={result['original_std']:.1f}")
    print(f"  Sampled:  mean={result['sampled_mean']:.1f}, "
          f"median={result['sampled_median']:.0f}, std={result['sampled_std']:.1f}")
    print(f"  KS test:  stat={ks_stat:.6f}, p={ks_pvalue:.2e}")

    if ks_pvalue > 0.05:
        print(f"  Result:   PASS (p > 0.05, cannot reject same distribution)")
    else:
        print(f"  Result:   FAIL (p < 0.05, distributions differ significantly)")

    return result


def save_distribution(dist: dict, name: str) -> str:
    filepath = RESULTS_DIR / f"{name}_bin_probs.csv"
    np.savetxt(
        filepath,
        np.column_stack([dist["bins"][:-1], dist["probs"]]),
        delimiter=",",
        header="bin_start,probability",
        comments="",
    )
    print(f"  Saved: {filepath}")
    return str(filepath)


def save_validation(validation: dict, name: str) -> str:
    filepath = RESULTS_DIR / f"{name}_validation.json"
    import json
    with open(filepath, "w") as f:
        json.dump(validation, f, indent=2)
    print(f"  Saved: {filepath}")
    return str(filepath)
