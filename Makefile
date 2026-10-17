PY ?= .venv/bin/python

.PHONY: setup demo comic serve test
setup:
	python3 -m venv .venv && $(PY) -m pip install -r requirements.txt
demo:
	$(PY) -m src.run_all
comic:
	$(PY) -m src.run_all --only comic
serve:
	$(PY) -m http.server 8000 --directory site
test:
	$(PY) -m pytest -q
