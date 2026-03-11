.PHONY: all db-up db-migrate dev dev-backend dev-frontend test

all: dev

db-up:
	docker compose up -d postgres redis

db-migrate:
	bash -c "source .venv/bin/activate && alembic upgrade head"

dev-backend:
	bash -c "source .venv/bin/activate && uvicorn --factory hadron.controller.app:create_app --reload"

dev-frontend:
	cd frontend && npm run dev

dev: db-up db-migrate
	@echo "Starting backend and frontend..."
	@if command -v concurrently > /dev/null; then \
		concurrently -n backend,frontend -c blue,green "make dev-backend" "make dev-frontend"; \
	else \
		echo "concurrently not found. Falling back to simple background jobs."; \
		make dev-backend & make dev-frontend & wait; \
	fi

test:
	bash -c "source .venv/bin/activate && pytest tests/ -v"
