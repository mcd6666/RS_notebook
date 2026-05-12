import argparse
from pathlib import Path

import numpy as np
import pandas as pd


INPUT_CSV = r"E:\tide_model\gf2_scene_tide.csv"
OUTPUT_CSV = r"E:\tide_model\tide_class_consistency_mismatches.csv"
REPORT_TXT = r"E:\tide_model\tide_class_consistency_report.txt"

CLASS_ORDER = ["低潮", "中低潮", "中高潮", "高潮"]


def weighted_kappa(table, weights="linear"):
    matrix = table.to_numpy(dtype=float)
    total = matrix.sum()
    if total == 0:
        return np.nan

    observed = matrix / total
    row = observed.sum(axis=1)
    col = observed.sum(axis=0)
    expected = np.outer(row, col)

    n = matrix.shape[0]
    distance = np.abs(np.subtract.outer(np.arange(n), np.arange(n)))
    if weights == "linear":
        w = distance / (n - 1)
    elif weights == "quadratic":
        w = (distance / (n - 1)) ** 2
    else:
        raise ValueError(f"Unknown weights: {weights}")

    observed_disagreement = (w * observed).sum()
    expected_disagreement = (w * expected).sum()
    if expected_disagreement == 0:
        return np.nan
    return 1.0 - observed_disagreement / expected_disagreement


def main():
    parser = argparse.ArgumentParser(description="Analyze consistency between two tide classification columns.")
    parser.add_argument("--input", default=INPUT_CSV)
    parser.add_argument("--mismatches", default=OUTPUT_CSV)
    parser.add_argument("--report", default=REPORT_TXT)
    args = parser.parse_args()

    df = pd.read_csv(args.input, encoding="utf-8-sig")
    left = "tide_level_class"
    right = "tide_level_class_threshold"
    missing = [c for c in (left, right) if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing columns: {missing}")

    valid = df[left].isin(CLASS_ORDER) & df[right].isin(CLASS_ORDER)
    data = df.loc[valid].copy()
    table = pd.crosstab(data[left], data[right]).reindex(index=CLASS_ORDER, columns=CLASS_ORDER, fill_value=0)

    same = data[left] == data[right]
    agreement = same.mean()
    exact_count = int(same.sum())
    total = int(len(data))

    class_to_rank = {name: idx for idx, name in enumerate(CLASS_ORDER)}
    rank_diff = data[left].map(class_to_rank) - data[right].map(class_to_rank)
    data["class_rank_difference"] = rank_diff
    data["class_difference_abs"] = rank_diff.abs()

    mismatch = data.loc[~same].copy()
    mismatch.to_csv(args.mismatches, index=False, encoding="utf-8-sig")

    lines = []
    lines.append(f"rows = {total}")
    lines.append(f"exact_agreement = {exact_count}")
    lines.append(f"exact_agreement_rate = {agreement:.4f}")
    lines.append(f"linear_weighted_kappa = {weighted_kappa(table, 'linear'):.4f}")
    lines.append(f"quadratic_weighted_kappa = {weighted_kappa(table, 'quadratic'):.4f}")
    lines.append("")
    lines.append("confusion_matrix_rows=tide_level_class columns=tide_level_class_threshold")
    lines.append(table.to_string())
    lines.append("")
    lines.append("absolute_class_difference_counts")
    lines.append(data["class_difference_abs"].value_counts().sort_index().to_string())
    lines.append("")
    lines.append("mismatch_pairs")
    pair_counts = mismatch.groupby([left, right]).size().sort_values(ascending=False)
    lines.append(pair_counts.to_string() if len(pair_counts) else "none")

    report = "\n".join(lines)
    Path(args.report).write_text(report, encoding="utf-8")
    print(report)
    print(f"\nmismatches = {Path(args.mismatches).resolve()}")
    print(f"report = {Path(args.report).resolve()}")


if __name__ == "__main__":
    main()
