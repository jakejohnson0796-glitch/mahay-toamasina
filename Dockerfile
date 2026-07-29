FROM python:3.12-slim

WORKDIR /app

# tesseract-ocr et poppler-utils sont optionnels : ne les ajoute que si tu
# veux l'OCR sur des documents scannes (images/PDF sans texte selectionnable).
# Decommente la ligne suivante si besoin (augmente la taille de l'image) :
# RUN apt-get update && apt-get install -y tesseract-ocr tesseract-ocr-fra poppler-utils && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Fly.io route le trafic vers le port interne declare dans fly.toml (8080 ici)
EXPOSE 8080

# Un seul worker : necessaire car le chat des cercles d'etude garde les
# connexions WebSocket en memoire dans le process (voir README, section
# "Cercles d'etude"). Ne PAS ajouter --workers > 1 sans changer cette
# architecture (pub/sub partage type Redis/Supabase Realtime).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
