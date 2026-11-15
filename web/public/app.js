// app.js: SPA-ul (Single Page Application).
//
// Cum funcționează un SPA fără framework:
//   - pagina HTML se încarcă o singură dată;
//   - partea de după # din adresă (hash) spune ce „pagină” vrem: #/, #/new ...
//   - când hash-ul se schimbă, browserul declanșează evenimentul "hashchange",
//     iar noi redesenăm conținutul din <main id="app">.
//
// Rute:
//   #/            -> Home (lista de rețete)
//   #/new         -> formular pentru rețetă nouă
//   #/edit/:id    -> formular pentru editarea unei rețete
//   #/cook/:id    -> modul de gătit (în cooking.js)
//   #/record      -> înregistrarea vocii: șabloane DTW + set de test (în recorder.js)

const app = document.getElementById("app");

// ---------------------------------------------------------------------
// Funcții ajutătoare
// ---------------------------------------------------------------------

// Transformă caracterele speciale în entități HTML, ca un titlu de genul
// "<b>Pizza</b>" să apară ca text, nu să fie interpretat ca HTML.
function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function showError(message) {
  app.innerHTML = `
    <div class="message-box">
      <p>Oops! ${escapeHtml(message)}</p>
      <a class="btn" href="#/">← Back to recipes</a>
    </div>`;
}

// ---------------------------------------------------------------------
// Router: alege pagina în funcție de hash
// ---------------------------------------------------------------------

