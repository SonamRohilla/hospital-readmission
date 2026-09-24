"""
Readmission model, comparison with the LACE-style score, and the adjusted
HbA1c analysis. Reads outputs/cohort.csv and outputs/risk_scores.csv
(created by run_pipeline.py). Writes result tables and charts to outputs/.

Usage:  python analysis/model_and_stats.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
CH = OUT / "charts"
CH.mkdir(parents=True, exist_ok=True)
SEED = 42

TEAL, GREY, RED, AMBER, INK = "#0e7a6b", "#9aa5a1", "#c2410c", "#b7791f", "#14201d"
plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 150})

df = pd.read_csv(OUT / "cohort.csv")
lace = pd.read_csv(OUT / "risk_scores.csv")[["encounter_id", "lace_score", "risk_band"]]
df = df.merge(lace, on="encounter_id")
# fixed row order: DuckDB may export rows in any order, which would change the train/test split
df = df.sort_values("encounter_id").reset_index(drop=True)
df["y"] = df["readmitted_30d"].astype(int)
df["race"] = df["race"].fillna("Unknown")
top_spec = df["medical_specialty"].value_counts().index[:10]
df["specialty_grp"] = np.where(df["medical_specialty"].isin(top_spec), df["medical_specialty"], "Other")
df["hba1c_group"] = np.select(
    [~df.hba1c_tested, df.hba1c_result == "Norm", ~df.medication_changed],
    ["Not tested", "Tested - normal", "Tested - high, no change"], "Tested - high, med changed")

NUM = ["age_mid", "los_days", "num_lab_procedures", "num_procedures", "num_medications",
       "number_diagnoses", "prior_outpatient", "prior_emergency", "prior_inpatient"]
CAT = ["gender", "race", "admission_type_group", "admission_source_group", "discharge_group",
       "primary_diagnosis_group", "specialty_grp", "hba1c_group", "insulin",
       "medication_changed", "on_diabetes_medication"]

train, test = train_test_split(df, test_size=0.25, random_state=SEED, stratify=df["y"])

# ------------------------------------------------------------------ model
model = Pipeline([
    ("prep", ColumnTransformer([("num", StandardScaler(), NUM),
                                ("cat", OneHotEncoder(handle_unknown="ignore", drop="first"), CAT)])),
    ("clf", LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5)),
])
model.fit(train[NUM + CAT], train["y"])
test = test.copy()
test["model_risk"] = model.predict_proba(test[NUM + CAT])[:, 1]

auc_model = roc_auc_score(test["y"], test["model_risk"])
auc_lace = roc_auc_score(test["y"], test["lace_score"])
auc_prior = roc_auc_score(test["y"], test["prior_inpatient"])


def capture_at(frac, score):
    """Share of all readmissions found if the care team follows up the top `frac` of patients."""
    n = int(len(test) * frac)
    top = test.sort_values([score, "encounter_id"], ascending=[False, True]).head(n)
    return top["y"].sum() / test["y"].sum(), top["y"].mean()


rows = []
for name, col, auc in [("Logistic regression (all features)", "model_risk", auc_model),
                       ("LACE-style score (SQL)", "lace_score", auc_lace),
                       ("Prior inpatient stays only", "prior_inpatient", auc_prior)]:
    cap, prec = capture_at(0.20, col)
    rows.append({"method": name, "auc": round(auc, 3), "readmissions_caught_top20_pct": round(100 * cap, 1),
                 "readmission_rate_in_top20_pct": round(100 * prec, 1)})
comparison = pd.DataFrame(rows)
comparison["baseline_rate_pct"] = round(100 * test["y"].mean(), 2)
comparison.to_csv(OUT / "model_comparison.csv", index=False)
print(comparison.to_string(index=False))

# odds ratios from the logistic model (per 1 SD for numeric features)
names = model.named_steps["prep"].get_feature_names_out()
coefs = model.named_steps["clf"].coef_[0]
odds = (pd.DataFrame({"feature": names, "odds_ratio": np.exp(coefs)})
        .assign(feature=lambda d: d.feature.str.replace("num__", "").str.replace("cat__", ""))
        .sort_values("odds_ratio", ascending=False))
odds.to_csv(OUT / "model_odds_ratios.csv", index=False)

# calibration / lift by risk decile
test["decile"] = pd.qcut(test["model_risk"].rank(method="first"), 10, labels=range(1, 11))
deciles = (test.groupby("decile", observed=True)
           .agg(patients=("y", "size"), readmission_rate_pct=("y", "mean"))
           .assign(readmission_rate_pct=lambda d: (100 * d.readmission_rate_pct).round(2))
           .reset_index())
deciles.to_csv(OUT / "risk_deciles.csv", index=False)

# ------------------------------------------------------------------ HbA1c: adjusted analysis
# Logistic regression on the whole cohort: does testing HbA1c relate to readmission
# after adjusting for the obvious confounders?
formula = ("y ~ C(hba1c_group, Treatment('Not tested')) + age_mid + los_days + prior_inpatient"
           " + prior_emergency + number_diagnoses + C(primary_diagnosis_group) + C(admission_source_group)"
           " + C(discharge_group)")
logit = smf.logit(formula, data=df).fit(disp=False)
ci = logit.conf_int()
hb = []
for term in logit.params.index:
    if term.startswith("C(hba1c_group"):
        hb.append({"group_vs_not_tested": term.split("[T.")[1].rstrip("]"),
                   "odds_ratio": round(np.exp(logit.params[term]), 3),
                   "ci95_low": round(np.exp(ci.loc[term, 0]), 3),
                   "ci95_high": round(np.exp(ci.loc[term, 1]), 3),
                   "p_value": round(logit.pvalues[term], 4)})
hb = pd.DataFrame(hb)
hb.to_csv(OUT / "hba1c_adjusted.csv", index=False)
print("\nHbA1c, adjusted odds ratios vs 'Not tested':")
print(hb.to_string(index=False))

# any test vs not tested (single number for the summary)
df["tested"] = df["hba1c_tested"].astype(int)
logit2 = smf.logit(formula.replace("C(hba1c_group, Treatment('Not tested'))", "tested"), data=df).fit(disp=False)
or_t, (lo, hi) = np.exp(logit2.params["tested"]), np.exp(logit2.conf_int().loc["tested"])
pd.DataFrame([{"odds_ratio": round(or_t, 3), "ci95_low": round(lo, 3), "ci95_high": round(hi, 3),
               "p_value": round(logit2.pvalues["tested"], 4)}]).to_csv(OUT / "hba1c_tested_adjusted.csv", index=False)
print(f"\nAny HbA1c test vs none: OR={or_t:.2f} (95% CI {lo:.2f}-{hi:.2f}), p={logit2.pvalues['tested']:.4f}")

# The original paper reported that the relationship depends on the primary diagnosis.
# Check it the same way: adjusted odds ratio of testing, separately per diagnosis group.
strat = []
f_strat = ("y ~ tested + age_mid + los_days + prior_inpatient + prior_emergency + number_diagnoses"
           " + C(admission_source_group) + C(discharge_group)")
for grp in ["Diabetes", "Circulatory", "Respiratory"]:
    sub = df[df.primary_diagnosis_group == grp]
    m = smf.logit(f_strat, data=sub).fit(disp=False)
    lo_s, hi_s = np.exp(m.conf_int().loc["tested"])
    strat.append({"primary_diagnosis": grp, "patients": len(sub),
                  "rate_not_tested_pct": round(100 * sub.loc[sub.tested == 0, "y"].mean(), 2),
                  "rate_tested_pct": round(100 * sub.loc[sub.tested == 1, "y"].mean(), 2),
                  "adjusted_odds_ratio": round(np.exp(m.params["tested"]), 3),
                  "ci95_low": round(lo_s, 3), "ci95_high": round(hi_s, 3),
                  "p_value": round(m.pvalues["tested"], 4)})
# formal interaction test: diabetes vs circulatory
sub = df[df.primary_diagnosis_group.isin(["Diabetes", "Circulatory"])].copy()
sub["diabetes_primary"] = (sub.primary_diagnosis_group == "Diabetes").astype(int)
mi = smf.logit(f_strat.replace("tested", "tested * diabetes_primary", 1), data=sub).fit(disp=False)
p_inter = mi.pvalues["tested:diabetes_primary"]
strat = pd.DataFrame(strat)
strat["interaction_p_diabetes_vs_circulatory"] = round(p_inter, 4)
strat.to_csv(OUT / "hba1c_by_diagnosis_adjusted.csv", index=False)
print("\nHbA1c testing by primary diagnosis (adjusted):")
print(strat.to_string(index=False))

# ------------------------------------------------------------------ charts
prof = pd.read_csv(OUT / "readmission_profile.csv")
base = 100 * df["y"].mean()

# 1) prior inpatient stays
p = prof[prof.dimension == "Inpatient stays in prior year"]
fig, ax = plt.subplots(figsize=(6.5, 3.4))
bars = ax.bar(p.category, p.readmission_rate_pct, color=[GREY, AMBER, RED, RED], width=0.6)
ax.axhline(base, color=INK, lw=1, ls="--")
ax.text(0.5, base + 0.6, f"average {base:.1f}%", ha="left", fontsize=9)
for b, v, n in zip(bars, p.readmission_rate_pct, p.patients):
    ax.text(b.get_x() + b.get_width() / 2, v + 0.4, f"{v:.1f}%", ha="center", fontweight="bold")
ax.set_xlabel("Inpatient stays in the year before")
ax.set_yticks([])
ax.set_title("30-day readmission rate by prior hospital stays", fontsize=11)
fig.tight_layout(); fig.savefig(CH / "prior_inpatient.png"); plt.close(fig)

# 2) discharge destination
p = prof[prof.dimension == "Discharged to"].sort_values("readmission_rate_pct")
fig, ax = plt.subplots(figsize=(8, 3.6))
ax.barh(p.category, p.readmission_rate_pct, color=[RED if v > base else GREY for v in p.readmission_rate_pct])
ax.axvline(base, color=INK, lw=1, ls="--")
for y, (v, n) in enumerate(zip(p.readmission_rate_pct, p.patients)):
    ax.text(v + 0.2, y, f"{v:.1f}%  ({n:,} patients)", va="center", fontsize=9)
ax.set_xlim(0, p.readmission_rate_pct.max() * 1.45)
ax.set_title("30-day readmission rate by discharge destination", fontsize=11)
fig.tight_layout(); fig.savefig(CH / "discharge.png"); plt.close(fig)

# 3) ROC curves
fig, ax = plt.subplots(figsize=(5.2, 4.6))
for col, lab, c in [("model_risk", f"Logistic regression (AUC {auc_model:.2f})", TEAL),
                    ("lace_score", f"LACE-style score (AUC {auc_lace:.2f})", AMBER)]:
    fpr, tpr, _ = roc_curve(test["y"], test[col])
    ax.plot(fpr, tpr, color=c, lw=2, label=lab)
ax.plot([0, 1], [0, 1], color=GREY, ls="--", lw=1, label="Random (AUC 0.50)")
ax.set_xlabel("False positive rate"); ax.set_ylabel("True positive rate")
ax.legend(fontsize=9, frameon=False, loc="lower right")
ax.set_title("Who will be readmitted? Test set", fontsize=11)
fig.tight_layout(); fig.savefig(CH / "roc.png"); plt.close(fig)

# 4) lift by decile
fig, ax = plt.subplots(figsize=(7, 3.4))
ax.bar(deciles.decile.astype(int), deciles.readmission_rate_pct,
       color=[RED if d >= 9 else GREY for d in deciles.decile.astype(int)])
ax.axhline(100 * test["y"].mean(), color=INK, lw=1, ls="--")
ax.set_xticks(range(1, 11))
ax.set_xlabel("Risk decile (1 = lowest predicted risk, 10 = highest)")
ax.set_ylabel("Readmitted within 30 days (%)")
ax.set_title("Actual readmission rate by predicted risk decile", fontsize=11)
fig.tight_layout(); fig.savefig(CH / "deciles.png"); plt.close(fig)

# 5) data quality: missing share of key columns
dq = pd.read_csv(OUT / "dq_results.csv")
m = dq[dq.check_id.isin([2, 3, 4, 5, 10, 11, 12])].copy()
m["pct"] = 100 * m.affected_rows / 101766
m = m.sort_values("pct")
fig, ax = plt.subplots(figsize=(8, 3.4))
labels = m.check_name.str.replace(" recorded as '?'", " missing").str.replace(r" \(.*\)", "", regex=True)
ax.barh(labels, m.pct, color=AMBER)
for y, v in enumerate(m.pct):
    ax.text(v + 1, y, f"{v:.0f}%", va="center", fontsize=9)
ax.set_xlim(0, 110)
ax.set_title("Share of encounters with missing or unknown values", fontsize=11)
fig.tight_layout(); fig.savefig(CH / "missing_values.png"); plt.close(fig)

print(f"\nCharts written to {CH}")
