import joblib
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODEL_PATH = os.path.join(BASE_DIR, 'ml_models/sentiment_model.joblib')
VECTORIZER_PATH = os.path.join(BASE_DIR, 'ml_models/vectorizer.joblib')

model = joblib.load(MODEL_PATH)
vectorizer = joblib.load(VECTORIZER_PATH)

def predict_sentiment(text):
    if not text.strip():
        return 2  # Neutral for empty text
    
    X = vectorizer.transform([text])
    prediction = model.predict(X)[0]
    
    return int(prediction)  # Ensure it's returned as integer