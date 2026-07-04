"use client";
import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { projects as projectsApi } from "@/lib/api";
import { useProjectStore } from "@/lib/store";
import NavBar from "@/components/NavBar";

export default function DashboardPage() {
  const router = useRouter();
  const { projects, setProjects } = useProjectStore();
  const [showCreate, setShowCreate] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [selectedStack, setSelectedStack] = useState("");
  const [error, setError] = useState("");
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploadName, setUploadName] = useState("");
  const [uploadPrompt, setUploadPrompt] = useState("");
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) { router.push("/login"); return; }
    projectsApi.list().then((res) => setProjects(res.data)).catch(() => {});
  }, [router, setProjects]);

  const stacks = [
    { id: 'flask', label: 'Flask', icon: '🐍', desc: 'Python web framework' },
    { id: 'django', label: 'Django', icon: '🎸', desc: 'Python full-stack framework' },
    { id: 'fastapi', label: 'FastAPI', icon: '⚡', desc: 'Python async API framework' },
    { id: 'react', label: 'React', icon: '⚛️', desc: 'JavaScript UI library' },
    { id: 'nextjs', label: 'Next.js', icon: '▲', desc: 'React full-stack framework' },
    { id: 'express', label: 'Express', icon: '🟢', desc: 'Node.js web framework' },
    { id: 'html', label: 'HTML/CSS/JS', icon: '🌐', desc: 'Static web app' },
    { id: 'android', label: 'Android (Java)', icon: '📱', desc: 'Android APK app' },
    { id: 'python', label: 'Python Script', icon: '🐍', desc: 'Pure Python project' },
  ];

  const handleCreate = async () => {
    if (!name.trim()) return;
    if (!selectedStack) { setError('Please select a technology stack'); return; }
    setLoading(true);
    setError("");
    const stackLabel = stacks.find(s => s.id === selectedStack)?.label || selectedStack;
    let finalPrompt = `[STACK: ${selectedStack}] Build with ${stackLabel}. ${prompt}`;
    if (selectedStack === 'android') {
      finalPrompt += "\n\n[BUILD_APK] Generate an Android APK for this project. Create a complete Android app with Java and XML layouts, include build.gradle files, and compile into a downloadable APK.";
    }
    try {
      const res = await projectsApi.create({ name, prompt: finalPrompt });
      setProjects([res.data, ...projects]);
      router.push(`/projects/${res.data.id}`);
    } catch (e: any) {
      if (e.response?.status === 429) {
        setError(e.response.data?.error?.message || "Daily limit reached. Upgrade your plan.");
      } else if (e.code === 'ECONNABORTED') {
        setError("Request timed out. Please try again.");
      } else if (e.response?.status === 401) {
        setError("Session expired. Please log in again.");
        router.push('/login');
        return;
      } else {
        setError(e.response?.data?.error?.message || "Failed to create project. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async () => {
    if (uploadFiles.length === 0) return;
    setUploading(true);
    setError("");
    try {
      const res = await projectsApi.upload(uploadFiles, uploadName || undefined, uploadPrompt || undefined);
      setProjects([res.data, ...projects]);
      router.push(`/projects/${res.data.id}`);
    } catch (e: any) {
      setError(e.response?.data?.error?.message || "Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(e.target.files || []);
    if (selected.length > 0) {
      setUploadFiles(selected);
      if (!uploadName && selected.length === 1) {
        const baseName = selected[0].name.replace(/\.(zip|7z|tar\.gz|tgz)$/i, '');
        setUploadName(baseName);
      }
      setShowUpload(true);
    }
  };

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!confirm("Delete this project? This cannot be undone.")) return;
    try {
      await projectsApi.delete(id);
      setProjects(projects.filter((p) => p.id !== id));
    } catch {
      alert("Failed to delete project");
    }
  };

  const statusColor = (status: string) => {
    const colors: Record<string, string> = {
      completed: "text-green-400", executing: "text-blue-400",
      planning: "text-yellow-400", failed: "text-red-400",
      paused: "text-gray-400", created: "text-gray-500",
    };
    return colors[status] || "text-gray-400";
  };

  return (
    <div className="min-h-screen bg-gray-950">
      <NavBar />
      <main className="max-w-5xl mx-auto px-6 py-8">
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-3xl font-bold">My Projects</h1>
          <div className="flex gap-3">
            <button onClick={() => { if (fileInputRef.current) fileInputRef.current.click(); }}
              className="px-4 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg transition flex items-center gap-2 group">
              <svg className="w-5 h-5 text-indigo-400 group-hover:text-indigo-300" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
              </svg>
              <span>Upload Project</span>
            </button>
            <input ref={fileInputRef} type="file" multiple accept=".zip,.7z,.tar.gz,.tgz,.py,.js,.ts,.tsx,.jsx,.html,.htm,.css,.scss,.json,.yaml,.yml,.xml,.md,.txt,.java,.kt,.swift,.go,.rs,.rb,.php,.c,.cpp,.h,.hpp,.cs,.sql,.sh,.bash,.toml,.ini,.cfg,.dockerfile,.makefile,.gradle,.vue,.svelte,.dart,.lua,.pl,.r,.graphql" onChange={handleFileSelect} className="hidden" />
            <button onClick={() => setShowCreate(true)}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg transition">
              + New Project
            </button>
          </div>
        </div>

        {showUpload && uploadFiles.length > 0 && (
          <div className="mb-8 p-6 bg-gray-900 border border-gray-800 rounded-xl">
            <h2 className="text-xl font-semibold mb-4">Upload Project</h2>
            {error && <p className="text-red-400 text-sm mb-3">{error}</p>}
            <div className="space-y-4">
              <div className="p-3 bg-gray-800 rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <svg className="w-5 h-5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8" />
                    </svg>
                    <span className="text-sm font-medium">{uploadFiles.length} file(s) selected</span>
                  </div>
                  <button onClick={() => { if (fileInputRef.current) fileInputRef.current.click(); }}
                    className="text-xs text-indigo-400 hover:text-indigo-300">Change</button>
                </div>
                <div className="space-y-1 max-h-32 overflow-y-auto">
                  {uploadFiles.map((f, i) => (
                    <div key={i} className="flex justify-between text-xs text-gray-400">
                      <span className="truncate">{f.name}</span>
                      <span className="text-gray-600 ml-2 shrink-0">{(f.size / 1024).toFixed(1)} KB</span>
                    </div>
                  ))}
                </div>
              </div>
              <input type="text" placeholder="Project name" value={uploadName}
                onChange={(e) => setUploadName(e.target.value)}
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-indigo-500" />
              <textarea placeholder="(Optional) Tell the agent what to do with this project... (e.g., Fix the login bug, Add dark mode, Update the API)" value={uploadPrompt}
                onChange={(e) => setUploadPrompt(e.target.value)} rows={3}
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-indigo-500 resize-none" />
              <div className="flex gap-3">
                <button onClick={handleUpload} disabled={uploading}
                  className="px-6 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg transition">
                  {uploading ? "Uploading..." : "Upload & Create"}
                </button>
                <button onClick={() => { setShowUpload(false); setUploadFiles([]); setUploadName(""); setUploadPrompt(""); }}
                  className="px-6 py-2 border border-gray-700 rounded-lg hover:bg-gray-800 transition">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        {showCreate && (
          <div className="mb-8 p-6 bg-gray-900 border border-gray-800 rounded-xl">
            <h2 className="text-xl font-semibold mb-4">Create New Project</h2>
            {error && <p className="text-red-400 text-sm mb-3">{error}</p>}
            <div className="space-y-4">
              <input type="text" placeholder="Project name" value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-indigo-500" />
              <div>
                <label className="block text-sm text-gray-400 mb-2">Choose Technology Stack</label>
                <div className="grid grid-cols-3 gap-2">
                  {stacks.map((stack) => (
                    <button key={stack.id} type="button"
                      onClick={() => setSelectedStack(stack.id)}
                      className={`p-3 rounded-lg border text-left transition text-sm ${
                        selectedStack === stack.id
                          ? 'border-indigo-500 bg-indigo-900/30 text-white'
                          : 'border-gray-700 bg-gray-800/50 text-gray-300 hover:border-gray-600 hover:bg-gray-800'
                      }`}>
                      <div className="flex items-center gap-2">
                        <span className="text-lg">{stack.icon}</span>
                        <div>
                          <div className="font-medium">{stack.label}</div>
                          <div className="text-xs text-gray-500">{stack.desc}</div>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
              <textarea placeholder="Describe what you want to build... (e.g., Build a calculator with a nice UI)" value={prompt}
                onChange={(e) => setPrompt(e.target.value)} rows={3}
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-indigo-500 resize-none" />
              <div className="flex gap-3">
                <button onClick={handleCreate} disabled={loading}
                  className="px-6 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg transition">
                  {loading ? "Creating..." : "Start Building"}
                </button>
                <button onClick={() => setShowCreate(false)}
                  className="px-6 py-2 border border-gray-700 rounded-lg hover:bg-gray-800 transition">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="grid gap-4">
          {projects.length === 0 ? (
            <div className="text-center py-16 text-gray-500">
              <p className="text-lg">No projects yet</p>
              <p className="text-sm mt-2">Create your first project to get started</p>
            </div>
          ) : (
            projects.map((project) => (
              <div key={project.id} onClick={() => router.push(`/projects/${project.id}`)}
                className="p-5 bg-gray-900 border border-gray-800 rounded-xl hover:border-gray-700 cursor-pointer transition">
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="text-lg font-semibold">{project.name}</h3>
                    <p className="text-gray-500 text-sm mt-1">{project.description || "No description"}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`text-sm font-medium capitalize ${statusColor(project.status)}`}>
                      {project.status}
                    </span>
                    <button onClick={(e) => handleDelete(e, project.id)}
                      className="text-gray-600 hover:text-red-400 transition p-1" title="Delete project">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                </div>
                <div className="flex gap-4 mt-3 text-xs text-gray-500">
                  {project.primary_language && <span>{project.primary_language}</span>}
                  <span>{project.tasks_count || 0} tasks</span>
                  <span>{new Date(project.created_at).toLocaleDateString()}</span>
                </div>
              </div>
            ))
          )}
        </div>
      </main>
    </div>
  );
}
