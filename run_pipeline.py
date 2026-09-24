"""
Run the SQL pipeline on DuckDB (local, no cloud account needed).

  1. load the raw CSVs into raw_* tables (encounters are loaded as text so
     that '?' placeholders and codes like 'V57' survive for the quality checks)
  2. run sql/00 ... sql/04 in order
  3. export result tables to outputs/*.csv

Usage:  python run_pipeline.py
"""
from pathlib import Path
import duckdb

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)

con = duckdb.connect(str(ROOT / "hospital.duckdb"))

con.execute(f"""CREATE OR REPLACE TABLE raw_encounters AS
                SELECT * FROM read_csv('{(RAW / 'diabetic_data.csv').as_posix()}', header=true, all_varchar=true)""")
for name in ["admission_type", "admission_source", "discharge_disposition"]:
    con.execute(f"""CREATE OR REPLACE TABLE raw_{name} AS
                    SELECT * FROM read_csv_auto('{(RAW / (name + '.csv')).as_posix()}', header=true)""")
for t in ["raw_encounters", "raw_admission_type", "raw_admission_source", "raw_discharge_disposition"]:
    print(f"loaded {t:<28} {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:>8,} rows")

for sql_file in sorted((ROOT / "sql").glob("*.sql")):
    con.execute(sql_file.read_text())
    print(f"ran    {sql_file.name}")

EXPORTS = ["dq_results", "cohort_funnel", "kpi_overall", "readmission_profile", "risk_scores",
           "risk_band_validation", "hba1c_summary", "hba1c_by_diagnosis", "cohort"]
for t in EXPORTS:
    con.execute(f"COPY {t} TO '{(OUT / (t + '.csv')).as_posix()}' (HEADER, DELIMITER ',')")

for title, t in [("Data quality", "SELECT check_id, check_name, affected_rows FROM dq_results"),
                 ("Cohort", "SELECT * FROM cohort_funnel"),
                 ("Overall", "SELECT * FROM kpi_overall"),
                 ("Risk bands", "SELECT * FROM risk_band_validation"),
                 ("HbA1c", "SELECT * FROM hba1c_summary")]:
    print(f"\n{title}:")
    print(con.sql(t).df().to_string(index=False))
con.close()
