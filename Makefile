PYTHON ?= python3
PREFIX ?= /usr/local

.PHONY: all test build install install-dev uninstall clean

all: test

build:
	$(PYTHON) -m pip install --quiet build
	$(PYTHON) -m build

test:
	$(PYTHON) -m pytest -q

install:
	$(PYTHON) -m pip install --prefix $(PREFIX) .

install-dev:
	$(PYTHON) -m pip install -e ".[dev]"

uninstall:
	$(PYTHON) -m pip uninstall -y pty4ai

clean:
	rm -rf build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
