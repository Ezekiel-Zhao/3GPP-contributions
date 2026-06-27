import pandas as pd
import numpy as np
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def load_burstgpt(filepath: str = None) -> pd.DataFrame:
    if filepath is None:
        candidates = list(DATA_DIR.glob("BurstGPT*.csv"))
        if not candidates:
            raise FileNotFoundError(
                f"No BurstGPT CSV files found in {DATA_DIR}. "
                "Download from https://github.com/HPMLL/BurstGPT "
                "and place CSV files in the data/ directory."
            )
        filepath = candidates[0]

    filepath = Path(filepath)
    df = pd.read_csv(filepath)
    print(f"Loaded {len(df):,} rows from {filepath.name}")
    print(f"Columns: {list(df.columns)}")
    return df


def filter_conversation_log(df: pd.DataFrame) -> pd.DataFrame:
    if "Log Type" not in df.columns:
        raise ValueError("Column 'Log Type' not found in data")

    before = len(df)
    df = df[df["Log Type"] == "Conversation log"]
    print(f"Filtered to Conversation log: {before:,} -> {len(df):,} rows")
    return df


def extract_lengths(df: pd.DataFrame, column: str) -> np.ndarray:
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found in data")

    lengths = df[column].dropna().values.astype(float)
    lengths = lengths[lengths > 0]

    print(f"\nExtracted {len(lengths):,} valid values from '{column}'")
    print(f"  Range:  [{lengths.min():.0f}, {lengths.max():.0f}]")
    print(f"  Mean:   {lengths.mean():.1f}")
    print(f"  Median: {np.median(lengths):.1f}")
    print(f"  Std:    {lengths.std():.1f}")
    print(f"  Skew:   {pd.Series(lengths).skew():.2f}")
    print(f"  Kurt:   {pd.Series(lengths).kurtosis():.2f}")

    return lengths
