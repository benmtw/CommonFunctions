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

## Changelog Policy

- Maintain `CHANGELOG.md` for all meaningful changes.
- Update the changelog in the same branch/commit when code changes include:
  - New helpers, behavior changes, or API surface updates.
  - Dataset refreshes or source changes (for example domain list updates).
  - Dependency or configuration changes that affect runtime behavior.
- Each changelog entry should include a short summary and date.

## Package Context

- Main package path: `src/common_functions/`
- Current feature focus: email utility helpers and domain datasets.
