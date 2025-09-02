# company_release.csv

| Column     | Type   | Required | Description                                   |
|------------|--------|----------|-----------------------------------------------|
| company_id | string | Yes      | FK → `company.csv`                            |
| release_id | string | Yes      | FK → `release.csv`                            |
| role       | string | No       | Roll (developer, publisher, distributor, …)   |
| source     | string | No       | Källa/notering (valfritt)                     |

## Användning
- När företagsrollen varierar per **release** (vanligt vid olika regioner).
- **Regel:** Release-nivån **skuggar** game-nivån vid konflikt.
