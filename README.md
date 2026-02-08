# Electricity Optimizer

AI-powered platform for electricity price monitoring, forecasting, and automated supplier switching.

## Key Features

- **Real-time price monitoring** across multiple electricity suppliers
- **ML-based price forecasting** using a CNN-LSTM model with XGBoost ensembles
- **Automated load shifting optimization** via mixed-integer linear programming (MILP)
- **Intelligent supplier switching** recommendations based on predicted savings
- **GDPR-compliant data management** with full audit trails
- **Interactive dashboards** for visualizing consumption, costs, and forecasts

## Tech Stack

| Layer          | Technologies                                      |
|----------------|---------------------------------------------------|
| Backend        | FastAPI, Python 3.9+, Celery, Redis               |
| Frontend       | Next.js 14, React 18, Tailwind CSS, Recharts, D3  |
| Database       | PostgreSQL (Neon), TimescaleDB                     |
| ML / Data      | TensorFlow, XGBoost, PuLP, Airflow                |
| Infrastructure | Docker, Kubernetes, Prometheus, Grafana            |
| CI/CD          | GitHub Actions                                     |

## Quick Start (Local Development)

### Prerequisites

- Python 3.9+
- Node.js 18+
- PostgreSQL (or a Neon database URL)

### Backend

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
uvicorn main:app --reload
```

The API server will start at `http://localhost:8000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The development server will start at `http://localhost:3000`.

## Testing

### Backend

```bash
cd backend
pytest
```

### Frontend

```bash
cd frontend
npm test
```

### Additional Test Suites

The repository also includes load, performance, and security tests under `tests/`.

## Deployment

| Service  | Platform |
|----------|----------|
| Backend  | Render   |
| Frontend | Vercel   |
| Database | Neon     |

Deployment configuration files:

- `render.yaml` -- Render service definitions
- `frontend/vercel.json` -- Vercel project settings
- `docker-compose.prod.yml` -- Production Docker Compose
- `scripts/deploy.sh` / `scripts/production-deploy.sh` -- Deployment scripts

Refer to `docs/DEPLOYMENT.md` for detailed deployment instructions.

## API Documentation

When the backend is running, interactive API docs are available at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Project Structure

```
electricity-optimizer/
  backend/            Backend API (FastAPI)
    api/              API route handlers
    models/           Database and Pydantic models
    services/         Business logic
    repositories/     Data access layer
    migrations/       Database migrations
    tests/            Backend unit and integration tests
  frontend/           Frontend application (Next.js 14)
    app/              Next.js app router pages
    components/       React components
    hooks/            Custom React hooks
    lib/              Shared utilities
    store/            Client-side state management
    __tests__/        Frontend unit tests
    e2e/              End-to-end tests (Playwright)
  ml/                 Machine learning pipelines
    models/           Model definitions (CNN-LSTM, XGBoost)
    training/         Training scripts and configs
    inference/        Inference and serving
    optimization/     MILP load shifting optimizer
    evaluation/       Model evaluation utilities
  airflow/            Airflow DAGs for data pipelines
  infrastructure/     Kubernetes manifests and monitoring configs
  scripts/            Deployment, backup, and utility scripts
  tests/              Load, performance, and security tests
  docs/               Project documentation
```

## License

MIT (see LICENSE file for details)
