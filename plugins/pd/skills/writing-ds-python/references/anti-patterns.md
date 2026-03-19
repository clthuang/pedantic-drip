# DS Python Anti-Patterns

Extended catalog of common anti-patterns in data science Python code with before/after examples.

## 1. Magic Numbers in Filters

```python
# BAD
df = df[df["revenue"] > 10000]
df = df[df["age"].between(18, 65)]

# GOOD
MIN_REVENUE_THRESHOLD = 10_000
WORKING_AGE_MIN = 18
WORKING_AGE_MAX = 65

df = df[df["revenue"] > MIN_REVENUE_THRESHOLD]
df = df[df["age"].between(WORKING_AGE_MIN, WORKING_AGE_MAX)]
```

## 2. In-Place DataFrame Mutation

```python
# BAD: Mutates original, breaks idempotency
def clean(df):
    df.dropna(inplace=True)
    df["name"] = df["name"].str.lower()
    df.reset_index(inplace=True, drop=True)

# GOOD: Returns new DataFrame, original untouched
def clean(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df
        .dropna()
        .assign(name=lambda x: x["name"].str.lower())
        .reset_index(drop=True)
    )
```

## 3. Hardcoded File Paths

```python
# BAD
df = pd.read_csv("/Users/alice/project/data/sales.csv")

# GOOD
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "raw"

df = pd.read_csv(DATA_DIR / "sales.csv")
```

## 4. Silent Data Loss

```python
# BAD: No idea what was dropped or how much
df = df.dropna()
df = df.drop_duplicates()

# GOOD: Log what happened
n_before = len(df)
df = df.dropna(subset=["target_column"])
n_after = len(df)
logger.info("Dropped %d rows with missing target (%d -> %d)", n_before - n_after, n_before, n_after)
```

## 5. Chained Indexing

```python
# BAD: SettingWithCopyWarning, unreliable
df[df["status"] == "active"]["score"] = 100

# GOOD: Use .loc for assignment
df.loc[df["status"] == "active", "score"] = 100
```

## 6. Mixed Concerns in One Function

```python
# BAD: I/O + transform + visualization in one function
def analyze_sales(filepath):
    df = pd.read_csv(filepath)
    df["margin"] = df["revenue"] - df["cost"]
    df.groupby("region")["margin"].mean().plot(kind="bar")
    plt.savefig("output.png")

# GOOD: Separate concerns
def load_sales(filepath: Path) -> pd.DataFrame:
    return pd.read_csv(filepath)

def compute_margins(df: pd.DataFrame) -> pd.DataFrame:
    return df.assign(margin=df["revenue"] - df["cost"])

def plot_margins_by_region(df: pd.DataFrame, output_path: Path) -> None:
    df.groupby("region")["margin"].mean().plot(kind="bar")
    plt.savefig(output_path)
```

## 7. Implicit Column Dependencies

```python
# BAD: Assumes columns exist without validation
def compute_features(df):
    df["bmi"] = df["weight"] / (df["height"] ** 2)
    return df

# GOOD: Validate at entry
REQUIRED_COLUMNS = {"weight", "height"}

def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    return df.assign(bmi=df["weight"] / (df["height"] ** 2))
```

## 8. Leaking Test Data into Training

```python
# BAD: Fit scaler on full dataset before splitting
scaler = StandardScaler()
df[features] = scaler.fit_transform(df[features])
train, test = train_test_split(df)

# GOOD: Fit only on training data
train, test = train_test_split(df)
scaler = StandardScaler()
train[features] = scaler.fit_transform(train[features])
test[features] = scaler.transform(test[features])  # transform only
```

## 9. Uncontrolled Randomness

```python
# BAD: Results change every run
sample = df.sample(frac=0.1)
model = RandomForestClassifier()

# GOOD: Explicit seeds
SEED = 42
sample = df.sample(frac=0.1, random_state=SEED)
model = RandomForestClassifier(random_state=SEED)
```

## 10. Ignoring Memory with Large DataFrames

```python
# BAD: Loading everything into memory at once
df = pd.read_csv("huge_file.csv")

# GOOD: Use appropriate dtypes and chunking
dtypes = {"user_id": "int32", "category": "category", "amount": "float32"}
df = pd.read_csv("huge_file.csv", dtype=dtypes, usecols=["user_id", "category", "amount"])

# Or process in chunks
for chunk in pd.read_csv("huge_file.csv", chunksize=100_000):
    process(chunk)
```
