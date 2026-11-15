// api.js: toate apelurile către backend, într-un singur loc.
// Fiecare funcție întoarce un Promise (o folosim cu `await`).

const Api = {
  // Funcție comună: trimite cererea și verifică dacă a reușit
  async request(method, url, body) {
    const options = { method, headers: {} };
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }

    const response = await fetch(url, options);

    // 204 = „No Content” (de ex. după ștergere): nu există JSON de citit
    if (response.status === 204) return null;

    const data = await response.json().catch(() => null);
    if (!response.ok) {
      // Backend-ul trimite {"error": "..."}: îl transformăm în excepție
      throw new Error((data && data.error) || "Server error " + response.status);
    }
    return data;
  },

  listRecipes()            { return this.request("GET", "/api/recipes"); },
  getRecipe(id)            { return this.request("GET", `/api/recipes/${id}`); },
  createRecipe(recipe)     { return this.request("POST", "/api/recipes", recipe); },
  updateRecipe(id, recipe) { return this.request("PUT", `/api/recipes/${id}`, recipe); },
  deleteRecipe(id)         { return this.request("DELETE", `/api/recipes/${id}`); },
};
