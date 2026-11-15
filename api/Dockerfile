# Imaginea de bază: Python 3.11, varianta „slim” (mai mică)
FROM python:3.11-slim

# Folderul de lucru din container
WORKDIR /app

# Întâi instalăm doar dependențele: Docker le ține în cache
# și nu le reinstalează la fiecare modificare de cod.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Apoi copiem codul aplicației
COPY . .

# Pornim Flask pe toate interfețele (0.0.0.0), ca să fie accesibil
# din celelalte containere. --debug = repornire automată la modificări.
CMD ["flask", "--app", "app", "run", "--host", "0.0.0.0", "--port", "5000", "--debug"]
