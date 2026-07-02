"use client";
import Link from "next/link";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-950 via-gray-900 to-indigo-950">
      <nav className="border-b border-gray-800 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-lg" />
          <span className="text-xl font-bold">AstraDev</span>
        </div>
        <div className="flex gap-4">
          <Link href="/login" className="px-4 py-2 text-gray-300 hover:text-white transition">
            Sign In
          </Link>
          <Link href="/signup" className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg transition">
            Get Started
          </Link>
        </div>
      </nav>

      <main className="max-w-6xl mx-auto px-6 py-24">
        <div className="text-center space-y-8">
          <h1 className="text-6xl font-bold bg-gradient-to-r from-indigo-400 via-purple-400 to-pink-400 bg-clip-text text-transparent">
            Autonomous AI Software Engineer
          </h1>
          <p className="text-xl text-gray-400 max-w-3xl mx-auto">
            AstraDev takes your idea and autonomously plans, codes, tests, debugs, and deploys
            complete applications — powered by multi-agent AI orchestration.
          </p>
          <div className="flex gap-4 justify-center">
            <Link href="/signup" className="px-8 py-3 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-lg font-medium transition">
              Start Building
            </Link>
            <Link href="/login" className="px-8 py-3 border border-gray-700 hover:border-gray-500 rounded-lg text-lg transition">
              Sign In
            </Link>
          </div>
        </div>

        <div className="mt-24 grid grid-cols-1 md:grid-cols-3 gap-8">
          {[
            { title: "Multi-Agent System", desc: "Orchestrator, Planner, Writer, Reviewer, Tester, Debugger, and Deployer agents work together autonomously." },
            { title: "Real-Time Streaming", desc: "Watch every thought, action, and line of code as agents work — streamed live via WebSocket." },
            { title: "Full-Stack Support", desc: "Python, JavaScript, TypeScript, Rust, Go, Java, PHP, C++, Kotlin — with framework detection." },
            { title: "Isolated Workspaces", desc: "Each project runs in a sandboxed environment with all runtimes pre-installed." },
            { title: "Smart Context (RAG)", desc: "Upload existing projects — agents understand your codebase and build upon it." },
            { title: "Auto Deployment", desc: "Web applications are automatically deployed with a live preview URL." },
          ].map((feature) => (
            <div key={feature.title} className="p-6 bg-gray-900/50 border border-gray-800 rounded-xl">
              <h3 className="text-lg font-semibold text-indigo-400">{feature.title}</h3>
              <p className="text-gray-400 mt-2">{feature.desc}</p>
            </div>
          ))}
        </div>

        <div className="mt-24 text-center">
          <h2 className="text-3xl font-bold mb-4">Supported Languages & Frameworks</h2>
          <div className="flex flex-wrap gap-3 justify-center">
            {["Python", "Django", "Flask", "FastAPI", "React", "Next.js", "Node.js", "Express",
              "Rust", "Go", "Java", "Spring Boot", "Kotlin", "PHP", "Laravel", "C++"].map((lang) => (
              <span key={lang} className="px-3 py-1 bg-gray-800 border border-gray-700 rounded-full text-sm">
                {lang}
              </span>
            ))}
          </div>
        </div>

        <div className="mt-24 p-8 bg-gray-900/50 border border-gray-800 rounded-xl">
          <h2 className="text-3xl font-bold mb-4 text-center">Build APK</h2>
          <p className="text-gray-400 text-center max-w-2xl mx-auto">
            AstraDev can generate Android APK files for your mobile apps.
            Simply describe your app, and the agents will create, compile, and package it
            into a downloadable APK — ready for installation on any Android device.
          </p>
        </div>
      </main>

      <footer className="border-t border-gray-800 px-6 py-8 text-center text-gray-500">
        <p>AstraDev v1.0.0 — AI Engineer: Dewan Sakibul Islam | CEO: Ayoob Mohamed Elias</p>
      </footer>
    </div>
  );
}
