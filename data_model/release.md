# release.csv

| Column        | Type   | Required | Description                                               |
|---------------|--------|----------|-----------------------------------------------------------|
| release_id    | string | Yes      | Unikt ID (ex. release_000001)                             |
| game_id       | string | Yes      | FK → `game.csv`                                           |
| region        | string | Yes      | Regionkod (US, SE, JP, EU, FR, DE, GB, …)                 |
| platform      | string | Yes      | Plattform (ex. Windows, PlayStation, Dreamcast, GBC)      |
| release_title | string | Yes      | Titel för **just denna release**                          |
| date          | string | No       | År eller YYYY-MM-DD om känt (ex. 2000 eller 2000-11-21)   |
| serial        | string | No       | Produkt-/katalognr (ex. SLES-xxxxx, Nintendo PN)          |
| language      | string | No       | Språkkod (sv, en, de, fr, …)                               |

## Notes
- En rad per unik kombination av (game_id, region, platform, ev. annan tydlig utgåvediff).
- `release_title` kan vara översatt/avvikande från `canonical_title`.
