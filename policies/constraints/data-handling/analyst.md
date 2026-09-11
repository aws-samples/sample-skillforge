**Work in the warehouse, not in production.** Query the analytics warehouse, never an application
database directly — a long-running analytical query against production is an outage. Run
`SELECT current_database()` and confirm before your first query of a session.
