"use client";
import NavBar from "@/components/NavBar";
import { useState } from "react";

const sections = [
  {
    id: "getting-started",
    title: "Getting Started",
    content: `AstraDev is an autonomous AI software engineering platform that takes your ideas and turns them into fully functional applications.

## How It Works

1. **Create a Project** — Describe what you want to build in natural language
2. **AI Agents Execute** — Our multi-agent system plans, codes, tests, and debugs
3. **Real-time Streaming** — Watch agents work in real-time via WebSocket
4. **Download Results** — Get your generated code as ZIP or APK

## Quick Start

1. Sign up for an account
2. Go to Dashboard → "New Project"
3. Enter your project name and description
4. Optionally enable "Build APK" for Android apps
5. Click "Start Building" and watch the magic happen`,
  },
  {
    id: "agents",
    title: "AI Agents",
    content: `AstraDev uses a hierarchical multi-agent architecture inspired by OpenHands.

## Agent Types

### Orchestrator
The master coordinator that manages the entire pipeline, delegates tasks to specialized agents, and ensures quality.

### Planner Agent
Analyzes requirements and creates a detailed execution roadmap with milestones and dependencies.

### Code Writer Agent
Generates production-quality code in 20+ programming languages with proper structure, error handling, and documentation.

### Code Reader Agent
Reads and understands existing codebases, builds AST/dependency graphs, and provides context to other agents.

### Reviewer Agent
Reviews generated code for quality, security vulnerabilities, performance issues, and best practices.

### Tester Agent
Writes and executes tests, validates functionality, and ensures code coverage meets standards.

### Debugger Agent
Identifies bugs, reads error logs, traces issues to root cause, and applies fixes automatically.

### Deployer Agent
Handles build configurations, deployment scripts, Docker setup, and production readiness.

### Terminal Agent
Executes shell commands in isolated sandboxes, runs build processes, installs dependencies.

### Browser Agent
Navigates web resources, reads documentation, gathers research data for implementation decisions.

### Git Agent
Manages version control — commits, branches, diffs, and repository operations.

### Security Agent
Scans for vulnerabilities, checks dependencies, validates input handling, ensures secure practices.`,
  },
  {
    id: "languages",
    title: "Supported Languages",
    content: `AstraDev can generate code in the following languages and frameworks:

## Languages
- Python
- JavaScript / TypeScript
- Java / Kotlin
- Go
- Rust
- C / C++
- PHP
- Ruby
- Swift
- Dart

## Frameworks
- React / Next.js
- Vue.js / Nuxt.js
- Angular
- Django / Flask / FastAPI
- Express / NestJS
- Spring Boot
- Laravel
- Flutter
- React Native
- Jetpack Compose (Android)

## Tooling
- Docker / Docker Compose
- Kubernetes manifests
- CI/CD pipelines (GitHub Actions, GitLab CI)
- Terraform / Infrastructure as Code`,
  },
  {
    id: "apk-build",
    title: "APK Build",
    content: `Build Android applications and download APK files directly from AstraDev.

## How APK Build Works

1. Enable "Build APK" when creating a project
2. Our agents generate a complete Android project (Kotlin + Jetpack Compose)
3. The build system compiles the project using Gradle
4. Download the resulting APK from the Files tab

## What's Generated

- \`app/build.gradle.kts\` — App-level build config
- \`build.gradle.kts\` — Project-level build config
- \`settings.gradle.kts\` — Project settings
- \`app/src/main/\` — Source code with Activities, Composables
- \`app/src/main/AndroidManifest.xml\` — App manifest
- \`app/src/main/res/\` — Resources, layouts, drawables

## Limitations (Free Plan)

- 3 APK builds per 24 hours
- Basic app complexity
- No Play Store signing

## Pro/Plus Plans

- 50+ APK builds per day
- Complex multi-module apps
- Custom signing keys
- Direct deployment to devices`,
  },
  {
    id: "plans",
    title: "Plans & Pricing",
    content: `## Free Plan
- 20 messages per day
- 3 APK builds per day
- Basic agent support
- Community support

## Pro Plan — $8/month (976 BDT)
- 500 messages per day
- 50 APK builds per day
- All agents unlocked
- Priority support
- Advanced RAG
- Custom deployments

## Plus Plan — $20/month (2440 BDT)
- Unlimited messages
- Unlimited APK builds
- All agents unlocked
- Priority support
- Advanced RAG
- Custom deployments
- Dedicated workspace
- API access

## Payment

We accept payments via **bKash**.

**bKash Number:** 01849691859
**Rate:** 1 USD = 122 BDT

Send the appropriate amount and submit your transaction ID on the Billing page.
Admin will verify within 24 hours.`,
  },
  {
    id: "workspace",
    title: "Workspaces",
    content: `Each project runs in an isolated workspace with full file system access.

## Features

- **Isolated Environment** — Each project gets its own container
- **File Browser** — Navigate generated files with syntax highlighting
- **Terminal Access** — Execute commands in the project context
- **Download** — Export entire workspace as ZIP
- **Persistence** — Files persist across sessions

## File Operations

The AI agents can:
- Create new files
- Modify existing files
- Delete files
- Read file contents
- Search across codebase
- Run build commands`,
  },
  {
    id: "api",
    title: "API Reference",
    content: `AstraDev exposes a REST API for programmatic access (Plus plan).

## Authentication

All API requests require a Bearer token:
\`\`\`
Authorization: Bearer <access_token>
\`\`\`

## Endpoints

### Auth
- \`POST /api/auth/signup/\` — Create account
- \`POST /api/auth/login/\` — Login
- \`GET /api/auth/profile/\` — Get profile
- \`GET /api/auth/usage/\` — Get usage stats

### Projects
- \`GET /api/projects/\` — List projects
- \`POST /api/projects/\` — Create project
- \`GET /api/projects/:id/\` — Get project
- \`DELETE /api/projects/:id/\` — Delete project
- \`GET /api/projects/:id/messages/\` — Get messages
- \`POST /api/projects/:id/chat/\` — Send message
- \`GET /api/projects/:id/files/\` — Get files

### Workspaces
- \`GET /api/workspaces/:id/files/\` — List files
- \`POST /api/workspaces/:id/download/\` — Download ZIP
- \`POST /api/workspaces/:id/execute/\` — Execute command

### WebSocket
- \`ws://host/ws/project/:id/\` — Real-time streaming`,
  },
];

