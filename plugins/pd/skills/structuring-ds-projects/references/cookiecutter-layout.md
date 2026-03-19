# Cookiecutter Data Science v2 Layout

Full annotated directory tree for a data science project.

```
project-name/
│
├── README.md                 # Project overview
│                              - What problem does this solve?
│                              - How to set up the environment
│                              - How to reproduce results
│                              - Data sources and provenance
│
├── pyproject.toml            # Project metadata and dependencies
│                              - Python version requirement
│                              - Core + dev + notebook dependency groups
│                              - Build system configuration
│
├── .gitignore                # Excludes data, models, environments
│
├── .env                      # Environment variables (NOT committed)
│                              - Database credentials
│                              - API keys
│                              - Environment-specific config
│
├── data/
│   ├── raw/                  # IMMUTABLE original data
│   │   └── .gitkeep          - Downloaded or received files
│   │                          - NEVER modify these files
│   │                          - Document provenance in README
│   │
│   ├── interim/              # Intermediate data
│   │   └── .gitkeep          - Cleaned subsets
│   │                          - Joined tables before final processing
│   │                          - Can be regenerated from raw/
│   │
│   └── processed/            # Final datasets
│       └── .gitkeep          - Feature matrices ready for modeling
│                              - Aggregated tables for analysis
│                              - Can be regenerated from raw/
│
├── notebooks/                # Jupyter notebooks
│   │                          - Numbered for execution order
│   │                          - Initialed for authorship
│   │                          - Naming: {nn}.{initials}-{description}.ipynb
│   │
│   ├── 01.ab-initial-eda.ipynb
│   ├── 02.ab-feature-engineering.ipynb
│   └── 03.ab-model-training.ipynb
│
├── src/                      # Reusable Python source code
│   └── project_name/
│       ├── __init__.py
│       │
│       ├── data/             # Data loading and cleaning
│       │   ├── __init__.py
│       │   ├── load.py       - Read from various sources
│       │   └── clean.py      - Standardize, deduplicate, handle missing
│       │
│       ├── features/         # Feature engineering
│       │   ├── __init__.py
│       │   └── build.py      - Create feature matrix from cleaned data
│       │
│       ├── models/           # Model training and evaluation
│       │   ├── __init__.py
│       │   ├── train.py      - Training logic with config
│       │   └── evaluate.py   - Metrics, cross-validation, reporting
│       │
│       └── visualization/    # Plotting utilities
│           ├── __init__.py
│           └── plots.py      - Reusable chart functions
│
├── models/                   # Trained model artifacts
│                              - Serialized models (.pkl, .joblib)
│                              - Model configs and hyperparameters
│                              - NOT committed to git (too large)
│
├── reports/                  # Generated analysis output
│   └── figures/              - Charts and visualizations
│                              - Exported from notebooks or scripts
│
└── tests/                    # Automated tests
    ├── conftest.py           - Shared fixtures
    ├── test_data.py          - Data loading and cleaning tests
    ├── test_features.py      - Feature engineering tests
    └── test_models.py        - Model training and evaluation tests
```

## When to Simplify

**EDA-only projects** can skip: `src/`, `models/`, `tests/`

Minimum viable structure:
```
project-name/
├── README.md
├── pyproject.toml
├── data/raw/
├── notebooks/
└── .gitignore
```

**ML pipeline projects** add: `src/`, `models/`, `tests/`

**Full production projects** add: `Dockerfile`, `Makefile`, `docs/`, CI/CD config
