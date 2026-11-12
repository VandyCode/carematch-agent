.PHONY: install dev test eval sanitize docker-build clean

PYTHON ?= python3
PORT ?= 8000

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m pip install -e .

dev:
	$(PYTHON) -m uvicorn app.fast_api_app:app --host 0.0.0.0 --port $(PORT) --reload

test:
	$(PYTHON) -m pytest tests/unit tests/integration -v

eval:
	$(PYTHON) tests/eval/eval_harness.py

sanitize:
	$(PYTHON) -m pytest tests/unit/test_rubric_95.py -k "sanitization" -v

docker-build:
	docker build -t carematch-agent:latest .

clean:
	rm -rf __pycache__ .pytest_cache .ruff_cache build dist *.egg-info *.db
