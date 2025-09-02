# game_alias.csv (optional)

| Column  | Type   | Required | Description                            |
|---------|--------|----------|----------------------------------------|
| game_id | string | Yes      | FK → `game.csv`                        |
| alias   | string | Yes      | Alternativ titel                       |
| locale  | string | No       | Språk/marknad (sv, en, fr, …)          |
| source  | string | No       | Källa (box, manual, databas, …)       |

## Användning
- Hjälper vid sök/dubblettmatchning över felstavningar och alternativa namn.
