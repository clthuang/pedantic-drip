# Data Science Notebook Code Quality Assessment

## Cell 1: Imports

```python
from pandas import *
from numpy import *
from sklearn import *
import matplotlib.pyplot as plt
```

Anti-pattern: Global wildcard imports from pandas, numpy, and sklearn pollute namespace, hide dependencies, and make debugging difficult.

## Cell 2-6: Feature Engineering Functions

```python
def load_data(path):
    return pd.read_csv(path)

def engineer_features(df):
    df['feature_a'] = df['col1'] * df['col2']
    df['feature_b'] = df['col3'] / df['col4']
    return df

def scale_data(X):
    return (X - X.mean()) / X.std()

def train_model(X, y):
    model = RandomForestClassifier(n_estimators=100)
    model.fit(X, y)
    return model

def evaluate(model, X, y):
    return model.score(X, y)
```

Anti-pattern: None of these five functions include docstrings. Function purposes, parameters, and return types are not documented.

## Cell 7: Data Loading

```python
data = load_data("/Users/john/data/train.csv")
features = engineer_features(data)
```

Anti-pattern: Hardcoded file path ("/Users/john/data/train.csv") makes code non-portable and breaks on other machines.

## Cell 8: Correct Pattern - Train/Test Split

```python
from sklearn.model_selection import train_test_split

X_train, X_test, y_train, y_test = train_test_split(
    features.drop('target', axis=1),
    features['target'],
    test_size=0.2,
    random_state=42
)
```

Correct: Proper train/test split with fixed random_state ensures reproducibility.

## Cell 9: Correct Pattern - Feature Scaling

```python
from sklearn.preprocessing import StandardScaler

scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)  # Note: transform only, no fit!
```

Correct: Feature scaling is fitted only on training data and applied (transform-only) to test data, preventing data leakage.
