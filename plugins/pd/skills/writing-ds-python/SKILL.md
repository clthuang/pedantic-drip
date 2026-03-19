---
name: writing-ds-python
description: "Use when writing or reviewing Python code involving pandas, numpy, scikit-learn, Jupyter notebooks, or data pipelines."
---

# Writing Data Science Python

Guidance for writing clean, maintainable data science Python code. Applies software engineering discipline to notebooks, pipelines, and analysis scripts.

## Core Principles

Apply these universally — they're not DS-specific, but DS code violates them most often:

| Principle | DS Translation |
|-----------|---------------|
| **KISS** | One transform per function. One question per notebook. |
| **YAGNI** | Don't build a "framework" for your EDA. Don't generalize until the 3rd use. |
| **Readability** | Your future self is the primary reader. Name things for humans, not CPUs. |
| **Reproducibility** | Same inputs must produce same outputs. Pin versions. Set seeds. |
| **Separation of concerns** | I/O at boundaries. Pure transforms in the middle. Config separate from logic. |

## Notebooks vs Scripts Decision Tree

```
Is this exploratory / one-off analysis?
  YES → Notebook (.ipynb)
    - Follow notebook conventions (see structuring-ds-projects skill)
    - Extract reusable functions to src/ after 3+ uses
  NO → Is this a reusable pipeline or utility?
    YES → Python module (.py)
      - Full type hints, docstrings, tests
      - CLI entry point if applicable
    NO → Is this a report or presentation?
      YES → Notebook with narrative markdown
        - Clear section headers
        - Hide implementation details in imported functions
        - Output cells should tell a story
      NO → Script (.py)
        - Standalone execution
        - argparse or click for CLI
        - Logging, not print()
```

**When to extract from notebook to module:**
1. Function used in 3+ notebooks (the 3-use rule)
2. Function longer than ~20 lines
3. Function needs unit tests
4. Function is a data transform that should be idempotent

## Anti-Patterns Quick Reference

| Anti-Pattern | Symptom | Fix |
|-------------|---------|-----|
| Magic numbers | `df[df['age'] > 25]` scattered everywhere | Named constants: `MINIMUM_AGE = 25` |
| Global mutable state | `df` modified in-place across cells | Pure functions returning new DataFrames |
| Copy-paste analysis | Same 10 lines in 5 notebooks | Extract to `src/` module |
| Hardcoded paths | `pd.read_csv('/Users/me/data/file.csv')` | `pathlib.Path` + config/env vars |
| "Just one more cell" | Notebook with 100+ cells, no structure | Split into focused notebooks |
| Silent failures | `df.dropna()` without checking what was dropped | Log counts: `n_before`, `n_after`, `n_dropped` |
| Untyped functions | `def process(data):` | `def process(data: pd.DataFrame) -> pd.DataFrame:` |
| Mixed I/O and logic | `def analyze(): df = pd.read_csv(...); ...` | Separate `load_data()` from `analyze(df)` |
| Premature optimization | Vectorizing a one-time 100-row operation | Profile first. Optimize only measured bottlenecks. |
| Implicit column deps | Function assumes column names without declaring | Validate columns at function entry |

See [anti-patterns.md](references/anti-patterns.md) for extended catalog with code examples.

## Clean Pipeline Rules

### Idempotent Transforms

Every transform function must be:
- **Pure**: No side effects. No modifying input DataFrames in-place.
- **Idempotent**: Running twice produces the same result.
- **Typed**: Input and output types declared.

```python
# GOOD: Pure, idempotent, typed
def normalize_names(df: pd.DataFrame) -> pd.DataFrame:
    return df.assign(
        name=df["name"].str.strip().str.lower()
    )

# BAD: Mutates input, not idempotent
def normalize_names(df):
    df["name"] = df["name"].str.strip().str.lower()
```

### I/O at Boundaries

```
load_data() → [pure transforms] → save_results()
     ↑                                    ↑
  I/O boundary                       I/O boundary
```

- Read data once at the start
- Pass DataFrames through pure functions
- Write results once at the end
- Never mix file I/O with transformation logic

### Pipeline Composition

Chain transforms explicitly:

```python
def run_pipeline(raw: pd.DataFrame) -> pd.DataFrame:
    return (
        raw
        .pipe(validate_schema)
        .pipe(clean_missing_values)
        .pipe(normalize_names)
        .pipe(add_derived_features)
    )
```

