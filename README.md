# Nexus Recon: Cryptocurrency Reconciliation Engine

Nexus Recon is a Django-based financial reconciliation engine designed to automatically match internal cryptocurrency ledger records against third-party partner statements.

## How to Run It

This application is fully containerized using Docker and Docker Compose. 

**Prerequisites:**
- Docker and Docker Compose installed on your machine.

**Steps:**
1. Clone the repository and navigate into the root directory.
2. Build and start the containers:
   ```bash
   docker-compose up -d --build
   ```
3. Run the database migrations to set up the schema:
   ```bash
   docker-compose exec web python manage.py migrate
   ```
4. Access the application in your browser at: **http://localhost:8000/**

**Optional:** If you want to use the Django Admin interface to view the raw database tables, you can create a superuser:
```bash
docker-compose exec web python manage.py createsuperuser
```
You can then log in at **http://localhost:8000/admin**.

## Architecture and Design Decisions

- **Database-Driven Engine**: Instead of keeping everything in memory, we parse CSVs into actual PostgreSQL database records (`LedgerRecord` and `StatementRecord`). This allows us to scale beyond memory limits, easily query past data, and maintain persistent state for manual human decisions.
- **Multi-Pass Matching Logic**:
  - *Pass 0 (Carry Over)*: Applies past human decisions (manual links or accepted unpaired records) before the engine touches them.
  - *Pass 1 (Exact)*: Matches transactions with identical `transaction_id` / `reference`.
  - *Pass 2 (Fuzzy)*: Uses a 2-hour time drift window and a 2% price deviation tolerance to match records where identifiers don't align perfectly.
- **Manual Resolution Tracking**: When humans manually link two orphaned rows or flag a row as permanently unpaired, those decisions are saved. The engine queries these decisions at the start of every new run to ensure human interventions are respected indefinitely.
- **Server-Side Rendered UI**: Built using pure HTML and CSS (a clean, light-themed glassmorphism aesthetic) served via Django templates for simplicity and speed, without the overhead of a heavy JavaScript framework. JavaScript is only used sparingly for the API requests during manual resolution.

## Limitations and Exclusions

- **Authentication & Authorization**: The application currently has no login screens or role-based access control (RBAC). Anyone who can access port 8000 can execute a reconciliation run.
- **Complex Audit Logs**: While we track whether a match was `resolved_by_human`, we do not track *which* specific user made the change or at what exact timestamp they clicked the button.
- **Pagination & Infinite Scroll**: If the CSV files contain hundreds of thousands of unmatched records, rendering them all on a single HTML page at once could cause browser performance issues.
- **File Format Agnostic Parsers**: Currently, the engine expects the CSV files to have very specific headers (e.g., `trade_id`, `reference`, `gross_amount`, `total`). It does not dynamically infer column meanings for new partner formats.

## Future Enhancements

1. **Implement Celery / Background Workers**: CSV parsing and matching block the main web thread. Moving `run_reconciliation` to an asynchronous Celery task would allow the dashboard to show a "Processing..." state for massive files.
2. **Dynamic Column Mapping**: Build a UI step where users upload a file and visually drag-and-drop map the CSV columns (like "Qty" or "Size") to our internal normalized fields (like `quantity`).
3. **Advanced Audit Trails**: Integrate `django-simple-history` to track every manual resolution decision back to a specific user account.
4. **Export Reports**: Add a button to export the `MatchResults` (the Exact, Fuzzy, and Unmatched tables) back into a downloadable Excel or CSV report for accounting teams.
