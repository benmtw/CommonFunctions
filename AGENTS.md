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
# Agent Instructions

Fast Apply: IMPORTANT: Use `edit_file` over `str_replace` or full file writes. It works with partial code snippets—no need for full file content.

Warp Grep: warp-grep is a subagent that takes in a search string and tries to find relevant context. Best practice is to use it at the beginning of codebase explorations to fast track finding relevant files/lines. Do not use it to pin point keywords, but use it for broader semantic queries. "Find the XYZ flow", "How does XYZ work", "Where is XYZ handled?", "Where is <error message> coming from?"
