"""
FastAPI application with OpenTelemetry instrumentation
Exports metrics, logs, and traces to OTEL Collector
"""

import os
import sys

# Fix Unicode encoding for Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Enable OTEL debug logging BEFORE importing OTEL packages
os.environ["OTEL_LOG_LEVEL"] = "debug"
os.environ["OTEL_PYTHON_LOG_LEVEL"] = "debug"

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import logging
import time
import random

# Configure logging to see OTEL internal logs
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Enable gRPC debug logging
# os.environ["GRPC_VERBOSITY"] = "DEBUG"
# os.environ["GRPC_TRACE"] = "all"

# OpenTelemetry imports
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from dotenv import load_dotenv
from typing import Dict

load_dotenv()

# Protocol selection for OTLP exporters (grpc or http/proto)
# Controlled via OTEL_EXPORTER_PROTOCOL environment variable.
# Supported values: "grpc" (default) or "http/proto" (or "http").
OTEL_EXPORTER_PROTOCOL = os.getenv("OTEL_EXPORTER_PROTOCOL", "http").lower()

# Choose sensible default endpoints depending on protocol unless user set one
default_endpoint = "http://localhost:4317" if OTEL_EXPORTER_PROTOCOL == "grpc" else "http://localhost:4318"
OTEL_COLLECTOR_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", default_endpoint)
OTEL_HEADERS = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")  # For auth tokens

print(f"[CONFIG] Protocol: {OTEL_EXPORTER_PROTOCOL}")
print(f"[CONFIG] Connecting to: {OTEL_COLLECTOR_ENDPOINT}")
if OTEL_HEADERS:
    print(f"[AUTH] Using authentication headers")
else:
    print(f"[WARN] No authentication headers set")

# Dynamically import the appropriate OTLP exporters based on protocol
OTLPSpanExporter = None
OTLPMetricExporter = None
OTLPLogExporter = None
if OTEL_EXPORTER_PROTOCOL in ("http/proto", "http"):
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        print("[OK] Using OTLP HTTP/proto exporters")
    except Exception as e:
        print(f"[ERROR] Failed to import HTTP/proto exporters: {e}")
        import traceback
        traceback.print_exc()
        # Fallback to grpc imports below
        OTEL_EXPORTER_PROTOCOL = "grpc"

if OTEL_EXPORTER_PROTOCOL == "grpc":
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
        print("[OK] Using OTLP gRPC exporters")
    except Exception as e:
        print(f"[ERROR] Failed to import gRPC exporters: {e}")
        import traceback
        traceback.print_exc()

# Instrumentation
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
# OTEL Collector endpoint (change to your cloud collector)
# OTEL_COLLECTOR_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
# OTEL_HEADERS = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")  # For auth tokens

print(f"[CONFIG] Connecting to: {OTEL_COLLECTOR_ENDPOINT}")
if OTEL_HEADERS:
    print(f"[AUTH] Using authentication headers")
else:
    print(f"[WARN] No authentication headers set")

# Create resource with service information
resource = Resource.create({
    "service.name": "fastapi-demo-service",
    "service.version": "1.0.0",
    "deployment.environment": "development"
})

# ===== TRACES SETUP =====
print("\n[TRACES] Setting up TRACES exporter...")
try:
    # Parse headers if provided
    headers = None
    if OTEL_HEADERS:
        headers = dict(item.split("=") for item in OTEL_HEADERS.split(","))
    
    trace_provider = TracerProvider(resource=resource)
    # Instantiate span exporter depending on protocol
    if OTEL_EXPORTER_PROTOCOL == "grpc":
        otlp_span_exporter = OTLPSpanExporter(
            endpoint=OTEL_COLLECTOR_ENDPOINT,
            insecure=True,  # Set to False for TLS
            headers=headers
        )
    else:
        otlp_span_exporter = OTLPSpanExporter(
            endpoint=OTEL_COLLECTOR_ENDPOINT+ "/v1/traces",
            headers=headers            
        )
    trace_provider.add_span_processor(BatchSpanProcessor(otlp_span_exporter))
    trace.set_tracer_provider(trace_provider)
    tracer = trace.get_tracer(__name__)
    
    print(f"[OK] Trace exporter configured: {OTEL_COLLECTOR_ENDPOINT}")
    print(f"[OK] Service name: {resource.attributes.get('service.name')}")
