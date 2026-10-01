import { motion } from 'framer-motion';
import { useState, type FormEvent } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { inputClass, labelClass, Button } from '../components/primitives';

const features = [
  { icon: '🤖', title: 'AI screening', text: 'Every form response scored against the job description.' },
  { icon: '🎙️', title: 'Interview tracking', text: 'Round-by-round feedback with audio recordings.' },
  { icon: '👑', title: 'Executive review', text: 'One dossier, one decision — approve or reject.' },
];

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email.trim(), password);
      const from = (location.state as { from?: string } | null)?.from ?? '/';
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-surface-950 px-4">
      {/* Animated background */}
      <div className="pointer-events-none absolute inset-0">
        <motion.div
          animate={{ x: [0, 40, 0], y: [0, -30, 0] }}
          transition={{ duration: 18, repeat: Infinity, ease: 'easeInOut' }}
          className="absolute -left-32 top-1/4 h-96 w-96 rounded-full bg-indigo-600/25 blur-[130px]"
        />
        <motion.div
          animate={{ x: [0, -40, 0], y: [0, 30, 0] }}
          transition={{ duration: 22, repeat: Infinity, ease: 'easeInOut' }}
          className="absolute -right-32 bottom-1/4 h-96 w-96 rounded-full bg-violet-600/20 blur-[130px]"
        />
        <motion.div
          animate={{ opacity: [0.3, 0.7, 0.3] }}
          transition={{ duration: 6, repeat: Infinity, ease: 'easeInOut' }}
          className="absolute left-1/2 top-10 h-64 w-64 -translate-x-1/2 rounded-full bg-fuchsia-500/10 blur-[110px]"
        />
      </div>

      <div className="relative z-10 grid w-full max-w-5xl items-center gap-10 lg:grid-cols-2">
        {/* Brand panel */}
        <motion.div
          initial={{ opacity: 0, x: -30 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
          className="hidden lg:block"
        >
          <div className="mb-8 flex h-16 w-16 items-center justify-center rounded-3xl bg-gradient-to-br from-indigo-500 via-violet-500 to-fuchsia-500 text-3xl shadow-glow">
            ⚡
          </div>
          <h1 className="bg-gradient-to-r from-white via-indigo-200 to-violet-300 bg-clip-text text-5xl font-extrabold leading-tight text-transparent">
            Hiring, finally
            <br />
            at the speed of AI.
          </h1>
          <p className="mt-4 max-w-md text-lg text-slate-400">
            TalentFlow turns Google Form responses into ranked, interview-ready candidates —
            with AI job descriptions, round tracking, and executive sign-off in one place.
          </p>
          <div className="mt-8 space-y-4">
            {features.map((f, i) => (
              <motion.div
                key={f.title}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.35 + i * 0.15, duration: 0.5 }}
                className="flex items-start gap-4 rounded-2xl border border-white/10 bg-white/[0.03] p-4 backdrop-blur-sm"
              >
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white/5 text-2xl">
                  {f.icon}
                </div>
                <div>
                  <div className="font-semibold text-white">{f.title}</div>
                  <div className="text-sm text-slate-400">{f.text}</div>
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>

        {/* Login card */}
        <motion.div
          initial={{ opacity: 0, y: 30, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.55, ease: 'easeOut' }}
          className="w-full rounded-3xl border border-white/10 bg-surface-900/80 p-8 shadow-2xl backdrop-blur-xl sm:p-10"
        >
          <div className="mb-8 lg:hidden">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-2xl shadow-glow">
              ⚡
            </div>
            <h1 className="text-2xl font-extrabold text-white">TalentFlow</h1>
          </div>

          <h2 className="text-2xl font-bold text-white">Welcome back</h2>
          <p className="mt-1 text-sm text-slate-400">Sign in to your hiring workspace.</p>

          <form onSubmit={handleSubmit} className="mt-6 space-y-5">
            <div>
              <label className={labelClass} htmlFor="email">
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="password">
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className={inputClass}
              />
            </div>

            {error && (
              <motion.div
                initial={{ opacity: 0, y: -6 }}
                animate={{ opacity: 1, y: 0 }}
                className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300"
              >
                {error}
              </motion.div>
            )}

            <Button type="submit" loading={busy} className="w-full" size="lg">
              {busy ? 'Signing in…' : 'Sign in →'}
            </Button>
          </form>

          <p className="mt-6 text-center text-xs text-slate-500">
            Sessions refresh automatically — stay signed in while you hire.
          </p>
        </motion.div>
      </div>
    </div>
  );
}
