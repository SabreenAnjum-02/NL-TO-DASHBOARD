"use client";

import { useState, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Upload,
  Database,
  FileSpreadsheet,
  Loader2,
  AlertCircle,
  Server,
  CheckCircle2,
} from "lucide-react";

export default function UploadPanel({ onFileUpload, onSQLConnect, isUploading, error }) {
  const [mode, setMode] = useState("file");
  const [isDragOver, setIsDragOver] = useState(false);
  const [sqlConnection, setSqlConnection] = useState("");
  const [sqlTable, setSqlTable] = useState("");
  const fileInputRef = useRef(null);

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      setIsDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) onFileUpload(file);
    },
    [onFileUpload]
  );

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => setIsDragOver(false), []);

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) onFileUpload(file);
  };

  return (
    <div
      className="card"
      style={{
        maxWidth: 560,
        width: "100%",
        padding: 0,
        overflow: "hidden",
      }}
    >
      {/* Mode tabs */}
      <div
        style={{
          display: "flex",
          borderBottom: "1px solid var(--border)",
        }}
      >
        {[
          { id: "file", label: "Upload File", icon: FileSpreadsheet },
          { id: "sql",  label: "Connect SQL",  icon: Database },
        ].map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setMode(id)}
            style={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 7,
              padding: "14px 20px",
              fontSize: 13,
              fontWeight: 600,
              fontFamily: "inherit",
              border: "none",
              borderBottom: mode === id ? "2px solid var(--accent)" : "2px solid transparent",
              background: mode === id ? "var(--accent-dim)" : "transparent",
              color: mode === id ? "var(--accent-light)" : "var(--text-muted)",
              cursor: "pointer",
              transition: "all 0.18s",
              marginBottom: -1,
            }}
          >
            <Icon size={15} />
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={{ padding: 28 }}>
        <AnimatePresence mode="wait">
          {mode === "file" ? (
            <motion.div
              key="file"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.18 }}
            >
              {/* Drop zone */}
              <div
                className={`upload-zone ${isDragOver ? "drag-over" : ""}`}
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onClick={() => !isUploading && fileInputRef.current?.click()}
                style={{ cursor: isUploading ? "default" : "pointer" }}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv,.xlsx,.xls,.json,.parquet"
                  className="hidden"
                  onChange={handleFileChange}
                  style={{ display: "none" }}
                />

                {isUploading ? (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
                    <div className="upload-icon-wrap animate-pulse-glow">
                      <Loader2 size={26} color="var(--accent-light)" style={{ animation: "spin 1s linear infinite" }} />
                    </div>
                    <div>
                      <p style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: 4 }}>
                        Analyzing your data…
                      </p>
                      <p style={{ fontSize: 12.5, color: "var(--text-muted)" }}>
                        This may take a moment for large files
                      </p>
                    </div>
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
                    <div className="upload-icon-wrap animate-float">
                      <Upload size={26} color="var(--accent-light)" />
                    </div>
                    <div>
                      <p style={{ fontWeight: 700, fontSize: 15, color: "var(--text-primary)", marginBottom: 6 }}>
                        Drop your dataset here
                      </p>
                      <p style={{ fontSize: 13, color: "var(--text-muted)" }}>
                        or{" "}
                        <span style={{ color: "var(--accent-light)", fontWeight: 600 }}>
                          click to browse
                        </span>
                      </p>
                    </div>
                    {/* Format pills */}
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "center" }}>
                      {["CSV", "Excel", "JSON", "Parquet"].map((fmt) => (
                        <span
                          key={fmt}
                          style={{
                            padding: "3px 10px",
                            borderRadius: "var(--radius-full)",
                            background: "var(--bg-elevated)",
                            border: "1px solid var(--border-strong)",
                            fontSize: 11,
                            fontWeight: 600,
                            color: "var(--text-secondary)",
                          }}
                        >
                          .{fmt.toLowerCase()}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="sql"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.18 }}
              style={{ display: "flex", flexDirection: "column", gap: 16 }}
            >
              {/* Connection string */}
              <div>
                <label
                  style={{
                    display: "block",
                    fontSize: 12.5,
                    fontWeight: 600,
                    color: "var(--text-secondary)",
                    marginBottom: 8,
                    letterSpacing: "0.01em",
                  }}
                >
                  Connection String
                </label>
                <input
                  type="text"
                  value={sqlConnection}
                  onChange={(e) => setSqlConnection(e.target.value)}
                  placeholder="sqlite:///path/to/database.db"
                  className="input"
                  disabled={isUploading}
                />
              </div>

              {/* Table name */}
              <div>
                <label
                  style={{
                    display: "block",
                    fontSize: 12.5,
                    fontWeight: 600,
                    color: "var(--text-secondary)",
                    marginBottom: 8,
                  }}
                >
                  Table Name{" "}
                  <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>
                    (optional)
                  </span>
                </label>
                <input
                  type="text"
                  value={sqlTable}
                  onChange={(e) => setSqlTable(e.target.value)}
                  placeholder="Leave empty to auto-detect"
                  className="input"
                  disabled={isUploading}
                />
              </div>

              {/* Connect button */}
              <button
                onClick={() => onSQLConnect(sqlConnection, sqlTable)}
                disabled={!sqlConnection || isUploading}
                className="btn btn-primary btn-lg"
                style={{ width: "100%", marginTop: 4 }}
              >
                {isUploading ? (
                  <Loader2 size={16} style={{ animation: "spin 1s linear infinite" }} />
                ) : (
                  <Server size={16} />
                )}
                {isUploading ? "Connecting…" : "Connect to Database"}
              </button>

              {/* Supported DBs */}
              <div>
                <p style={{ fontSize: 11.5, color: "var(--text-muted)", marginBottom: 8, fontWeight: 500 }}>
                  Supported databases
                </p>
                <div style={{ display: "flex", gap: 6 }}>
                  {["SQLite", "PostgreSQL", "MySQL"].map((db) => (
                    <span key={db} className="badge badge-info">
                      {db}
                    </span>
                  ))}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Error notification */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="notification notification-error"
              style={{ marginTop: 16 }}
            >
              <AlertCircle size={15} style={{ flexShrink: 0, marginTop: 1 }} />
              <p>{error}</p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
