import sys
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src import (
    load_burstgpt, filter_conversation_log, extract_lengths,
    build_empirical_distribution, sample_from_distribution,
    validate_sampling, save_distribution, save_validation,
    plot_sampling_comparison,
)

OUTPUT_BIN_SIZE = 10
INPUT_BIN_SIZE = 3
N_SAMPLES = 100000
RANDOM_SEED = 42


def main():
    print("=" * 70)
    print("LLM Input/Output Length Empirical Distribution Sampling")
    print("Dataset: BurstGPT (Azure OpenAI GPT, Conversation log)")
    print("=" * 70)

    # Step 1: Load and clean data
    print("\n" + "-" * 70)
    print("Step 1: Load and Clean Data")
    print("-" * 70)

    df = load_burstgpt()
    df = filter_conversation_log(df)

    # Step 2: Extract lengths
    print("\n" + "-" * 70)
    print("Step 2: Extract Input/Output Lengths")
    print("-" * 70)

    print("\n--- Output Length (Response tokens) ---")
    output_lengths = extract_lengths(df, "Response tokens")

    print("\n--- Input Length (Request tokens) ---")
    input_lengths = extract_lengths(df, "Request tokens")

    # Step 3: Build empirical distributions
    print("\n" + "-" * 70)
    print("Step 3: Build Empirical Distributions")
    print("-" * 70)

    print("\n--- Output Length Distribution ---")
    output_dist = build_empirical_distribution(output_lengths, OUTPUT_BIN_SIZE)

    print("\n--- Input Length Distribution ---")
    input_dist = build_empirical_distribution(input_lengths, INPUT_BIN_SIZE)

    # Step 4: Sample and validate
    np.random.seed(RANDOM_SEED)

    print("\n" + "-" * 70)
    print("Step 4: Sample and Validate")
    print("-" * 70)

    print("\n--- Output Length Sampling ---")
    output_sampled = sample_from_distribution(
        N_SAMPLES, output_dist["bins"], output_dist["probs"], OUTPUT_BIN_SIZE
    )
    output_validation = validate_sampling(output_lengths, output_sampled)

    print("\n--- Input Length Sampling ---")
    input_sampled = sample_from_distribution(
        N_SAMPLES, input_dist["bins"], input_dist["probs"], INPUT_BIN_SIZE
    )
    input_validation = validate_sampling(input_lengths, input_sampled)

    # Step 5: Save results
    print("\n" + "-" * 70)
    print("Step 5: Save Results")
    print("-" * 70)

    save_distribution(output_dist, "output")
    save_distribution(input_dist, "input")
    save_validation(output_validation, "output")
    save_validation(input_validation, "input")

    # Step 6: Generate plots
    print("\n" + "-" * 70)
    print("Step 6: Generate Plots")
    print("-" * 70)

    plot_sampling_comparison(
        output_lengths, output_sampled, output_dist,
        label="Output Length", name="output",
    )
    plot_sampling_comparison(
        input_lengths, input_sampled, input_dist,
        label="Input Length", name="input",
    )

    # Summary
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"\nOutput Length (bin={OUTPUT_BIN_SIZE}):")
    print(f"  KS stat:  {output_validation['ks_stat']:.6f}")
    print(f"  KS p-val: {output_validation['ks_pvalue']:.2e}")
    print(f"  Bins:     {output_dist['n_nonzero']} non-empty")

    print(f"\nInput Length (bin={INPUT_BIN_SIZE}):")
    print(f"  KS stat:  {input_validation['ks_stat']:.6f}")
    print(f"  KS p-val: {input_validation['ks_pvalue']:.2e}")
    print(f"  Bins:     {input_dist['n_nonzero']} non-empty")

    print(f"\nResults saved to: results/")
    print(f"Plots saved to:   plots/")
    print("=" * 70)


if __name__ == "__main__":
    main()
