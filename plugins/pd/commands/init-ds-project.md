---
description: Scaffold a new data science project with Cookiecutter v2 structure
argument-hint: <project name>
---

# Init DS Project Command

Load the project structuring skill and scaffold a new data science project.

## Get Project Name

If $ARGUMENTS is provided, use it as the project name.

If $ARGUMENTS is empty, ask: "What would you like to name your data science project?"

Sanitize the name:
- Lowercase
- Replace spaces/special chars with hyphens
- Validate: must be a valid directory name

## Load Skill

Read the project structuring skill: Glob `~/.claude/plugins/cache/*/pd*/*/skills/structuring-ds-projects/SKILL.md` — read first match.
Fallback: Read `plugins/pd/skills/structuring-ds-projects/SKILL.md` (dev workspace).
If not found: proceed with general DS project conventions.

## Ask Scope

```
AskUserQuestion:
  questions: [{
    "question": "What scope does this project need?",
    "header": "Project Scope",
    "options": [
      {"label": "EDA only", "description": "Notebooks + data + README (minimal structure for exploration)"},
      {"label": "ML pipeline", "description": "EDA + src/ modules + models/ + tests/ (standard ML project)"},
      {"label": "Full project", "description": "Everything + CI/CD ready structure (production-grade)"}
    ],
    "multiSelect": false
  }]
```

## Scaffold Structure

Based on scope selection, create the directory structure:

### EDA Only
```
{project-name}/
├── README.md
├── pyproject.toml
├── .gitignore
├── data/
│   ├── raw/.gitkeep
│   ├── interim/.gitkeep
│   └── processed/.gitkeep
└── notebooks/
    └── 01.xx-initial-eda.ipynb
```

### ML Pipeline (adds to EDA)
```
{project-name}/
├── ... (EDA files)
├── src/
│   └── {project_name}/
│       ├── __init__.py
│       ├── data/
│       │   └── __init__.py
│       ├── features/
│       │   └── __init__.py
│       ├── models/
│       │   └── __init__.py
│       └── visualization/
│           └── __init__.py
├── models/.gitkeep
└── tests/
    └── conftest.py
```

### Full Project (adds to ML Pipeline)
```
{project-name}/
├── ... (ML Pipeline files)
├── reports/
│   └── figures/.gitkeep
└── Makefile
```

## Create Starter Files

### README.md
```markdown
# {Project Name}

## Overview

{Brief description — to be filled in}

## Setup

```bash
# Create environment
uv venv
source .venv/bin/activate
uv sync
```

## Data

Describe data sources and how to obtain raw data.

## Project Structure

{Include annotated tree matching selected scope}
```

### pyproject.toml
Generate with matching dependencies for selected scope:
- **EDA only:** pandas, numpy, matplotlib, seaborn, jupyterlab
- **ML pipeline:** EDA + scikit-learn, pytest, hypothesis, pandera, ruff
- **Full project:** ML pipeline + papermill, great-expectations

### .gitignore
Use the standard DS .gitignore from the structuring skill.

### Initial Notebook (01.xx-initial-eda.ipynb)
Create with the header template from notebook-conventions.md:
- Title cell
- Imports + config cell
- Data loading section
- Empty EDA section

### conftest.py (ML pipeline and Full only)
```python
import pytest
import pandas as pd

@pytest.fixture
def sample_data():
    """Minimal sample DataFrame for testing."""
    return pd.DataFrame({
        "id": [1, 2, 3],
    })
```

## On Completion

Display:
```
Project scaffolded at: {project-name}/

Next steps:
1. cd {project-name}
2. Add raw data to data/raw/
3. Start exploring in notebooks/01.xx-initial-eda.ipynb
```

If ML pipeline or Full scope, also show:
```
4. Extract reusable code to src/{project_name}/
5. Run tests: pytest tests/
```
