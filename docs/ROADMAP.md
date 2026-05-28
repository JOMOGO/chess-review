# Roadmap

## Shipped

### Tactical Motif Classifier ✓
Shipped in v1.0. Clusters missed tactics by type (fork, pin, skewer, discovered attack, …) via pattern matching on the PV and the board state. Lives under `/players/:id/tactics`.

### Endgame Conversion Stats ✓
Shipped in v1.0. Conversion rates in won endgames (rook, pawn, etc.) with per-bucket drill-down. Lives under `/players/:id/endgames`.

### Openings Overhaul ✓
Shipped in v1.1. Unified `/players/:id/openings` umbrella with a list view (ECO/name grouping, drill-down with per-game accuracy + CPL) and a true position-based move tree (W-D-L per node, colour filter for repertoire isolation). Chess-standard score-rate replaces the old `wins / N` metric.

## v1.2 candidates

### Lichess Import
Support importing games from Lichess via their ndjson API. Unify ingestion under a `Provider` enum so chess.com and Lichess archives are first-class peers in the pipeline. Today everything in `ingestion/` assumes chess.com.

### Per-game notes & bookmarks
Add a `notes` text column + `is_bookmarked` flag to `Game` so users can annotate critical games and quickly find them. Schema-only feature, frontend cards already have room.

### Avg opponent rating per opening
Add `MAX(played_at)` / avg opponent rating to the opening-stats analytics so the Win Rates list can show "you score 60% — but vs ~1200s". Cheap one-query add.

### Recent-form arrow
Compare last-5-games score% to all-time score% per opening, display a ↑/↓ arrow on the row. Two-window query.

## Beyond v1

### Multi-user support
Auth, per-user data isolation, account management. Would convert the single-user desktop model into a small SaaS shell; probably its own major version (v2) given the scope.

### Annotation export
Export per-game review as a `.pgn` with `{ ... }` annotations and `$` NAG codes for blunders/mistakes — opens the door to studying inside ChessBase, Scid, lichess studies, etc.

### Backend test suite
Currently zero tests under `backend/tests/`. The analytics modules are the obvious target — pure functions, easy fixtures via a small in-memory SQLite DB with hand-curated games.
