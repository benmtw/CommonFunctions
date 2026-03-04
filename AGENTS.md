# AGENTS.md

Instructions for AI coding agents working in this repository.

## Scope

- This file is for agent workflow and contribution behavior.
- User-facing package documentation belongs in `README.md`.

## Required Workflow

- Do all development inside a Python virtual environment.
- Prefer editable install for local development:
  - `python -m pip install -e ".[dev]"`
- Run tests before committing:
  - `pytest`

## Code Standards

- Add type hints for public functions.
- Add concise docstrings for public functions.
- Add or update tests for every new helper or behavior change.

## Package Context

- Main package path: `src/common_functions/`
- Current feature focus: email utility helpers and domain datasets.
