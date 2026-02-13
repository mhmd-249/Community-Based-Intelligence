# CBI AWS Deployment & Production Monitoring Plan

> Practical, interview-ready guide for deploying the CBI system to AWS as a Senior AI Engineer.

---

## 1. Production Architecture

```
                         ┌──────────────────────────────────────────────────────────────────┐
                         │                        AWS Cloud (eu-east-1)                      │
                         │                                                                   │
  Telegram Bot API       │  ┌─────────────┐    ┌──────────────────────────────────────────┐  │
  ───────────────────────┼─►│    ALB       │    │              VPC                         │  │
                         │  │ (HTTPS:443)  │    │                                          │  │
  Health Officers        │  │              │    │  ┌─────────────────────────────────────┐ │  │
  (Dashboard)            │  │ Path-based   │    │  │     Private Subnets (2 AZs)         │ │  │
  ───────────────────────┼─►│ routing:     │    │  │                                     │ │  │
                         │  │              │    │  │  ┌───────────┐  ┌────────────────┐  │ │  │
                         │  │ /api/*       │───────►│ ECS Fargate│  │  ECS Fargate   │  │ │  │
                         │  │ /webhook/*   │    │  │  │    API    │  │    Worker(s)   │  │ │  │
                         │  │ /ws/*        │    │  │  │  (2 tasks)│  │  (2-4 tasks)   │  │ │  │
                         │  │              │    │  │  └─────┬─────┘  └───────┬────────┘  │ │  │
                         │  │ /*           │    │  │        │                │            │ │  │
                         │  │ (dashboard)  │    │  │        ▼                ▼            │ │  │
                         │  └──────┬───────┘    │  │  ┌──────────┐  ┌──────────────┐     │ │  │
                         │         │            │  │  │   RDS    │  │ ElastiCache  │     │ │  │
                         │         ▼            │  │  │ PostgreSQL│  │   Redis      │     │ │  │
                         │  ┌─────────────┐    │  │  │ + PostGIS │  │  (cluster)   │     │ │  │
                         │  │ CloudFront  │    │  │  │ Multi-AZ  │  │  Multi-AZ    │     │ │  │
                         │  │    CDN      │    │  │  └──────────┘  └──────────────┘     │ │  │
                         │  │ (dashboard  │    │  │                                     │ │  │
                         │  │  static)    │    │  └─────────────────────────────────────┘ │  │
                         │  └─────────────┘    │                                          │  │
                         │                      └──────────────────────────────────────────┘  │
                         │                                                                   │
                         │  ┌──────────────┐  ┌──────────┐  ┌────────────┐  ┌────────────┐  │
                         │  │  CloudWatch  │  │   ECR    │  │  Secrets   │  │    S3      │  │
                         │  │  (logs +     │  │ (images) │  │  Manager   │  │ (exports,  │  │
                         │  │   metrics)   │  │          │  │            │  │  backups)  │  │
                         │  └──────────────┘  └──────────┘  └────────────┘  └────────────┘  │
                         └──────────────────────────────────────────────────────────────────┘
```

### Why This Architecture (Interview-Ready Justification)

| Decision | Why | Alternative Rejected |
|----------|-----|---------------------|
| **ECS Fargate** over EC2 | No server management, pay-per-task, auto-scaling built in. For a small team deploying an AI app, managing EC2 instances is overhead with no benefit. | EC2 (patching burden), EKS (Kubernetes complexity overkill for 3 services) |
| **ALB** over API Gateway | WebSocket support (for real-time dashboard), path-based routing, cheaper at sustained traffic. API Gateway charges per-request which gets expensive with WebSocket connections. | API Gateway (no native WebSocket for REST APIs, per-request pricing) |
| **RDS Multi-AZ** over self-managed | Automated failover, backups, patching. PostGIS is available on RDS PostgreSQL. Health surveillance data cannot be lost — Multi-AZ gives us RPO ≈ 0. | Aurora Serverless (PostGIS support is limited), self-managed (operational burden) |
| **ElastiCache Redis** over self-managed | Managed failover, persistence, monitoring. Our system uses Redis for three critical functions (state, queue, pub/sub) — can't afford Redis downtime. | MemoryDB (more expensive, we don't need 11ms durability), self-managed Redis on EC2 |
| **CloudFront** for dashboard | Next.js static assets served from edge, API calls proxied to ALB. Reduces latency for officers across Sudan. | Serving directly from ALB (higher latency, all traffic hits origin) |
| **Secrets Manager** over env vars | Rotatable secrets, audit trail, no secrets in task definitions. Required for ANTHROPIC_API_KEY, JWT_SECRET, DB credentials. | SSM Parameter Store (cheaper but no auto-rotation), plain env vars (security risk) |
| **Region: eu-east-1 or me-south-1** | Closest AWS regions to Sudan. me-south-1 (Bahrain) gives lowest latency but limited services. eu-east-1 gives full service availability. | us-east-1 (high latency to Sudan, ~200ms vs ~50ms) |

