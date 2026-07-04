"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { auth } from "@/lib/api";
import { useAuthStore } from "@/lib/store";

export default function SignupPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const setUser = useAuthStore((s) => s.setUser);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await auth.signup({ email, password, display_name: displayName });
      localStorage.setItem("access_token", res.data.access_token);
      localStorage.setItem("refresh_token", res.data.refresh_token);
      setUser(res.data.user);
      router.push("/dashboard");
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { error?: { message?: string } } } };
      setError(axiosErr.response?.data?.error?.message || "Signup failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-950 via-gray-900 to-indigo-950">
      <div className="w-full max-w-md p-8 bg-gray-900 border border-gray-800 rounded-xl">
        <div className="text-center mb-8">
          <div className="w-12 h-12 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl mx-auto mb-4" />
          <h1 className="text-2xl font-bold">Create your account</h1>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-900/30 border border-red-800 rounded-lg text-red-400 text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Display Name</label>
            <input type="text" value={displayName} onChange={(e) => setDisplayName(e.target.value)}
              className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-indigo-500" />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Email</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
              className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-indigo-500"
              required />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-indigo-500"
              placeholder="Min 8 chars, uppercase, lowercase, number, special"
              required />
          </div>
          <button type="submit" disabled={loading}
            className="w-full py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg font-medium transition">
            {loading ? "Creating account..." : "Create Account"}
          </button>
        </form>

        <p className="mt-6 text-center text-gray-500 text-sm">
          Already have an account?{" "}
          <Link href="/login" className="text-indigo-400 hover:text-indigo-300">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
