"""
Download the "Diabetes 130-US Hospitals for Years 1999-2008" dataset.

Official source: UCI Machine Learning Repository (CC BY 4.0)
  https://archive.ics.uci.edu/dataset/296/diabetes+130-us+hospitals+for+years+1999-2008
Paper: Strack B. et al. (2014). Impact of HbA1c Measurement on Hospital Readmission
       Rates: Analysis of 70,000 Clinical Database Patient Records. BioMed Research International.

The UCI zip contains diabetic_data.csv and one IDs_mapping.csv. This script uses the
UCI zip if reachable, otherwise a public GitHub mirror with the mapping already split
into three files. Either way it writes:
  data/raw/diabetic_data.csv, admission_type.csv, admission_source.csv, discharge_disposition.csv

Usage:  python data/download_data.py
"""
import io
import urllib.request
import zipfile
from pathlib import Path

RAW = Path(__file__).parent / "raw"
RAW.mkdir(parents=True, exist_ok=True)

UCI = "https://archive.ics.uci.edu/static/public/296/diabetes+130-us+hospitals+for+years+1999-2008.zip"
MIRROR = "https://raw.githubusercontent.com/renuka-fernando/diabetes_data_warehouse/master/dataset/"


def split_mapping(text: str):
    """UCI's IDs_mapping.csv stacks three tables separated by blank lines."""
    names = ["admission_type", "discharge_disposition", "admission_source"]
    blocks = [b.strip() for b in text.replace("\r", "").split("\n,\n") if b.strip()]
    for name, block in zip(names, blocks):
        (RAW / f"{name}.csv").write_text(block + "\n")


try:
    print("Trying UCI ...")
    z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(UCI, timeout=60).read()))
    for n in z.namelist():
        if n.endswith("diabetic_data.csv"):
            (RAW / "diabetic_data.csv").write_bytes(z.read(n))
        elif n.endswith("IDs_mapping.csv"):
            split_mapping(z.read(n).decode("utf-8"))
    print("Downloaded from UCI")
except Exception as e:
    print(f"UCI not reachable ({e}); using GitHub mirror ...")
    files = {"diabetic_data.csv": "diabetic_data.csv",
             "admission_type.csv": "IDs_mapping_admission_type.csv",
             "admission_source.csv": "IDs_mapping_admission_source.csv",
             "discharge_disposition.csv": "IDs_mapping_discharge_disposition.csv"}
    for local, remote in files.items():
        (RAW / local).write_bytes(urllib.request.urlopen(MIRROR + remote, timeout=60).read())
    print("Downloaded from mirror")

rows = sum(1 for _ in open(RAW / "diabetic_data.csv")) - 1
print(f"diabetic_data.csv: {rows:,} rows (expected 101,766)")
