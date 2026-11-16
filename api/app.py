"""
Serviciul `api`: rețetele (adăugare, citire, editare, ștergere).

  GET    /api/recipes        lista rețetelor
  GET    /api/recipes/<id>   o rețetă completă, cu ingrediente și pași
  POST   /api/recipes        rețetă nouă
  PUT    /api/recipes/<id>   modifică o rețetă
  DELETE /api/recipes/<id>   șterge o rețetă

O rețetă în JSON:
  {"title": "Pancakes", "servings": 4, "total_minutes": 30,
   "ingredients": ["2 eggs", "500 ml milk"],
   "steps": [{"text": "Whisk the eggs", "timer_minutes": null}, ...]}
"""

import os

import psycopg
from flask import Flask, jsonify, request
from psycopg.rows import dict_row

app = Flask(__name__)
DATABASE_URL = os.environ["DATABASE_URL"]   # vine din docker-compose.yml


def connect():
    """Conexiune la Postgres. dict_row = fiecare rând vine ca dicționar (ușor de trimis ca JSON).
    Folosită cu `with`, salvează automat modificările la final (COMMIT)."""
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def read_recipe_from_request():
    """Citește rețeta trimisă de formular și elimină câmpurile goale."""
    data = request.get_json()
    recipe = {
        "title": data.get("title", "").strip(),
        "servings": int(data.get("servings") or 1),
        "total_minutes": int(data.get("total_minutes") or 0),
        "ingredients": [i.strip() for i in data.get("ingredients", []) if i.strip()],
        "steps": [{"text": s["text"].strip(), "timer_minutes": s.get("timer_minutes") or None}
                  for s in data.get("steps", []) if s.get("text", "").strip()],
    }
    if not recipe["title"] or not recipe["steps"]:
        raise ValueError("The recipe needs a title and at least one step")
    return recipe


def save_ingredients_and_steps(db, recipe_id, recipe):
    # position = 1, 2, 3... păstrează ordinea
    for position, text in enumerate(recipe["ingredients"], start=1):
        db.execute("INSERT INTO ingredients (recipe_id, position, text) VALUES (%s, %s, %s)",
                   (recipe_id, position, text))
    for position, step in enumerate(recipe["steps"], start=1):
        db.execute("INSERT INTO steps (recipe_id, position, text, timer_minutes) VALUES (%s, %s, %s, %s)",
                   (recipe_id, position, step["text"], step["timer_minutes"]))


@app.get("/api/recipes")
def list_recipes():
    with connect() as db:
        recipes = db.execute("SELECT id, title, servings, total_minutes FROM recipes ORDER BY id").fetchall()
    return jsonify(recipes)


@app.get("/api/recipes/<int:recipe_id>")
def get_recipe(recipe_id):
    with connect() as db:
        # %s = loc completat de psycopg (sigur, fără SQL injection)
        recipe = db.execute("SELECT id, title, servings, total_minutes FROM recipes WHERE id = %s",
                            (recipe_id,)).fetchone()
        if recipe is None:
            return {"error": "Recipe not found"}, 404
        ingredients = db.execute("SELECT text FROM ingredients WHERE recipe_id = %s ORDER BY position",
                                 (recipe_id,)).fetchall()
        steps = db.execute("SELECT text, timer_minutes FROM steps WHERE recipe_id = %s ORDER BY position",
                           (recipe_id,)).fetchall()

    recipe["ingredients"] = [row["text"] for row in ingredients]
    recipe["steps"] = steps
    return recipe


@app.post("/api/recipes")
def create_recipe():
    recipe = read_recipe_from_request()
    with connect() as db:
        new_id = db.execute(
            "INSERT INTO recipes (title, servings, total_minutes) VALUES (%s, %s, %s) RETURNING id",
            (recipe["title"], recipe["servings"], recipe["total_minutes"]),
        ).fetchone()["id"]
        save_ingredients_and_steps(db, new_id, recipe)
    return {"id": new_id}, 201


@app.put("/api/recipes/<int:recipe_id>")
def update_recipe(recipe_id):
    """Cel mai simplu mod de a edita: actualizăm titlul etc.,
    ștergem ingredientele și pașii vechi, apoi îi scriem pe cei noi."""
    recipe = read_recipe_from_request()
    with connect() as db:
        db.execute("UPDATE recipes SET title = %s, servings = %s, total_minutes = %s WHERE id = %s",
                   (recipe["title"], recipe["servings"], recipe["total_minutes"], recipe_id))
        db.execute("DELETE FROM ingredients WHERE recipe_id = %s", (recipe_id,))
        db.execute("DELETE FROM steps WHERE recipe_id = %s", (recipe_id,))
        save_ingredients_and_steps(db, recipe_id, recipe)
    return {"id": recipe_id}


@app.delete("/api/recipes/<int:recipe_id>")
def delete_recipe(recipe_id):
    # ingredientele și pașii se șterg automat (ON DELETE CASCADE în init.sql)
    with connect() as db:
        db.execute("DELETE FROM recipes WHERE id = %s", (recipe_id,))
    return "", 204


@app.errorhandler(ValueError)
def bad_request(error):
    return {"error": str(error)}, 400
