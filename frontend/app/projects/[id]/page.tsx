"use client";
import { useEffect, useState, useRef, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import { projects as projectsApi, workspaces, apk as apkApi } from "@/lib/api";
import { ProjectWebSocket } from "@/lib/websocket";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

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

type RightTab = "code" | "terminal" | "browser" | "planner" | "tasks";

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [project, setProject] = useState<Record<string, unknown> | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [rightTab, setRightTab] = useState<RightTab>("code");
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState("");
  const [saveStatus, setSaveStatus] = useState<string | null>(null);
  const [terminalOutput, setTerminalOutput] = useState("");
  const [terminalInput, setTerminalInput] = useState("");
  const [deployPromptShown, setDeployPromptShown] = useState(false);
  const [deployTriggered, setDeployTriggered] = useState(false);
  const [leftPanelWidth, setLeftPanelWidth] = useState(45);
  const [isDragging, setIsDragging] = useState(false);
  const [showFileTree, setShowFileTree] = useState(true);
  const [chatAttachments, setChatAttachments] = useState<File[]>([]);
  const [apkBuilding, setApkBuilding] = useState(false);
  const [apkReady, setApkReady] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<ProjectWebSocket | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const chatFileRef = useRef<HTMLInputElement>(null);

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
      const deployPromptIdx = msgs.findIndex((m: Message) => m.type === "deploy_prompt");
      if (deployPromptIdx >= 0) {
        setDeployPromptShown(true);
        const hasPostPromptDeploy = msgs.slice(deployPromptIdx + 1).some(
          (m: Message) => m.type === "deployment"
        );
        if (hasPostPromptDeploy) {
          setDeployTriggered(true);
        }
      }
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
      if (msg.type === "deployment") {
        projectsApi.get(id).then((res) => setProject(res.data)).catch(() => {});
      }
      if (msg.type === "deploy_prompt") {
        setDeployPromptShown(true);
      }
    });

    const pollInterval = setInterval(() => {
      projectsApi.get(id).then((res) => {
        setProject((prev: any) => {
          if (prev?.status === 'deploying' && res.data.status !== 'deploying') {
            projectsApi.messages(id).then((r) => {
              const msgs = r.data.map((m: Record<string, unknown>) => ({
                type: m.message_type as string,
                content: m.content as string,
                agent: m.role as string,
                timestamp: m.created_at as string,
              }));
              setMessages(msgs);
            }).catch(() => {});
          }
          return res.data;
        });
      }).catch(() => {});
    }, 5000);
    ws.connect();
    wsRef.current = ws;

    return () => { ws.disconnect(); clearInterval(pollInterval); };
  }, [id, router]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Resize handler
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  useEffect(() => {
    if (!isDragging) return;
    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      setLeftPanelWidth(Math.min(80, Math.max(25, pct)));
    };
    const handleMouseUp = () => setIsDragging(false);
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => { window.removeEventListener("mousemove", handleMouseMove); window.removeEventListener("mouseup", handleMouseUp); };
  }, [isDragging]);

  const loadFiles = () => {
    workspaces.files(id).then((res) => setFiles(res.data.files || [])).catch(() => {});
  };

  const handleChat = async () => {
    if (!chatInput.trim() && chatAttachments.length === 0) return;
    const content = chatInput.trim();
    const msg: Message = { type: "message", content: content || `[Attached ${chatAttachments.length} file(s)]`, agent: "user", timestamp: new Date().toISOString() };
    setMessages((prev) => [...prev, msg]);
    setChatInput("");

    if (chatAttachments.length > 0) {
      try {
        await projectsApi.upload(chatAttachments, undefined, content || undefined);
        setChatAttachments([]);
        loadFiles();
      } catch (e) {
        console.error(e);
      }
    } else {
      try {
        await projectsApi.chat(id, content);
      } catch (e) {
        console.error(e);
      }
    }
  };

  const handleFileClick = async (path: string) => {
    setSelectedFile(path);
    setIsEditing(false);
    setSaveStatus(null);
    try {
      let content = "";
      try {
        const res = await projectsApi.fileContent(id, path);
        content = res.data.content;
      } catch {
        const res = await workspaces.fileContent(id, path);
        content = res.data.content;
      }
      setFileContent(content);
      setEditContent(content);
      setRightTab("code");
    } catch {
      setFileContent("Error loading file");
      setEditContent("");
    }
  };

  const handleFileSave = async () => {
    if (!selectedFile) return;
    setSaveStatus("saving");
    try {
      const res = await projectsApi.editFile(id, selectedFile, editContent);
      setFileContent(res.data.content);
      setSaveStatus("saved");
      setIsEditing(false);
      setTimeout(() => setSaveStatus(null), 2000);
    } catch {
      setSaveStatus("error");
      setTimeout(() => setSaveStatus(null), 3000);
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
    setApkBuilding(true);
    setApkReady(false);
    setMessages((prev) => [...prev, { type: "message", content: "Building Android APK (Java)...", agent: "user", timestamp: new Date().toISOString() }]);
    try {
      const res = await apkApi.build(id, `Build an Android APK for: ${(project as Record<string, string>)?.name || "this project"}`);
      if (res.data.status === "success") {
        setApkReady(true);
        setMessages((prev) => [...prev, { type: "success", content: "APK built successfully! Click 'Download APK' to get the file.", agent: "deployer", timestamp: new Date().toISOString() }]);
      } else {
        setMessages((prev) => [...prev, { type: "action", content: res.data.message || "APK build completed. Download as ZIP to build locally.", agent: "deployer", timestamp: new Date().toISOString() }]);
      }
    } catch (e) {
      console.error(e);
      setMessages((prev) => [...prev, { type: "error", content: "APK build failed. Check the activity log for details.", agent: "deployer", timestamp: new Date().toISOString() }]);
    } finally {
      setApkBuilding(false);
    }
  };

  const handleDownloadApk = async () => {
    try {
      const res = await apkApi.download(id);
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement("a");
      link.href = url;
      const name = (project as Record<string, string>)?.name || "app";
      link.setAttribute("download", `${name}.apk`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch {
      // If no APK, try downloading ZIP instead
      try {
        const res = await apkApi.download(id);
        const url = window.URL.createObjectURL(new Blob([res.data]));
        const link = document.createElement("a");
        link.href = url;
        link.setAttribute("download", `${(project as Record<string, string>)?.name || "project"}-android.zip`);
        document.body.appendChild(link);
        link.click();
        link.remove();
      } catch (e2) {
        console.error(e2);
      }
    }
  };

  const getLanguage = (path: string): string => {
    const ext = path.split('.').pop()?.toLowerCase() || '';
    const langMap: Record<string, string> = {
      py: 'python', js: 'javascript', ts: 'typescript', tsx: 'tsx', jsx: 'jsx',
      html: 'html', htm: 'html', css: 'css', scss: 'scss', less: 'less',
      json: 'json', yaml: 'yaml', yml: 'yaml', xml: 'xml', svg: 'xml',
      md: 'markdown', sh: 'bash', bash: 'bash', zsh: 'bash',
      java: 'java', kt: 'kotlin', kts: 'kotlin', swift: 'swift',
      go: 'go', rs: 'rust', rb: 'ruby', php: 'php',
      c: 'c', cpp: 'cpp', h: 'c', hpp: 'cpp',
      cs: 'csharp', sql: 'sql', r: 'r',
      dart: 'dart', lua: 'lua', perl: 'perl', pl: 'perl',
      toml: 'toml', ini: 'ini', cfg: 'ini',
      dockerfile: 'docker', makefile: 'makefile',
      graphql: 'graphql', gql: 'graphql',
      txt: 'text',
    };
    const name = path.split('/').pop()?.toLowerCase() || '';
    if (name === 'dockerfile') return 'docker';
    if (name === 'makefile') return 'makefile';
    if (name.startsWith('.env')) return 'bash';
    if (name === '.gitignore' || name === '.dockerignore') return 'bash';
    return langMap[ext] || 'text';
  };

  const handleDeploy = async (action: 'approve' | 'deny') => {
    try {
      const res = await projectsApi.deploy(id, action);
      setMessages((prev) => [...prev, {
        type: "deployment",
        content: res.data.message,
        agent: "deployer",
        timestamp: new Date().toISOString(),
      }]);
      if (action === 'approve') {
        setProject((prev: any) => prev ? { ...prev, status: 'deploying' } : prev);
      }
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
      deployment: "D", message: "M", deploy_prompt: "R",
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
      deploy_prompt: "border-purple-500",
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

  const getFileIcon = (path: string) => {
    const ext = path.split('.').pop()?.toLowerCase() || '';
    const name = path.split('/').pop()?.toLowerCase() || '';
    if (name === 'dockerfile') return 'D';
    if (name === 'makefile') return 'M';
    if (name.endsWith('.py')) return 'Py';
    if (name.endsWith('.js') || name.endsWith('.jsx')) return 'JS';
    if (name.endsWith('.ts') || name.endsWith('.tsx')) return 'TS';
    if (name.endsWith('.html') || name.endsWith('.htm')) return 'H';
    if (name.endsWith('.css') || name.endsWith('.scss')) return 'C';
    if (name.endsWith('.json')) return 'J';
    if (name.endsWith('.md')) return 'M';
    if (name.endsWith('.yaml') || name.endsWith('.yml')) return 'Y';
    return 'F';
  };

  const getFileIconColor = (path: string) => {
    const ext = path.split('.').pop()?.toLowerCase() || '';
    const colors: Record<string, string> = {
      py: 'text-blue-400', js: 'text-yellow-400', jsx: 'text-yellow-400',
      ts: 'text-blue-500', tsx: 'text-blue-500', html: 'text-orange-400',
      css: 'text-pink-400', scss: 'text-pink-400', json: 'text-green-400',
      md: 'text-gray-300', yaml: 'text-red-400', yml: 'text-red-400',
    };
    return colors[ext] || 'text-gray-400';
  };

  if (!project) return <div className="min-h-screen flex items-center justify-center text-gray-400">Loading...</div>;

  const proj = project as Record<string, any>;

  return (
    <div className="h-screen flex flex-col bg-gray-950 text-white">
      {/* Top bar - OpenHands style */}
      <div className="h-12 border-b border-gray-800 px-4 flex items-center justify-between shrink-0 bg-gray-900/50">
        <div className="flex items-center gap-3">
          <button onClick={() => router.push("/dashboard")} className="text-gray-400 hover:text-white transition p-1">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <div className="w-6 h-6 bg-gradient-to-br from-indigo-500 to-purple-600 rounded flex items-center justify-center">
            <svg className="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
            </svg>
          </div>
          <span className="font-semibold text-sm">{proj.name}</span>
          <span className={`text-xs px-2 py-0.5 rounded-full border capitalize ${
            proj.status === "completed" ? "border-green-700 text-green-400 bg-green-900/20" :
            proj.status === "executing" || proj.status === "in_progress" ? "border-blue-700 text-blue-400 bg-blue-900/20" :
            proj.status === "failed" ? "border-red-700 text-red-400 bg-red-900/20" :
            "border-gray-700 text-gray-400"
          }`}>{proj.status}</span>
          {proj.deployment_url && (
            <a href={proj.deployment_url} target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full bg-green-900/30 border border-green-700 text-green-400 hover:bg-green-800/40 transition">
              <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" />
              Live
            </a>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => handleDeploy('approve')} className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-purple-700 hover:bg-purple-600 rounded-lg transition font-medium">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            Deploy
          </button>
          <button onClick={handleBuildApk} disabled={apkBuilding}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-green-700 hover:bg-green-600 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition font-medium">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
            </svg>
            {apkBuilding ? "Building..." : "Build APK"}
          </button>
          {apkReady && (
            <button onClick={handleDownloadApk} className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-emerald-600 hover:bg-emerald-500 rounded-lg transition font-medium animate-pulse">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Download APK
            </button>
          )}
          <button onClick={handleDownload} className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg transition font-medium">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            ZIP
          </button>
        </div>
      </div>

      {/* Main split layout - OpenHands style */}
      <div ref={containerRef} className="flex-1 flex overflow-hidden" style={{ cursor: isDragging ? 'col-resize' : 'auto' }}>
        {/* LEFT: Chat + Activity Panel */}
        <div className="flex flex-col overflow-hidden bg-gray-950" style={{ width: `${leftPanelWidth}%`, transition: isDragging ? 'none' : 'width 0.3s' }}>
          {/* Messages area */}
          <div className="flex-1 overflow-y-auto">
            <div className="p-4 space-y-3">
              {messages.length === 0 && (
                <div className="text-center py-16">
                  <div className="w-16 h-16 mx-auto mb-4 bg-gradient-to-br from-indigo-500/20 to-purple-600/20 rounded-2xl flex items-center justify-center border border-indigo-500/20">
                    <svg className="w-8 h-8 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                    </svg>
                  </div>
                  <p className="text-gray-400 text-sm">Chat with the AI agent to modify your project</p>
                  <p className="text-gray-600 text-xs mt-1">Upload files, request changes, or ask questions</p>
                </div>
              )}
              {messages.map((msg, i) => (
                <div key={i} className={`group relative ${msg.agent === "user" ? "flex justify-end" : ""}`}>
                  {msg.agent === "user" ? (
                    <div className="max-w-[85%] px-4 py-2.5 rounded-2xl rounded-br-md bg-indigo-600/80 text-sm">
                      <p className="whitespace-pre-wrap">{msg.content}</p>
                      <p className="text-xs text-indigo-300/60 mt-1 text-right">
                        {msg.timestamp && new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </p>
                    </div>
                  ) : msg.type === "deploy_prompt" ? (
                    <div className="bg-purple-900/20 border border-purple-800/40 rounded-xl p-4">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="w-6 h-6 rounded-full bg-purple-600/30 flex items-center justify-center">
                          <svg className="w-3.5 h-3.5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                          </svg>
                        </div>
                        <span className="text-xs font-medium text-purple-300">Deployment Ready</span>
                      </div>
                      <p className="text-sm text-gray-300 mb-3">{msg.content}</p>
                      {!deployTriggered ? (
                        <div className="flex gap-2">
                          <button onClick={() => { setDeployTriggered(true); handleDeploy('approve'); }}
                            className="px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg text-sm font-medium transition flex items-center gap-1.5">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                            </svg>
                            Approve & Deploy
                          </button>
                          <button onClick={() => setDeployTriggered(true)}
                            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg text-sm transition">
                            Skip
                          </button>
                        </div>
                      ) : (
                        <span className="text-xs text-gray-500 flex items-center gap-1.5">
                          <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                          </svg>
                          Deployment initiated...
                        </span>
                      )}
                    </div>
                  ) : msg.type === "deployment" ? (
                    <div className="bg-green-900/10 border border-green-800/30 rounded-xl p-3">
                      <div className="flex items-center gap-2 mb-1">
                        <div className="w-5 h-5 rounded-full bg-green-600/30 flex items-center justify-center">
                          <svg className="w-3 h-3 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                        </div>
                        <span className="text-xs font-medium text-green-300">Deployment</span>
                      </div>
                      <div className="text-sm text-gray-300 whitespace-pre-wrap">
                        {msg.content.split(/(https?:\/\/[^\s]+)/g).map((part: string, idx: number) =>
                          part.match(/^https?:\/\//) ? (
                            <a key={idx} href={part} target="_blank" rel="noopener noreferrer"
                              className="text-green-400 underline hover:text-green-300 font-medium">{part}</a>
                          ) : <span key={idx}>{part}</span>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className={`flex gap-3 ${msg.type === "error" ? "bg-red-900/10 border border-red-800/30 rounded-xl p-3" : ""}`}>
                      <div className={`w-6 h-6 shrink-0 rounded-full flex items-center justify-center text-[10px] font-bold ${
                        msg.type === "success" ? "bg-green-600/30 text-green-400" :
                        msg.type === "error" ? "bg-red-600/30 text-red-400" :
                        msg.type === "code" ? "bg-emerald-600/30 text-emerald-400" :
                        msg.type === "plan" ? "bg-blue-600/30 text-blue-400" :
                        msg.type === "thinking" ? "bg-yellow-600/30 text-yellow-400" :
                        msg.type === "action" ? "bg-indigo-600/30 text-indigo-400" :
                        "bg-gray-700/50 text-gray-400"
                      }`}>
                        {messageIcon(msg.type)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-0.5">
                          <span className="text-xs font-medium text-gray-400 capitalize">{msg.agent || "system"}</span>
                          {msg.timestamp && <span className="text-[10px] text-gray-600">{new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>}
                        </div>
                        {msg.type === "code" ? (
                          <pre className="bg-gray-900 border border-gray-800 rounded-lg p-3 overflow-x-auto mt-1">
                            <code className="text-xs text-green-300 font-mono whitespace-pre-wrap">{msg.content}</code>
                          </pre>
                        ) : (
                          <p className="text-sm text-gray-300 whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Chat input - OpenHands style with attachment */}
          <div className="shrink-0 border-t border-gray-800 bg-gray-900/30">
            {chatAttachments.length > 0 && (
              <div className="px-4 pt-2 flex gap-2 flex-wrap">
                {chatAttachments.map((f, i) => (
                  <div key={i} className="flex items-center gap-1.5 px-2 py-1 bg-gray-800 rounded-lg text-xs text-gray-300">
                    <svg className="w-3 h-3 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    {f.name}
                    <button onClick={() => setChatAttachments(prev => prev.filter((_, j) => j !== i))} className="text-gray-500 hover:text-red-400">
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div className="p-3 flex items-end gap-2">
              <button onClick={() => chatFileRef.current?.click()}
                className="p-2 text-gray-400 hover:text-indigo-400 hover:bg-gray-800 rounded-lg transition" title="Attach files">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                </svg>
              </button>
              <input ref={chatFileRef} type="file" multiple
                accept=".zip,.7z,.tar.gz,.tgz,.py,.js,.ts,.tsx,.jsx,.html,.htm,.css,.scss,.json,.yaml,.yml,.xml,.md,.txt,.java,.kt,.swift,.go,.rs,.rb,.php,.c,.cpp,.h,.hpp,.cs,.sql,.sh,.bash,.toml,.ini,.cfg,.dockerfile,.makefile,.gradle,.vue,.svelte,.dart,.lua,.pl,.r,.graphql"
                onChange={(e) => {
                  const selected = Array.from(e.target.files || []);
                  if (selected.length > 0) setChatAttachments(prev => [...prev, ...selected]);
                  e.target.value = '';
                }}
                className="hidden" />
              <div className="flex-1 relative">
                <textarea value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleChat(); } }}
                  className="w-full px-4 py-2.5 bg-gray-800 border border-gray-700 rounded-xl text-sm focus:outline-none focus:border-indigo-500 resize-none min-h-[40px] max-h-[120px] pr-12"
                  placeholder="Type a message... (Shift+Enter for new line)"
                  rows={1}
                  style={{ height: 'auto' }}
                  onInput={(e) => {
                    const target = e.target as HTMLTextAreaElement;
                    target.style.height = 'auto';
                    target.style.height = Math.min(target.scrollHeight, 120) + 'px';
                  }}
                />
              </div>
              <button onClick={handleChat}
                disabled={!chatInput.trim() && chatAttachments.length === 0}
                className="p-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-30 disabled:hover:bg-indigo-600 rounded-xl transition">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        {/* Resize handle */}
        <div onMouseDown={handleMouseDown}
          className="w-1 hover:w-1.5 bg-gray-800 hover:bg-indigo-500/50 cursor-col-resize transition-all shrink-0 relative group">
          <div className="absolute inset-y-0 -left-1 -right-1" />
        </div>

        {/* RIGHT: Tabs Panel - OpenHands style */}
        <div className="flex-1 flex flex-col overflow-hidden bg-gray-950">
          {/* Tab navigation */}
          <div className="h-10 border-b border-gray-800 flex items-center px-2 shrink-0 bg-gray-900/30">
            <div className="flex items-center gap-1">
              {([
                { key: "code" as RightTab, label: "Code", icon: (
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                  </svg>
                )},
                { key: "terminal" as RightTab, label: "Terminal", icon: (
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                )},
                { key: "browser" as RightTab, label: "Browser", icon: (
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
                  </svg>
                )},
                { key: "planner" as RightTab, label: "Planner", icon: (
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
                  </svg>
                )},
                { key: "tasks" as RightTab, label: "Tasks", icon: (
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
                  </svg>
                )},
              ]).map(({ key, label, icon }) => (
                <button key={key} onClick={() => setRightTab(key)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition ${
                    rightTab === key ? "bg-gray-800 text-white" : "text-gray-500 hover:text-gray-300 hover:bg-gray-800/50"
                  }`}>
                  {icon}
                  {label}
                </button>
              ))}
            </div>
            {rightTab === "code" && (
              <button onClick={() => setShowFileTree(!showFileTree)}
                className="ml-auto p-1.5 text-gray-500 hover:text-white hover:bg-gray-800 rounded transition" title="Toggle file tree">
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h7" />
                </svg>
              </button>
            )}
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-hidden">
            {/* Code tab */}
            {rightTab === "code" && (
              <div className="h-full flex">
                {/* File tree sidebar */}
                {showFileTree && (
                  <div className="w-56 border-r border-gray-800 overflow-y-auto bg-gray-900/30">
                    <div className="p-2">
                      <div className="flex items-center justify-between px-2 py-1.5 mb-1">
                        <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">Explorer</span>
                      </div>
                      <div className="space-y-0.5">
                        {files.filter(f => !f.is_dir).slice(0, 50).map((file) => (
                          <div key={file.path}
                            onClick={() => handleFileClick(file.path)}
                            className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer text-xs transition ${
                              selectedFile === file.path ? "bg-indigo-600/20 text-white" : "text-gray-400 hover:text-white hover:bg-gray-800/50"
                            }`}>
                            <span className={`text-[10px] font-mono font-bold ${getFileIconColor(file.path)}`}>{getFileIcon(file.path)}</span>
                            <span className="truncate">{file.path.split('/').pop()}</span>
                          </div>
                        ))}
                        {files.length === 0 && <p className="text-xs text-gray-600 px-2 py-4">No files yet</p>}
                      </div>
                    </div>
                  </div>
                )}

                {/* Code viewer */}
                <div className="flex-1 flex flex-col overflow-hidden">
                  {selectedFile ? (
                    <>
                      <div className="h-9 border-b border-gray-800 flex items-center justify-between px-3 shrink-0 bg-gray-900/30">
                        <div className="flex items-center gap-2">
                          <span className={`text-[10px] font-mono font-bold ${getFileIconColor(selectedFile)}`}>{getFileIcon(selectedFile)}</span>
                          <span className="text-xs text-gray-300 font-mono">{selectedFile}</span>
                          {saveStatus === "saved" && <span className="text-[10px] text-green-400 font-medium">Saved!</span>}
                          {saveStatus === "error" && <span className="text-[10px] text-red-400 font-medium">Save failed</span>}
                          {saveStatus === "saving" && <span className="text-[10px] text-yellow-400 font-medium">Saving...</span>}
                        </div>
                        <div className="flex items-center gap-1.5">
                          {isEditing ? (
                            <>
                              <button onClick={handleFileSave}
                                className="text-[10px] px-2 py-0.5 bg-green-700 hover:bg-green-600 rounded transition font-medium">
                                Save
                              </button>
                              <button onClick={() => { setIsEditing(false); setEditContent(fileContent); }}
                                className="text-[10px] px-2 py-0.5 bg-gray-700 hover:bg-gray-600 rounded transition">
                                Cancel
                              </button>
                            </>
                          ) : (
                            <button onClick={() => setIsEditing(true)}
                              className="text-[10px] px-2 py-0.5 bg-indigo-700 hover:bg-indigo-600 rounded transition font-medium">
                              Edit
                            </button>
                          )}
                          <button onClick={() => setSelectedFile(null)} className="text-gray-500 hover:text-white p-0.5 transition">
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                          </button>
                        </div>
                      </div>
                      <div className="flex-1 overflow-auto bg-[#282c34]">
                        {isEditing ? (
                          <div className="flex h-full">
                            <div className="py-4 px-2 text-right select-none bg-[#21252b] border-r border-gray-700/50">
                              {editContent.split('\n').map((_, i) => (
                                <div key={i} className="text-[11px] font-mono text-gray-600 leading-5">{i + 1}</div>
                              ))}
                            </div>
                            <textarea value={editContent} onChange={(e) => setEditContent(e.target.value)}
                              onKeyDown={(e) => { if (e.key === 's' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); handleFileSave(); } }}
                              className="flex-1 p-4 bg-transparent text-[11px] text-gray-200 font-mono resize-none outline-none leading-5 whitespace-pre"
                              spellCheck={false} />
                          </div>
                        ) : (
                          <SyntaxHighlighter language={getLanguage(selectedFile)} style={oneDark} showLineNumbers
                            customStyle={{ margin: 0, padding: '0.5rem 0', background: 'transparent', fontSize: '0.7rem', lineHeight: '1.25rem' }}
                            lineNumberStyle={{ minWidth: '2.5em', paddingRight: '1em', color: '#636d83', fontSize: '0.7rem' }}
                            codeTagProps={{ style: { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' } }}>
                            {fileContent}
                          </SyntaxHighlighter>
                        )}
                      </div>
                    </>
                  ) : (
                    <div className="flex-1 flex items-center justify-center text-gray-600">
                      <div className="text-center">
                        <svg className="w-12 h-12 mx-auto mb-3 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                        </svg>
                        <p className="text-sm">Select a file to view</p>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Terminal tab */}
            {rightTab === "terminal" && (
              <div className="h-full flex flex-col bg-[#1a1b26] p-4 font-mono text-sm">
                <div className="flex-1 overflow-y-auto">
                  <pre className="whitespace-pre-wrap text-green-400">{terminalOutput || "$ Welcome to AstraDev Terminal\n$ Type commands to interact with your project workspace\n\n"}</pre>
                </div>
                <div className="flex items-center gap-2 mt-2 border-t border-gray-800 pt-2">
                  <span className="text-green-400 text-xs font-bold">$</span>
                  <input type="text" value={terminalInput} onChange={(e) => setTerminalInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleTerminal()}
                    className="flex-1 bg-transparent outline-none text-white text-xs"
                    placeholder="Enter command..." />
                </div>
              </div>
            )}

            {/* Browser tab */}
            {rightTab === "browser" && (
              <div className="h-full flex flex-col">
                {proj.deployment_url ? (
                  <>
                    <div className="h-9 border-b border-gray-800 flex items-center px-3 bg-gray-900/30">
                      <div className="flex-1 flex items-center gap-2 bg-gray-800 rounded-md px-3 py-1">
                        <svg className="w-3 h-3 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" clipRule="evenodd" />
                        </svg>
                        <span className="text-xs text-gray-400 truncate">{proj.deployment_url}</span>
                      </div>
                      <a href={proj.deployment_url} target="_blank" rel="noopener noreferrer"
                        className="ml-2 p-1 text-gray-500 hover:text-white transition">
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                        </svg>
                      </a>
                    </div>
                    <div className="flex-1 bg-white">
                      <iframe src={proj.deployment_url} className="w-full h-full border-0" title="Deployed App Preview"
                        sandbox="allow-scripts allow-same-origin allow-forms allow-popups" />
                    </div>
                  </>
                ) : (
                  <div className="flex-1 flex items-center justify-center text-gray-600">
                    <div className="text-center">
                      <svg className="w-12 h-12 mx-auto mb-3 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
                      </svg>
                      <p className="text-sm">No deployment yet</p>
                      <p className="text-xs text-gray-700 mt-1">Deploy your project to see the live preview here</p>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Planner tab */}
            {rightTab === "planner" && (
              <div className="h-full overflow-y-auto p-4">
                <div className="space-y-4">
                  {messages.filter(m => m.type === "plan").length > 0 ? (
                    messages.filter(m => m.type === "plan").map((msg, i) => (
                      <div key={i} className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
                        <div className="flex items-center gap-2 mb-2">
                          <div className="w-5 h-5 rounded-full bg-blue-600/30 flex items-center justify-center">
                            <svg className="w-3 h-3 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                            </svg>
                          </div>
                          <span className="text-xs font-medium text-blue-300 capitalize">{msg.agent || "planner"}</span>
                          {msg.timestamp && <span className="text-[10px] text-gray-600">{new Date(msg.timestamp).toLocaleTimeString()}</span>}
                        </div>
                        <p className="text-sm text-gray-300 whitespace-pre-wrap">{msg.content}</p>
                      </div>
                    ))
                  ) : (
                    <div className="flex items-center justify-center h-full text-gray-600">
                      <div className="text-center">
                        <svg className="w-12 h-12 mx-auto mb-3 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                        </svg>
                        <p className="text-sm">No plans yet</p>
                        <p className="text-xs text-gray-700 mt-1">Plans will appear here when the agent starts working</p>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Tasks tab */}
            {rightTab === "tasks" && (
              <div className="h-full overflow-y-auto p-4">
                <div className="space-y-2">
                  {tasks.length > 0 ? tasks.map((task) => (
                    <div key={task.id} className="bg-gray-900/50 border border-gray-800 rounded-lg p-3">
                      <div className="flex items-center gap-3">
                        <div className={`w-5 h-5 rounded flex items-center justify-center text-[10px] font-bold ${
                          task.status === "completed" ? "bg-green-600/30 text-green-400" :
                          task.status === "in_progress" ? "bg-blue-600/30 text-blue-400" :
                          task.status === "failed" ? "bg-red-600/30 text-red-400" :
                          "bg-gray-700/50 text-gray-500"
                        }`}>
                          {taskStatusIcon(task.status)}
                        </div>
                        <div className="flex-1">
                          <p className="text-sm text-gray-300">{task.title}</p>
                          <div className="flex items-center gap-3 mt-1">
                            <span className={`text-[10px] capitalize ${taskStatusColor(task.status)}`}>{task.status}</span>
                            {task.assigned_agent && <span className="text-[10px] text-gray-600">{task.assigned_agent}</span>}
                          </div>
                        </div>
                      </div>
                    </div>
                  )) : (
                    <div className="flex items-center justify-center h-full text-gray-600">
                      <div className="text-center">
                        <svg className="w-12 h-12 mx-auto mb-3 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
                        </svg>
                        <p className="text-sm">No tasks yet</p>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
