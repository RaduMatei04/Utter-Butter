-- =====================================================================
-- init.sql: rulează AUTOMAT o singură dată, când containerul Postgres
-- pornește prima dată (cu volumul de date gol).
-- Creează tabelele și adaugă 3 rețete demo.
-- Dacă modifici fișierul și vrei să-l rulezi din nou:
--     docker compose down -v      (șterge volumul cu date!)
--     docker compose up --build
-- =====================================================================

-- Tabelul principal: o linie = o rețetă
CREATE TABLE recipes (
    id            SERIAL PRIMARY KEY,          -- id generat automat (1, 2, 3...)
    title         TEXT    NOT NULL,
    servings      INTEGER NOT NULL DEFAULT 1,  -- număr de porții
    total_minutes INTEGER NOT NULL DEFAULT 0,  -- timp total estimat
    created_at    TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Ingredientele: fiecare ingredient aparține unei rețete (recipe_id).
-- ON DELETE CASCADE = dacă ștergi rețeta, se șterg și ingredientele ei.
CREATE TABLE ingredients (
    id        SERIAL PRIMARY KEY,
    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    position  INTEGER NOT NULL,                -- ordinea în listă (1, 2, 3...)
    text      TEXT    NOT NULL                 -- ex: "2 eggs"
);

-- Pașii rețetei, în ordine. timer_minutes e opțional (NULL = fără timer).
CREATE TABLE steps (
    id            SERIAL PRIMARY KEY,
    recipe_id     INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    position      INTEGER NOT NULL,
    text          TEXT    NOT NULL,
    timer_minutes INTEGER                      -- ex: 10 pentru "las-o 10 minute"
);

-- ---------------------------------------------------------------------
-- Rețeta 1: Clătite (Pancakes)
-- ---------------------------------------------------------------------
INSERT INTO recipes (id, title, servings, total_minutes) VALUES
    (1, 'Pancakes', 4, 30);

INSERT INTO ingredients (recipe_id, position, text) VALUES
    (1, 1, '2 eggs'),
    (1, 2, '500 ml milk'),
    (1, 3, '250 g flour'),
    (1, 4, '1 tbsp sugar'),
    (1, 5, 'A pinch of salt'),
    (1, 6, '2 tbsp oil (plus a little for the pan)');

INSERT INTO steps (recipe_id, position, text, timer_minutes) VALUES
    (1, 1, 'Whisk the eggs, sugar and salt in a large bowl.', NULL),
    (1, 2, 'Pour in half of the milk, then add the flour little by little, whisking until the batter is smooth with no lumps.', NULL),
    (1, 3, 'Stir in the rest of the milk and the oil. Let the batter rest for 10 minutes.', 10),
    (1, 4, 'Heat a non-stick pan over medium heat and grease it lightly with oil.', NULL),
    (1, 5, 'Pour in a ladle of batter and tilt the pan to spread it thin. Cook for about 1 minute, flip, and cook 1 more minute.', 2),
    (1, 6, 'Repeat with the remaining batter. Serve with jam, sweet cheese or chocolate.', NULL);

-- ---------------------------------------------------------------------
-- Rețeta 2: Omletă (Omelette)
-- ---------------------------------------------------------------------
INSERT INTO recipes (id, title, servings, total_minutes) VALUES
    (2, 'Omelette', 1, 10);

INSERT INTO ingredients (recipe_id, position, text) VALUES
    (2, 1, '3 eggs'),
    (2, 2, '2 tbsp milk'),
    (2, 3, '1 tbsp butter'),
    (2, 4, '30 g grated cheese'),
    (2, 5, 'Salt and black pepper'),
    (2, 6, 'Fresh chives (optional)');

INSERT INTO steps (recipe_id, position, text, timer_minutes) VALUES
    (2, 1, 'Crack the eggs into a bowl, add the milk, salt and pepper, and whisk until frothy.', NULL),
    (2, 2, 'Melt the butter in a non-stick pan over medium-low heat.', NULL),
    (2, 3, 'Pour in the eggs. As the edges set, gently push them toward the center and tilt the pan so the runny egg fills the gaps.', NULL),
    (2, 4, 'Cook for about 2 minutes, until almost set but still a little soft on top. Sprinkle the cheese over one half.', 2),
    (2, 5, 'Fold the omelette in half, slide it onto a plate and top with chives.', NULL);

-- ---------------------------------------------------------------------
-- Rețeta 3: Paste carbonara (Spaghetti Carbonara)
-- ---------------------------------------------------------------------
INSERT INTO recipes (id, title, servings, total_minutes) VALUES
    (3, 'Spaghetti Carbonara', 2, 25);

INSERT INTO ingredients (recipe_id, position, text) VALUES
    (3, 1, '200 g spaghetti'),
    (3, 2, '100 g guanciale (or pancetta)'),
    (3, 3, '3 egg yolks + 1 whole egg'),
    (3, 4, '50 g grated pecorino romano'),
    (3, 5, 'Freshly ground black pepper'),
    (3, 6, 'Salt for the pasta water');

INSERT INTO steps (recipe_id, position, text, timer_minutes) VALUES
    (3, 1, 'Bring a large pot of salted water to the boil.', NULL),
    (3, 2, 'Cut the guanciale into small strips. In a bowl, mix the yolks, the whole egg, most of the pecorino and plenty of pepper into a thick cream.', NULL),
    (3, 3, 'Cook the spaghetti until al dente, about 10 minutes.', 10),
    (3, 4, 'Meanwhile, fry the guanciale in a dry pan over medium heat until golden and crispy, about 5 minutes. Turn off the heat.', 5),
    (3, 5, 'Save a cup of pasta water, then drain the spaghetti and toss it in the pan with the guanciale.', NULL),
    (3, 6, 'Off the heat, pour in the egg cream and a splash of pasta water. Stir quickly until silky, so the eggs do not scramble.', NULL),
    (3, 7, 'Serve right away with the remaining pecorino and more black pepper.', NULL);

-- Am dat id-urile manual (1, 2, 3), așa că spunem contorului automat
-- să continue de la 4 pentru rețetele adăugate de utilizator.
SELECT setval('recipes_id_seq', (SELECT MAX(id) FROM recipes));
