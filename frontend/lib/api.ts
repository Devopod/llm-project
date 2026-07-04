import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
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
    const url = error.config?.url || '';
    const isAuthEndpoint = url.includes('/auth/login') || url.includes('/auth/signup') || url.includes('/auth/refresh') || url.includes('/auth/admin/login');
    if (error.response?.status === 401 && typeof window !== 'undefined' && !isAuthEndpoint) {
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
  updateProfile: (data: { display_name?: string; bio?: string }) =>
    api.put('/auth/profile/', data),
  changePassword: (data: { current_password: string; new_password: string }) =>
    api.put('/auth/change-password/', data),
  usage: () => api.get('/auth/usage/'),
  plans: () => api.get('/auth/plans/'),
  submitPayment: (data: { plan: string; transaction_id: string; sender_number: string }) =>
    api.post('/auth/payments/submit/', data),
  paymentHistory: () => api.get('/auth/payments/history/'),
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
  deploy: (id: string, action: 'approve' | 'deny') =>
    api.post(`/projects/${id}/deploy/`, { action }),
  fileContent: (id: string, path: string) =>
    api.get(`/projects/${id}/file-content/${path}`),
  editFile: (id: string, path: string, content: string) =>
    api.put(`/projects/${id}/file-edit/${path}`, { content }),
  editFileLines: (id: string, path: string, startLine: number, endLine: number, newContent: string) =>
    api.put(`/projects/${id}/file-edit/${path}`, { start_line: startLine, end_line: endLine, new_content: newContent }),
  upload: (files: File | File[], name?: string, prompt?: string) => {
    const formData = new FormData();
    const fileList = Array.isArray(files) ? files : [files];
    for (const f of fileList) {
      formData.append('files', f);
    }
    if (name) formData.append('name', name);
    if (prompt) formData.append('prompt', prompt);
    return api.post('/projects/upload/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    });
  },
};

export const apk = {
  build: (projectId: string, description?: string) =>
    api.post(`/projects/${projectId}/apk/build/`, { description }, { timeout: 600000 }),
  download: (projectId: string) =>
    api.get(`/projects/${projectId}/apk/download/`, { responseType: 'blob' }),
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

export const admin = {
  login: (data: { username: string; password: string }) =>
    api.post('/auth/admin/login/', data),
  dashboard: () => api.get('/auth/admin/dashboard/'),
  users: () => api.get('/auth/admin/users/'),
  payments: () => api.get('/auth/admin/payments/'),
  verifyPayment: (id: string, action: string, note?: string) =>
    api.post(`/auth/admin/payments/${id}/verify/`, { action, note }),
  deleteUser: (id: string) => api.delete(`/auth/admin/users/${id}/delete/`),
};