---

## 2. Infrastructure as Code (Terraform)

### Project Structure

```
infra/
├── environments/
│   ├── staging/
│   │   └── terraform.tfvars
│   └── production/
│       └── terraform.tfvars
├── modules/
│   ├── networking/        # VPC, subnets, security groups
│   ├── database/          # RDS PostgreSQL + PostGIS
│   ├── cache/             # ElastiCache Redis
│   ├── ecs/               # Cluster, services, task definitions
│   ├── loadbalancer/      # ALB, target groups, listeners
│   ├── monitoring/        # CloudWatch dashboards, alarms
│   └── secrets/           # Secrets Manager resources
├── main.tf
├── variables.tf
└── outputs.tf
```

### Key Terraform Resources (What Interviewers Expect You to Know)

#### ECS Task Definition for API

```hcl
resource "aws_ecs_task_definition" "api" {
  family                   = "cbi-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512        # 0.5 vCPU
  memory                   = 1024       # 1 GB
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name  = "api"
    image = "${aws_ecr_repository.cbi.repository_url}:${var.api_image_tag}"

    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]

    # Secrets from AWS Secrets Manager — not env vars
    secrets = [
      { name = "DATABASE_URL",      valueFrom = "${aws_secretsmanager_secret.db_url.arn}" },
      { name = "REDIS_URL",         valueFrom = "${aws_secretsmanager_secret.redis_url.arn}" },
      { name = "ANTHROPIC_API_KEY", valueFrom = "${aws_secretsmanager_secret.anthropic.arn}" },
      { name = "JWT_SECRET",        valueFrom = "${aws_secretsmanager_secret.jwt.arn}" },
      { name = "ENCRYPTION_KEY",    valueFrom = "${aws_secretsmanager_secret.encryption.arn}" },
      { name = "PHONE_HASH_SALT",   valueFrom = "${aws_secretsmanager_secret.phone_salt.arn}" },
    ]

    environment = [
      { name = "ENVIRONMENT", value = "production" },
      { name = "LOG_FORMAT",  value = "json" },
    ]

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/ecs/cbi-api"
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "api"
      }
    }
  }])
}
```

#### ECS Task Definition for Worker

```hcl
resource "aws_ecs_task_definition" "worker" {
  family                   = "cbi-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256        # 0.25 vCPU (mostly waiting on LLM)
  memory                   = 512        # 0.5 GB
  # ... same secrets as API ...

  container_definitions = jsonencode([{
    name    = "worker"
    image   = "${aws_ecr_repository.cbi.repository_url}:${var.worker_image_tag}"
    command = ["python", "-m", "cbi.workers.main"]

    # Worker health check on port 8081
    healthCheck = {
      command = ["CMD-SHELL", "curl -f http://localhost:8081/health || exit 1"]
      interval = 30
      timeout  = 10
      retries  = 3
    }
  }])
}
```

**Interview point — why is the Worker 0.25 vCPU?**
> "The worker is I/O-bound, not CPU-bound. It spends 90% of its time waiting on LLM API calls (~3 seconds) and database writes. It doesn't need compute — it needs network. 0.25 vCPU with async Python handles this perfectly. If we need more throughput, we add more worker tasks, not bigger tasks."

#### Auto-Scaling for Workers

```hcl
resource "aws_appautoscaling_target" "worker" {
  max_capacity       = 8
  min_capacity       = 2
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.worker.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

# Scale based on Redis Stream queue depth
resource "aws_appautoscaling_policy" "worker_queue_depth" {
  name               = "worker-queue-depth"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.worker.resource_id
  scalable_dimension = aws_appautoscaling_target.worker.scalable_dimension
  service_namespace  = aws_appautoscaling_target.worker.service_namespace

  target_tracking_scaling_policy_configuration {
    target_value = 50  # Target: 50 pending messages per worker
    
    customized_metric_specification {
      metric_name = "PendingMessages"
      namespace   = "CBI/Worker"
      statistic   = "Average"
    }

    scale_in_cooldown  = 300   # Wait 5 min before scaling in
    scale_out_cooldown = 60    # Scale out quickly (1 min)
  }
}
```

