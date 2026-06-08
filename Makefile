# Kasa — root task runner. JS via pnpm workspaces, Python via uv.
.PHONY: help up down logs test gen seed deploy-testnet e2e fmt lint install

help: ## list targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## install all deps (pnpm + uv)
	pnpm install
	cd backend && uv sync

up: ## start full stack (postgres + hardhat-node + backend + worker + frontend)
	docker compose -f infra/docker-compose.yml up --build

down: ## stop stack and wipe volumes
	docker compose -f infra/docker-compose.yml down -v

logs: ## tail stack logs
	docker compose -f infra/docker-compose.yml logs -f

test: ## run every test suite
	cd contracts && pnpm test
	pnpm --filter @kasa/shared test
	cd backend && uv run pytest

gen: ## regenerate all cross-language artifacts (schema → deployments → openapi → ts client)
	pnpm gen:schema
	pnpm gen:deployments
	cd backend && uv run python scripts/export_openapi.py
	pnpm gen:api
	pnpm check:parity

seed: ## seed DB assets from the registry
	cd backend && uv run python scripts/seed_assets.py

deploy-testnet: ## deploy + verify contracts on Sepolia and Fuji
	cd contracts && pnpm hardhat run scripts/deploy.ts --network sepolia
	cd contracts && pnpm hardhat run scripts/deploy.ts --network fuji

e2e: ## end-to-end demo: register → deposit → credit → withdraw → confirmed
	./infra/e2e.sh

fmt: ## format everything
	pnpm -r format
	cd backend && uv run ruff format .

lint: ## lint everything
	pnpm -r lint
	cd backend && uv run ruff check . && uv run mypy .
