"""
Build dashboard/index.html from the pipeline outputs.
Usage:  python dashboard/build_dashboard.py
"""
import json
from pathlib import Path
import pandas as pd

AUTHOR = "Sonam Rohilla"
GITHUB = "https://github.com/sonamrohilla/hospital-readmission"
LINKEDIN = "https://www.linkedin.com/in/sonam-rohilla-09418723"

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
r = lambda f: pd.read_csv(OUT / f)

data = {
    "kpi": r("kpi_overall.csv").iloc[0].to_dict(),
    "profile": r("readmission_profile.csv").to_dict("records"),
    "models": r("model_comparison.csv").to_dict("records"),
    "deciles": r("risk_deciles.csv").to_dict("records"),
    "hba": r("hba1c_by_diagnosis_adjusted.csv").to_dict("records"),
    "hbaAll": r("hba1c_tested_adjusted.csv").iloc[0].to_dict(),
    "funnel": r("cohort_funnel.csv").to_dict("records"),
    "dq": r("dq_results.csv").to_dict("records"),
}
html = (ROOT / "dashboard" / "template.html").read_text()
html = (html.replace("__DATA__", json.dumps(data, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
            .replace("__AUTHOR__", AUTHOR).replace("__GITHUB__", GITHUB).replace("__LINKEDIN__", LINKEDIN))
(ROOT / "dashboard" / "index.html").write_text(html)
print(f"wrote dashboard/index.html ({len(html) / 1024:.0f} KB)")
