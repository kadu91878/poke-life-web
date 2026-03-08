<template>
  <div id="app">
    <router-view />
  </div>
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: 'Segoe UI', system-ui, sans-serif;
  background: #1a1a2e;
  color: #eee;
  min-height: 100vh;
}

#app {
  min-height: 100vh;
}

/* ── Variáveis globais ── */
:root {
  --color-primary:    #e63946;
  --color-secondary:  #457b9d;
  --color-accent:     #f4d03f;
  --color-bg:         #1a1a2e;
  --color-bg-card:    #16213e;
  --color-bg-panel:   #0f3460;
  --color-text:       #eee;
  --color-text-muted: #aaa;
  --radius:           8px;
  --shadow:           0 4px 16px rgba(0,0,0,0.4);
}

button {
  cursor: pointer;
  border: none;
  border-radius: var(--radius);
  padding: 0.6rem 1.2rem;
  font-size: 0.95rem;
  font-weight: 600;
  transition: opacity 0.2s, transform 0.1s;
}
button:hover:not(:disabled) { opacity: 0.88; transform: translateY(-1px); }
button:active:not(:disabled) { transform: translateY(0); }
button:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-primary   { background: var(--color-primary);   color: #fff; }
.btn-secondary { background: var(--color-secondary); color: #fff; }
.btn-accent    { background: var(--color-accent);    color: #333; }
.btn-ghost     { background: transparent; color: var(--color-text); border: 1px solid #555; }

input, select {
  background: #2a2a4e;
  border: 1px solid #444;
  border-radius: var(--radius);
  color: var(--color-text);
  padding: 0.5rem 0.8rem;
  font-size: 1rem;
  width: 100%;
}
input:focus, select:focus { outline: 2px solid var(--color-primary); border-color: transparent; }
</style>