**Interview point — why scale on queue depth, not CPU?**
> "Worker CPU will always be low because it's I/O-bound. CPU-based auto-scaling would never trigger. The real bottleneck is the Redis Stream queue depth — if messages are piling up, we need more workers to consume them. I publish a custom CloudWatch metric from each worker that reports pending message count, and scale on that."

#### RDS with PostGIS

```hcl
resource "aws_db_instance" "main" {
  identifier           = "cbi-production"
  engine               = "postgres"
  engine_version       = "15.4"
  instance_class       = "db.t3.medium"     # 2 vCPU, 4 GB RAM
  allocated_storage    = 50                  # GB
  max_allocated_storage = 200                # Auto-scale storage

  db_name  = "cbi"
  username = "cbi_admin"
  password = random_password.db.result       # Stored in Secrets Manager

  # High availability
  multi_az               = true
  backup_retention_period = 14               # 14-day backup window
  backup_window          = "03:00-04:00"     # 3 AM UTC (5 AM Sudan time)
  
  # Security
  storage_encrypted      = true
  vpc_security_group_ids = [aws_security_group.db.id]
  db_subnet_group_name   = aws_db_subnet_group.private.name
  publicly_accessible    = false

  # Performance
  performance_insights_enabled = true        # Free on t3.medium
  monitoring_interval          = 60          # Enhanced monitoring

  # PostGIS — installed via parameter group + init script
  parameter_group_name = aws_db_parameter_group.postgres15.name
}
```

**PostGIS on RDS**: You can't run `CREATE EXTENSION postgis` without the `rds_superuser` role. Use a Lambda-backed custom resource or an init script that runs after RDS is available:

```sql
-- Run as rds_superuser during initial setup
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

#### Security Groups (Network Segmentation)

```hcl
# ALB: Accepts HTTPS from anywhere
resource "aws_security_group" "alb" {
  ingress { from_port = 443; to_port = 443; protocol = "tcp"; cidr_blocks = ["0.0.0.0/0"] }
}

# API: Only from ALB
resource "aws_security_group" "api" {
  ingress { from_port = 8000; to_port = 8000; protocol = "tcp"
            security_groups = [aws_security_group.alb.id] }
}

# Worker: No inbound (pulls from Redis, doesn't receive traffic)
# Exception: health check port 8081 from VPC CIDR for ECS health checks
resource "aws_security_group" "worker" {
  ingress { from_port = 8081; to_port = 8081; protocol = "tcp"
            cidr_blocks = [var.vpc_cidr] }
}

# RDS: Only from API + Worker
resource "aws_security_group" "db" {
  ingress { from_port = 5432; to_port = 5432; protocol = "tcp"
            security_groups = [aws_security_group.api.id, aws_security_group.worker.id] }
}

# Redis: Only from API + Worker
resource "aws_security_group" "redis" {
  ingress { from_port = 6379; to_port = 6379; protocol = "tcp"
            security_groups = [aws_security_group.api.id, aws_security_group.worker.id] }
}
```

**Interview point — "Why can't the worker have no inbound at all?"**
> "ECS Fargate health checks need to reach the worker's health server on port 8081. Without this, ECS can't determine if the worker is healthy and will keep replacing tasks. I restrict it to VPC CIDR so only internal health checks can reach it."

---

## 3. CI/CD Pipeline (GitHub Actions)

```yaml
# .github/workflows/deploy.yml
name: Deploy CBI

on:
  push:
    branches: [main]           # Production deploy
  pull_request:
    branches: [main]           # Test + build only