## Type Hints Strategy

| Context | Type Hints? | Rationale |
|---------|-------------|-----------|
| Function signatures (modules) | Always | Essential for maintainability |
| Function signatures (notebooks) | Yes, for shared functions | Catches errors early |
| Ad-hoc notebook cells | Skip | Exploratory code is ephemeral |
| DataFrame schemas | Use Pandera | Runtime validation > static types |
| Return types | Always for modules | Enables IDE support |
| Complex generics | Only if clarifying | Don't over-annotate |

### DataFrame Schema Validation

Use Pandera for runtime schema validation rather than type hints alone:

```python
import pandera as pa

schema = pa.DataFrameSchema({
    "user_id": pa.Column(int, nullable=False, unique=True),
    "age": pa.Column(int, pa.Check.in_range(0, 150)),
    "email": pa.Column(str, pa.Check.str_matches(r".+@.+")),
})

validated_df = schema.validate(raw_df)
```

## Testing Strategy

| What to Test | Tool | When |
|-------------|------|------|
| Data transforms | Hypothesis (property-based) | Always for `src/` functions |
| DataFrame schemas | Pandera | At pipeline boundaries |
| Data quality | Great Expectations | For production data pipelines |
| Notebook execution | papermill / nbval | CI/CD for critical notebooks |
| Statistical properties | scipy.stats | When validating distributions |

See [testing-strategy.md](references/testing-strategy.md) for detailed examples.

**Key testing principle**: Test properties, not specific values.

```python
# GOOD: Property test — output always has same length as input
@given(df=dataframes(columns=[column("x", dtype=float)]))
def test_normalize_preserves_length(df):
    result = normalize(df)
    assert len(result) == len(df)

# BAD: Brittle value test
def test_normalize():
    assert normalize(pd.DataFrame({"x": [1, 2, 3]})).equals(
        pd.DataFrame({"x": [0.0, 0.5, 1.0]})
    )
```

## Docstring Format

Use NumPy style for all documented functions:

```python
def compute_metrics(
    df: pd.DataFrame,
    target_col: str,
    prediction_col: str,
) -> dict[str, float]:
    """Compute classification metrics for model evaluation.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing target and prediction columns.
    target_col : str
        Name of the ground truth column.
    prediction_col : str
        Name of the model prediction column.

    Returns
    -------
    dict[str, float]
        Dictionary with keys: 'accuracy', 'precision', 'recall', 'f1'.

    Raises
    ------
    ValueError
        If target or prediction columns are missing from df.
    """
```

## Import Ordering

```python
# Standard library
import json
import logging
from pathlib import Path

# Third-party: data
import numpy as np
import pandas as pd

# Third-party: ML
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

# Third-party: visualization
import matplotlib.pyplot as plt
import seaborn as sns

# Local
from src.features import build_features
from src.models import train_model
```

Group by purpose, not just stdlib/third-party/local. Separate data, ML, and visualization imports for clarity.

## Logging, Not Print

```python
import logging

logger = logging.getLogger(__name__)

# In modules: use logging
logger.info("Loaded %d rows from %s", len(df), filepath)
logger.warning("Dropped %d rows with missing target", n_dropped)

# In notebooks: print() is acceptable for EDA output
# But structured logging is preferred for anything reusable
```

## Dependency Management

- Use `pyproject.toml` as the single source of truth
- Pin major+minor versions: `pandas>=2.0,<3.0`
- Use `uv` or `pip-compile` for reproducible lockfiles
- Separate dev dependencies from production

See [dependency-management.md](references/dependency-management.md) for full setup guide.

## Random Seeds and Reproducibility

```python
import numpy as np

RANDOM_SEED = 42

# Set globally at script/notebook start
np.random.seed(RANDOM_SEED)

# Pass explicitly to functions that need randomness
train_df, test_df = train_test_split(df, random_state=RANDOM_SEED)
model = RandomForestClassifier(random_state=RANDOM_SEED)
```

**Rules:**
- Define seed as a named constant, not a magic number
- Pass `random_state` explicitly to every function that accepts it
- Document any non-deterministic steps (e.g., GPU training order)
- Set seeds at the top of notebooks/scripts, not buried in code
