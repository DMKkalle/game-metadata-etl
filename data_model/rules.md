# Data Rules

## Primärnycklar (PK)
- Alla `*_id` måste vara unika inom sin fil.

## Främmande nycklar (FK)
- `release.game_id` → `game.game_id`
- `person_game.person_id` → `person.person_id`; `game_id` → `game.game_id`
- `company_game.company_id` → `company.company_id`; `game_id` → `game.game_id`
- `person_release.person_id` → `person.person_id`; `release_id` → `release.release_id`
- `company_release.company_id` → `company.company_id`; `release_id` → `release.release_id`

## Obligatoriska fält
- `person.name`, `company.name`, `game.canonical_title`, `release.release_title`, `release.region`, `release.platform`.

## Region- och plattformsregler
- `region`: använd tvåbokstavskoder som `US, SE, JP, EU, FR, DE, GB` (kan utökas).
- `platform`: fri text men konsekvent stavning (Windows, PlayStation, Dreamcast, GBC, …).

## Game vs Release
- Om versioner är **fundamentalt olika** (motor/studio/credits) → olika `game_id`.
- Annars använd **release** för region/plattform/år/namn-skillnader.
- Vid konflikt mellan game-nivå och release-nivå gäller **release** (“skuggar”).

## Roller
- Om `role.csv` finns: validera `role`-fält mot denna (case-insensitive).
- Rollfält är fria strängar tills `role.csv` tas i bruk.

## Formatering
- CSV, UTF-8, komma-separerat, header på rad 1.
- Trimma whitespace; inga tomma fält i obligatoriska kolumner.

## Källspårning
- `source`-fält i relationsfiler kan användas för att notera källa (webb, skärmdump, booklet).