except Exception as e:
    print(f"[ERROR] TRACES setup failed: {e}")
    import traceback
    traceback.print_exc()

# ===== METRICS SETUP =====
print("\n[METRICS] Setting up METRICS exporter...")
try:
    headers = None
    if OTEL_HEADERS:
        headers = dict(item.split("=") for item in OTEL_HEADERS.split(","))
    
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(
            endpoint=OTEL_COLLECTOR_ENDPOINT + ("/v1/metrics" if OTEL_EXPORTER_PROTOCOL != "grpc" else ""),
            **({"insecure": True} if OTEL_EXPORTER_PROTOCOL == "grpc" else {}),
            headers=headers
        ),
        export_interval_millis=5000
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)
    meter = metrics.get_meter(__name__)
    
    print(f"[OK] Metrics exporter configured with 5s interval")
except Exception as e:
    print(f"[ERROR] METRICS setup failed: {e}")
    import traceback
    traceback.print_exc()

# Create custom metrics
request_counter = meter.create_counter(
    name="api_requests_total",
    description="Total number of API requests",
    unit="1"
)

processing_time_histogram = meter.create_histogram(
    name="request_processing_time",
    description="Request processing time in seconds",
    unit="s"
)

active_users_gauge = meter.create_up_down_counter(
    name="active_users",
    description="Number of active users",
    unit="1"
)

# ===== LOGS SETUP =====
print("\n[LOGS] Setting up LOGS exporter...")
try:
    headers = None
    if OTEL_HEADERS:
        headers = dict(item.split("=") for item in OTEL_HEADERS.split(","))
    
    logger_provider = LoggerProvider(resource=resource)
    set_logger_provider(logger_provider)
    otlp_log_exporter = OTLPLogExporter(
        endpoint=OTEL_COLLECTOR_ENDPOINT + ("/v1/logs" if OTEL_EXPORTER_PROTOCOL != "grpc" else ""),
        **({"insecure": True} if OTEL_EXPORTER_PROTOCOL == "grpc" else {}),
        headers=headers
    )
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(otlp_log_exporter))
    
    print(f"[OK] Logs exporter configured")
except Exception as e:
    print(f"[ERROR] LOGS setup failed: {e}")
    import traceback
    traceback.print_exc()

# Configure Python logging to use OTEL
handler = LoggingHandler(level=logging.DEBUG, logger_provider=logger_provider)
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.DEBUG)

# Create application logger
logger = logging.getLogger(__name__)


# Helper to extract current trace/span ids and return as attributes for correlation
def _get_trace_span_attrs() -> Dict[str, str]:
    try:
        span = trace.get_current_span()
        # Non-recording span may still have a span context
        ctx = getattr(span, "get_span_context", lambda: None)()
        if not ctx:
            return {}
        # trace_id and span_id are ints; format as hex with proper zero-padding
        trace_id = getattr(ctx, "trace_id", None)
        span_id = getattr(ctx, "span_id", None)
        if not trace_id:
            return {}
        trace_hex = format(trace_id, "032x")
        span_hex = format(span_id, "016x") if span_id is not None else ""
        return {"trace_id": trace_hex, "span_id": span_hex}
    except Exception:
        return {}


# Logging filter to inject trace/span ids into LogRecord so logs correlate with traces
class OTelContextFilter(logging.Filter):
    def filter(self, record):
        try:
            ids = _get_trace_span_attrs()
            # Ensure attributes exist on the record for formatters/exporters
            record.trace_id = ids.get("trace_id", "")
            record.span_id = ids.get("span_id", "")
        except Exception:
            record.trace_id = ""
            record.span_id = ""
        return True


# Attach the filter to the root logger and the OTEL logging handler so OTEL log exporter sees the ids
otel_filter = OTelContextFilter()
logging.getLogger().addFilter(otel_filter)
handler.addFilter(otel_filter)

print("=" * 60)
print("[SUCCESS] OpenTelemetry Configuration Complete")
print(f"Endpoint: {OTEL_COLLECTOR_ENDPOINT}")
print(f"Service: {resource.attributes.get('service.name')}")
print("=" * 60)
print("\n[STARTING] FastAPI application...")
print("Watch for export logs below:\n")

# ===== FASTAPI APP =====
app = FastAPI(title="OTEL Demo API", version="1.0.0")

