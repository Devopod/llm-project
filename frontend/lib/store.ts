import { create } from 'zustand';

interface User {
  id: string;
  email: string;
  display_name: string;
  avatar_url: string | null;
  is_verified: boolean;
}

interface Project {
  id: string;
  name: string;
  description: string;
  status: string;
  primary_language: string | null;
  primary_framework: string | null;
  deployment_url: string | null;
  total_tokens_used: number;
  created_at: string;
  updated_at: string;
  tasks_count: number;
  completed_tasks: number;
}

interface Message {
  id: string;
  type: string;
  content: string;
  metadata: Record<string, unknown> | null;
  timestamp: string;
  agent: string;
}

interface AuthStore {
  user: User | null;
  isAuthenticated: boolean;
  setUser: (user: User | null) => void;
  logout: () => void;
}

interface ProjectStore {
  projects: Project[];
  currentProject: Project | null;
  messages: Message[];
  setProjects: (projects: Project[]) => void;
  setCurrentProject: (project: Project | null) => void;
  addMessage: (message: Message) => void;
  setMessages: (messages: Message[]) => void;
  updateProjectStatus: (id: string, status: string) => void;
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  isAuthenticated: false,
  setUser: (user) => set({ user, isAuthenticated: !!user }),
  logout: () => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
    }
    set({ user: null, isAuthenticated: false });
  },
}));

export const useProjectStore = create<ProjectStore>((set) => ({
  projects: [],
  currentProject: null,
  messages: [],
  setProjects: (projects) => set({ projects }),
  setCurrentProject: (project) => set({ currentProject: project }),
  addMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),
  setMessages: (messages) => set({ messages }),
  updateProjectStatus: (id, status) =>
    set((state) => ({
      projects: state.projects.map((p) =>
        p.id === id ? { ...p, status } : p
      ),
      currentProject:
        state.currentProject?.id === id
          ? { ...state.currentProject, status }
          : state.currentProject,
    })),
}));
