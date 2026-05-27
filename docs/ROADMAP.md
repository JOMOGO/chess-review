# Roadmap

## v1 Features

### Tactical Motif Classifier
Cluster missed tactics by type (fork, pin, skewer, discovered attack, etc.) using pattern matching on the PV and board state.

### Endgame Conversion Stats
Track conversion rates in won endgames (e.g., rook endings, pawn endings) and identify where the user fails to convert.

### Lichess Import
Support importing games from Lichess via their ndjson API. Unify ingestion under a Provider enum.

### Multi-user Support
Add authentication, per-user data isolation, and basic account management.
