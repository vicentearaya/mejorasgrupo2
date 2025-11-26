const API_RRHH = import.meta.env.VITE_API_RRHH || 'http://localhost:8000/api/rrhh';

export async function login(email: string, password: string): Promise<{ access_token: string }> {
  const formData = new FormData();
  formData.append('username', email);
  formData.append('password', password);

  const res = await fetch(`${API_RRHH}/auth/login`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || 'Error al iniciar sesión');
  }

  return res.json();
}
