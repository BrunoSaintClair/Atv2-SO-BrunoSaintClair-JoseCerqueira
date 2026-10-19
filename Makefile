# Makefile para gerenciamento e execução do GenResearch-Servidor

VENV = .venv
PYTHON = $(VENV)/bin/python3
UVICORN = $(VENV)/bin/uvicorn

.PHONY: help setup run test test-concurrency test-queue test-race-condition clean

PORT ?= 8001

help:
	@echo "Comandos disponíveis:"
	@echo "  make setup                - Cria ambiente virtual e instala dependências"
	@echo "  make run                  - Inicia a API FastAPI (porta $(PORT))"
	@echo "  make test                 - Executa todos os testes automatizados da API"
	@echo "  make test-race-condition  - Executa Experimento D (Condição de Corrida vs Lock)"
	@echo "  make test-concurrency     - Testa concorrência (2 produtores, 2 workers e cache LRU)"
	@echo "  make test-queue           - Testa saturação de fila cheia (HTTP 503) e escala de workers"
	@echo "  make clean                - Remove arquivos temporários e cache"

setup:
	python3 -m venv $(VENV)
	./$(VENV)/bin/pip install --upgrade pip
	./$(VENV)/bin/pip install -r requirements.txt

run:
	$(UVICORN) app.main:app --host 0.0.0.0 --port $(PORT) --reload

test-race-condition:
	@echo "==> Executando Experimento D (Condição de Corrida vs Sincronização)..."
	PYTHONPATH=. $(PYTHON) scripts/test_race_condition.py

test-experiments:
	@echo "==> Executando Experimentos Acadêmicos C1 a C6..."
	PYTHONPATH=. $(PYTHON) scripts/run_all_c_experiments.py

test-concurrency:
	@echo "==> Executando teste de concorrência e cache LRU..."
	PYTHONPATH=. $(PYTHON) scripts/test_concurrency_and_cache.py

test-queue:
	@echo "==> Executando teste de saturação de fila e escala de workers..."
	PYTHONPATH=. $(PYTHON) scripts/test_queue_full_and_scaling.py

test: test-race-condition test-concurrency test-queue test-experiments
	@echo "==> Todos os testes e experimentos foram concluídos com sucesso!"

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
