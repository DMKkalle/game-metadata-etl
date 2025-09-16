# IGDB – Extracted CSVs

Denna mapp innehåller normaliserade CSV:er hämtade från IGDB-API:t. Alla filer är idempotenta: körning skriver endast nya rader baserat på definierade nycklar.

## Filformat

### igdb_games.csv
**Kolumner:**  
- igdb_id (PK)  
- name  
- first_release_date_ts  
- first_release_date_ymd  
- genres (semicolon; text)  
- themes (semicolon; text)  
- game_modes (semicolon; text)  
- player_perspectives (semicolon; text)  
- franchises (semicolon; text)  
- collection (text)  
- platforms (semicolon; plattformsnamn)  
- aggregated_rating

**Primärnyckel:** (igdb_id) – exakt en rad per spel.

---

### igdb_alternative_names.csv
**Kolumner:**  
- igdb_id  
- alias

**Unik nyckel:** (igdb_id, alias) – case-insensitiv jämförelse vid insättning.

---

### igdb_platforms.csv
**Kolumner:**  
- igdb_id  
- platform_id  
- platform_name

**Unik nyckel:** (igdb_id, platform_id)

---

### igdb_release_dates.csv
**Kolumner:**  
- igdb_id  
- date_ts  
- date_ymd  
- human  
- region_id  
- region_name  
- region_code (EU/US/JP/… eller `UNKNOWN`)  
- platform_id  
- platform_name

**Unik nyckel:** (igdb_id, date_ts, region_id, platform_id, human)  
> Not: Om `date_ts` finns ignoreras `human` i nyckeln (dvs. tidsstämpeln styr).

---

### igdb_websites.csv
**Kolumner:**  
- igdb_id  
- category_id (IGDB:s kategori-int)  
- url

**Unik nyckel:** (igdb_id, url)

---

### igdb_involved_companies.csv
**Kolumner:**  
- igdb_id  
- company_name  
- developer (bool)  
- publisher (bool)  
- porting (bool)  
- supporting (bool)

**Unik nyckel:** (igdb_id, company_name, developer, publisher, porting, supporting)

## Körning

```bash
# aktivera din venv först
python igdb_extract.py "Golden Axe" "Super Mario World" --limit 1