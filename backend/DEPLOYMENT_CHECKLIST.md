# Deployment Checklist - Free Tier Optimizations

## Pre-Deployment

- [ ] Review changes in `main.py`
- [ ] Review changes in `config/database.py`
- [ ] Test locally with production settings:
  ```bash
  export ENVIRONMENT=production
  python main.py
  ```
- [ ] Verify all endpoints respond:
  - [ ] `GET /health` - Basic health
  - [ ] `GET /health/live` - Liveness check
  - [ ] `GET /health/ready` - Readiness check (tests DB connections)
  - [ ] `GET /` - Root endpoint

## Render.com Configuration

### 1. Build Settings

- [ ] **Build Command**: `pip install -r requirements.prod.txt`
- [ ] **Start Command**: `./start.sh` OR `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1 --no-access-log --timeout-keep-alive 5 --limit-concurrency 50`

### 2. Environment Variables (Required)

- [ ] `ENVIRONMENT=production`
- [ ] `DATABASE_URL=postgresql://...` (or `TIMESCALEDB_URL`)
- [ ] `JWT_SECRET=<strong-random-secret>`

### 3. Environment Variables (Recommended)

- [ ] `REDIS_URL=redis://...` (for caching - Upstash free tier works)
- [ ] `CORS_ORIGINS=https://yourapp.onrender.com,https://yourdomain.com`

### 4. Environment Variables (Optional)

- [ ] `SENTRY_DSN=https://...` (skip to save 15MB RAM)

### 5. Health Check Configuration

- [ ] **Health Check Path**: `/health/live`
- [ ] **Health Check Interval**: 60 seconds
- [ ] **Health Check Timeout**: 5 seconds

## Post-Deployment Verification

### 1. Basic Connectivity

- [ ] Service is running: `curl https://your-app.onrender.com/health`
- [ ] Returns 200 status code
- [ ] Response includes version and environment

### 2. Database Connectivity

- [ ] Check ready endpoint: `curl https://your-app.onrender.com/health/ready`
- [ ] Verify all database checks pass (redis, timescaledb, neon postgresql)

### 3. Performance Metrics

- [ ] Check startup time in logs (should be <2s)
- [ ] Check memory usage in Render dashboard (should be <150MB)
- [ ] Check response times:
  ```bash
  curl -w "@curl-format.txt" -s https://your-app.onrender.com/health
  ```
  Create `curl-format.txt`:
  ```
  time_namelookup:  %{time_namelookup}s\n
  time_connect:  %{time_connect}s\n
  time_appconnect:  %{time_appconnect}s\n
  time_pretransfer:  %{time_pretransfer}s\n
  time_redirect:  %{time_redirect}s\n
  time_starttransfer:  %{time_starttransfer}s\n
  time_total:  %{time_total}s\n
  ```

### 4. Feature Testing

- [ ] Test API endpoints:
  - [ ] `POST /api/v1/ml/predict/price` - Price predictions
  - [ ] `POST /api/v1/ml/predict/optimal-times` - Optimal scheduling
  - [ ] `GET /api/v1/prices` - Price data
  - [ ] `POST /api/v1/auth/register` - User registration
  - [ ] `POST /api/v1/auth/login` - User login

### 5. Security

- [ ] CORS headers present: `curl -I https://your-app.onrender.com/health`
- [ ] Security headers present:
  - [ ] `X-Frame-Options: DENY`
  - [ ] `X-Content-Type-Options: nosniff`
  - [ ] `X-XSS-Protection: 1; mode=block`
  - [ ] `Content-Security-Policy: ...`
  - [ ] `Strict-Transport-Security: ...` (production only)

### 6. Monitoring

- [ ] Prometheus metrics accessible: `curl https://your-app.onrender.com/metrics`
- [ ] Logs visible in Render dashboard
- [ ] (Optional) Sentry receiving errors if configured

### 7. Load Testing (Optional)

- [ ] Run basic load test:
  ```bash
  # Install hey: brew install hey (macOS) or equivalent
  hey -n 100 -c 10 https://your-app.onrender.com/health
  ```
- [ ] Verify no errors under load
- [ ] Check memory doesn't spike above 400MB

## Rollback Plan

If issues occur:

1. **Quick rollback**: Revert to previous deployment in Render dashboard
2. **Check logs**: Review Render logs for errors
3. **Common issues**:
   - **OOM (Out of Memory)**: Reduce pool sizes further or disable Sentry
   - **Slow startup**: Check database connectivity, ensure migrations are done
   - **Connection errors**: Verify DATABASE_URL and REDIS_URL are correct

## Performance Budget Verification

After 24 hours of operation:

- [ ] Average memory usage < 200MB
- [ ] P50 response time < 100ms
- [ ] P95 response time < 500ms
- [ ] No 5xx errors (except expected ones)
- [ ] CPU usage < 50% average

## Optimization Success Criteria

✅ **Startup time**: < 2 seconds
✅ **Memory usage**: < 150MB baseline
✅ **Response time**: < 100ms p50
✅ **No OOM errors**: 24+ hours uptime
✅ **All features working**: No regressions

## Troubleshooting

### High Memory Usage
1. Check if Sentry is enabled (adds ~15MB)
2. Reduce database pool sizes further
3. Check for memory leaks in custom code
4. Review `/metrics` for connection counts

### Slow Responses
1. Check database query times
2. Verify Redis is connected (caching enabled)
3. Check for N+1 queries
4. Review `/metrics` for request duration

### Connection Timeouts
1. Verify DATABASE_URL is correct
2. Check database server is accessible
3. Increase `pool_timeout` if needed
4. Check firewall rules

### Startup Failures
1. Check environment variables are set
2. Verify `start.sh` has execute permissions
3. Check database migrations are complete
4. Review build logs for missing dependencies

## Support

- **Documentation**: See `PERFORMANCE_OPTIMIZATIONS.md`
- **Logs**: Render.com dashboard → Logs tab
- **Metrics**: `https://your-app.onrender.com/metrics`
- **Health**: `https://your-app.onrender.com/health/ready`

---

**Last Updated**: 2026-02-07
**Optimized For**: Render.com Free Tier (512MB RAM)
