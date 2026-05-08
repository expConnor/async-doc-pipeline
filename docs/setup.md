## 1. Do the setup stuff

## 2. Run alembic migrations

## Important Metrics

Latency — p99 end-to-end job completion time
Traffic — RPS at API + msgs/sec at queue
Errors — DLQ depth + 5xx rate + worker failure rate
Saturation — Queue depth growth rate + Fargate CPU + RDS connections
