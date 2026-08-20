# CloudOpsAI — Runnable Python MVP

CloudOpsAI is a complete academic prototype based on the report **“An Intelligent Multi-Cloud Resource Management and DevOps Platform Using Artificial Intelligence.”** It provides a polished browser dashboard, a JSON API, a SQLite data model, explainable recommendation logic, deployment-risk scoring, approval workflows, audit logging, seed data, and automated tests.

## Implemented modules

- Session login and demo role-based access
- Unified AWS, Azure, and GCP resource inventory
- Telemetry and cost history stored in SQLite
- Executive dashboard with cost trend, provider distribution, recommendations, and deployment risk
- Explainable rule-based resource optimization recommendations
- Human approval, rejection, deferment, simulated execution, and outcome verification
- Interpretable deployment-risk model
- Immutable-style audit-event records
- Interactive API documentation at `/docs`
- Unit tests for analytics and password security

> This is a safe demonstration MVP. It does not connect to live cloud accounts and never changes real infrastructure. Provider adapters are represented by seeded sample data and stable internal models.

## Quick start in VS Code (Windows)

1. Extract the ZIP and open the `CloudOpsAI_MVP` folder in VS Code.
2. Open **Terminal → New Terminal**.
3. Create a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

4. Install dependencies:

```powershell
pip install -r requirements.txt
```

5. Start the application:

```powershell
python run.py
```

6. Open:

```text
http://127.0.0.1:8000
```

## Demo accounts

| Role | Email | Password |
|---|---|---|
| Cloud administrator | `admin@cloudopsai.local` | `admin123` |
| Cloud engineer | `engineer@cloudopsai.local` | `engineer123` |
| Finance manager | `finance@cloudopsai.local` | `finance123` |
| Security analyst | `security@cloudopsai.local` | `security123` |

## API documentation

After login, open:

```text
http://127.0.0.1:8000/docs
```

Important endpoints include:

- `GET /api/health`
- `GET /api/dashboard`
- `GET /api/resources`
- `POST /api/telemetry`
- `GET /api/recommendations`
- `POST /api/recommendations/generate`
- `POST /api/recommendations/{id}/decision`
- `POST /api/deployments/risk`
- `GET /api/audits`

## Run tests

```powershell
pytest -q
```

## Reset the demonstration database

Stop the server, then run:

```powershell
python scripts/reset_demo.py
```

## Docker option

```powershell
docker compose up --build
```

Then open `http://127.0.0.1:8000`.

## Project structure

```text
CloudOpsAI_MVP/
├── app/
│   ├── main.py
│   ├── models.py
│   ├── schemas.py
│   ├── security.py
│   ├── seed.py
│   ├── routers/
│   ├── services/
│   ├── templates/
│   └── static/
├── data/
├── scripts/
├── tests/
├── run.py
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## Production extension points

To convert the MVP into a production platform, add real read-only provider adapters, OAuth/OIDC, a secret vault, PostgreSQL and time-series storage, background queues, provider contract tests, model monitoring, and Infrastructure-as-Code change generation with multi-party approval.