env:
  AWS_REGION: eu-east-1
  ECR_REPOSITORY: cbi
  ECS_CLUSTER: cbi-production

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: kartoza/postgis:15-3.3
        env:
          POSTGRES_DB: cbi_test
          POSTGRES_USER: cbi_test
          POSTGRES_PASSWORD: test
        ports: ['5432:5432']
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7-alpine
        ports: ['6379:6379']

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install ".[dev]"

      - name: Run unit tests
        run: pytest tests/unit/ -v --tb=short

      - name: Run agent tests (mocked LLM)
        run: pytest tests/agents/ -v --tb=short

      - name: Run integration tests (real DB)
        env:
          DATABASE_URL: postgresql+asyncpg://cbi_test:test@localhost:5432/cbi_test
          REDIS_URL: redis://localhost:6379/1
          # Test-only secrets
          JWT_SECRET: ${{ secrets.TEST_JWT_SECRET }}
          ANTHROPIC_API_KEY: "test-key-not-real"
          ENCRYPTION_KEY: ${{ secrets.TEST_ENCRYPTION_KEY }}
          PHONE_HASH_SALT: "test-salt"
        run: pytest tests/integration/ -v --tb=short

      - name: Lint
        run: |
          ruff check cbi/
          ruff format --check cbi/

  build-and-push:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to ECR
        id: ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push
        env:
          ECR_REGISTRY: ${{ steps.ecr.outputs.registry }}
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build --target runtime -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG .
          docker build --target runtime -t $ECR_REGISTRY/$ECR_REPOSITORY:latest .
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:latest

  deploy:
    needs: build-and-push
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: [api, worker]

    steps:
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Deploy to ECS
        run: |
          aws ecs update-service \
            --cluster ${{ env.ECS_CLUSTER }} \
            --service cbi-${{ matrix.service }} \
            --force-new-deployment \
            --wait
```

### Deployment Strategy: Rolling Update

```hcl
resource "aws_ecs_service" "api" {
  deployment_configuration {
    minimum_healthy_percent = 100   # Keep all old tasks running
    maximum_percent         = 200   # Start new tasks alongside old ones
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true    # Auto-rollback if new tasks fail health checks
  }
}
```

**Interview point — why rolling update over blue/green?**
> "For this system, rolling update with circuit breaker is the right balance. Blue/green requires maintaining two full environments, which doubles cost during deployment. With `minimum_healthy_percent = 100`, we never have fewer tasks than desired — ECS launches new tasks first, verifies health checks pass, then drains old tasks. The circuit breaker automatically rolls back if the new version fails. For a health surveillance system with ~100 req/min, this gives zero-downtime deploys without the complexity of CodeDeploy blue/green."

### Database Migrations

```yaml
  migrate:
    needs: build-and-push
    runs-on: ubuntu-latest
    steps:
      - name: Run migrations via ECS RunTask
        run: |
          # Run a one-off Fargate task for migrations
          aws ecs run-task \
            --cluster ${{ env.ECS_CLUSTER }} \
            --task-definition cbi-migrate \
            --launch-type FARGATE \
            --network-configuration "awsvpcConfiguration={
              subnets=[$PRIVATE_SUBNET_1,$PRIVATE_SUBNET_2],
              securityGroups=[$API_SG]
            }" \
            --overrides '{
              "containerOverrides": [{
                "name": "migrate",
                "command": ["alembic", "upgrade", "head"]
              }]
            }'
```

**Interview point — why a separate task for migrations?**
> "Migrations should never run as part of the application startup. If you put `alembic upgrade head` in your entrypoint, you'll have multiple tasks racing to run the same migration when you scale. A separate one-off Fargate task runs migrations exactly once before the deploy. If it fails, deployment stops."

---

## 4. Production Monitoring

### Monitoring Stack

```
┌─────────────────────────────────────────────────────────────────┐
│                    CloudWatch (Central Hub)                       │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │   Metrics     │  │    Logs      │  │     Alarms           │   │
│  │              │  │              │  │                      │   │
│  │ ECS CPU/Mem  │  │ API (JSON)   │  │ LLM error rate >5%  │───┼──► SNS → PagerDuty
│  │ RDS IOPS     │  │ Worker (JSON)│  │ Queue depth >200    │   │
│  │ Redis memory │  │ LLM traces   │  │ API 5xx rate >1%    │   │
│  │ Custom:      │  │ Audit logs   │  │ DB connections >80% │   │
│  │  - LLM latency│ │              │  │ Worker crash loop   │   │
│  │  - Queue depth│ │              │  │ Redis memory >80%   │   │
│  │  - Reports/hr│  │              │  │ Report latency >30s │   │
│  │  - Parse fails│ │              │  │                      │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                CloudWatch Dashboard                       │    │
│  │  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────────────┐ │    │
│  │  │Reports │  │  LLM   │  │ Queue  │  │   System       │ │    │
│  │  │/hour   │  │latency │  │depth   │  │  health        │ │    │
│  │  │chart   │  │P50/P99 │  │gauge   │  │  overview      │ │    │
│  │  └────────┘  └────────┘  └────────┘  └────────────────┘ │    │
│  └──────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### Custom Metrics (Published from Application Code)

