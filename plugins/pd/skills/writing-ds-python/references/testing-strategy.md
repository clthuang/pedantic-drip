# DS Testing Strategy

Testing approaches for data science code: property-based tests, schema validation, and data quality checks.

## Hypothesis (Property-Based Testing)

Use for data transform functions where properties hold for any valid input.

### Common Properties for DS Transforms

```python
from hypothesis import given, settings
from hypothesis.extra.pandas import columns, column, data_frames

# Property: Output length equals input length (no rows lost/gained)
@given(df=data_frames(columns=[column("x", dtype=float)]))
def test_transform_preserves_length(df):
    result = my_transform(df)
    assert len(result) == len(df)

# Property: Output columns are a superset of input columns
@given(df=data_frames(columns=[column("a", dtype=float), column("b", dtype=float)]))
def test_adds_columns_not_removes(df):
    result = add_features(df)
    assert set(df.columns).issubset(set(result.columns))

# Property: Idempotency — applying twice gives same result
@given(df=data_frames(columns=[column("name", dtype=str)]))
def test_normalize_is_idempotent(df):
    once = normalize_names(df)
    twice = normalize_names(once)
    pd.testing.assert_frame_equal(once, twice)

# Property: Monotonicity — sorted input stays sorted
@given(df=data_frames(columns=[column("date", dtype="datetime64[ns]")]))
@settings(max_examples=50)
def test_sorted_dates_stay_sorted(df):
    df = df.sort_values("date")
    result = process_timeseries(df)
    assert result["date"].is_monotonic_increasing
```

### Custom Strategies for Domain Data

```python
from hypothesis import strategies as st

# Strategy for valid age values
valid_ages = st.integers(min_value=0, max_value=150)

# Strategy for valid email-like strings
valid_emails = st.from_regex(r"[a-z]{3,10}@[a-z]{3,10}\.[a-z]{2,4}", fullmatch=True)

# Strategy for currency amounts
currency_amounts = st.decimals(min_value=0, max_value=1_000_000, places=2)
```

## Pandera (Schema Validation)

Use at pipeline boundaries to validate DataFrame structure and content.

```python
import pandera as pa
from pandera import Column, Check, DataFrameSchema

# Define schema
raw_data_schema = DataFrameSchema({
    "user_id": Column(int, Check.greater_than(0), nullable=False, unique=True),
    "age": Column(int, Check.in_range(0, 150), nullable=True),
    "email": Column(str, Check.str_matches(r".+@.+\..+"), nullable=False),
    "signup_date": Column("datetime64[ns]", nullable=False),
    "revenue": Column(float, Check.greater_than_or_equal_to(0), nullable=True),
})

# Validate at pipeline entry
def load_and_validate(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["signup_date"])
    return raw_data_schema.validate(df)
```

### Schema as Documentation

```python
# Output schema documents what your pipeline produces
output_schema = DataFrameSchema({
    "user_id": Column(int, nullable=False, unique=True),
    "cohort": Column(str, Check.isin(["new", "returning", "churned"])),
    "lifetime_value": Column(float, Check.greater_than_or_equal_to(0)),
    "risk_score": Column(float, Check.in_range(0.0, 1.0)),
})

def run_pipeline(raw: pd.DataFrame) -> pd.DataFrame:
    result = (
        raw
        .pipe(clean)
        .pipe(compute_cohorts)
        .pipe(compute_ltv)
        .pipe(compute_risk)
    )
    return output_schema.validate(result)
```

## Great Expectations (Production Data Quality)

Use for production data pipelines where data quality needs monitoring.

```python
import great_expectations as gx

context = gx.get_context()

# Define expectations
validator = context.sources.pandas_default.read_dataframe(df)
validator.expect_column_values_to_not_be_null("user_id")
validator.expect_column_values_to_be_between("age", min_value=0, max_value=150)
validator.expect_column_distinct_values_to_be_in_set("status", ["active", "inactive", "suspended"])
validator.expect_column_mean_to_be_between("revenue", min_value=0, max_value=100_000)

# Run validation
results = validator.validate()
```

## Notebook Testing with papermill

```python
# Run notebook programmatically and check for errors
import papermill as pm

pm.execute_notebook(
    "notebooks/01-eda.ipynb",
    "notebooks/output/01-eda-tested.ipynb",
    parameters={"data_path": "tests/fixtures/sample_data.csv"},
)
```

## Test Fixtures for DS Code

```python
import pytest
import pandas as pd

@pytest.fixture
def sample_users():
    """Minimal valid user DataFrame for testing."""
    return pd.DataFrame({
        "user_id": [1, 2, 3],
        "age": [25, 30, 45],
        "email": ["a@b.com", "c@d.com", "e@f.com"],
        "revenue": [100.0, 250.0, 0.0],
    })

@pytest.fixture
def sample_users_with_nulls(sample_users):
    """User DataFrame with realistic missing data."""
    df = sample_users.copy()
    df.loc[1, "age"] = None
    df.loc[2, "email"] = None
    return df
```
