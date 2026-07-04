"use client";
import { useEffect, useState } from "react";
import { admin } from "@/lib/api";

export default function AdminPage() {
  const [loggedIn, setLoggedIn] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [dashboard, setDashboard] = useState<any>(null);
  const [users, setUsers] = useState<any[]>([]);
  const [payments, setPayments] = useState<any[]>([]);
  const [tab, setTab] = useState<"dashboard" | "users" | "payments">("dashboard");

  const handleLogin = async () => {
    setError("");
    try {
      const res = await admin.login({ username, password });
      localStorage.setItem("access_token", res.data.access_token);
      localStorage.setItem("refresh_token", res.data.refresh_token);
      setLoggedIn(true);
      loadData();
    } catch {
      setError("Invalid admin credentials");
    }
  };

  const loadData = async () => {
    try {
      const [d, u, p] = await Promise.all([admin.dashboard(), admin.users(), admin.payments()]);
      setDashboard(d.data);
      setUsers(u.data);
      setPayments(p.data);
    } catch {
      setError("Failed to load admin data");
    }
  };

  const handleVerifyPayment = async (id: string, action: string) => {
    try {
      await admin.verifyPayment(id, action);
      loadData();
    } catch {
      alert("Failed to process payment");
    }
  };

  const handleDeleteUser = async (id: string, email: string) => {
    if (!confirm(`Delete user ${email}? This cannot be undone.`)) return;
    try {
      await admin.deleteUser(id);
      setUsers(users.filter((u) => u.id !== id));
    } catch (e: any) {
      alert(e.response?.data?.error || "Failed to delete user");
    }
  };

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (token) {
      admin.dashboard().then((res) => {
        setDashboard(res.data);
        setLoggedIn(true);
        loadData();
      }).catch(() => {});
    }
  }, []);

  if (!loggedIn) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="w-full max-w-md p-8 bg-gray-900 border border-gray-800 rounded-xl">
          <div className="flex items-center gap-2 mb-6">
            <div className="w-8 h-8 bg-gradient-to-br from-red-500 to-orange-600 rounded-lg" />
            <span className="text-xl font-bold">AstraDev Admin</span>
          </div>
          {error && <p className="text-red-400 text-sm mb-4">{error}</p>}
          <div className="space-y-4">
            <input type="text" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)}
              className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-red-500" />
            <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleLogin()}
              className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-red-500" />
            <button onClick={handleLogin}
              className="w-full px-4 py-2 bg-red-600 hover:bg-red-500 rounded-lg transition font-medium">
              Login as Admin
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-950">
      <nav className="border-b border-gray-800 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-gradient-to-br from-red-500 to-orange-600 rounded-lg" />
          <span className="text-xl font-bold">AstraDev Admin</span>
        </div>
        <button onClick={() => { localStorage.clear(); setLoggedIn(false); }}
          className="text-gray-400 hover:text-red-400 text-sm">Logout</button>
      </nav>

      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Tabs */}
        <div className="flex gap-4 mb-8 border-b border-gray-800 pb-4">
          {(["dashboard", "users", "payments"] as const).map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 py-2 rounded-lg text-sm font-medium capitalize transition ${
                tab === t ? "bg-red-600/20 text-red-400" : "text-gray-400 hover:text-white"
              }`}>{t}</button>
          ))}
        </div>

        {/* Dashboard Tab */}
        {tab === "dashboard" && dashboard && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="p-6 bg-gray-900 border border-gray-800 rounded-xl">
              <p className="text-sm text-gray-400">Total Users</p>
              <p className="text-3xl font-bold mt-1">{dashboard.total_users}</p>
            </div>
            <div className="p-6 bg-gray-900 border border-gray-800 rounded-xl">
              <p className="text-sm text-gray-400">Active Users</p>
              <p className="text-3xl font-bold mt-1">{dashboard.active_users}</p>
            </div>
            <div className="p-6 bg-gray-900 border border-gray-800 rounded-xl">
              <p className="text-sm text-gray-400">Total Projects</p>
              <p className="text-3xl font-bold mt-1">{dashboard.total_projects}</p>
            </div>
            <div className="p-6 bg-gray-900 border border-gray-800 rounded-xl">
              <p className="text-sm text-gray-400">Pending Payments</p>
              <p className="text-3xl font-bold text-yellow-400 mt-1">{dashboard.pending_payments}</p>
            </div>
            <div className="p-6 bg-gray-900 border border-gray-800 rounded-xl col-span-full">
              <p className="text-sm text-gray-400 mb-3">Plan Distribution</p>
              <div className="flex gap-6">
                <div><span className="text-2xl font-bold">{dashboard.plan_distribution.free}</span><span className="text-gray-500 ml-1 text-sm">Free</span></div>
                <div><span className="text-2xl font-bold text-indigo-400">{dashboard.plan_distribution.pro}</span><span className="text-gray-500 ml-1 text-sm">Pro</span></div>
                <div><span className="text-2xl font-bold text-purple-400">{dashboard.plan_distribution.plus}</span><span className="text-gray-500 ml-1 text-sm">Plus</span></div>
              </div>
            </div>
          </div>
        )}

        {/* Users Tab */}
        {tab === "users" && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-800">
                  <tr>
                    <th className="text-left p-3 text-gray-400">Email</th>
                    <th className="text-left p-3 text-gray-400">Name</th>
                    <th className="text-left p-3 text-gray-400">Plan</th>
                    <th className="text-left p-3 text-gray-400">Messages</th>
                    <th className="text-left p-3 text-gray-400">Projects</th>
                    <th className="text-left p-3 text-gray-400">Joined</th>
                    <th className="text-left p-3 text-gray-400">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u: any) => (
                    <tr key={u.id} className="border-t border-gray-800">
                      <td className="p-3">{u.email}</td>
                      <td className="p-3">{u.display_name || "-"}</td>
                      <td className="p-3 capitalize">{u.plan}</td>
                      <td className="p-3">{u.total_messages_sent}</td>
                      <td className="p-3">{u.total_projects_created}</td>
                      <td className="p-3">{new Date(u.created_at).toLocaleDateString()}</td>
                      <td className="p-3">
                        {!u.is_staff && (
                          <button onClick={() => handleDeleteUser(u.id, u.email)}
                            className="text-red-400 hover:text-red-300 text-xs">Delete</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Payments Tab */}
        {tab === "payments" && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-800">
                  <tr>
                    <th className="text-left p-3 text-gray-400">Date</th>
                    <th className="text-left p-3 text-gray-400">User</th>
                    <th className="text-left p-3 text-gray-400">Plan</th>
                    <th className="text-left p-3 text-gray-400">Amount</th>
                    <th className="text-left p-3 text-gray-400">TxID</th>
                    <th className="text-left p-3 text-gray-400">Sender</th>
                    <th className="text-left p-3 text-gray-400">Status</th>
                    <th className="text-left p-3 text-gray-400">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {payments.map((p: any) => (
                    <tr key={p.id} className="border-t border-gray-800">
                      <td className="p-3">{new Date(p.created_at).toLocaleDateString()}</td>
                      <td className="p-3">{p.user_email}</td>
                      <td className="p-3 capitalize">{p.plan}</td>
                      <td className="p-3">${p.amount_usd}</td>
                      <td className="p-3 font-mono text-xs">{p.transaction_id}</td>
                      <td className="p-3">{p.sender_number}</td>
                      <td className="p-3">
                        <span className={`px-2 py-1 rounded text-xs ${
                          p.status === 'verified' ? 'bg-green-900/50 text-green-400' :
                          p.status === 'rejected' ? 'bg-red-900/50 text-red-400' :
                          'bg-yellow-900/50 text-yellow-400'
                        }`}>{p.status}</span>
                      </td>
                      <td className="p-3">
                        {p.status === 'pending' && (
                          <div className="flex gap-2">
                            <button onClick={() => handleVerifyPayment(p.id, 'verify')}
                              className="text-green-400 hover:text-green-300 text-xs">Verify</button>
                            <button onClick={() => handleVerifyPayment(p.id, 'reject')}
                              className="text-red-400 hover:text-red-300 text-xs">Reject</button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                  {payments.length === 0 && (
                    <tr><td colSpan={8} className="p-6 text-center text-gray-500">No payments yet</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
