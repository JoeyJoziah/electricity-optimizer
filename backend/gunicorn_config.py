"""
Gunicorn Configuration for Production Deployment (Free Tier Optimized)

Optimized for:
- Render.com free tier (512MB RAM, single worker)
- Low memory footprint
- Fast startup time
- Graceful degradation
"""

import multiprocessing
import os

# Worker Configuration
# For free tier: Use 1 worker to minimize memory usage
# Each worker costs ~80-120MB RAM + shared resources
workers = 1  # Single worker for free tier

# Worker class
worker_class = "uvicorn.workers.UvicornWorker"

# Timeout Configuration
# Keep connections alive to avoid cold starts
timeout = 120  # 2 minutes
keepalive = 5  # Keep-alive connections for 5 seconds
graceful_timeout = 30  # Allow 30s for graceful shutdown

# Preload app to save memory (shared code between workers)
# Not useful with single worker, but good practice for scaling
preload_app = False  # Set to False to avoid startup issues

# Max requests before worker restart (prevent memory leaks)
max_requests = 1000
max_requests_jitter = 50  # Add randomness to avoid thundering herd

# Logging
accesslog = "-"  # stdout
errorlog = "-"   # stderr
loglevel = os.getenv("LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sμs'

# Bind
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"

# Process naming
proc_name = "electricity-optimizer-api"

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL (if needed)
# keyfile = None
# certfile = None

# Server hooks
def on_starting(server):
    """Called just before the master process is initialized"""
    server.log.info("Starting Electricity Optimizer API...")
    server.log.info(f"Workers: {workers}, Timeout: {timeout}s")

def on_reload(server):
    """Called to recycle workers during a reload"""
    server.log.info("Reloading workers...")

def when_ready(server):
    """Called just after the server is started"""
    server.log.info("Server is ready. Spawning workers...")

def worker_int(worker):
    """Called when worker receives SIGINT or SIGQUIT"""
    worker.log.info("Worker received SIGINT, shutting down gracefully...")

def worker_abort(worker):
    """Called when worker receives SIGTERM"""
    worker.log.info("Worker received SIGTERM, aborting...")
