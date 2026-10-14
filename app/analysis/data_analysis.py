"""Bounded, deterministic profiling for user-selected tabular uploads."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_ROWS_FOR_PROFILE = 100_000
MAX_SAMPLE_ROWS = 12
MAX_COLUMNS_IN_CONTEXT = 40


def analyze_dataset(file_path: str, query: str) -> dict:
    """Summarize a CSV/XLSX with bounded context for the language model.

    The returned statistics are computed by pandas, not inferred by the model.
    Raw rows are sampled and capped to avoid sending an entire workbook to Ollama.
    """
    path = Path(file_path)
    try:
        if not path.is_file():
            return {"success": False, "error": "The selected dataset file is missing."}
        if path.stat().st_size > MAX_FILE_BYTES:
            return {"success": False, "error": "The dataset exceeds the 25 MB analysis limit."}
        ext = path.suffix.lower()
        if ext == ".csv":
            frame = pd.read_csv(path, nrows=MAX_ROWS_FOR_PROFILE + 1, on_bad_lines="error")
        elif ext in {".xlsx", ".xls"}:
            frame = pd.read_excel(path, nrows=MAX_ROWS_FOR_PROFILE + 1)
        else:
            return {"success": False, "error": f"Unsupported dataset type: {ext or 'unknown'}"}
        if frame.empty:
            return {"success": False, "error": "The selected dataset is empty."}
        truncated = len(frame) > MAX_ROWS_FOR_PROFILE
        if truncated:
            frame = frame.iloc[:MAX_ROWS_FOR_PROFILE]

        frame.columns = [str(column) for column in frame.columns]
        selected_columns = list(frame.columns[:MAX_COLUMNS_IN_CONTEXT])
        view = frame[selected_columns]
        numeric = view.select_dtypes(include="number")
        summary: list[str] = [
            f"Rows analyzed: {len(view)}{ ' (first 100,000 rows only)' if truncated else ''}.",
            f"Columns ({len(frame.columns)} total): {', '.join(frame.columns[:MAX_COLUMNS_IN_CONTEXT])}" + (" … [additional columns omitted]" if len(frame.columns) > MAX_COLUMNS_IN_CONTEXT else ""),
            "Missing values by column: " + "; ".join(f"{col}={int(view[col].isna().sum())}" for col in selected_columns[:20]),
        ]
        if len(numeric.columns):
            stats = numeric.describe(percentiles=[.25, .5, .75]).transpose()
            summary.append("Numeric statistics (count, mean, std, min, 25%, median, 75%, max):")
            for column, row in stats.iterrows():
                summary.append(
                    f"- {column}: count={row['count']:.0f}, mean={row['mean']:.6g}, std={row['std']:.6g}, "
                    f"min={row['min']:.6g}, p25={row['25%']:.6g}, median={row['50%']:.6g}, "
                    f"p75={row['75%']:.6g}, max={row['max']:.6g}"
                )
                summary.append(f"  Min={row['min']:g}, Max={row['max']:g}, Mean={row['mean']:.2f}")
        categorical = [column for column in selected_columns if column not in numeric.columns]
        if categorical:
            summary.append("Categorical/date value examples:")
            for column in categorical[:12]:
                values = view[column].dropna().astype(str).value_counts().head(5)
                summary.append(f"- {column}: " + (", ".join(f"{value} ({count})" for value, count in values.items()) or "no values"))
        grouped_columns = [column for column in categorical if view[column].nunique(dropna=True) <= 20]
        if len(numeric.columns) and grouped_columns:
            summary.append("Grouped numeric averages by low-cardinality column (computed across analyzed rows):")
            numeric_columns = list(numeric.columns[:8])
            for group_column in grouped_columns[:6]:
                grouped = view.groupby(group_column, dropna=False)[numeric_columns].mean().round(4)
                summary.append(f"- {group_column}: {grouped.head(20).to_dict(orient='index')}")
        if len(numeric.columns) > 1:
            correlations = numeric.iloc[:, :12].corr().round(3)
            pairs = []
            for left_index, left in enumerate(correlations.columns):
                for right in correlations.columns[left_index + 1:]:
                    value = correlations.loc[left, right]
                    if pd.notna(value):
                        pairs.append((abs(float(value)), left, right, float(value)))
            if pairs:
                strongest = sorted(pairs, reverse=True)[:10]
                summary.append("Strongest pairwise Pearson correlations (association only, not causation): " + "; ".join(f"{left} vs {right}={value:.3f}" for _, left, right, value in strongest))
        sample_frame = view.head(MAX_SAMPLE_ROWS).astype(object)
        sample = sample_frame.where(pd.notna(sample_frame), None).to_dict(orient="records")
        summary.append(f"First {len(sample)} rows (sample only; not the full dataset): {sample}")
        return {
            "success": True,
            "analysis_text": "\n".join(summary),
            "columns": list(frame.columns),
            "rows_analyzed": len(view),
            "truncated": truncated,
            "query": query,
        }
    except (OSError, ValueError, ImportError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        return {"success": False, "error": f"Could not read this dataset: {exc}"}
