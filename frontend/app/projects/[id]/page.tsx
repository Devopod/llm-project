"use client";
import { useEffect, useState, useRef, use } from "react";
import { useRouter } from "next/navigation";
import { projects as projectsApi, workspaces } from "@/lib/api";
import { ProjectWebSocket } from "@/lib/websocket";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";

interface Message {
  type: string;
  content: string;
  metadata?: Record<string, unknown>;
  timestamp?: string;
  agent?: string;
  message_id?: string;
}

interface Task {
  id: string;
  title: string;
  status: string;
  task_type: string;
  assigned_agent: string;
}

interface FileEntry {
  path: string;
  is_dir: boolean;
  size: number;
}

export default function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [project, setProject] = useState<Record<string, unknown> | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [activeTab, setActiveTab] = useState<"activity" | "files" | "terminal">("activity");
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [terminalOutput, setTerminalOutput] = useState("");
  const [terminalInput, setTerminalInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<ProjectWebSocket | null>(null);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) { router.push("/login"); return; }

    projectsApi.get(id).then((res) => setProject(res.data)).catch(() => {});
    projectsApi.messages(id).then((res) => {
      const msgs = res.data.map((m: Record<string, unknown>) => ({
        type: m.message_type as string,
        content: m.content as string,
        agent: m.role as string,
        timestamp: m.created_at as string,
      }));
      setMessages(msgs);
    }).catch(() => {});
    projectsApi.roadmap(id).then((res) => setTasks(res.data.tasks || [])).catch(() => {});
    loadFiles();

    const ws = new ProjectWebSocket(id, (data) => {
      const msg = data as unknown as Message;
      setMessages((prev) => [...prev, msg]);
      if (msg.type === "plan") {
        projectsApi.roadmap(id).then((res) => setTasks(res.data.tasks || [])).catch(() => {});
      }
      if (msg.type === "success" || msg.type === "code") {
        loadFiles();
      }
    });
    ws.connect();
    wsRef.current = ws;

    return () => { ws.disconnect(); };
  }, [id, router]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const loadFiles = () => {
    workspaces.files(id).then((res) => setFiles(res.data.files || [])).catch(() => {});
  };

  const handleChat = async () => {
    if (!chatInput.trim()) return;
    const msg: Message = { type: "message", content: chatInput, agent: "user", timestamp: new Date().toISOString() };
    setMessages((prev) => [...prev, msg]);
    setChatInput("");
    try {
      await projectsApi.chat(id, chatInput);
    } catch (e) {
      console.error(e);
    }
  };

  const handleFileClick = async (path: string) => {
    setSelectedFile(path);
    try {
      const res = await workspaces.fileContent(id, path);
      setFileContent(res.data.content);
      setActiveTab("files");
    } catch {
      setFileContent("Error loading file");
    }
  };

  const handleDownload = async () => {
    try {
      const res = await workspaces.download(id);
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `${(project as Record<string, string>)?.name || "project"}.zip`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (e) {
      console.error(e);
    }
  };

  const handleBuildApk = async () => {
    const apkPrompt = "Build an Android APK from this project. Create the necessary Android project structure with Kotlin, build.gradle, AndroidManifest.xml, and compile it into a downloadable APK file.";
    setMessages((prev) => [...prev, { type: "message", content: apkPrompt, agent: "user", timestamp: new Date().toISOString() }]);
    try {
      await projectsApi.chat(id, apkPrompt);
    } catch (e) {
      console.error(e);
    }
  };

  const handleTerminal = async () => {
    if (!terminalInput.trim()) return;
    setTerminalOutput((prev) => prev + `$ ${terminalInput}\n`);
    try {
      const res = await workspaces.execute(id, terminalInput);
      setTerminalOutput((prev) => prev + (res.data.stdout || "") + (res.data.stderr || "") + "\n");
    } catch {
      setTerminalOutput((prev) => prev + "Error executing command\n");
    }
    setTerminalInput("");
  };

  const messageIcon = (type: string) => {
    const icons: Record<string, string> = {
      thinking: "...", plan: "P", action: "A", code: "</>",
      output: ">", error: "!", fix: "F", success: "OK",
      deployment: "D", message: "M",
    };
    return icons[type] || "?";
  };

  const messageColor = (type: string) => {
    const colors: Record<string, string> = {
      thinking: "border-yellow-600", plan: "border-blue-600",
      action: "border-indigo-600", code: "border-green-600",
      output: "border-gray-600", error: "border-red-600",
      fix: "border-orange-600", success: "border-green-500",
      deployment: "border-purple-600", message: "border-gray-700",
    };
    return colors[type] || "border-gray-700";
  };

  const taskStatusIcon = (status: string) => {
    const icons: Record<string, string> = {
      completed: "C", in_progress: "~", pending: "o", failed: "X",
    };
    return icons[status] || "?";
  };

  const taskStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      completed: "text-green-400", in_progress: "text-blue-400",
      pending: "text-gray-500", failed: "text-red-400",
    };
    return colors[status] || "text-gray-500";
  };

  if (!project) return <div className="min-h-screen flex items-center justify-center text-gray-400">Loading...</div>;

  return (
    <div className="h-screen flex flex-col bg-gray-950">
      {/* Top bar */}
      <div className="border-b border-gray-800 px-4 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-4">
          <button onClick={() => router.push("/dashboard")} className="text-gray-400 hover:text-white">&larr;</button>
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-gradient-to-br from-indigo-500 to-purple-600 rounded" />
            <span className="font-semibold">{(project as Record<string, string>).name}</span>
          </div>
          <span className={`text-xs px-2 py-0.5 rounded-full border capitalize ${
            (project as Record<string, string>).status === "completed" ? "border-green-700 text-green-400" :
            (project as Record<string, string>).status === "executing" ? "border-blue-700 text-blue-400" :
            "border-gray-700 text-gray-400"
          }`}>{(project as Record<string, string>).status}</span>
        </div>
        <div className="flex gap-2">
          <button onClick={handleBuildApk} className="px-3 py-1.5 text-sm bg-green-700 hover:bg-green-600 rounded-lg transition">
            Build APK
          </button>
          <button onClick={handleDownload} className="px-3 py-1.5 text-sm bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg transition">
            Download ZIP
          </button>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left sidebar - Tasks */}
        <div className="w-64 border-r border-gray-800 overflow-y-auto p-3">
          <h3 className="text-sm font-semibold text-gray-400 mb-3">TASKS</h3>
          <div className="space-y-2">
            {tasks.map((task) => (
              <div key={task.id} className="p-2 bg-gray-900 rounded-lg text-xs">
                <div className="flex items-center gap-2">
                  <span className={`font-mono ${taskStatusColor(task.status)}`}>{taskStatusIcon(task.status)}</span>
                  <span className="truncate">{task.title}</span>
                </div>
              </div>
            ))}
            {tasks.length === 0 && <p className="text-xs text-gray-600">No tasks yet</p>}
          </div>

          <h3 className="text-sm font-semibold text-gray-400 mt-6 mb-3">FILES</h3>
          <div className="space-y-1">
            {files.filter(f => !f.is_dir).slice(0, 30).map((file) => (
              <div key={file.path} onClick={() => handleFileClick(file.path)}
                className="px-2 py-1 text-xs text-gray-400 hover:text-white hover:bg-gray-800 rounded cursor-pointer truncate">
                {file.path}
              </div>
            ))}
          </div>
        </div>

        {/* Center - Activity/Code/Terminal */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex border-b border-gray-800 shrink-0">
            {(["activity", "files", "terminal"] as const).map((tab) => (
              <button key={tab} onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 text-sm capitalize ${activeTab === tab ? "text-white border-b-2 border-indigo-500" : "text-gray-500"}`}>
                {tab}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-y-auto p-4">
            {activeTab === "activity" && (
              <div className="space-y-3">
                {messages.map((msg, i) => (
                  <div key={i} className={`p-3 rounded-lg border-l-2 ${messageColor(msg.type)} bg-gray-900/50`}>
                    <div className="flex items-center gap-2 text-xs text-gray-500 mb-1">
                      <span className="font-mono bg-gray-800 px-1.5 py-0.5 rounded">{messageIcon(msg.type)}</span>
                      <span className="capitalize">{msg.agent || "system"}</span>
                      {msg.timestamp && <span>{new Date(msg.timestamp).toLocaleTimeString()}</span>}
                    </div>
                    {msg.type === "code" ? (
                      <SyntaxHighlighter language="typescript" style={vscDarkPlus}
                        customStyle={{ fontSize: "12px", margin: 0, borderRadius: "6px" }}>
                        {msg.content}
                      </SyntaxHighlighter>
                    ) : (
                      <p className="text-sm text-gray-300 whitespace-pre-wrap">{msg.content}</p>
                    )}
                  </div>
                ))}
                <div ref={messagesEndRef} />
              </div>
            )}

            {activeTab === "files" && (
              <div>
                {selectedFile ? (
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-sm text-gray-400">{selectedFile}</span>
                      <button onClick={() => setSelectedFile(null)} className="text-xs text-gray-500 hover:text-white">Close</button>
                    </div>
                    <SyntaxHighlighter language="typescript" style={vscDarkPlus}
                      customStyle={{ fontSize: "12px", borderRadius: "8px" }} showLineNumbers>
                      {fileContent}
                    </SyntaxHighlighter>
                  </div>
                ) : (
                  <p className="text-gray-500">Select a file from the sidebar to view</p>
                )}
              </div>
            )}

            {activeTab === "terminal" && (
              <div className="font-mono text-xs">
                <pre className="whitespace-pre-wrap text-green-400 mb-4">{terminalOutput || "Terminal ready.\n"}</pre>
                <div className="flex gap-2">
                  <span className="text-green-400">$</span>
                  <input type="text" value={terminalInput} onChange={(e) => setTerminalInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleTerminal()}
                    className="flex-1 bg-transparent outline-none text-white"
                    placeholder="Enter command..." />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right sidebar - Chat */}
        <div className="w-80 border-l border-gray-800 flex flex-col">
          <div className="p-3 border-b border-gray-800">
            <h3 className="text-sm font-semibold text-gray-400">CHAT WITH AGENT</h3>
          </div>
          <div className="flex-1 overflow-y-auto p-3 space-y-3">
            {messages.filter(m => m.type === "message" || m.agent === "user").map((msg, i) => (
              <div key={i} className={`p-2 rounded-lg text-sm ${msg.agent === "user" ? "bg-indigo-900/30 ml-4" : "bg-gray-800 mr-4"}`}>
                <p className="text-xs text-gray-500 mb-1 capitalize">{msg.agent || "agent"}</p>
                <p>{msg.content}</p>
              </div>
            ))}
          </div>
          <div className="p-3 border-t border-gray-800">
            <div className="flex gap-2">
              <input type="text" value={chatInput} onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleChat()}
                className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-indigo-500"
                placeholder="Type a message..." />
              <button onClick={handleChat}
                className="px-3 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm transition">
                Send
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