# Instrument FastAPI
FastAPIInstrumentor.instrument_app(app)

# Sample data
users_db = {
    1: {"id": 1, "name": "Alice", "email": "alice@example.com"},
    2: {"id": 2, "name": "Bob", "email": "bob@example.com"},
    3: {"id": 3, "name": "Charlie", "email": "charlie@example.com"}
}

@app.get("/")
async def root():
    """Root endpoint with basic logging"""
    logger.info("Root endpoint accessed")
    request_counter.add(1, {**{"endpoint": "/", "method": "GET"}, **_get_trace_span_attrs()})
    return {"message": "Hello from OTEL instrumented FastAPI!", "status": "healthy"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    logger.debug("Health check performed")
    request_counter.add(1, {**{"endpoint": "/health", "method": "GET"}, **_get_trace_span_attrs()})
    return {"status": "healthy", "timestamp": time.time()}

@app.get("/users")
async def get_users():
    """Get all users with custom span"""
    start_time = time.time()
    
    with tracer.start_as_current_span("get_users_operation") as span:
        logger.info("Fetching all users from database")
        span.set_attribute("user.count", len(users_db))
        
        # Simulate some processing
        time.sleep(random.uniform(0.01, 0.05))
        
        logger.info(f"Successfully retrieved {len(users_db)} users")
        request_counter.add(1, {**{"endpoint": "/users", "method": "GET"}, **_get_trace_span_attrs()})

        processing_time = time.time() - start_time
        processing_time_histogram.record(processing_time, {**{"endpoint": "/users"}, **_get_trace_span_attrs()})
        
        return {"users": list(users_db.values()), "count": len(users_db)}

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    """Get specific user with detailed logging"""
    start_time = time.time()
    
    with tracer.start_as_current_span("get_user_by_id") as span:
        span.set_attribute("user.id", user_id)
        logger.info(f"Fetching user with ID: {user_id}")
        
        if user_id not in users_db:
            logger.warning(f"User not found: {user_id}")
            span.set_attribute("error", True)
            span.add_event("User not found", {"user.id": user_id})
            raise HTTPException(status_code=404, detail="User not found")
        
        # Simulate database query
        time.sleep(random.uniform(0.01, 0.03))
        
        user = users_db[user_id]
        logger.info(f"Successfully retrieved user: {user['name']}")
        span.set_attribute("user.name", user["name"])
        
        request_counter.add(1, {**{"endpoint": "/users/{id}", "method": "GET", "status": "success"}, **_get_trace_span_attrs()})

        processing_time = time.time() - start_time
        processing_time_histogram.record(processing_time, {**{"endpoint": "/users/{id}"}, **_get_trace_span_attrs()})
        
        return user

@app.post("/users/{user_id}/login")
async def user_login(user_id: int):
    """Simulate user login with metrics"""
    with tracer.start_as_current_span("user_login") as span:
        span.set_attribute("user.id", user_id)
        logger.info(f"User login attempt: {user_id}")
        
        if user_id not in users_db:
            logger.error(f"Login failed - user not found: {user_id}")
            request_counter.add(1, {**{"endpoint": "/users/{id}/login", "method": "POST", "status": "failed"}, **_get_trace_span_attrs()})
            raise HTTPException(status_code=404, detail="User not found")
        
        # Simulate login processing
        time.sleep(random.uniform(0.02, 0.06))
        
        active_users_gauge.add(1, {**{"status": "logged_in"}, **_get_trace_span_attrs()})
        logger.info(f"User {users_db[user_id]['name']} logged in successfully")
        
        request_counter.add(1, {**{"endpoint": "/users/{id}/login", "method": "POST", "status": "success"}, **_get_trace_span_attrs()})
        
        return {"message": "Login successful", "user": users_db[user_id]}

@app.post("/users/{user_id}/logout")
async def user_logout(user_id: int):
    """Simulate user logout"""
    with tracer.start_as_current_span("user_logout") as span:
        span.set_attribute("user.id", user_id)
        logger.info(f"User logout: {user_id}")
        
        active_users_gauge.add(-1, {**{"status": "logged_out"}, **_get_trace_span_attrs()})
        
        request_counter.add(1, {**{"endpoint": "/users/{id}/logout", "method": "POST", "status": "success"}, **_get_trace_span_attrs()})
        
        return {"message": "Logout successful"}

@app.get("/error")
async def trigger_error():
    """Endpoint to test error logging and tracing"""
    with tracer.start_as_current_span("error_endpoint") as span:
        logger.error("Intentional error triggered for testing")
        span.set_attribute("error", True)
        span.add_event("Error triggered intentionally")
        
        request_counter.add(1, {**{"endpoint": "/error", "method": "GET", "status": "error"}, **_get_trace_span_attrs()})
        
        raise HTTPException(status_code=500, detail="This is a test error")

@app.get("/slow")
async def slow_endpoint():
    """Simulate a slow endpoint"""
    start_time = time.time()
    
    with tracer.start_as_current_span("slow_operation") as span:
        logger.warning("Slow endpoint called - this will take 2-3 seconds")
        
        # Simulate slow processing
        delay = random.uniform(2, 3)
        span.set_attribute("delay.seconds", delay)
        time.sleep(delay)
        
        logger.info("Slow operation completed")
        
        processing_time = time.time() - start_time
        processing_time_histogram.record(processing_time, {**{"endpoint": "/slow"}, **_get_trace_span_attrs()})
        request_counter.add(1, {**{"endpoint": "/slow", "method": "GET"}, **_get_trace_span_attrs()})
        
        return {"message": "Slow operation completed", "duration_seconds": delay}

@app.get("/test-export")
async def test_export():
    """Force export of telemetry data and check connection"""
    print("\n" + "="*60)
    print("[TEST] MANUAL EXPORT TEST")
    print("="*60)
    
    results = {"status": "testing", "results": {}}
    
    # Test trace export
    print("\n[1/3] Testing TRACES export...")
    try:
        with tracer.start_as_current_span("test_span") as span:
            span.set_attribute("test.type", "manual_export")
            span.set_attribute("test.timestamp", time.time())
            span.add_event("Manual test event")
        
        flush_result = trace_provider.force_flush(timeout_millis=10000)
        results["results"]["traces"] = "success" if flush_result else "timeout"
        print(f"   [OK] Traces flush: {results['results']['traces']}")
    except Exception as e:
        results["results"]["traces"] = f"error: {str(e)}"
        print(f"   [ERROR] Traces error: {e}")
    
    # Test metrics export
    print("\n[2/3] Testing METRICS export...")
    try:
        request_counter.add(1, {**{"test": "manual_export"}, **_get_trace_span_attrs()})
        flush_result = meter_provider.force_flush(timeout_millis=10000)
        results["results"]["metrics"] = "success" if flush_result else "timeout"
        print(f"   [OK] Metrics flush: {results['results']['metrics']}")
    except Exception as e:
        results["results"]["metrics"] = f"error: {str(e)}"
        print(f"   [ERROR] Metrics error: {e}")
    
    # Test logs export
    print("\n[3/3] Testing LOGS export...")
    try:
        logger.info("Manual test log message", extra={"test.manual": True})
        flush_result = logger_provider.force_flush(timeout_millis=10000)
        results["results"]["logs"] = "success" if flush_result else "timeout"
        print(f"   [OK] Logs flush: {results['results']['logs']}")
    except Exception as e:
        results["results"]["logs"] = f"error: {str(e)}"
        print(f"   [ERROR] Logs error: {e}")
    
    print("\n" + "="*60)
    print("Check your cloud collector dashboard for data")
    print("="*60 + "\n")
    
    return results

@app.get("/connection-status")
async def connection_status():
    """Check connection configuration"""
    return {
        "endpoint": OTEL_COLLECTOR_ENDPOINT,
        "service_name": resource.attributes.get('service.name'),
        "has_headers": bool(OTEL_HEADERS),
        "exporters": {
            "traces": "configured",
            "metrics": "configured",
            "logs": "configured"
        },
        "note": "Call /test-export to force a data export"
    }

@app.get("/metrics")
async def get_metrics_info():
    """Endpoint to get information about available metrics"""
    logger.debug("Metrics info endpoint accessed")
    return {
        "metrics": [
            "api_requests_total - Counter for total API requests",
            "request_processing_time - Histogram of request processing times",
            "active_users - Gauge for active user count"
        ],
        "note": "Metrics are exported to OTEL Collector"
    }

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting FastAPI application with OTEL instrumentation")
    uvicorn.run(app, host="0.0.0.0", port=8000)
    