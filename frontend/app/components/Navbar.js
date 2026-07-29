"use client";

import { motion } from "framer-motion";
import {
  Sparkles,
  Upload,
  Database,
  FileSpreadsheet,
  RotateCcw,
} from "lucide-react";

export default function Navbar({ currentView, onReset, onUpload, datasetInfo }) {
  return (
    <header className="navbar">
      {/* Logo */}
      <div className="navbar-logo" onClick={onReset} role="button" tabIndex={0}>
        <div className="navbar-logo-mark">
          <Sparkles size={16} color="white" strokeWidth={2.5} />
        </div>
        <span className="navbar-logo-text">
          <span>DataSense</span>{" "}
          <span style={{ color: "var(--text-secondary)", fontWeight: 500 }}>AI</span>
        </span>
      </div>

      {/* Dataset pill — appears in workspace */}
      {currentView === "workspace" && datasetInfo && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.2 }}
          className="dataset-pill"
        >
          <span className="dataset-pill-dot" />
          <FileSpreadsheet size={12} style={{ color: "var(--accent-light)", flexShrink: 0 }} />
          <span className="dataset-pill-name">
            {datasetInfo.filename || datasetInfo.source_table || "SQL Database"}
          </span>
          <span style={{ color: "var(--text-muted)", flexShrink: 0 }}>
            {datasetInfo.profile?.row_count?.toLocaleString()}r ×{" "}
            {datasetInfo.profile?.column_count}c
          </span>
        </motion.div>
      )}

      <div className="navbar-spacer" />

      {/* Actions */}
      <div className="navbar-actions">
        {currentView === "workspace" && (
          <button
            onClick={onReset}
            className="btn btn-ghost btn-sm"
          >
            <RotateCcw size={13} />
            New Dataset
          </button>
        )}

        <button
          onClick={onUpload || onReset}
          className="btn btn-secondary btn-sm"
        >
          <Upload size={13} />
          Upload
        </button>

        <button className="btn btn-secondary btn-sm">
          <Database size={13} />
          Connect SQL
        </button>

        {/* Status indicator */}
        <div className="status-dot">
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: "var(--success)",
              flexShrink: 0,
              boxShadow: "0 0 5px var(--success)",
              display: "inline-block",
            }}
          />
          AI Ready
        </div>

        {/* User avatar placeholder */}
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: "50%",
            background: "var(--bg-elevated)",
            border: "1px solid var(--border-strong)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
            cursor: "pointer",
            fontSize: 12,
            fontWeight: 700,
            color: "var(--text-secondary)",
          }}
        >
          U
        </div>
      </div>
    </header>
  );
}
