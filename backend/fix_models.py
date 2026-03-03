import joblib
import os

models = ["fraud_isomodel.pkl", "return_fraud_rfmodel.pkl", "category_encoder.pkl","return_fraud_model_trained.pkl"]

for m in models:
    path = f"models/{m}"
    if os.path.exists(path):
        data = joblib.load(path)
        joblib.dump(data, path) 
        print(f"Fixed {m}")