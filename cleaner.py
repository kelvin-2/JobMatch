import pandas as pd
import re


def clean_jobs(jobs: list[dict]) -> list[dict]:
    if not jobs:
        return []

    df = pd.DataFrame(jobs)
    df = _remove_duplicates(df)
    df = _clean_text(df)
    df = _clean_nulls(df)

    print(f"Cleaning complete. {len(df)} jobs remaining.")
    return df.to_dict(orient="records")


def _remove_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    before = len(df)
    df = df.drop_duplicates(subset=["url"])
    df = df.drop_duplicates(subset=["title", "company"])
    print(f"Deduplication: {before} → {len(df)}")
    return df.reset_index(drop=True)


def _clean_text(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["title", "company", "location", "description", "requirements"]:
        if col in df.columns:
            df[col] = (
                df[col]
                .fillna("")
                .str.strip()
                .str.replace(r"\s+", " ", regex=True)
            )
    df["company"] = df["company"].str.title()
    return df


def _clean_nulls(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(subset=["title", "url"])
    df = df[df["title"].str.len() > 3]
    return df