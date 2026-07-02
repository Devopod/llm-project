"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { projects as projectsApi } from "@/lib/api";
import { useProjectStore } from "@/lib/store";

export default function DashboardPage() {
  const router = useRouter();
  const { projects, setProjects } = useProjectStore();
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [buildApk, setBuildApk] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) { router.push("/login"); return; }
    projectsApi.list().then((res) => setProjects(res.data)).catch(() => {});
  }, [router, setProjects]);

  const handleCreate = async () => {
    if (!name.trim()) return;
    setLoading(true);
    let finalPrompt = prompt;
    if (buildApk) {
      finalPrompt += "\n\n[BUILD_APK] Generate an Android APK for this project. Create a complete Android app with Kotlin/Jetpack Compose, include build.gradle files, and compile into a downloadable APK.";
    }
    try {
      const res = await projectsApi.create({ name, prompt: finalPrompt });
      setProjects([res.data, ...projects]);
      router.push(`/projects/${res.data.id}`);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
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
      <nav className="border-b border-gray-800 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-lg" />
          <span className="text-xl font-bold">AstraDev</span>
        </div>
        <button onClick={() => { localStorage.clear(); router.push("/login"); }}
          className="text-gray-400 hover:text-white text-sm">Logout</button>
      </nav>

      <main className="max-w-5xl mx-auto px-6 py-8">
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-3xl font-bold">My Projects</h1>
          <button onClick={() => setShowCreate(true)}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg transition">
            + New Project
          </button>
        </div>

        {showCreate && (
          <div className="mb-8 p-6 bg-gray-900 border border-gray-800 rounded-xl">
            <h2 className="text-xl font-semibold mb-4">Create New Project</h2>
            <div className="space-y-4">
              <input type="text" placeholder="Project name" value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-indigo-500" />
              <textarea placeholder="Describe what you want to build... (e.g., Build a todo app with React and FastAPI)" value={prompt}
                onChange={(e) => setPrompt(e.target.value)} rows={4}
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-indigo-500 resize-none" />
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={buildApk} onChange={(e) => setBuildApk(e.target.checked)}
                  className="w-4 h-4 rounded border-gray-700 bg-gray-800 text-indigo-600 focus:ring-indigo-500" />
                <span className="text-sm text-gray-300">Build APK (Android Package)</span>
              </label>
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
                  <span className={`text-sm font-medium capitalize ${statusColor(project.status)}`}>
                    {project.status}
                  </span>
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
