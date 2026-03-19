# DS Dependency Management

Setup and conventions for managing Python dependencies in data science projects.

## pyproject.toml as Single Source of Truth

```toml
[project]
name = "my-ds-project"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pandas>=2.0,<3.0",
    "numpy>=1.24,<2.0",
    "scikit-learn>=1.3,<2.0",
    "matplotlib>=3.7,<4.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "hypothesis>=6.0",
    "pandera>=0.17",
    "ruff>=0.1",
    "mypy>=1.5",
]
notebooks = [
    "jupyterlab>=4.0",
    "papermill>=2.4",
    "nbval>=0.10",
]
```

## Pinning Strategy

| Dependency Type | Pin Style | Example | Rationale |
|----------------|-----------|---------|-----------|
| Core (pandas, numpy) | Major+minor range | `>=2.0,<3.0` | Avoid breaking API changes |
| ML frameworks | Major+minor range | `>=1.3,<2.0` | Model compatibility |
| Utilities (click, tqdm) | Major range | `>=8.0,<9.0` | Low risk of breakage |
| Dev tools (ruff, pytest) | Major range | `>=7.0` | Not in production |

## Lockfile for Reproducibility

### Using uv (Recommended)

```bash
# Create lockfile from pyproject.toml
uv lock

# Install from lockfile (reproducible)
uv sync

# Add a new dependency
uv add pandas

# Add a dev dependency
uv add --dev pytest
```

### Using pip-compile (Alternative)

```bash
# Generate lockfile
pip-compile pyproject.toml -o requirements.lock

# Install from lockfile
pip install -r requirements.lock

# Update a specific package
pip-compile --upgrade-package pandas pyproject.toml -o requirements.lock
```

## Environment Isolation

```bash
# Option 1: uv (fastest)
uv venv
source .venv/bin/activate
uv sync

# Option 2: venv + pip
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,notebooks]"
```

## .gitignore Essentials

```gitignore
# Environments
.venv/
*.egg-info/

# Data (track with DVC or similar, not git)
data/raw/
data/processed/
*.parquet
*.h5

# Notebook outputs
notebooks/.ipynb_checkpoints/

# Model artifacts
models/*.pkl
models/*.joblib
```

## Reproducibility Checklist

- [ ] `pyproject.toml` with pinned dependency ranges
- [ ] Lockfile committed (`uv.lock` or `requirements.lock`)
- [ ] Python version specified in `requires-python`
- [ ] Random seeds set and documented
- [ ] Data versioning strategy (DVC, git-lfs, or manual checksums)
- [ ] Environment creation documented in README
