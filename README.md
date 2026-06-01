# Game Metadata ETL Pipeline
### Bachelor Thesis · Karlstad University × Embracer Games Archive

A scalable ETL (Extract, Transform, Load) pipeline for collecting, normalising and quality-assuring video game metadata from multiple external sources. Built in collaboration with [Embracer Games Archive](https://embracergamesarchive.com), one of the world's largest game preservation archives (80,000+ items).

---

## What it does

Video game metadata is notoriously inconsistent — the same game can appear under different titles, regions and spellings across databases. This pipeline solves that by:

- **Extracting** metadata from IGDB, GiantBomb and Wikidata via their APIs
- **Normalising** titles, platforms and regions into a unified data model
- **Matching** records across sources using fuzzy matching and rule-based algorithms
- **Scoring** data quality with confidence values so uncertain matches are flagged for review
- **Loading** the result into traceable, structured CSV files ready for the archive's catalogue

The pipeline processed 10,000+ game editions and significantly reduced the need for manual metadata review.

---

## Architecture

```
External APIs          Extractors              Transformers            Output
─────────────    →    ──────────────    →    ─────────────────    →   ────────
IGDB               API fetching           Normalisation              editions.csv
GiantBomb          Authentication         Fuzzy matching             releases.csv  
Wikidata           Caching & logging      Alias handling             enriched_master.csv
                                          Confidence scoring         catalog_embracer.csv
```

---

## Tech stack

- **Python** — core pipeline
- **pandas** — data processing
- **python-slugify** — title normalisation
- **IGDB API** (via Twitch) — primary game metadata source
- **GiantBomb API** — supplementary credits and genre data
- **Wikidata SPARQL** — open-source verification layer

---

## Project structure

```
├── src/
│   ├── normalize_one.py        # Normalise raw Embracer exports
│   ├── build_releases.py       # Build editions/releases tables with hash IDs
│   ├── igdb_enrich_editions.py # Enrich from IGDB API
│   ├── gb_enrich_editions.py   # Enrich from GiantBomb API
│   ├── enrich_wikidata.py      # Enrich from Wikidata
│   ├── merge_enriched.py       # Merge all sources into master file
│   └── merge_credits_preview.py # Export final Embracer catalogue view
├── configs/
│   ├── platform_map.yaml       # Platform normalisation rules
│   ├── accessory_map.yaml      # Accessory type mapping
│   └── source_weights.yaml     # Source reliability weights
├── data_model/                 # Data model specifications
├── validators/                 # Data validation scripts
├── data/
│   ├── raw/                    # Raw Embracer exports (not included)
│   ├── outputs/                # Pipeline outputs
│   └── external/               # Cached API responses
├── requirements.txt
└── .env.example                # Required environment variables
```

---

## Getting started

**1. Clone the repo**
```bash
git clone https://github.com/yourusername/exjobb-embracer.git
cd exjobb-embracer
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Set up environment variables**
```bash
cp .env.example .env
# Fill in your API keys in .env
```

**4. Run the pipeline**
```bash
python src/normalize_one.py      # Step 1: Normalise raw data
python src/build_releases.py     # Step 2: Build editions table
python src/igdb_enrich_editions.py  # Step 3: Enrich from IGDB
python src/gb_enrich_editions.py    # Step 4: Enrich from GiantBomb
python src/enrich_wikidata.py       # Step 5: Enrich from Wikidata
python src/merge_enriched.py        # Step 6: Merge all sources
```

---

## Key design decisions

**Hash-based edition IDs** — each game edition is identified by a deterministic hash of title + platform + region, making IDs stable and reproducible across pipeline runs.

**Modular extractors** — each data source is a separate module, so new sources can be added without touching the rest of the pipeline.

**Confidence scoring** — every output record gets a confidence score (1–10) and flag (low/medium/high) based on how many sources confirmed the match.

**Source provenance** — every data point is traceable back to its original source, enabling transparent quality auditing.

---

## Results

| Metric | Result |
|--------|--------|
| Game editions processed | 10,000+ |
| Normalisation | Automated platform, region and title standardisation |
| Duplicate detection | Rule-based + fuzzy matching across all sources |
| Confidence scoring | 3-tier flagging system for manual review prioritisation |

---

## Academic context

This project was developed as a bachelor thesis in Computer Science at Karlstad University (15 hp), in collaboration with Embracer Games Archive. The full thesis paper is available upon request.

**Supervisor:** Hans Hedbom  
**Examiner:** Jonathan Vestin  
**Date:** January 2026
