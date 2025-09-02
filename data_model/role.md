# role.csv (optional men rekommenderas)

| Column  | Type   | Required | Description                  |
|---------|--------|----------|------------------------------|
| role_id | string | Yes      | Unikt ID (ex. role_0001)     |
| name    | string | Yes      | Rollnamn (ex. developer)     |
| group   | string | No       | Grupp (dev, art, audio, qa)  |
| notes   | string | No       | Förklaring/exempel           |

## Rekommendation
- Validera `role`-fält i relationsfiler mot denna lista för att minska stavfel.