export default function DocsPage() {
  const [activeSection, setActiveSection] = useState("getting-started");

  return (
    <div className="min-h-screen bg-gray-950">
      <NavBar />
      <div className="flex max-w-7xl mx-auto">
        {/* Sidebar */}
        <aside className="hidden lg:block w-64 border-r border-gray-800 p-6 sticky top-0 h-screen overflow-y-auto">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">Documentation</h2>
          <nav className="space-y-1">
            {sections.map((s) => (
              <button key={s.id} onClick={() => setActiveSection(s.id)}
                className={`block w-full text-left px-3 py-2 rounded-lg text-sm transition ${
                  activeSection === s.id ? "bg-indigo-600/20 text-indigo-400" : "text-gray-400 hover:text-white hover:bg-gray-800"
                }`}>
                {s.title}
              </button>
            ))}
          </nav>
        </aside>

        {/* Mobile nav */}
        <div className="lg:hidden w-full px-6 pt-4">
          <select value={activeSection} onChange={(e) => setActiveSection(e.target.value)}
            className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white">
            {sections.map((s) => (
              <option key={s.id} value={s.id}>{s.title}</option>
            ))}
          </select>
        </div>

        {/* Content */}
        <main className="flex-1 px-6 lg:px-12 py-8 overflow-y-auto">
          {sections.filter((s) => s.id === activeSection).map((section) => (
            <article key={section.id} className="prose prose-invert max-w-none">
              <h1 className="text-3xl font-bold mb-6">{section.title}</h1>
              <div className="space-y-4 text-gray-300 leading-relaxed whitespace-pre-line">
                {section.content.split('\n').map((line, i) => {
                  if (line.startsWith('## ')) return <h2 key={i} className="text-xl font-bold text-white mt-6 mb-3">{line.replace('## ', '')}</h2>;
                  if (line.startsWith('### ')) return <h3 key={i} className="text-lg font-semibold text-white mt-4 mb-2">{line.replace('### ', '')}</h3>;
                  if (line.startsWith('- ')) return <li key={i} className="ml-4 text-gray-300">{line.replace('- ', '')}</li>;
                  if (line.startsWith('```')) return null;
                  if (line.trim() === '') return <br key={i} />;
                  return <p key={i} className="text-gray-300">{line}</p>;
                })}
              </div>
            </article>
          ))}
        </main>
      </div>
    </div>
  );
}
