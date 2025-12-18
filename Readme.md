# Prepare
# Install FastAPI and server
pip install fastapi uvicorn

# Install OpenTelemetry core packages
pip install opentelemetry-api opentelemetry-sdk

# Install OTLP exporters
pip install opentelemetry-exporter-otlp-proto-grpc

# Install FastAPI instrumentation
pip install opentelemetry-instrumentation-fastapi

OR
pip install fastapi uvicorn opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc opentelemetry-instrumentation-fastapi

# Run
python main.py

# Test
curl http://localhost:8000/users
curl http://localhost:8000/users/1
curl -X POST http://localhost:8000/users/1/login
curl http://localhost:8000/slow


# Diagnose
# Set these before running your app

$env:OTEL_EXPORTER_OTLP_ENDPOINT="http://54.156.154.167:4318"
$env:OTEL_EXPORTER_PROTOCOL="http/proto"
# $env:OTEL_EXPORTER_OTLP_HEADERS="authorization=Bearer YOUR_TOKEN"
$env:OTEL_EXPORTER_OTLP_INSECURE="true"
$env:OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"
$env:OTEL_LOG_LEVEL="debug"
$env:OTEL_TRACES_EXPORTER="otlp"
$env:OTEL_METRICS_EXPORTER="otlp"
$env:OTEL_LOGS_EXPORTER="otlp"

# Run with Python unbuffered output
python -u main.py 2>&1 | tee otel-debug.log

# Run app with timestamp and filtered logs
python main.py 2>&1 | ts '[%Y-%m-%d %H:%M:%S]' | grep -E '(Exporting|Failed|ERROR|✓|❌|🔧)'
