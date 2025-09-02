# company_game.csv

| Column     | Type   | Required | Description                                       |
|------------|--------|----------|---------------------------------------------------|
| company_id | string | Yes      | FK → `company.csv`                                |
| game_id    | string | Yes      | FK → `game.csv`                                   |
| role       | string | No       | Roll (developer, publisher, distributor, …)       |
| source     | string | No       | Källa/notering (valfritt)                         |

## Användning
- När ett företags roll gäller **alla releases** av ett spel.
- Om roll/företag varierar per release → använd `company_release.csv`.