These are the metrics a senior engineer would instrument — not just AWS defaults.

#### Worker Metrics

```python
# cbi/workers/metrics.py
import boto3
import time

cloudwatch = boto3.client('cloudwatch')

class WorkerMetrics:
    def __init__(self, worker_id: str):
        self.worker_id = worker_id
    
    async def publish(self):
        """Publish custom metrics every 60 seconds."""
        cloudwatch.put_metric_data(
            Namespace='CBI/Worker',
            MetricData=[
                # Queue depth — drives auto-scaling
                {
                    'MetricName': 'PendingMessages',
                    'Value': await self._get_queue_depth(),
                    'Unit': 'Count',
                    'Dimensions': [{'Name': 'WorkerId', 'Value': self.worker_id}]
                },
                # LLM call latency — the critical production metric
                {
                    'MetricName': 'LLMLatencyMs',
                    'Value': self._last_llm_latency_ms,
                    'Unit': 'Milliseconds',
                    'Dimensions': [
                        {'Name': 'Agent', 'Value': 'reporter'},  # per-agent
                    ]
                },
                # JSON parse failure rate — detects LLM output degradation
                {
                    'MetricName': 'JSONParseFailures',
                    'Value': self._parse_failures_last_minute,
                    'Unit': 'Count',
                },
                # Reports completed per hour
                {
                    'MetricName': 'ReportsCompleted',
                    'Value': self._reports_completed,
                    'Unit': 'Count',
                },
                # End-to-end report latency (first message → report in DB)
                {
                    'MetricName': 'ReportE2ELatencySeconds',
                    'Value': self._last_e2e_latency,
                    'Unit': 'Seconds',
                },
            ]
        )
```

#### API Metrics Middleware

```python
# cbi/api/middleware.py
import time
from starlette.middleware.base import BaseHTTPMiddleware

class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000
        
        # Publish to CloudWatch
        cloudwatch.put_metric_data(
            Namespace='CBI/API',
            MetricData=[{
                'MetricName': 'RequestLatencyMs',
                'Value': duration_ms,
                'Dimensions': [
                    {'Name': 'Method', 'Value': request.method},
                    {'Name': 'Path', 'Value': request.url.path},
                    {'Name': 'StatusCode', 'Value': str(response.status_code)},
                ]
            }]
        )
        return response
```

#### LLM Call Tracing (Structured Logs)

```python
# cbi/agents/tracing.py
import structlog
import time

logger = structlog.get_logger()

async def traced_llm_call(client, agent_name: str, **kwargs):
    """Wrapper that logs every LLM call with structured metadata."""
    start = time.time()
    input_tokens = 0
    output_tokens = 0
    
    try:
        response = await client.messages.create(**kwargs)
        duration_ms = (time.time() - start) * 1000
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        
        logger.info("llm_call_success",
            agent=agent_name,
            model=kwargs.get("model"),
            duration_ms=round(duration_ms, 1),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=_estimate_cost(input_tokens, output_tokens),
            temperature=kwargs.get("temperature"),
        )
        return response
        
    except Exception as e:
        duration_ms = (time.time() - start) * 1000
        logger.error("llm_call_failure",
            agent=agent_name,
            error_type=type(e).__name__,
            error_message=str(e),
            duration_ms=round(duration_ms, 1),
        )
        raise

def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """Sonnet pricing: $3/M input, $15/M output."""
    return (input_tokens * 3 / 1_000_000) + (output_tokens * 15 / 1_000_000)
```

### CloudWatch Alarms (Terraform)

