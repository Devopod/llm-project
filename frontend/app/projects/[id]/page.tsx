"use client";
import { useEffect, useState, useRef } from "react";
import { useRouter, useParams } from "next/navigation";
import { projects as projectsApi, workspaces } from "@/lib/api";
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

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [project, setProject] = useState<Record<string, unknown> | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [activeTab, setActiveTab] = useState<"activity" | "files" | "terminal">("activity");
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState("");
  const [saveStatus, setSaveStatus] = useState<string | null>(null);
  const [terminalOutput, setTerminalOutput] = useState("");
  const [terminalInput, setTerminalInput] = useState("");
  const [deployPromptShown, setDeployPromptShown] = useState(false);
  const [deployTriggered, setDeployTriggered] = useState(false);
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
      // Check if there's an existing deploy_prompt in history
      const deployPromptIdx = msgs.findIndex((m: Message) => m.type === "deploy_prompt");
      if (deployPromptIdx >= 0) {
        setDeployPromptShown(true);
        // Only mark as triggered if there's a deployment message AFTER the prompt
        // (indicating user already clicked Approve)
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

    // Poll for project status when deploying
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
    setIsEditing(false);
    setSaveStatus(null);
    try {
      // Try new API first, fallback to workspace API
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
      setActiveTab("files");
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
    const apkPrompt = "Build an Android APK from this project. Create the necessary Android project structure with Kotlin, build.gradle, AndroidManifest.xml, and compile it into a downloadable APK file.";
    setMessages((prev) => [...prev, { type: "message", content: apkPrompt, agent: "user", timestamp: new Date().toISOString() }]);
    try {
      await projectsApi.chat(id, apkPrompt);
    } catch (e) {
      console.error(e);
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
      deployment: "D", message: "M", deploy_prompt: "🚀",
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
          {(project as any).deployment_url && (
            <a href={(project as any).deployment_url} target="_blank" rel="noopener noreferrer"
              className="text-xs px-2 py-0.5 rounded-full bg-green-900/50 border border-green-700 text-green-400 hover:bg-green-800/50 transition">
              Live: {(project as any).deployment_url}
            </a>
          )}
        </div>
        <div className="flex gap-2">
          <button onClick={() => handleDeploy('approve')} className="px-3 py-1.5 text-sm bg-purple-700 hover:bg-purple-600 rounded-lg transition">
            Deploy
          </button>
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
                      <pre className="bg-gray-900 border border-gray-700 rounded-md p-3 overflow-x-auto">
                        <code className="text-xs text-green-300 font-mono whitespace-pre-wrap">{msg.content}</code>
                      </pre>
                    ) : msg.type === "deploy_prompt" ? (
                      <div className="text-sm">
                        <p className="text-gray-300 mb-3">{msg.content}</p>
                        {!deployTriggered ? (
                          <div className="flex gap-3">
                            <button
                              onClick={() => {
                                setDeployTriggered(true);
                                handleDeploy('approve');
                              }}
                              className="px-4 py-2 bg-green-700 hover:bg-green-600 text-white rounded-lg text-sm font-medium transition">
                              Approve & Deploy
                            </button>
                            <button
                              onClick={() => setDeployTriggered(true)}
                              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg text-sm font-medium transition">
                              Skip Deployment
                            </button>
                          </div>
                        ) : (
                          <span className="text-xs text-gray-500">Deployment initiated...</span>
                        )}
                      </div>
                    ) : msg.type === "deployment" ? (
                      <div className="text-sm text-gray-300 whitespace-pre-wrap">
                        {msg.content.split(/(https?:\/\/[^\s]+)/g).map((part: string, idx: number) =>
                          part.match(/^https?:\/\//) ? (
                            <a key={idx} href={part} target="_blank" rel="noopener noreferrer"
                              className="text-green-400 underline hover:text-green-300 font-medium">{part}</a>
                          ) : <span key={idx}>{part}</span>
                        )}
                      </div>
                    ) : (
                      <p className="text-sm text-gray-300 whitespace-pre-wrap">{msg.content}</p>
                    )}
                  </div>
                ))}
                <div ref={messagesEndRef} />
              </div>
            )}

            {activeTab === "files" && (
              <div className="h-full flex flex-col">
                {selectedFile ? (
                  <div className="flex flex-col h-full">
                    <div className="flex items-center justify-between mb-3 shrink-0">
                      <span className="text-sm text-gray-400 font-mono">{selectedFile}</span>
                      <div className="flex items-center gap-2">
                        {saveStatus === "saved" && <span className="text-xs text-green-400">Saved!</span>}
                        {saveStatus === "error" && <span className="text-xs text-red-400">Save failed</span>}
                        {saveStatus === "saving" && <span className="text-xs text-yellow-400">Saving...</span>}
                        {isEditing ? (
                          <>
                            <button onClick={handleFileSave}
                              className="text-xs px-2 py-1 bg-green-700 hover:bg-green-600 rounded transition">
                              Save
                            </button>
                            <button onClick={() => { setIsEditing(false); setEditContent(fileContent); }}
                              className="text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded transition">
                              Cancel
                            </button>
                          </>
                        ) : (
                          <button onClick={() => setIsEditing(true)}
                            className="text-xs px-2 py-1 bg-indigo-700 hover:bg-indigo-600 rounded transition">
                            Edit
                          </button>
                        )}
                        <button onClick={() => setSelectedFile(null)} className="text-xs text-gray-500 hover:text-white">Close</button>
                      </div>
                    </div>
                    <div className="flex-1 overflow-auto bg-gray-900 border border-gray-700 rounded-lg">
                      {isEditing ? (
                        <div className="flex h-full">
                          <div className="py-4 px-2 text-right select-none bg-gray-950 border-r border-gray-700">
                            {editContent.split('\n').map((_, i) => (
                              <div key={i} className="text-xs font-mono text-gray-600 leading-5">{i + 1}</div>
                            ))}
                          </div>
                          <textarea
                            value={editContent}
                            onChange={(e) => setEditContent(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 's' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); handleFileSave(); } }}
                            className="flex-1 p-4 bg-transparent text-xs text-gray-200 font-mono resize-none outline-none leading-5 whitespace-pre"
                            spellCheck={false}
                          />
                        </div>
                      ) : (
                        <div className="flex syntax-view">
                          <div className="py-4 px-2 text-right select-none bg-gray-950 border-r border-gray-700">
                            {fileContent.split('\n').map((_, i) => (
                              <div key={i} className="text-xs font-mono text-gray-600 leading-5">{i + 1}</div>
                            ))}
                          </div>
                          <div className="flex-1 overflow-x-auto">
                            <SyntaxHighlighter
                              language={getLanguage(selectedFile || '')}
                              style={oneDark}
                              showLineNumbers={false}
                              customStyle={{ margin: 0, padding: '1rem', background: 'transparent', fontSize: '0.75rem', lineHeight: '1.25rem' }}
                              codeTagProps={{ style: { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' } }}
                            >
                              {fileContent}
                            </SyntaxHighlighter>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <p className="text-gray-500">Select a file from the sidebar to view and edit</p>
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
