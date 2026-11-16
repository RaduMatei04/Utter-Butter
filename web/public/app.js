// app.js: router-ul SPA + paginile Home și formular.
//
// SPA = pagina se încarcă o singură dată, iar partea de după # din adresă alege ce afișăm:
//   #/           Home (rețetele)
//   #/new        rețetă nouă
//   #/edit/3     editarea rețetei 3
//   #/cook/3     modul de gătit (cooking.js)
//   #/record     înregistrarea vocii (recorder.js)

const app = document.getElementById("app");

// Textul scris de utilizator nu trebuie interpretat ca HTML („<b>” rămâne text)
function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}

// ---------------------------------------------------------------------
// Router
// ---------------------------------------------------------------------

function router() {
  const [page, id] = location.hash.replace("#/", "").split("/");   // "#/edit/3" -> ["edit", "3"]

  // Oprim microfonul, timer-ul etc. ale paginii de dinainte
  Cooking.stop();
  Recorder.stop();
  window.scrollTo(0, 0);

  if (page === "new") renderForm(null);
  else if (page === "edit") renderForm(id);
  else if (page === "cook") Cooking.start(app, id);
  else if (page === "record") Recorder.start(app);
  else renderHome();
}

window.addEventListener("hashchange", router);   // browserul ne anunță când se schimbă #
router();

// ---------------------------------------------------------------------
// Home: cardurile cu rețete
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
    <div id="recipe-list" class="recipe-grid"><p class="muted">Loading recipes…</p></div>
    <p class="footer-link"><a href="#/record">🎙 Voice recorder (DTW templates &amp; test set)</a></p>`;

  const list = document.getElementById("recipe-list");
  try {
    const recipes = await Api.listRecipes();
    list.innerHTML = recipes.map(recipeCard).join("") || '<p class="muted">No recipes yet. Add your first one!</p>';
  } catch {
    list.innerHTML = '<p class="muted">Could not load recipes. Is the backend running?</p>';
  }

  // Butoanele Delete
  list.querySelectorAll("[data-delete]").forEach((button) => {
    button.onclick = async () => {
      if (!confirm("Delete this recipe? This cannot be undone.")) return;
      await Api.deleteRecipe(button.dataset.delete);
      renderHome();
    };
  });
}

function recipeCard(recipe) {
  return `
    <article class="recipe-card">
      <a class="card-main" href="#/cook/${recipe.id}">
        <h2>${escapeHtml(recipe.title)}</h2>
        <div class="recipe-meta">
          <span>🍽 ${recipe.servings} servings</span>
          <span>⏱ ${recipe.total_minutes} min</span>
        </div>
      </a>
      <div class="card-actions">
        <a class="btn btn-small btn-primary" href="#/cook/${recipe.id}">Cook</a>
        <a class="btn btn-small" href="#/edit/${recipe.id}">Edit</a>
        <button class="btn btn-small btn-danger" data-delete="${recipe.id}">Delete</button>
      </div>
    </article>`;
}

// ---------------------------------------------------------------------
// Formularul: rețetă nouă (id = null) sau editare
// ---------------------------------------------------------------------

async function renderForm(id) {
  let recipe = { title: "", servings: 2, total_minutes: 30, ingredients: [""], steps: [{ text: "" }] };
  if (id) recipe = await Api.getRecipe(id);

  app.innerHTML = `
    <h1>${id ? "Edit recipe" : "New recipe"}</h1>
    <form id="recipe-form" class="recipe-form">
      <label class="field"><span>Title</span>
        <input name="title" required value="${escapeHtml(recipe.title)}" placeholder="e.g. Banana bread">
      </label>
      <div class="field-row">
        <label class="field"><span>Servings</span>
          <input name="servings" type="number" min="1" value="${recipe.servings}">
        </label>
        <label class="field"><span>Total time (minutes)</span>
          <input name="total_minutes" type="number" min="0" value="${recipe.total_minutes}">
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

  // Un rând nou în listă: câmpul (sau câmpurile) + butonul ✕ care șterge rândul
  function addRow(list, html) {
    const row = document.createElement("li");
    row.innerHTML = html + '<button type="button" class="btn-icon" aria-label="Remove">✕</button>';
    row.querySelector(".btn-icon").onclick = () => row.remove();
    list.append(row);
    return row;
  }

  const addIngredient = (text = "") => addRow(ingredientList,
    `<input class="ingredient" value="${escapeHtml(text)}" placeholder="e.g. 2 eggs" aria-label="Ingredient">`);

  const addStep = (step = {}) => addRow(stepList,
    `<textarea class="step-text" rows="2" placeholder="Describe this step…" aria-label="Step">${escapeHtml(step.text)}</textarea>
     <label class="timer-field">⏱ <input class="step-timer" type="number" min="0"
       value="${step.timer_minutes ?? ""}" placeholder="min" aria-label="Timer in minutes (optional)"></label>`);

  recipe.ingredients.forEach((text) => addIngredient(text));
  recipe.steps.forEach((step) => addStep(step));
  document.getElementById("add-ingredient").onclick = () => addIngredient().querySelector("input").focus();
  document.getElementById("add-step").onclick = () => addStep().querySelector("textarea").focus();

  // Salvarea: adunăm valorile din formular și le trimitem la backend
  const form = document.getElementById("recipe-form");
  form.onsubmit = async (event) => {
    event.preventDefault();   // fără reîncărcarea paginii
    const fields = form.elements;   // atenție: form.title ar fi atributul formularului, nu câmpul!

    const data = {
      title: fields.title.value,
      servings: fields.servings.value,
      total_minutes: fields.total_minutes.value,
      ingredients: [...ingredientList.querySelectorAll(".ingredient")].map((input) => input.value),
      steps: [...stepList.children].map((row) => ({
        text: row.querySelector(".step-text").value,
        timer_minutes: Number(row.querySelector(".step-timer").value) || null,
      })),
    };

    try {
      if (id) await Api.updateRecipe(id, data);
      else await Api.createRecipe(data);
      location.hash = "#/";
    } catch (error) {
      document.getElementById("form-error").textContent = error.message;
    }
  };
}
