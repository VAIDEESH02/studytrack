// Where the API lives. No hand edits are needed when deploying:
// - Local development (localhost or 127.0.0.1) talks to uvicorn directly on port 8000.
// - Anywhere else (Netlify) uses the same-origin /api proxy defined in netlify.toml, so the
//   session cookie is first-party and the Render URL never appears in browser code.
const LOCAL_HOSTNAMES = new Set(["localhost", "127.0.0.1", "[::1]"]);

export const IS_LOCAL = LOCAL_HOSTNAMES.has(window.location.hostname);
export const API_BASE_URL = IS_LOCAL ? `${window.location.protocol}//${window.location.hostname}:8000` : "/api";