```hcl
# CRITICAL: LLM error rate spike
resource "aws_cloudwatch_metric_alarm" "llm_error_rate" {
  alarm_name          = "cbi-llm-error-rate-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  threshold           = 5         # 5% failure rate
  period              = 300       # 5-minute windows

  metric_name = "JSONParseFailures"
  namespace   = "CBI/Worker"
  statistic   = "Sum"

  alarm_actions = [aws_sns_topic.pagerduty.arn]

  alarm_description = <<-EOF
    LLM JSON parse failure rate exceeded 5%.
    This indicates Claude may be returning malformed responses.
    Check: prompt changes, Anthropic status page, model version changes.
  EOF
}

# CRITICAL: Message queue backing up
resource "aws_cloudwatch_metric_alarm" "queue_depth_high" {
  alarm_name          = "cbi-queue-depth-critical"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  threshold           = 500
  period              = 60

  metric_name = "PendingMessages"
  namespace   = "CBI/Worker"
  statistic   = "Maximum"

  alarm_actions = [aws_sns_topic.pagerduty.arn]

  alarm_description = <<-EOF
    Redis Stream queue depth >500 for 3 minutes.
    Workers may be crashed, rate-limited by Anthropic, or DB is slow.
    Check: ECS worker task status, Anthropic rate limits, RDS CPU.
  EOF
}

# WARNING: Report end-to-end latency too high
resource "aws_cloudwatch_metric_alarm" "report_latency" {
  alarm_name          = "cbi-report-latency-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  threshold           = 30         # 30 seconds
  period              = 300

  metric_name = "ReportE2ELatencySeconds"
  namespace   = "CBI/Worker"
  statistic   = "p95"

  alarm_actions = [aws_sns_topic.ops_team.arn]
}

# CRITICAL: API 5xx rate
resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "cbi-api-5xx-rate"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  threshold           = 10          # 10 errors in 5 minutes
  period              = 300

  metric_name = "HTTPCode_Target_5XX_Count"
  namespace   = "AWS/ApplicationELB"
  statistic   = "Sum"

  dimensions = {
    TargetGroup  = aws_lb_target_group.api.arn_suffix
    LoadBalancer = aws_lb.main.arn_suffix
  }

  alarm_actions = [aws_sns_topic.pagerduty.arn]
}

# WARNING: RDS connections approaching limit
resource "aws_cloudwatch_metric_alarm" "db_connections" {
  alarm_name          = "cbi-rds-connections-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  threshold           = 60          # t3.medium supports ~80 connections
  period              = 300

  metric_name = "DatabaseConnections"
  namespace   = "AWS/RDS"
  statistic   = "Maximum"

  alarm_actions = [aws_sns_topic.ops_team.arn]
}

# CRITICAL: Redis memory approaching limit
resource "aws_cloudwatch_metric_alarm" "redis_memory" {
  alarm_name          = "cbi-redis-memory-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  threshold           = 80          # 80% of max memory
  period              = 300

  metric_name = "DatabaseMemoryUsagePercentage"
  namespace   = "AWS/ElastiCache"
  statistic   = "Maximum"

  alarm_actions = [aws_sns_topic.ops_team.arn]
}
```

### CloudWatch Dashboard (Terraform)

```hcl
resource "aws_cloudwatch_dashboard" "cbi" {
  dashboard_name = "CBI-Production"
  dashboard_body = jsonencode({
    widgets = [
      # Row 1: Key business metrics
      { type = "metric", properties = {
          title = "Reports Created / Hour"
          metrics = [["CBI/Worker", "ReportsCompleted", { stat = "Sum", period = 3600 }]]
      }},
      { type = "metric", properties = {
          title = "Report E2E Latency (P50/P95/P99)"
          metrics = [
            ["CBI/Worker", "ReportE2ELatencySeconds", { stat = "p50" }],
            ["CBI/Worker", "ReportE2ELatencySeconds", { stat = "p95" }],
            ["CBI/Worker", "ReportE2ELatencySeconds", { stat = "p99" }],
          ]
      }},
      
      # Row 2: LLM health
      { type = "metric", properties = {
          title = "LLM Latency by Agent (P50)"
          metrics = [
            ["CBI/Worker", "LLMLatencyMs", "Agent", "reporter"],
            ["CBI/Worker", "LLMLatencyMs", "Agent", "surveillance"],
            ["CBI/Worker", "LLMLatencyMs", "Agent", "analyst"],
          ]
      }},
      { type = "metric", properties = {
          title = "JSON Parse Failures"
          metrics = [["CBI/Worker", "JSONParseFailures", { stat = "Sum", period = 300 }]]
      }},

      # Row 3: Queue + Infrastructure
      { type = "metric", properties = {
          title = "Redis Stream Queue Depth"
          metrics = [["CBI/Worker", "PendingMessages", { stat = "Maximum" }]]
      }},
      { type = "metric", properties = {
          title = "ECS Task Count"
          metrics = [
            ["AWS/ECS", "RunningTaskCount", "ServiceName", "cbi-api"],
            ["AWS/ECS", "RunningTaskCount", "ServiceName", "cbi-worker"],
          ]
      }},

      # Row 4: Database + Redis
      { type = "metric", properties = {
          title = "RDS CPU + Connections"
          metrics = [
            ["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", "cbi-production"],
            ["AWS/RDS", "DatabaseConnections", "DBInstanceIdentifier", "cbi-production"],
          ]
      }},
      { type = "metric", properties = {
          title = "Redis Memory + Connections"
          metrics = [
            ["AWS/ElastiCache", "DatabaseMemoryUsagePercentage"],
            ["AWS/ElastiCache", "CurrConnections"],
          ]
      }},
    ]
  })
}
```

