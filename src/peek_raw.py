"""
inspect.py — Steg 1: Läs EN rå-CSV och skriv ut en tydlig översikt.
Syfte:
- Hitta encoding och separator automatiskt
- Visa form (rader x kolumner) och kolumnnamn
- Visa de 10 första raderna
- Visa toppvärden i några nyckelfält om de finns

Körning:
    python src/inspect.py

Förutsättningar:
- Lägg endast den fil du vill testa nu i data/raw/
- Beroenden: pandas
"""

from pathlib import Path
import pandas as pd

# Pekar på mappen med rådata (vi rör aldrig filerna här inne).
RAW_DIR = Path("data/raw")


def read_csv_auto(p: Path, encodings=("utf-8", "latin1", "utf-16"), seps=(",", ";", "\t")):
    """
    Försöker läsa en CSV med olika encodings och separatorer.
    - Om en läsning ger bara 1 kolumn (vanligt tecken på fel separator) så testas nästa separator
    - Returnerar: (DataFrame, vald_encoding, vald_separator)
    - Kastar RuntimeError om inget försök lyckas
    """
    for enc in encodings:
        for sep in seps:
            try:
                df = pd.read_csv(p, encoding=enc, sep=sep)
                # Heuristik: om allt åkte in i EN kolumn och vi inte testade tab-separering,
                # prova nästa separator.
                if df.shape[1] == 1 and sep != "\t":
                    continue
                return df, enc, sep
            except Exception:
                # Misslyckad läsning? Fortsätt testa nästa kombination.
                continue
    # Om alla försök misslyckades:
    raise RuntimeError(f"Kunde inte läsa filen med vanliga encodings/separatorer: {p}")


def main():
    """Huvudflöde: välj EN fil, läs in den, skriv ut sammanfattning."""
    # Leta upp alla CSV-filer i data/raw (även undermappar). Vi tar endast den första.
    csvs = sorted(RAW_DIR.rglob("*.csv"))
    if not csvs:
        print("❌ Hittade inga CSV-filer i data/raw/. Lägg in en fil och kör igen.")
        return

    path = csvs[0]  # Vi jobbar långsamt: exakt en fil åt gången (den första i listan).
    print(f"[INSPECT] Läser: {path}")

    # Läs in med auto-detektering av encoding och separator.
    df, used_enc, used_sep = read_csv_auto(path)
    print(f"- Encoding upptäckt: {used_enc} | Separator upptäckt: {repr(used_sep)}")
    print(f"- Form: {df.shape[0]} rader × {df.shape[1]} kolumner")
    print("- Kolumner:", list(df.columns))

    # Visa de 10 första raderna i en läsbar tabell (bryter inte rader).
    print("\n--- Första 10 rader ---")
    with pd.option_context("display.max_colwidth", 200, "display.width", 200):
        # to_string() ger snygg konsolutskrift utan indexkolumn
        print(df.head(10).to_string(index=False))

    # Nyckelfält vi ofta vill kika på (visas bara om de råkar finnas i filen).
    key_cols = [
        "object_name",          # plattform i rådata
        "broadcast_standard",   # PAL/NTSC/NTSC-J etc
        "place_of_publication", # plats/land
        "title.language",       # språk
    ]

    for col in key_cols:
        if col in df.columns:
            print(f"\n--- Toppvärden (max 10): {col} ---")
            # value_counts med NaN synliga: dropna=False
            vc = df[col].value_counts(dropna=False).head(10)
            # to_string() → kompakt, läsbar i terminalen
            print(vc.to_string())

    # TODO (senare steg): spara en liten rapport till data/outputs om vi vill.
    # Nu skriver vi bara till konsolen för att gå igenom det tillsammans.


if __name__ == "__main__":
    main()
