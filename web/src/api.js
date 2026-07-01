// In local dev, call the FastAPI server directly (CORS is enabled on :8000).
// Production/Docker use same-origin /api via nginx, or VITE_API_BASE on Vercel.
const API_BASE =
  import.meta.env.VITE_API_BASE ??
  (import.meta.env.DEV ? 'http://127.0.0.1:8000' : '');

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });

  const contentType = response.headers.get('content-type') || '';

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }

  if (!contentType.includes('application/json')) {
    const text = await response.text();
    if (text.trimStart().startsWith('<!')) {
      throw new Error(
        'API returned HTML instead of JSON. Start the backend with ./scripts/run_server.sh (port 8000).',
      );
    }
    throw new Error(text || 'Unexpected non-JSON response from API');
  }

  return response.json();
}

export async function getHealth() {
  return request('/api/health');
}

export async function getTools() {
  return request('/api/tools');
}

export async function postQuery(query) {
  return request('/api/query', {
    method: 'POST',
    body: JSON.stringify({ query }),
  });
}
