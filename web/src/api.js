const API_BASE = import.meta.env.VITE_API_BASE ?? '';

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
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
