# Automated Electricity Supplier Price Optimizer

An AI-powered platform that continuously monitors electricity prices, forecasts market trends, optimizes consumption patterns, and automatically switches suppliers to minimize costs.

## Overview

This platform leverages machine learning (CNN-LSTM models), optimization algorithms (MILP), and real-time data integration to deliver:

- **Price Forecasting**: 24-hour ahead predictions with <10% MAPE
- **Load Optimization**: Smart scheduling of appliances to reduce costs by 15%+
- **Automated Switching**: Intelligent supplier recommendations saving £150+/year
- **Real-time Monitoring**: Live price tracking and alerts

## Architecture

- **Backend**: FastAPI + Supabase + Redis + TimescaleDB
- **Frontend**: Next.js 14 + React 18 + shadcn/ui
- **ML/Data**: TensorFlow (CNN-LSTM) + Airflow + XGBoost
- **Infrastructure**: Docker + GitHub Actions + Prometheus + Grafana

## Project Status

**Current Phase**: Phase 1 - Project Initialization & Notion Setup
**Target MVP**: April 30, 2026
**Target Launch**: May 15, 2026

## Quick Start

```bash
# Clone repository
git clone <repository-url>
cd electricity-optimizer

# Set up environment
cp .env.example .env
# Edit .env with your API keys

# Start services
docker-compose up -d

# Access
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# Airflow: http://localhost:8080
# Grafana: http://localhost:3001
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [API Documentation](docs/API.md)
- [Deployment Guide](docs/DEPLOYMENT.md)
- [Development Guide](docs/DEVELOPMENT.md)

## Project Management

This project uses autonomous AI development with:
- **Notion Roadmap**: Synced every 15 minutes
- **GitHub Integration**: Automated PR creation and issue tracking
- **Swarm Coordination**: 15 concurrent AI agents across 7 specialized swarms

## License

MIT License - see [LICENSE](LICENSE) for details

---

**Built with Claude Code** 🤖
