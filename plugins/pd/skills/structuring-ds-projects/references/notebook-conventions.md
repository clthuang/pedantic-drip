# Notebook Conventions

Standards for Jupyter notebook structure, headers, and cell ordering.

## Notebook Header Template

Every notebook should start with a markdown cell containing:

```markdown
# {Descriptive Title}

**Author:** {Name/Initials}
**Date:** {YYYY-MM-DD}
**Purpose:** {One sentence describing what this notebook does}

## Setup
```

Followed by a code cell with imports and configuration:

```python
# Standard library
import os
from pathlib import Path

# Third-party
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Local
from src.project_name.data.load import load_raw_data

# Configuration
%matplotlib inline
plt.style.use("seaborn-v0_8-whitegrid")
pd.set_option("display.max_columns", 50)

# Paths
PROJECT_ROOT = Path.cwd().parent  # assumes notebook is in notebooks/
DATA_DIR = PROJECT_ROOT / "data"
```

## Cell Ordering

```
1. Header markdown         — Title, author, date, purpose
2. Imports + config        — All imports in one cell
3. Data loading            — Read data, show shape/head
4. Analysis sections       — Each with markdown header + code
5. Summary/conclusions     — Key findings in markdown
6. Next steps              — What to do next (if applicable)
```

## Markdown Standards

### Section Headers

Use markdown cells to create a narrative structure:

```markdown
## 1. Data Loading
## 2. Exploratory Analysis
### 2.1 Distribution of Target Variable
### 2.2 Correlation Analysis
## 3. Feature Engineering
## 4. Modeling
## 5. Results
## 6. Conclusions
```

### Inline Documentation

Before each non-obvious code cell, add a markdown cell explaining:
- **What** the cell does
- **Why** (the analytical reasoning)
- **Key observations** after output cells

```markdown
### Revenue Distribution by Region

We expect significant variation by region due to population differences.
Let's check if the distribution is normal or skewed.
```

## Cell Hygiene

**Do:**
- Keep cells focused — one logical operation per cell
- Show intermediate results (`df.shape`, `df.head()`, `df.describe()`)
- Use markdown cells to explain decisions
- Clear outputs before committing (or use `nbstripout`)

**Don't:**
- Have cells longer than ~30 lines (split into smaller cells)
- Leave debugging cells (`print(x)`, `display(df)`) in final version
- Have cells that depend on execution order different from top-to-bottom
- Mix different concerns in one cell (loading + processing + plotting)

## Output Discipline

```python
# At the end of a loading cell, always show:
print(f"Shape: {df.shape}")
df.head()

# At the end of a processing cell, show what changed:
print(f"Before: {n_before} rows, After: {n_after} rows ({n_before - n_after} dropped)")

# Before modeling, show feature summary:
print(f"Features: {X.shape[1]}, Samples: {X.shape[0]}")
print(f"Target distribution:\n{y.value_counts(normalize=True)}")
```

## Notebook Execution Order

Notebooks MUST be executable top-to-bottom. If restarting the kernel and running all cells produces errors, the notebook is broken.

Test with:
```bash
jupyter nbconvert --execute --to notebook notebook.ipynb
# or
papermill notebook.ipynb output.ipynb
```
