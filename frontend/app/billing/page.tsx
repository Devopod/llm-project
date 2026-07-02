"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { auth } from "@/lib/api";
import NavBar from "@/components/NavBar";

export default function BillingPage() {
  const router = useRouter();
  const [usage, setUsage] = useState<any>(null);
  const [plans, setPlans] = useState<any>(null);
  const [payments, setPayments] = useState<any[]>([]);
  const [showPayment, setShowPayment] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState("");
  const [txId, setTxId] = useState("");
  const [senderNum, setSenderNum] = useState("");
  const [payMsg, setPayMsg] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) { router.push("/login"); return; }
    auth.usage().then((res) => setUsage(res.data)).catch(() => {});
    auth.plans().then((res) => setPlans(res.data)).catch(() => {});
    auth.paymentHistory().then((res) => setPayments(res.data)).catch(() => {});
  }, [router]);

  const handlePaymentSubmit = async () => {
    if (!txId || !senderNum) { setPayMsg("Fill in all fields"); return; }
    setLoading(true);
    try {
      await auth.submitPayment({ plan: selectedPlan, transaction_id: txId, sender_number: senderNum });
      setPayMsg("Payment submitted! Awaiting admin verification.");
      setTxId("");
      setSenderNum("");
      setShowPayment(false);
      auth.paymentHistory().then((res) => setPayments(res.data));
    } catch (e: any) {
      setPayMsg(e.response?.data?.error || "Payment submission failed");
    } finally {
      setLoading(false);
    }
  };

  if (!usage || !plans) return <div className="min-h-screen bg-gray-950 flex items-center justify-center"><div className="animate-spin w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full" /></div>;

  return (
    <div className="min-h-screen bg-gray-950">
      <NavBar />
      <main className="max-w-5xl mx-auto px-6 py-8">
        <h1 className="text-3xl font-bold mb-8">Usage & Billing</h1>

        {/* Usage Stats */}
        <section className="mb-8 p-6 bg-gray-900 border border-gray-800 rounded-xl">
          <h2 className="text-xl font-semibold mb-4">Current Usage</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 bg-gray-800 rounded-lg">
              <p className="text-sm text-gray-400">Messages Today</p>
              <p className="text-2xl font-bold">{usage.messages_used_today} <span className="text-sm text-gray-500">/ {usage.message_limit}</span></p>
              <div className="mt-2 h-2 bg-gray-700 rounded-full overflow-hidden">
                <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${Math.min((usage.messages_used_today / usage.message_limit) * 100, 100)}%` }} />
              </div>
            </div>
            <div className="p-4 bg-gray-800 rounded-lg">
              <p className="text-sm text-gray-400">APK Builds Today</p>
              <p className="text-2xl font-bold">{usage.apk_builds_today} <span className="text-sm text-gray-500">/ {usage.apk_limit}</span></p>
              <div className="mt-2 h-2 bg-gray-700 rounded-full overflow-hidden">
                <div className="h-full bg-purple-500 rounded-full" style={{ width: `${Math.min((usage.apk_builds_today / usage.apk_limit) * 100, 100)}%` }} />
              </div>
            </div>
            <div className="p-4 bg-gray-800 rounded-lg">
              <p className="text-sm text-gray-400">Total Projects</p>
              <p className="text-2xl font-bold">{usage.total_projects}</p>
              <p className="text-sm text-gray-500 mt-1">{usage.completed_projects} completed</p>
            </div>
          </div>
          <div className="mt-4 flex items-center gap-3">
            <span className="text-sm text-gray-400">Current Plan:</span>
            <span className="px-3 py-1 bg-indigo-600/20 text-indigo-400 rounded-full text-sm font-medium capitalize">{usage.plan}</span>
          </div>
        </section>

        {/* Plans */}
        <section className="mb-8">
          <h2 className="text-xl font-semibold mb-4">Plans</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {plans.plans.map((plan: any) => (
              <div key={plan.id} className={`p-6 bg-gray-900 border rounded-xl ${usage.plan === plan.id ? 'border-indigo-500' : 'border-gray-800'}`}>
                <h3 className="text-xl font-bold">{plan.name}</h3>
                <p className="text-3xl font-bold mt-2">
                  {plan.price_usd === 0 ? "Free" : `$${plan.price_usd}`}
                  {plan.price_usd > 0 && <span className="text-sm text-gray-400">/month</span>}
                </p>
                {plan.price_bdt > 0 && <p className="text-sm text-gray-500 mt-1">{plan.price_bdt} BDT/month</p>}
                <ul className="mt-4 space-y-2">
                  {plan.features.map((f: string, i: number) => (
                    <li key={i} className="text-sm text-gray-300 flex items-center gap-2">
                      <span className="text-green-400">&#10003;</span> {f}
                    </li>
                  ))}
                </ul>
                {usage.plan === plan.id ? (
                  <button disabled className="w-full mt-4 px-4 py-2 bg-gray-700 text-gray-400 rounded-lg cursor-not-allowed">
                    Current Plan
                  </button>
                ) : plan.price_usd > 0 ? (
                  <button onClick={() => { setSelectedPlan(plan.id); setShowPayment(true); }}
                    className="w-full mt-4 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg transition">
                    Upgrade to {plan.name}
                  </button>
                ) : null}
              </div>
            ))}
          </div>
        </section>

        {/* Payment Modal */}
        {showPayment && (
          <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 max-w-md w-full">
              <h3 className="text-xl font-bold mb-4">Pay via bKash</h3>
              <div className="p-4 bg-gray-800 rounded-lg mb-4">
                <p className="text-sm text-gray-400">Send payment to:</p>
                <p className="text-2xl font-bold text-pink-400 mt-1">{plans.payment_info.number}</p>
                <p className="text-sm text-gray-400 mt-2">Amount: <span className="text-white font-bold">
                  {selectedPlan === 'pro' ? '$8 (976 BDT)' : '$20 (2440 BDT)'}
                </span></p>
                <p className="text-xs text-gray-500 mt-1">Rate: {plans.payment_info.rate}</p>
              </div>
              <div className="space-y-3">
                <input type="text" placeholder="bKash Transaction ID" value={txId}
                  onChange={(e) => setTxId(e.target.value)}
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-indigo-500" />
                <input type="text" placeholder="Your bKash Number" value={senderNum}
                  onChange={(e) => setSenderNum(e.target.value)}
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-indigo-500" />
              </div>
              {payMsg && <p className="text-sm text-green-400 mt-3">{payMsg}</p>}
              <div className="flex gap-3 mt-4">
                <button onClick={handlePaymentSubmit} disabled={loading}
                  className="flex-1 px-4 py-2 bg-pink-600 hover:bg-pink-500 disabled:opacity-50 rounded-lg transition">
                  {loading ? "Submitting..." : "Submit Payment"}
                </button>
                <button onClick={() => setShowPayment(false)}
                  className="px-4 py-2 border border-gray-700 rounded-lg hover:bg-gray-800 transition">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Payment History */}
        {payments.length > 0 && (
          <section className="mb-8">
            <h2 className="text-xl font-semibold mb-4">Payment History</h2>
            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-800">
                  <tr>
                    <th className="text-left p-3 text-gray-400">Date</th>
                    <th className="text-left p-3 text-gray-400">Plan</th>
                    <th className="text-left p-3 text-gray-400">Amount</th>
                    <th className="text-left p-3 text-gray-400">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {payments.map((p: any) => (
                    <tr key={p.id} className="border-t border-gray-800">
                      <td className="p-3">{new Date(p.created_at).toLocaleDateString()}</td>
                      <td className="p-3 capitalize">{p.plan}</td>
                      <td className="p-3">${p.amount_usd} ({p.amount_bdt} BDT)</td>
                      <td className="p-3">
                        <span className={`px-2 py-1 rounded text-xs ${
                          p.status === 'verified' ? 'bg-green-900/50 text-green-400' :
                          p.status === 'rejected' ? 'bg-red-900/50 text-red-400' :
                          'bg-yellow-900/50 text-yellow-400'
                        }`}>{p.status}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
