# person_game.csv

| Column    | Type   | Required | Description                               |
|-----------|--------|----------|-------------------------------------------|
| person_id | string | Yes      | FK → `person.csv`                          |
| game_id   | string | Yes      | FK → `game.csv`                            |
| role      | string | No       | Roll (valideras mot `role.csv` om den finns) |
| source    | string | No       | Källa/notering (valfritt)                  |

## Användning
- När en persons credit gäller **alla releases** av ett spel.
- Om credit skiljer per region/plattform → använd `person_release.csv`.