### Structured Logging (CloudWatch Logs Insights)

All application logs are JSON (structlog). Here are the queries you'd actually run in production:

```
# Find all LLM failures in the last hour
fields @timestamp, agent, error_type, error_message, duration_ms
| filter @message like /llm_call_failure/
| sort @timestamp desc
| limit 50

# LLM cost analysis per day
fields @timestamp, agent, cost_usd
| filter @message like /llm_call_success/
| stats sum(cost_usd) as daily_cost by bin(1d) as day
| sort day desc

# Slowest reports (end-to-end)
fields @timestamp, conversation_id, e2e_latency_seconds
| filter @message like /report_completed/
| sort e2e_latency_seconds desc
| limit 20

# Track urgency distribution over time
fields @timestamp, urgency
| filter @message like /report_created/
| stats count(*) by urgency, bin(1d) as day

# Find conversations where JSON parsing fell back to regex
fields @timestamp, conversation_id, parse_method
| filter parse_method = "regex_fallback"
| sort @timestamp desc
```

---

## 5. Cost Estimation

### Monthly Cost Breakdown (Production)

| Service | Config | Est. Monthly Cost |
|---------|--------|-------------------|
| **ECS Fargate — API** | 2 tasks × 0.5 vCPU, 1 GB | ~$30 |
| **ECS Fargate — Worker** | 2 tasks × 0.25 vCPU, 0.5 GB | ~$15 |
| **ECS Fargate — Dashboard** | 1 task × 0.25 vCPU, 0.5 GB | ~$8 |
| **RDS PostgreSQL** | db.t3.medium, Multi-AZ, 50 GB | ~$140 |
| **ElastiCache Redis** | cache.t3.micro, Multi-AZ | ~$25 |
| **ALB** | 1 ALB + LCUs | ~$25 |
| **CloudWatch** | Logs, metrics, dashboard | ~$15 |
| **ECR** | Image storage | ~$2 |
| **Secrets Manager** | 7 secrets | ~$3 |
| **CloudFront** | Dashboard CDN | ~$5 |
| **Anthropic API** | ~2000 conversations/day × $0.01 | ~$600 |
| | **Total** | **~$870/month** |

**Interview point — what's the biggest cost?**
> "The Anthropic API at ~$600/month is 70% of the total. Everything else is infrastructure noise. To optimize, I'd look at: caching classification results for identical symptom patterns, using Haiku for the Reporter (conversation is less precision-sensitive), and batching Surveillance calls. But for a health surveillance system, $600/month for 2000 conversations/day is extraordinarily cheap compared to hiring health officers."

---

## 6. Disaster Recovery & Backup

### RPO/RTO Targets

| Component | RPO (data loss tolerance) | RTO (downtime tolerance) | Strategy |
|-----------|--------------------------|--------------------------|----------|
| **PostgreSQL** | 0 (no data loss) | <15 minutes | Multi-AZ automatic failover |
| **Redis** | 5 minutes | <5 minutes | ElastiCache Multi-AZ with AOF |
| **Application** | N/A (stateless) | <5 minutes | ECS auto-replacement |
| **LLM API** | N/A | Graceful degradation | Fallback to Haiku, queue retry |

### Backup Strategy

```hcl
# RDS automated backups (14 days)
backup_retention_period = 14

# Additional: weekly snapshots kept for 90 days
resource "aws_db_snapshot" "weekly" {
  # Triggered by EventBridge rule every Sunday 4 AM
  db_instance_identifier = aws_db_instance.main.id
  db_snapshot_identifier = "cbi-weekly-${formatdate("YYYY-MM-DD", timestamp())}"
}

# S3 bucket for report exports and conversation archives
resource "aws_s3_bucket" "backups" {
  bucket = "cbi-production-backups"

  lifecycle_rule {
    enabled = true
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
    transition {
      days          = 90
      storage_class = "GLACIER"
    }
  }
}
```

### What Happens When the LLM API Goes Down?

This is a critical interview question. Your answer:

