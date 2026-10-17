import requests
import numpy as np

def embed(texts):
    r = requests.post("http://localhost:11434/api/embed",
                      json={"model": "bge-m3", "input": texts}, timeout=120)
    r.raise_for_status()
    return np.array(r.json()["embeddings"])

def test(student, steps):
    vecs = embed([student] + steps)
    vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
    scores = vecs[1:] @ vecs[0]
    for step, sc in sorted(zip(steps, scores), key=lambda x: -x[1]):
        print(f"{sc:.2f}  {step}")
    print()

# Tamil: the student line should match the first teacher step
test("இரண்டு பக்கமும் 3 கழிக்கிறேன்",
     ["இரு பக்கங்களிலும் 3 ஐ கழிக்கவும்",
      "இரு பக்கங்களையும் 2 ஆல் வகுக்கவும்",
      "முக்கோணத்தின் பரப்பளவு காண்க"])

# Kannada: the student line should match the first teacher step
test("ಎರಡೂ ಕಡೆ 3 ಕಳೆಯುತ್ತೇನೆ",
     ["ಎರಡೂ ಬದಿಗಳಿಂದ 3 ಕಳೆಯಿರಿ",
      "ಎರಡೂ ಬದಿಗಳನ್ನು 2 ರಿಂದ ಭಾಗಿಸಿ",
      "ತ್ರಿಕೋನದ ವಿಸ್ತೀರ್ಣ ಕಂಡುಹಿಡಿಯಿರಿ"])