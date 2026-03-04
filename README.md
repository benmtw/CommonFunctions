# CommonFunctions

Reusable Python utility functions for data provider projects.

This repository starts with email-focused helpers (for example, checking whether an email looks personalized) and will grow over time with other common utility functions.

## Goals

- Keep shared logic in one place instead of duplicating it across projects.
- Provide a stable package that other repositories can install.
- Build and test all code inside a Python virtual environment.

## Planned Functionality

- `is_personalized_email(email: str) -> bool`
- `is_disposable_email(email: str) -> bool`
- `is_free_provider_email(email: str) -> bool`
- Additional common validation and normalization helpers (to be added).

## Development Rules

- All development must happen in a Python virtual environment.
- Use type hints and docstrings for public functions.
- Add tests for every new helper.

## Local Development (venv)

```powershell
# from repository root
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Run tests:

```powershell
pytest
```

## Packaging Plan

This project is intended to be installable by other repositories from GitHub.

Example install (after packaging is in place):

```powershell
pip install "git+https://github.com/<org-or-user>/CommonFunctions.git"
```

`pyproject.toml` is included, so this repository can be installed directly from GitHub.

## Suggested Project Structure

```text
CommonFunctions/
  src/
    common_functions/
      __init__.py
      email_utils.py
  tests/
    test_email_utils.py
  pyproject.toml
  README.md
```

## Useful GitHub References (Found via MCP)

- https://github.com/JoshData/python-email-validator  
  Robust Python email syntax/deliverability validation.
- https://github.com/disposable-email-domains/python-disposable-email-domains  
  Maintained disposable-domain dataset and Python access.
- https://github.com/michaelherold/pyIsEmail  
  Lightweight email validation approach.
- https://github.com/audreyfeldroy/cookiecutter-pypackage  
  Well-known Python package template.
- https://github.com/alvarobartt/python-package-template  
  Modern `pyproject.toml` + tooling template.

## Roadmap

1. Expand `email_utils.py` with additional detection rules and domain datasets.
2. Add CI (lint + tests) on pull requests.
3. Add semantic versioning and GitHub release workflow.
4. Document API changes as new helpers are added.
