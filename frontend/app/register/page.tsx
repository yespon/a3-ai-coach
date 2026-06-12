"use client";

import { FormEvent, useState } from "react";
import { register } from "@/lib/auth";
import Link from "next/link";

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [nickname, setNickname] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");

    if (password.length < 6) {
      setError("密码至少需要 6 个字符");
      return;
    }
    if (password !== confirmPassword) {
      setError("两次密码不一致");
      return;
    }

    setBusy(true);
    try {
      await register(email, password, nickname || undefined);
      window.location.href = "/";
    } catch (err) {
      setError(err instanceof Error ? err.message : "注册失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-card">
        <h1 className="auth-title">注册</h1>
        <form onSubmit={handleSubmit} className="auth-form">
          <label className="auth-label">
            邮箱
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              className="auth-input"
              placeholder="your@email.com"
            />
          </label>
          <label className="auth-label">
            密码
            <div className="auth-password-row">
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="new-password"
                className="auth-input"
              placeholder="密码（至少 6 个字符）"
              />
              <button
                type="button"
                className="auth-toggle-pw"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? "隐藏密码" : "显示密码"}
              >
                {showPassword ? "隐" : "显"}
              </button>
            </div>
          </label>
          <label className="auth-label">
            确认密码
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              autoComplete="new-password"
              className="auth-input"
              placeholder="再次输密码"
            />
          </label>
          <label className="auth-label">
            昵称（可选）
            <input
              type="text"
              value={nickname}
              onChange={(e) => setNickname(e.target.value)}
              autoComplete="nickname"
              className="auth-input"
              placeholder="昵称"
            />
          </label>
          {error && <div className="auth-error">{error}</div>}
          <button type="submit" disabled={busy} className="auth-btn">
            {busy ? "注册中..." : "注册"}
          </button>
        </form>
        <p className="auth-link-text">
          已有账号？<Link href="/login">登录</Link>
        </p>
      </div>
    </main>
  );
}
