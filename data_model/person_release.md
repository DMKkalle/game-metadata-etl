# person_release.csv

| Column     | Type   | Required | Description                                        |
|------------|--------|----------|----------------------------------------------------|
| person_id  | string | Yes      | FK → `person.csv`                                  |
| release_id | string | Yes      | FK → `release.csv`                                 |
| role       | string | No       | Roll (valideras mot `role.csv` om den finns)      |
| source     | string | No       | Källa/notering (valfritt)                          |

## Användning
- När krediter skiljer sig mellan olika **releases** (region/plattform).
- **Regel:** Release-nivån **skuggar** game-nivån vid konflikt.
