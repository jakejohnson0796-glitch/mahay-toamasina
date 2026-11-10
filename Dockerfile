FROM python:3.12-slim

WORKDIR /app

# OCR actif en production : les scans PDF/JPG/PNG doivent être réellement lus.
# antiword/catdoc couvrent aussi les anciens formats Word .doc et PowerPoint .ppt.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-fra poppler-utils antiword catdoc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Télécharge, vérifie et embarque les bibliothèques d'affichage IA et les polices.
# Le navigateur les sert ensuite depuis /static/vendor, sans dépendre d'un CDN.
RUN python scripts/vendor_frontend_dependencies.py

# Render transmet le trafic au port interne expose par le service (8080 par défaut).
EXPOSE 8080

# Un seul worker : necessaire car le chat des cercles d'etude garde les
# connexions WebSocket en memoire dans le process (voir README, section
# "Cercles d'etude"). Ne PAS ajouter --workers > 1 sans changer cette
# architecture (pub/sub partage type Redis/Supabase Realtime).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