function router() {
  const hash = location.hash || "#/";
  // ex: "#/edit/3" -> ["edit", "3"]
  const parts = hash.replace(/^#\/?/, "").split("/");
  const page = parts[0];
  const id = Number(parts[1]);

  window.scrollTo(0, 0);

  // Dacă ieșim din modul de gătit sau din recorder, oprim microfonul, timer-ul etc.
  Cooking.stop();
  Recorder.stop();

  if (page === "") return renderHome();
  if (page === "new") return renderForm(null);
  if (page === "edit" && id) return renderForm(id);
  if (page === "cook" && id) return Cooking.start(app, id); // vezi cooking.js
  if (page === "record") return Recorder.start(app);        // vezi recorder.js

  showError("This page does not exist.");
}

window.addEventListener("hashchange", router);
router(); // prima afișare, la încărcarea paginii

// ---------------------------------------------------------------------
// Pagina Home: cardurile cu rețete
// ---------------------------------------------------------------------

async function renderHome() {
  app.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Your recipes</h1>
        <p class="subtitle">Pick a recipe and cook hands-free. Just say “next step”!</p>
      </div>
      <a class="btn btn-primary" href="#/new">+ New recipe</a>
    </div>
    <div id="recipe-list" class="recipe-grid">
      <p class="muted">Loading recipes…</p>
    </div>
    <p class="footer-link"><a href="#/record">🎙 Voice recorder (DTW templates &amp; test set)</a></p>`;

  const list = document.getElementById("recipe-list");

  let recipes;
  try {
    recipes = await Api.listRecipes();
  } catch (error) {
    list.innerHTML = '<p class="muted">Could not load recipes. Is the backend running?</p>';
    return;
  }

  if (recipes.length === 0) {
    list.innerHTML = '<p class="muted">No recipes yet. Add your first one!</p>';
    return;
  }

  // Construim HTML-ul tuturor cardurilor
  list.innerHTML = recipes.map((r) => `
    <article class="recipe-card">
      <a class="card-main" href="#/cook/${r.id}" aria-label="Start cooking ${escapeHtml(r.title)}">
        <h2>${escapeHtml(r.title)}</h2>
        <div class="recipe-meta">
          <span>🍽 ${r.servings} servings</span>
          <span>⏱ ${r.total_minutes} min</span>
        </div>
      </a>
      <div class="card-actions">
        <a class="btn btn-small btn-primary" href="#/cook/${r.id}">Cook</a>
        <a class="btn btn-small" href="#/edit/${r.id}">Edit</a>
        <button class="btn btn-small btn-danger" data-delete="${r.id}"
                data-title="${escapeHtml(r.title)}">Delete</button>
      </div>
    </article>`).join("");

  // Butoanele de ștergere: cerem confirmare, apoi ștergem și redesenăm
  list.querySelectorAll("[data-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      const title = button.dataset.title;
      if (!confirm(`Delete "${title}"? This cannot be undone.`)) return;
      try {
        await Api.deleteRecipe(button.dataset.delete);
        renderHome();
      } catch (error) {
        alert("Could not delete: " + error.message);
      }
    });
  });
}

// ---------------------------------------------------------------------
// Formularul: rețetă nouă (id = null) sau editare (id = număr)
// ---------------------------------------------------------------------

async function renderForm(id) {
  // Pentru rețetă nouă pornim cu un ingredient și un pas goale
  let recipe = {
    title: "",
    servings: 2,
    total_minutes: 30,
    ingredients: [""],
    steps: [{ text: "", timer_minutes: null }],
  };

  if (id) {
    app.innerHTML = '<p class="muted">Loading…</p>';
    try {
      recipe = await Api.getRecipe(id);
    } catch (error) {
      return showError(error.message);
    }
  }

  app.innerHTML = `
    <h1>${id ? "Edit recipe" : "New recipe"}</h1>

    <form id="recipe-form" class="recipe-form" novalidate>
      <label class="field">
        <span>Title</span>
        <input name="title" type="text" required maxlength="120"
               value="${escapeHtml(recipe.title)}" placeholder="e.g. Banana bread">
      </label>

      <div class="field-row">
        <label class="field">
          <span>Servings</span>
          <input name="servings" type="number" min="1" max="50" value="${recipe.servings}">
        </label>
        <label class="field">
          <span>Total time (minutes)</span>
          <input name="total_minutes" type="number" min="0" max="1440" value="${recipe.total_minutes}">
        </label>
      </div>

      <fieldset>
        <legend>Ingredients</legend>
        <ul id="ingredient-list" class="edit-list"></ul>
        <button type="button" class="btn btn-small" id="add-ingredient">+ Add ingredient</button>
      </fieldset>

      <fieldset>
        <legend>Steps</legend>
        <ol id="step-list" class="edit-list"></ol>
        <button type="button" class="btn btn-small" id="add-step">+ Add step</button>
      </fieldset>

      <p id="form-error" class="form-error" role="alert"></p>

      <div class="form-actions">
        <a class="btn" href="#/">Cancel</a>
        <button type="submit" class="btn btn-primary">Save recipe</button>
      </div>
    </form>`;

  const ingredientList = document.getElementById("ingredient-list");
  const stepList = document.getElementById("step-list");

  // Adaugă un rând de ingredient (un câmp text + buton de ștergere)
  function addIngredientRow(text) {
    const li = document.createElement("li");
    li.innerHTML = `
      <input type="text" class="ingredient-input" maxlength="200"
             value="${escapeHtml(text)}" placeholder="e.g. 2 eggs" aria-label="Ingredient">
      <button type="button" class="btn-icon" aria-label="Remove ingredient">✕</button>`;
    li.querySelector("button").addEventListener("click", () => li.remove());
    ingredientList.append(li);
    return li;
  }

  // Adaugă un rând de pas (text + timer opțional + buton de ștergere)
  function addStepRow(step) {
    const li = document.createElement("li");
    li.innerHTML = `
      <textarea class="step-text" rows="2" maxlength="1000"
                placeholder="Describe this step…" aria-label="Step text">${escapeHtml(step.text)}</textarea>
      <label class="timer-field">
        <span>⏱</span>
        <input type="number" class="step-timer" min="0" max="600"
               value="${step.timer_minutes ?? ""}" placeholder="min" aria-label="Timer in minutes (optional)">
      </label>
      <button type="button" class="btn-icon" aria-label="Remove step">✕</button>`;
    li.querySelector(".btn-icon").addEventListener("click", () => li.remove());
    stepList.append(li);
    return li;
  }

  // Completăm listele cu datele existente
  (recipe.ingredients.length ? recipe.ingredients : [""]).forEach(addIngredientRow);
  (recipe.steps.length ? recipe.steps : [{ text: "", timer_minutes: null }]).forEach(addStepRow);

  // Butoanele „+ Add”: adaugă un rând nou și pun cursorul în el
  document.getElementById("add-ingredient").addEventListener("click", () => {
    addIngredientRow("").querySelector("input").focus();
  });
  document.getElementById("add-step").addEventListener("click", () => {
    addStepRow({ text: "", timer_minutes: null }).querySelector("textarea").focus();
  });

  // Salvarea: citim toate câmpurile, trimitem la backend, ne întoarcem pe Home
  const form = document.getElementById("recipe-form");
  const errorBox = document.getElementById("form-error");

  form.addEventListener("submit", async (event) => {
    event.preventDefault(); // oprim reîncărcarea paginii

    // Atenție: folosim form.elements.title, nu form.title.
    // form.title e atributul „title” al formularului, nu câmpul nostru!
    const fields = form.elements;
    const data = {
      title: fields.title.value.trim(),
      servings: Number(fields.servings.value) || 1,
      total_minutes: Number(fields.total_minutes.value) || 0,
      ingredients: [...ingredientList.querySelectorAll(".ingredient-input")]
        .map((input) => input.value.trim())
        .filter((text) => text !== ""),
      steps: [...stepList.querySelectorAll("li")]
        .map((li) => ({
          text: li.querySelector(".step-text").value.trim(),
          timer_minutes: Number(li.querySelector(".step-timer").value) || null,
        }))
        .filter((step) => step.text !== ""),
    };

    // Verificări simple înainte de trimitere
    if (!data.title) {
      errorBox.textContent = "Please give your recipe a title.";
      fields.title.focus();
      return;
    }
    if (data.steps.length === 0) {
      errorBox.textContent = "Please add at least one step.";
      return;
    }

    errorBox.textContent = "";
    try {
      if (id) {
        await Api.updateRecipe(id, data);
      } else {
        await Api.createRecipe(data);
      }
      location.hash = "#/"; // înapoi pe Home
    } catch (error) {
      errorBox.textContent = "Could not save: " + error.message;
    }
  });
}
