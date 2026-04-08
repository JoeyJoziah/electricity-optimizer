# Product Definition

## Project Name

RateShift

## Description

AI-powered platform that finds consumers cheaper electricity rates and can automatically switch plans on their behalf. Combines real-time price tracking, utility integrations, ML forecasting, and autonomous plan switching.

## Problem Statement

Consumers overpay for electricity because they lack visibility into rate changes, cheaper alternatives, and optimal usage windows. In deregulated markets (~17 US states), better plans exist but switching is manual and confusing.

## Target Users

Residential consumers looking to reduce electricity bills, particularly in deregulated US markets where plan switching is possible.

## Key Goals

1. **Save users money** -- Surface actionable savings opportunities automatically
2. **Autonomous plan switching** -- AI agent evaluates and switches plans for Pro users (Auto Rate Switcher)
3. **Provide actionable insights** -- Every data point drives a clear recommendation
4. **Automate rate monitoring** -- Continuous tracking without manual effort
5. **Nationwide coverage** -- Support all 50 states + DC across deregulated and regulated markets
6. **ML-driven forecasting** -- Predict price trends to optimize timing decisions
7. **Seamless utility integrations** -- Connect to utility accounts with minimal friction

## Core Features (shipped)

- **Price Tracking**: Real-time electricity rates across all US states via EIA/NREL APIs
- **ML Forecasting**: Ensemble predictor with HNSW vector search and adaptive learning
- **Utility Connections**: 5 methods (UtilityAPI direct, email import, portal scrape, bill upload, manual)
- **Smart Alerts**: Price threshold alerts with dedup cooldowns, push + email delivery
- **AI Assistant**: "RateShift AI" chatbot (Gemini 3 Flash + Groq Llama fallback + Composio tools)
- **Auto Rate Switcher** (Pro): Autonomous plan switching via EnergyBot + Arcadia Arc APIs. Decision engine with 7 rules, contract lifecycle management, switch safeguards
- **Community**: Posts, voting, AI moderation, neighborhood insights
- **Multi-Utility**: Natural gas, heating oil, propane, community solar dashboards
- **Tiered Plans**: Free / $4.99 Pro / $14.99 Business with Stripe billing
- **UtilityAPI Add-On**: $2.25/meter/month for direct meter connections (all tiers)
