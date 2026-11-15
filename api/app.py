"""
Serviciul `api`: backend-ul pentru rețete (CRUD = Create, Read, Update, Delete).

  GET    /api/recipes        -> lista tuturor rețetelor (fără pași)
  GET    /api/recipes/<id>   -> o rețetă completă, cu ingrediente și pași
  POST   /api/recipes        -> adaugă o rețetă nouă
  PUT    /api/recipes/<id>   -> modifică o rețetă existentă
  DELETE /api/recipes/<id>   -> șterge o rețetă

Formatul JSON al unei rețete (la POST și PUT):
{
  "title": "Pancakes",
  "servings": 4,
  "total_minutes": 30,
  "ingredients": ["2 eggs", "500 ml milk"],
  "steps": [
    {"text": "Whisk the eggs...", "timer_minutes": null},
    {"text": "Let it rest.",       "timer_minutes": 10}
  ]
}
"""

import os

import psycopg
from psycopg.rows import dict_row
from flask import Flask, jsonify, request

app = Flask(__name__)

# Adresa bazei de date vine din docker-compose.yml (variabilă de mediu).
# "db" este numele serviciului Postgres în rețeaua Docker.
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://butter:butter@db:5432/utterbutter"
)


def get_connection():
    """Deschide o conexiune nouă la Postgres.
    row_factory=dict_row => fiecare rând vine ca dicționar {coloana: valoare},
    deci îl putem transforma direct în JSON.
    Folosită cu `with`, conexiunea face COMMIT automat la final
    (sau ROLLBACK dacă apare o eroare)."""
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


# ---------------------------------------------------------------------
# Funcții ajutătoare
# ---------------------------------------------------------------------

def to_positive_int(value, default):
    """Transformă o valoare în număr întreg >= 0. Dacă nu se poate, întoarce default."""
    try:
        number = int(value)
        return number if number >= 0 else default
    except (TypeError, ValueError):
        return default


def validate_recipe(data):
    """Verifică și curăță datele primite de la formular.
    Întoarce (recipe, None) dacă e totul în regulă, sau (None, mesaj_eroare)."""
    if not isinstance(data, dict):
        return None, "Invalid JSON"

    title = str(data.get("title", "")).strip()
    if not title:
        return None, "The recipe needs a title"

    # Păstrăm doar ingredientele care nu sunt goale
    ingredients = [
        str(item).strip() for item in data.get("ingredients", []) if str(item).strip()
    ]

    # Păstrăm doar pașii cu text; timer-ul e opțional (None = fără timer)
    steps = []
    for step in data.get("steps", []):
        if not isinstance(step, dict):
            continue
        text = str(step.get("text", "")).strip()
        if not text:
            continue
        timer = to_positive_int(step.get("timer_minutes"), None)
        if timer == 0:
            timer = None
        steps.append({"text": text, "timer_minutes": timer})

    if not steps:
        return None, "The recipe needs at least one step"

    recipe = {
        "title": title,
        "servings": to_positive_int(data.get("servings"), 1) or 1,
        "total_minutes": to_positive_int(data.get("total_minutes"), 0),
        "ingredients": ingredients,
        "steps": steps,
    }
    return recipe, None


def save_ingredients_and_steps(conn, recipe_id, recipe):
    """Scrie ingredientele și pașii unei rețete, în ordine (position = 1, 2, 3...)."""
    for position, text in enumerate(recipe["ingredients"], start=1):
        conn.execute(
            "INSERT INTO ingredients (recipe_id, position, text) VALUES (%s, %s, %s)",
            (recipe_id, position, text),
        )
    for position, step in enumerate(recipe["steps"], start=1):
        conn.execute(
            """
            INSERT INTO steps (recipe_id, position, text, timer_minutes)
            VALUES (%s, %s, %s, %s)
            """,
            (recipe_id, position, step["text"], step["timer_minutes"]),
        )


# ---------------------------------------------------------------------
# Rute (endpoint-uri)
# ---------------------------------------------------------------------

@app.get("/api/health")
def health():
    """Verificare rapidă că serverul merge (utilă la depanare)."""
    return jsonify({"status": "ok"})


@app.get("/api/recipes")
def list_recipes():
    """Întoarce toate rețetele, cele mai vechi primele."""
    with get_connection() as conn:
        recipes = conn.execute(
            """
            SELECT id, title, servings, total_minutes
            FROM recipes
            ORDER BY id
            """
        ).fetchall()
    return jsonify(recipes)


@app.get("/api/recipes/<int:recipe_id>")
def get_recipe(recipe_id):
    """Întoarce o rețetă completă: datele ei + ingrediente + pași."""
    with get_connection() as conn:
        # %s este un „loc liber” completat sigur de psycopg (fără SQL injection)
        recipe = conn.execute(
            "SELECT id, title, servings, total_minutes FROM recipes WHERE id = %s",
            (recipe_id,),
        ).fetchone()

        if recipe is None:
            return jsonify({"error": "Recipe not found"}), 404

        ingredients = conn.execute(
            "SELECT text FROM ingredients WHERE recipe_id = %s ORDER BY position",
            (recipe_id,),
        ).fetchall()

        steps = conn.execute(
            """
            SELECT text, timer_minutes
            FROM steps
            WHERE recipe_id = %s
            ORDER BY position
            """,
            (recipe_id,),
        ).fetchall()

    # Ingredientele le trimitem ca listă simplă de texte: ["2 eggs", ...]
    recipe["ingredients"] = [row["text"] for row in ingredients]
    recipe["steps"] = steps
    return jsonify(recipe)


@app.post("/api/recipes")
def create_recipe():
    """Adaugă o rețetă nouă și întoarce id-ul ei."""
    recipe, error = validate_recipe(request.get_json(silent=True))
    if error:
        return jsonify({"error": error}), 400

    with get_connection() as conn:
        # RETURNING id = Postgres ne spune ce id a generat
        row = conn.execute(
            """
            INSERT INTO recipes (title, servings, total_minutes)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (recipe["title"], recipe["servings"], recipe["total_minutes"]),
        ).fetchone()
        save_ingredients_and_steps(conn, row["id"], recipe)

    return jsonify({"id": row["id"]}), 201


@app.put("/api/recipes/<int:recipe_id>")
def update_recipe(recipe_id):
    """Modifică o rețetă. Cel mai simplu mod: actualizăm datele de bază,
    ștergem vechile ingrediente și pași, apoi îi scriem pe cei noi."""
    recipe, error = validate_recipe(request.get_json(silent=True))
    if error:
        return jsonify({"error": error}), 400

    with get_connection() as conn:
        result = conn.execute(
            """
            UPDATE recipes
            SET title = %s, servings = %s, total_minutes = %s
            WHERE id = %s
            """,
            (recipe["title"], recipe["servings"], recipe["total_minutes"], recipe_id),
        )
        if result.rowcount == 0:
            return jsonify({"error": "Recipe not found"}), 404

        conn.execute("DELETE FROM ingredients WHERE recipe_id = %s", (recipe_id,))
        conn.execute("DELETE FROM steps WHERE recipe_id = %s", (recipe_id,))
        save_ingredients_and_steps(conn, recipe_id, recipe)

    return jsonify({"id": recipe_id})


@app.delete("/api/recipes/<int:recipe_id>")
def delete_recipe(recipe_id):
    """Șterge o rețetă. Ingredientele și pașii se șterg automat (ON DELETE CASCADE)."""
    with get_connection() as conn:
        result = conn.execute("DELETE FROM recipes WHERE id = %s", (recipe_id,))
        if result.rowcount == 0:
            return jsonify({"error": "Recipe not found"}), 404
    return "", 204
