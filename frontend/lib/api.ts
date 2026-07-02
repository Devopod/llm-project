import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401 && typeof window !== 'undefined') {
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        try {
          const res = await axios.post(`/api/auth/refresh/`, {
            refresh_token: refreshToken,
          });
          localStorage.setItem('access_token', res.data.access_token);
          localStorage.setItem('refresh_token', res.data.refresh_token);
          error.config.headers.Authorization = `Bearer ${res.data.access_token}`;
          return api(error.config);
        } catch {
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          window.location.href = '/login';
        }
      } else {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default api;

export const auth = {
  signup: (data: { email: string; password: string; display_name?: string }) =>
    api.post('/auth/signup/', data),
  login: (data: { email: string; password: string }) =>
    api.post('/auth/login/', data),
  logout: () => api.post('/auth/logout/'),
  profile: () => api.get('/auth/profile/'),
  stats: () => api.get('/auth/stats/'),
};

export const projects = {
  list: () => api.get('/projects/'),
  create: (data: { name: string; description?: string; prompt?: string }) =>
    api.post('/projects/', data),
  get: (id: string) => api.get(`/projects/${id}/`),
  delete: (id: string) => api.delete(`/projects/${id}/`),
  pause: (id: string) => api.post(`/projects/${id}/pause/`),
  resume: (id: string) => api.post(`/projects/${id}/resume/`),
  roadmap: (id: string) => api.get(`/projects/${id}/roadmap/`),
  messages: (id: string) => api.get(`/projects/${id}/messages/`),
  chat: (id: string, message: string) =>
    api.post(`/projects/${id}/chat/`, { message }),
  files: (id: string) => api.get(`/projects/${id}/files/`),
};

export const workspaces = {
  files: (projectId: string) => api.get(`/workspaces/${projectId}/files/`),
  fileContent: (projectId: string, path: string) =>
    api.get(`/workspaces/${projectId}/files/${path}/`),
  download: (projectId: string) =>
    api.post(`/workspaces/${projectId}/download/`, {}, { responseType: 'blob' }),
  execute: (projectId: string, command: string) =>
    api.post(`/workspaces/${projectId}/execute/`, { command }),
};

export const uploads = {
  upload: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/uploads/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  status: (id: string) => api.get(`/uploads/${id}/`),
};
