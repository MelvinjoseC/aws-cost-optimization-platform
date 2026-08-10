.PHONY: help setup test lint format clean

PYTHON = python
VENV = venv
BIN = $(VENV)/Scripts

# Check if non-Windows shell
ifneq ($(OS),Windows_NT)
	PYTHON = python3
	VENV = .venv
	BIN = $(VENV)/bin
endif

help:
	@echo "AWS Cost Optimization Platform - Developer Tooling"
	@echo "=================================================="
	@echo "Commands:"
	@echo "  setup      - Create venv and install requirements"
	@echo "  test       - Run pytest unit tests"
	@echo "  lint       - Run static code checks (flake8, pylint)"
	@echo "  format     - Run code formatter (black)"
	@echo "  clean      - Remove temporary cache files"

setup:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt
	$(BIN)/pip install black pylint flake8

test:
	$(PYTHON) -m pytest -v

lint:
	$(PYTHON) -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	$(PYTHON) -m pylint --disable=C,R --errors-only src/ lambda/handler.py

format:
	$(BIN)/black src/ lambda/handler.py tests/

clean:
	@echo "Cleaning cache files..."
	@if [ -d ".pytest_cache" ]; then rm -rf .pytest_cache; fi
	@if [ -d "__pycache__" ]; then rm -rf __pycache__; fi
