VENV_BIN := .venv/bin

.PHONY: format format-check

# --exit-zero: some issues (e.g. whitespace inside docstrings) are only fixed by
# `ruff format`, so let it run before the final check reports what is left.
format:
	$(VENV_BIN)/ruff check --fix --exit-zero --silent .
	$(VENV_BIN)/ruff format .
	$(VENV_BIN)/ruff check .

format-check:
	$(VENV_BIN)/ruff check .
	$(VENV_BIN)/ruff format --check .
