"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { auth } from "@/lib/api";
import NavBar from "@/components/NavBar";

export default function SettingsPage() {
  const router = useRouter();
  const [profile, setProfile] = useState<any>(null);
  const [displayName, setDisplayName] = useState("");
  const [bio, setBio] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [msg, setMsg] = useState("");
  const [pwMsg, setPwMsg] = useState("");

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) { router.push("/login"); return; }
    auth.profile().then((res) => {
      setProfile(res.data);
      setDisplayName(res.data.display_name || "");
      setBio(res.data.bio || "");
    }).catch(() => router.push("/login"));
  }, [router]);

  const handleProfileUpdate = async () => {
    try {
      const res = await auth.updateProfile({ display_name: displayName, bio });
      setProfile(res.data);
      setMsg("Profile updated successfully");
      setTimeout(() => setMsg(""), 3000);
    } catch {
      setMsg("Failed to update profile");
    }
  };

  const handlePasswordChange = async () => {
    if (!currentPassword || !newPassword) { setPwMsg("Fill in both fields"); return; }
    try {
      await auth.changePassword({ current_password: currentPassword, new_password: newPassword });
      setPwMsg("Password changed successfully");
      setCurrentPassword("");
      setNewPassword("");
      setTimeout(() => setPwMsg(""), 3000);
    } catch (e: any) {
      setPwMsg(e.response?.data?.error || "Failed to change password");
    }
  };

  if (!profile) return <div className="min-h-screen bg-gray-950 flex items-center justify-center"><div className="animate-spin w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full" /></div>;

  return (
    <div className="min-h-screen bg-gray-950">
      <NavBar />
      <main className="max-w-3xl mx-auto px-6 py-8">
        <h1 className="text-3xl font-bold mb-8">Account Settings</h1>

        <div className="space-y-8">
          {/* Profile Section */}
          <section className="p-6 bg-gray-900 border border-gray-800 rounded-xl">
            <h2 className="text-xl font-semibold mb-4">Profile</h2>
            <div className="space-y-4">
              <div>
                <label className="text-sm text-gray-400 block mb-1">Email</label>
                <input type="email" value={profile.email} disabled
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-gray-500 cursor-not-allowed" />
              </div>
              <div>
                <label className="text-sm text-gray-400 block mb-1">Display Name</label>
                <input type="text" value={displayName} onChange={(e) => setDisplayName(e.target.value)}
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-indigo-500" />
              </div>
              <div>
                <label className="text-sm text-gray-400 block mb-1">Bio</label>
                <textarea value={bio} onChange={(e) => setBio(e.target.value)} rows={3}
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-indigo-500 resize-none" />
              </div>
              {msg && <p className={`text-sm ${msg.includes("success") ? "text-green-400" : "text-red-400"}`}>{msg}</p>}
              <button onClick={handleProfileUpdate}
                className="px-6 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg transition">Save Changes</button>
            </div>
          </section>

          {/* Plan Info */}
          <section className="p-6 bg-gray-900 border border-gray-800 rounded-xl">
            <h2 className="text-xl font-semibold mb-4">Subscription</h2>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-lg capitalize font-medium">{profile.plan || "free"} Plan</p>
                <p className="text-gray-400 text-sm">Manage your subscription and billing</p>
              </div>
              <button onClick={() => router.push("/billing")}
                className="px-4 py-2 border border-indigo-600 text-indigo-400 hover:bg-indigo-600 hover:text-white rounded-lg transition">
                Manage Billing
              </button>
            </div>
          </section>

          {/* Password Section */}
          <section className="p-6 bg-gray-900 border border-gray-800 rounded-xl">
            <h2 className="text-xl font-semibold mb-4">Change Password</h2>
            <div className="space-y-4">
              <div>
                <label className="text-sm text-gray-400 block mb-1">Current Password</label>
                <input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)}
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-indigo-500" />
              </div>
              <div>
                <label className="text-sm text-gray-400 block mb-1">New Password</label>
                <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-indigo-500" />
              </div>
              {pwMsg && <p className={`text-sm ${pwMsg.includes("success") ? "text-green-400" : "text-red-400"}`}>{pwMsg}</p>}
              <button onClick={handlePasswordChange}
                className="px-6 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg transition">Update Password</button>
            </div>
          </section>

          {/* Danger Zone */}
          <section className="p-6 bg-gray-900 border border-red-900/50 rounded-xl">
            <h2 className="text-xl font-semibold text-red-400 mb-4">Danger Zone</h2>
            <p className="text-gray-400 text-sm mb-4">Once you delete your account, there is no going back.</p>
            <button className="px-4 py-2 bg-red-600/20 text-red-400 border border-red-600/50 hover:bg-red-600 hover:text-white rounded-lg transition">
              Delete Account
            </button>
          </section>
        </div>
      </main>
    </div>
  );
}
