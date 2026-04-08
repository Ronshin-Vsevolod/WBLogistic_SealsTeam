.PHONY: up down logs-ml logs-java test smoke

up:
	docker compose up --build -d

down:
	docker compose down -v

logs-ml:
	docker compose logs -f ml-service

logs-java:
	docker compose logs -f backend

test:
	pytest tests/ -v

smoke:
	docker compose -f docker-compose.python-smoke.yml up --abort-on-container-exit