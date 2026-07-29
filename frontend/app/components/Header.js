"use client";

import { motion } from "framer-motion";
import { Sparkles, RotateCcw, Database, FileSpreadsheet, Upload } from "lucide-react";

export default function Header({ currentView, onReset, datasetInfo }) {
  return (
    <header className="sticky top-0 z-50 backdrop-blur-xl bg-[rgba(10,11,20,0.85)] border-b border-[var(--card-border)]">
      <div className="max-w-[1800px] mx-auto px-4 sm:px-6 h-[72px] flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center gap-3 cursor-pointer" onClick={onReset}>
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#8b5cf6] to-[#14b8a6] flex items-center justify-center shadow-lg shadow-[rgba(139,92,246,0.3)]">
            <Sparkles size={18} className="text-white" />
          </div>
          <span className="text-lg font-bold tracking-tight">
            <span className="glow-text">DataSense</span>
            <span className="text-[var(--foreground)]"> AI</span>
          </span>
        </div>

        {/* Center: Dataset Info */}
        <nav className="hidden md:flex items-center gap-6">
          <a href="#features" className="text-sm text-[var(--text-dim)] hover:text-[var(--foreground)] transition-colors">Features</a>
          <a href="#pricing" className="text-sm text-[var(--text-dim)] hover:text-[var(--foreground)] transition-colors">Pricing</a>
          <a href="#docs" className="text-sm text-[var(--text-dim)] hover:text-[var(--foreground)] transition-colors">Docs</a>
          <a href="#contact" className="text-sm text-[var(--text-dim)] hover:text-[var(--foreground)] transition-colors">Contact</a>
        </nav>
        {currentView === "workspace" && datasetInfo && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="hidden md:flex items-center gap-3"
          >
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--surface-elevated)] border border-[var(--card-border)]">
              <FileSpreadsheet size={14} className="text-[var(--accent-primary)]" />
              <span className="text-sm text-[var(--text-dim)]">
                {datasetInfo.filename || datasetInfo.source_table || "SQL Database"}
              </span>
              <span className="text-xs text-[var(--text-muted)]">
                {datasetInfo.profile?.row_count?.toLocaleString()} rows ×{" "}
                {datasetInfo.profile?.column_count} cols
              </span>
            </div>
          </motion.div>
        )}

        {/* Right: Actions */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-3">
          {currentView === "workspace" && (
            <button
              onClick={onReset}
              className="btn-secondary text-sm flex items-center gap-2"
            >
              <RotateCcw size={14} />
              New Dataset
            </button>
          )}
          <button
            onClick={onReset}
            className="btn-primary text-sm flex items-center gap-2"
          >
            <Upload size={14} />
            Upload Dataset
          </button>
          <button className="btn-secondary text-sm flex items-center gap-2">
            Sign In
          </button>
          <div className="badge badge-success">
            <span className="w-1.5 h-1.5 rounded-full bg-[#4ade80]" />
            AI Ready
          </div>
        </div>
        </div>
      </div>
    </header>
  );
}
