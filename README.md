# ECON6067 Final Individual Project — Fama-French Three-Factor Replication

## Research objective

Replicate the Fama–French three-factor model using monthly CRSP stock data and
Compustat accounting data: construct the size (SMB) and value (HML) factors via
the standard 2×3 portfolio sorts, and evaluate the model's ability to explain
the cross-section of average returns.

## Data access note

This repository does **not** include the restricted course datasets. The raw
CSV files (CRSP monthly stocks, Fama–French factors, Compustat fundamentals, and
the CRSP–Compustat link table) are downloaded from the course's numbered data
packages and are excluded from version control via `.gitignore` (`data/raw/`,
`data/processed/`, and `*.zip`).

To reproduce the analysis, download the required packages
(`02_Monthly_Stocks_and_Factors.zip` and `04_Supplementary_Data.zip`) and
extract them into `data/raw/`, preserving the original numbered folder names and
CSV filenames. See `data/raw/*/README.md` and `data/raw/*/DATA_DICTIONARY.md`
(after extraction) for the data dictionary and column definitions.
