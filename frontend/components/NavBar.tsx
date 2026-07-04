"use client";
import { useRouter } from "next/navigation";
import Link from "next/link";

export default function NavBar() {
  const router = useRouter();

  return (
    <nav className="border-b border-gray-800 px-6 py-4 flex items-center justify-between">
      <div className="flex items-center gap-6">
        <Link href="/dashboard" className="flex items-center gap-2">
          <div className="w-8 h-8 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-lg" />
          <span className="text-xl font-bold">AstraDev</span>
        </Link>
        <div className="hidden md:flex items-center gap-4 text-sm text-gray-400">
          <Link href="/dashboard" className="hover:text-white transition">Projects</Link>
          <Link href="/docs" className="hover:text-white transition">Docs</Link>
          <Link href="/billing" className="hover:text-white transition">Billing</Link>
          <Link href="/settings" className="hover:text-white transition">Settings</Link>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <Link href="/settings" className="text-gray-400 hover:text-white text-sm transition">Account</Link>
        <button onClick={() => { localStorage.clear(); router.push("/login"); }}
          className="text-gray-400 hover:text-red-400 text-sm transition">Logout</button>
      </div>
    </nav>
  );
}
