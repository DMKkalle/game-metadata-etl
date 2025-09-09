import sys  # Importerar systemmodul för att kunna avsluta programmet
from pathlib import Path  # Importerar Path för att hantera filvägar
import pandas as pd  # Importerar pandas för att läsa och hantera CSV-filer

# ----------------------------
# Paths
# ----------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]  # Hittar projektets rotmapp
DATASET_DIR = REPO_ROOT / "datasets" / "sample"  # Sätter sökväg till exempeldata
REPORTS_DIR = REPO_ROOT / "reports"  # Sätter sökväg till rapportmapp
REPORTS_DIR.mkdir(parents=True, exist_ok=True)  # Skapar rapportmapp om den inte finns
REPORT_PATH = REPORTS_DIR / "quality_report.csv"  # Sökväg till rapportfilen

# ----------------------------
# Report helpers
# ----------------------------
REPORT_HEADERS = ["file", "row", "issue_type", "field", "message", "suggestion"]  # Kolumnnamn för rapporten

def init_report():
    if not REPORT_PATH.exists():  # Om rapportfilen inte finns
        REPORT_PATH.write_text(",".join(REPORT_HEADERS) + "\n", encoding="utf-8")  # Skapa fil med rubriker

def log_issue(file, row, issue_type, field, message, suggestion=""):
    with REPORT_PATH.open("a", encoding="utf-8") as f:  # Öppna rapportfilen för att lägga till en rad
        def clean(s):
            return (str(s) if s is not None else "").replace("\n", " ").strip()  # Tar bort radbrytningar och mellanslag
        f.write(",".join([
            clean(file), clean(row), clean(issue_type), clean(field), clean(message), clean(suggestion)
        ]) + "\n")  # Skriv en rad med information om problemet

# ----------------------------
# CSV loader
# ----------------------------
def read_csv_maybe(path: Path, required_columns=None):
    if not path.exists():  # Om filen inte finns
        log_issue(path.name, "", "missing_file", "", "File not found", f"Create {path.relative_to(REPO_ROOT)}")
        return None  # Returnera None om filen saknas
    try:
        df = pd.read_csv(path, dtype=str).fillna("")  # Försök läsa in CSV-filen som text, ersätt NaN med tomt
    except Exception as e:  # Om det blir fel vid inläsning
        log_issue(path.name, "", "read_error", "", f"Could not read CSV: {e}", "Check encoding/commas/header")
        return None  # Returnera None om det blir fel

    if required_columns:  # Om vissa kolumner krävs
        for col in required_columns:
            if col not in df.columns:  # Om en kolumn saknas
                log_issue(path.name, "", "missing_column", col, "Required column missing", f"Add column '{col}' to header")
    return df  # Returnera DataFrame

# ----------------------------
# PK checks
# ----------------------------
def check_pk_uniqueness(df, file_name, pk_col):
    if df is None or pk_col not in df.columns:  # Om DataFrame saknas eller PK-kolumnen inte finns
        return  # Gör inget
    dupe_mask = df[pk_col].duplicated(keep=False) & (df[pk_col] != "")  # Hitta dubbletter i PK-kolumnen
    if dupe_mask.any():  # Om det finns dubbletter
        for idx, row in df[dupe_mask].iterrows():  # Gå igenom varje rad med dubblett
            log_issue(
                file=file_name,
                row=idx + 2,  # Räkna ut radnummer (med header och 0-index)
                issue_type="pk_duplicate",
                field=pk_col,
                message=f"Duplicate primary key value: '{row[pk_col]}'",
                suggestion="Ensure all *_id values are unique within this file"
            )

# ----------------------------
# Main
# ----------------------------
def main():
    print("=== Embracer validator (Step 1) ===")  # Skriv ut startmeddelande
    print(f"Dataset dir: {DATASET_DIR}")  # Visa vilken mapp som används
    init_report()  # Skapa rapportfil om den inte finns

    required = {  # Vilka kolumner som krävs i varje fil
        "person.csv":   ["person_id", "name"],
        "company.csv":  ["company_id", "name"],
        "game.csv":     ["game_id", "canonical_title"],
        "release.csv":  ["release_id", "game_id", "region", "platform", "release_title"],
    }

    loaded = {}  # Ordbok för inlästa DataFrames
    for fname, cols in required.items():  # Gå igenom varje fil och dess krav
        path = DATASET_DIR / fname  # Sökväg till filen
        df = read_csv_maybe(path, required_columns=cols)  # Läs in filen
        if df is not None:  # Om filen kunde läsas in
            loaded[fname] = df  # Spara DataFrame
            print(f"Loaded {fname}: {len(df):>4} rows")  # Skriv ut antal rader
        else:
            print(f"Missing or unreadable: {fname}")  # Skriv ut felmeddelande

    # ---- Step 2: PK uniqueness checks ----
    check_pk_uniqueness(loaded.get("person.csv"),  "person.csv",  "person_id")  # Kontrollera unika person_id
    check_pk_uniqueness(loaded.get("company.csv"), "company.csv", "company_id")  # Kontrollera unika company_id
    check_pk_uniqueness(loaded.get("game.csv"),    "game.csv",    "game_id")  # Kontrollera unika game_id
    check_pk_uniqueness(loaded.get("release.csv"), "release.csv", "release_id")  # Kontrollera unika release_id

    print("\nReport written to:", REPORT_PATH)  # Visa var rapporten finns
    print("Step 1 done. Next step: add PK checks (uniqueness of *_id).")  # Tips om nästa steg

if __name__ == "__main__":  # Om filen körs direkt
    sys.exit(main())  # Starta programmet och avsluta med rätt kod