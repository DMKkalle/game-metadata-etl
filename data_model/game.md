# game.csv

| Column          | Type   | Required | Description                                           |
|-----------------|--------|----------|-------------------------------------------------------|
| game_id         | string | Yes      | Unikt ID (ex. game_000001)                            |
| canonical_title | string | Yes      | Huvudnamn för spelet                                  |
| genre           | string | No       | Genre (ex. Action)                                    |
| perspective     | string | No       | Perspektiv (ex. 3rd-person, Side view)                |

## När ska två versioner vara olika `game_id`?
- Om motor/kodbas/studio/credits är **väsentligt olika** (ex. PC/PS/DC vs GBC): skapa **separata** `game_id`.
- Små skillnader (översättning, region, mindre tillägg) → hanteras som olika **releases** av samma `game_id`.

## Notes
- `canonical_title` är ett praktiskt huvudnamn; release-titlar kan avvika per region/plattform.
- Ytterligare alias kan läggas i `game_alias.csv` (valfritt).
