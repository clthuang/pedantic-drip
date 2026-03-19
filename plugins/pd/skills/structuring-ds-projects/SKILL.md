---
name: structuring-ds-projects
description: "Use when creating a new data science project, organizing notebooks and data files, or deciding where code belongs in a DS project."
---

# Structuring Data Science Projects

Conventions for organizing data science projects based on Cookiecutter Data Science v2. Apply these when scaffolding new projects or reorganizing existing ones.

## Directory Layout

Use the Cookiecutter Data Science v2 structure as the starting point. See [cookiecutter-layout.md](references/cookiecutter-layout.md) for the full annotated directory tree.

```
project-name/
├── README.md              # Project overview, setup, usage
├── pyproject.toml         # Dependencies and project metadata
├── .gitignore             # Standard DS gitignore
├── data/
│   ├── raw/               # IMMUTABLE original data
│   ├── interim/           # Intermediate transforms
│   └── processed/         # Final analysis-ready datasets
├── notebooks/             # Jupyter notebooks (numbered + initialed)
├── src/                   # Reusable Python modules
│   └── project_name/
│       ├── __init__.py
│       ├── data/          # Data loading and cleaning
│       ├── features/      # Feature engineering
│       ├── models/        # Model training and evaluation
│       └── visualization/ # Plotting utilities
├── models/                # Trained model artifacts
├── reports/               # Generated analysis reports
│   └── figures/           # Generated graphics
└── tests/                 # Unit and property tests
```

## Data Immutability

**`data/raw/` is sacred. Never modify raw data files.**

| Directory | Purpose | Mutability |
|-----------|---------|------------|
| `data/raw/` | Original source data | IMMUTABLE — never edit, overwrite, or delete |
| `data/interim/` | Intermediate processing steps | Reproducible — can be regenerated |
| `data/processed/` | Final, analysis-ready data | Reproducible — can be regenerated |

**Rules:**
- Raw data goes in `data/raw/` and is never modified
- All transforms are code, not manual edits to data files
- If raw data is too large for git, use DVC, git-lfs, or document the download process
- Add `data/raw/` contents to `.gitignore` if sensitive or large; document provenance in README

## Notebook Naming Convention

```
{number}.{initials}-{description}.ipynb
```

**Examples:**
- `01.ab-initial-eda.ipynb`
- `02.ab-feature-engineering.ipynb`
- `03.cd-model-comparison.ipynb`
- `04.ab-final-analysis.ipynb`

**Rules:**
- Two-digit prefix for ordering
- Author initials for attribution
- Lowercase, hyphenated description
- Notebooks must execute sequentially (01 before 02 before 03)

See [notebook-conventions.md](references/notebook-conventions.md) for header template and cell ordering.

## The 3-Use Rule

```
Used in 1 notebook → Keep in the notebook
Used in 2 notebooks → Consider extracting
Used in 3+ notebooks → MUST extract to src/
```

**Where to extract:**

| Function Type | Destination |
|--------------|-------------|
| Data loading/cleaning | `src/project_name/data/` |
| Feature engineering | `src/project_name/features/` |
| Model training/evaluation | `src/project_name/models/` |
| Plotting helpers | `src/project_name/visualization/` |

## src/ Module Structure

```python
# src/project_name/data/load.py
def load_raw_sales(data_dir: Path) -> pd.DataFrame:
    """Load raw sales data from CSV."""
    ...

# src/project_name/features/build.py
def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build feature matrix from cleaned data."""
    ...

# src/project_name/models/train.py
def train_model(X: pd.DataFrame, y: pd.Series, params: dict) -> BaseEstimator:
    """Train model with given parameters."""
    ...
```

**Import from notebooks:**
```python
from src.project_name.data.load import load_raw_sales
from src.project_name.features.build import build_features
```

## Config Management

### Use pathlib for All Paths

```python
from pathlib import Path

# Derive paths relative to project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # from src/pkg/module.py
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MODELS_DIR = PROJECT_ROOT / "models"
```

### No Hardcoded Paths

```python
# BAD
df = pd.read_csv("/Users/alice/projects/sales/data/raw/sales.csv")

# GOOD
df = pd.read_csv(RAW_DIR / "sales.csv")
```

### Secrets via Environment Variables

```python
# .env (never committed)
DATABASE_URL=postgresql://user:pass@host/db
API_KEY=sk-...

# Python
import os
from dotenv import load_dotenv

load_dotenv()
db_url = os.environ["DATABASE_URL"]
```

## Scope Tiers

Not every project needs the full structure. Scale the scaffold to the project scope:

| Scope | What You Need | What You Skip |
|-------|--------------|---------------|
| **EDA only** | `notebooks/`, `data/raw/`, README, pyproject.toml | `src/`, `models/`, `tests/` |
| **ML pipeline** | All of EDA + `src/`, `models/`, `tests/` | — |
| **Full project** | Everything + CI/CD, Docker, docs/ | — |

## .gitignore Essentials

```gitignore
# Python
__pycache__/
*.py[cod]
.venv/
*.egg-info/

# Data
data/raw/*
data/interim/*
data/processed/*
!data/raw/.gitkeep
!data/interim/.gitkeep
!data/processed/.gitkeep

# Notebooks
.ipynb_checkpoints/

# Models
models/*.pkl
models/*.joblib
models/*.h5

# Environment
.env

# IDE
.vscode/
.idea/
```
