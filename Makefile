.PHONY: build demo test lint typecheck quality

build:
	docker compose build

demo:
	docker compose run --rm agent "给我生成一份关于 Pilbara 锂矿的今日简报" --mode fixture --output /app/output/pilbara-daily.md

test:
	docker compose run --rm test

lint:
	docker compose run --rm --entrypoint ruff test check .

typecheck:
	docker compose run --rm --entrypoint mypy test

quality: lint typecheck test

