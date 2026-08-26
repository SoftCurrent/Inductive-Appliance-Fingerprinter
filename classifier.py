# Data Processing
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import joblib

# Modelling
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, precision_score, recall_score, ConfusionMatrixDisplay
from sklearn.model_selection import RandomizedSearchCV, train_test_split, StratifiedKFold, cross_val_predict, RepeatedStratifiedKFold, cross_val_score
from scipy.stats import randint

# --- Load (plumbing) ---
df = pd.read_csv("data/features.csv")

y = df["label"]                                   # the answer
X = df.drop(columns=["event_id", "label"])        # the features

print(f"{len(df)} events, {X.shape[1]} features, "
      f"{y.nunique()} classes: {sorted(y.unique())}")
print(X.columns.tolist())

# Split the data into training and test sets
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42)

rf = RandomForestClassifier()
rf.fit(X_train, y_train)

cv = StratifiedKFold(n_splits=7, shuffle=True, random_state=42)

y_pred = cross_val_predict(rf, X, y, cv=cv)
cm = confusion_matrix(y, y_pred)
ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=sorted(y.unique())).plot();
plt.show()


# rkf = RepeatedStratifiedKFold(n_splits=7, n_repeats=15, random_state=42)
# scores = cross_val_score(rf, X, y, cv=rkf)
# print(f"Mean accuracy: {scores.mean():.1%}")
# print(f"Std dev:       {scores.std():.1%}")
# print(f"Range:         {scores.min():.1%} to {scores.max():.1%}")