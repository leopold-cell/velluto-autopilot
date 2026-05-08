.PHONY: up down dev migrate test lint fmt

up:
	docker-compose up -d

down:
	docker-compose down

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	python -m app.workers.queue

scheduler:
	python -m app.orchestrator.scheduler

migrate:
	alembic upgrade head

migrate-new:
	alembic revision --autogenerate -m "$(msg)"

migrate-down:
	alembic downgrade -1

test:
	pytest -x -v

test-cov:
	pytest --cov=app --cov-report=html

lint:
	ruff check app tests

fmt:
	ruff format app tests

install:
	poetry install

shell:
	python -c "import asyncio; from app.database import init_db; asyncio.run(init_db())"

daily-report:
	python -m app.workers.daily_report

orchestrate:
	python -c "import asyncio; from app.orchestrator.agent import Orchestrator; asyncio.run(Orchestrator().run_cycle())"