> "The system degrades gracefully, it doesn't crash. The webhook still accepts messages and queues them in Redis Streams. Workers will retry LLM calls with exponential backoff (3 retries, 5/15/30 second delays). If all retries fail, the Surveillance Agent falls back to medium urgency with 'Manual review required.' The report still gets created and officers still get notified. Meanwhile, I have a CloudWatch alarm on LLM failure rate that pages the on-call engineer. The queue buffers messages during the outage, and workers process the backlog automatically when the API recovers."

---

## 7. Interview Questions They'll Ask

### Q: "How do you handle zero-downtime deployments?"

> "ECS rolling update with `minimum_healthy_percent = 100`. New tasks start alongside old ones, pass health checks (the /health endpoint verifies both Postgres and Redis connectivity), then ECS drains connections from old tasks. The ALB deregistration delay gives in-flight requests 30 seconds to complete. I also have a deployment circuit breaker — if the new version fails health checks 3 times, ECS automatically rolls back to the previous task definition."

### Q: "What if your Redis instance dies?"

> "ElastiCache Multi-AZ gives us automatic failover to a replica within about 60 seconds. During that window, the API returns degraded health (since the health check verifies Redis), the ALB stops sending new requests, and the workers pause consumption. Conversation state for active conversations is lost — those users will start a new conversation on their next message. This is acceptable because conversations are short-lived (average 4-5 turns) and the critical data (completed reports) is already in PostgreSQL."

### Q: "How do you manage secrets rotation?"

> "All secrets are in AWS Secrets Manager and injected into ECS tasks at startup. For database credentials, I'd use Secrets Manager's built-in RDS rotation with a Lambda function that rotates every 30 days. For the Anthropic API key, rotation is manual but the key is never in code, environment files, or task definition JSON — it's only in Secrets Manager. If I need to rotate the JWT secret, I'd deploy the new secret alongside the old one (both valid), then remove the old one after all existing tokens expire (24 hours)."

### Q: "How would you estimate infrastructure needs for 10x the current load?"

> "Currently targeting 2,000 messages/day. At 20,000 messages/day:
> - **Workers**: Scale from 2 to 8 tasks (auto-scaling handles this automatically based on queue depth)
> - **RDS**: Upgrade from t3.medium to r6g.large (more memory for PostGIS spatial queries). Add a read replica for the Analyst Agent's analytics queries.
> - **Redis**: Upgrade from t3.micro to r6g.large. Consider separating into two clusters — one for state (persistent) and one for pub/sub (ephemeral).
> - **API**: Scale from 2 to 4 tasks. Still 0.5 vCPU each since it's mostly proxying to database and Redis.
> - **Anthropic API**: Move to the higher-tier plan for increased rate limits. Implement request batching for Surveillance classifications.
> - **Estimated cost**: ~$2,500/month, dominated by the Anthropic API at ~$6,000/month."

### Q: "How do you ensure the Telegram webhook URL is correct after deployment?"

> "In local development I use ngrok. In production, the ALB has a fixed domain (e.g., `api.cbi-sudan.org`). I register the webhook URL with Telegram's Bot API during initial setup using `setWebhook`. The webhook URL doesn't change between deployments because the ALB domain is stable — only the backend tasks are replaced. I include a startup check in the API that verifies the webhook is correctly registered by calling `getWebhookInfo` and logging a warning if it doesn't match the expected URL."

### Q: "What's your approach to database migrations in production?"

> "Migrations run as a separate Fargate task before the application deploy. I use Alembic with `--sql` mode to generate and review the SQL before applying. For risky migrations (adding columns to large tables, changing indexes), I use `CREATE INDEX CONCURRENTLY` and `ALTER TABLE ... ADD COLUMN` which don't lock the table in PostgreSQL. The CI pipeline runs: (1) tests, (2) build + push image, (3) run migration task, (4) wait for success, (5) deploy new application tasks. If the migration task fails, the pipeline stops and the old application keeps running."

### Q: "You're using WebSocket for real-time. How does that work with multiple API tasks behind a load balancer?"

> "This is a real gotcha. WebSocket connections are sticky to a single task, but Redis pub/sub events could arrive at any task. My solution: every API task subscribes to the same Redis pub/sub channels. When a new notification is published to Redis, ALL API tasks receive it and forward to any WebSocket clients connected to them. So it doesn't matter which task the officer's browser is connected to — they'll get the notification. The ALB has sticky sessions enabled for WebSocket connections using the `AWSALB` cookie."
