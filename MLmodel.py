import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
import joblib

# change filename if needed
df = pd.read_csv("India Map Solar Irradiance Dataset.csv")

df['Month'] = df['Month'].str.strip().str.capitalize()

X = df[['State','District','Month']]
y = df['Insolation (in kWh/m²)'].astype(float)

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

cat_cols = ['State','District','Month']
# Fixed: Changed 'sparse=False' to 'sparse_output=False'
pre = ColumnTransformer([("cat", OneHotEncoder(handle_unknown='ignore', sparse_output=False), cat_cols)])
pipe = Pipeline([("pre", pre), ("model", RandomForestRegressor(n_estimators=200, random_state=42, n_jobs=-1))])

print("Training...")
pipe.fit(X_train, y_train)
preds = pipe.predict(X_test)
print("MAE:", mean_absolute_error(y_test, preds))
print("R2:", r2_score(y_test, preds))

joblib.dump(pipe, "solar_irradiance_pipeline_local.pkl")
print("Saved model -> solar_irradiance_pipeline_local.pkl")