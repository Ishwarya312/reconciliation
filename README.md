# Reconciliation Application

A simple Django application built to solve the transaction reconciliation problem, where two distinct systems record transactions with drifting amounts, drifting times, different naming conventions, and different schemas.

## Getting Started

This application is fully containerized using Docker and Docker Compose.

### Prerequisites
- Docker and Docker Compose installed and running on your machine.

### Steps
1. Clone the repository and navigate into it.
2. The environment variables are already configured via the `.env` file for the default setup.
3. Build and start the containers:
   ```bash
   docker-compose up --build
   ```
4. Once the database is ready and the Django server is running, the app will be available at `http://localhost:8000`.
5. You can use the provided sample data in the `data/` directory to test the reconciliation engine:
   - `data/ledger_initial.csv`
   - `data/statement_initial.csv`
   - `data/statement_correction.csv`

## Architecture and Design Decisions

- **Database Choice (PostgreSQL)**: Met the technical requirements and handles robust, relational financial data very well.
- **Framework (Django + DRF)**: Chosen per requirements. Django's ORM makes it extremely easy to model the relationships between `LedgerRecords`, `StatementRecords`, and `MatchResults`. 
- **Matching Logic & Engine**: 
  - **Normalization**: Instead of having complex `if/else` statements sprinkled everywhere, we parse incoming CSVs into a standardized internal representation first (converting dates to UTC, normalizing sides like `B` -> `BUY`).
  - **Passes**: Matching is done in passes (Exact identifiers first, then Fuzzy matching with a time and amount tolerance window). This ensures we catch the "happy path" quickly and gracefully degrade to fuzzy logic.
- **Synchronous Processing**: To keep the initial version simple, file uploads and the reconciliation engine run synchronously during the HTTP request. 

## Limitations and Exclusions

- **Asynchronous Task Queue**: In a production environment with millions of rows, processing files synchronously in a web request would timeout. I left out Celery/Redis for now to keep the setup simple and easy to run via `docker-compose`.
- **Advanced Authentication/Authorization**: The app currently does not enforce strict user logins or roles for uploading vs. resolving matches.
- **Dynamic Mapping Configuration**: Currently, the column mappings for the "Ledger" and "Statement" are hardcoded to the problem description formats. In a real scenario, this would be a UI configuration where a user maps columns on their first upload.

## Future Enhancements

1. **Implement Celery**: Offload the parsing and matching engine to background workers to handle massive file sizes seamlessly.
2. **Audit Logging**: Implement a history table to track *who* manually matched a record and *when* (essential for compliance in financial systems).
3. **Machine Learning / Advanced Fuzzy Matching**: For strings (like instrument names) that might be misspelled, adding a Levenshtein distance check or a simple ML classifier to suggest matches for the "Unmatched" bucket.
4. **Interactive Dashboard**: Build a React/Vue frontend consuming the DRF API to provide a more dynamic, drag-and-drop manual matching experience instead of server-rendered Django templates.
