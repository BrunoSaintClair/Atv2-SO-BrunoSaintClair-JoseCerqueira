# Makefile para gerenciamento e execução do GenResearch-Servidor

VENV = .venv
PYTHON = $(VENV)/bin/python3
UVICORN = $(VENV)/bin/uvicorn

.PHONY: help setup run clean

PORT ?= 8001

help:
	@echo "Comandos disponíveis:"
	@echo "  make setup     - Cria ambiente virtual e instala dependências"
	@echo "  make run       - Inicia a API FastAPI (porta $(PORT))"
	@echo "  make clean     - Remove arquivos temporários e cache"

setup:
	python3 -m venv $(VENV)
	./$(VENV)/bin/pip install --upgrade pip
	./$(VENV)/bin/pip install -r requirements.txt

run:
	$(UVICORN) app.main:app --host 0.0.0.0 --port $(PORT) --reload

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
