import sys
from pathlib import Path
import pandas as pd

# ----------------------------
# Paths
# ----------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = REPO_ROOT / "datasets" / "sample"
REPORTS_DIR = REPO_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = REPORTS_DIR / "quality_report.csv"

# ----------------------------
# Report helpers
# ----------------------------
REPORT_HEADERS = ["file", "row", "issue_type", "field", "message", "suggestion"]

def init_report():
    if not REPORT_PATH.exists():
        REPORT_PATH.write_text(",".join(REPORT_HEADERS) + "\n", encoding="utf-8")

def log_issue(file, row, issue_type, field, message, suggestion=""):
    with REPORT_PATH.open("a", encoding="utf-8") as f:
        # Allt som text; inga kommatecken i fälten för enkelhet i steg 1
        def clean(s):
            return (str(s) if s is not None else "").replace("\n", " ").strip()
        f.write(",".join([
            clean(file), clean(row), clean(issue_type), clean(field), clean(message), clean(suggestion)
        ]) + "\n")

# ----------------------------
# CSV loader
# ----------------------------
def read_csv_maybe(path: Path, required_columns=None):
    if not path.exists():
        log_issue(path.name, "", "missing_file", "", "File not found", f"Create {path.relative_to(REPO_ROOT)}")
        return None
    try:
        df = pd.read_csv(path, dtype=str).fillna("")
    except Exception as e:
        log_issue(path.name, "", "read_error", "", f"Could not read CSV: {e}", "Check encoding/commas/header")
        return None

    if required_columns:
        for col in required_columns:
            if col not in df.columns:
                log_issue(path.name, "", "missing_column", col, "Required column missing", f"Add column '{col}' to header")
    return df

# ----------------------------
# PK checks
# ----------------------------
def check_pk_uniqueness(df, file_name, pk_col):
    if df is None or pk_col not in df.columns:
        return
    # hitta dubbletter i PK-kolumnen
    dupe_mask = df[pk_col].duplicated(keep=False) & (df[pk_col] != "")
    if dupe_mask.any():
        for idx, row in df[dupe_mask].iterrows():
            log_issue(
                file=file_name,
                row=idx + 2,  # +2 pga headerrad + 0-index
                issue_type="pk_duplicate",
                field=pk_col,
                message=f"Duplicate primary key value: '{row[pk_col]}'",
                suggestion="Ensure all *_id values are unique within this file"
            )


# ----------------------------
# Main
# ----------------------------
def main():
    print("=== Embracer validator (Step 1) ===")
    print(f"Dataset dir: {DATASET_DIR}")
    init_report()

    required = {
        "person.csv":   ["person_id", "name"],
        "company.csv":  ["company_id", "name"],
        "game.csv":     ["game_id", "canonical_title"],
        "release.csv":  ["release_id", "game_id", "region", "platform", "release_title"],
    }

    loaded = {}
    for fname, cols in required.items():
        path = DATASET_DIR / fname
        df = read_csv_maybe(path, required_columns=cols)
        if df is not None:
            loaded[fname] = df
            print(f"Loaded {fname}: {len(df):>4} rows")
        else:
            print(f"Missing or unreadable: {fname}")


    # ---- Step 2: PK uniqueness checks ----
    check_pk_uniqueness(loaded.get("person.csv"),  "person.csv",  "person_id")
    check_pk_uniqueness(loaded.get("company.csv"), "company.csv", "company_id")
    check_pk_uniqueness(loaded.get("game.csv"),    "game.csv",    "game_id")
    check_pk_uniqueness(loaded.get("release.csv"), "release.csv", "release_id")


    print("\nReport written to:", REPORT_PATH)
    print("Step 1 done. Next step: add PK checks (uniqueness of *_id).")

if __name__ == "__main__":
    sys.exit(main())
