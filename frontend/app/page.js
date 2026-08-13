"use client";

import { useState, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Upload,
  Database,
  BarChart3,
  Sparkles,
  Brain,
  Eye,
  Shield,
  Target,
  ArrowRight,
  FileSpreadsheet,
  Rows,
  Columns,
  HardDrive,
  Clock,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";
import Navbar from "./components/Navbar";
import Sidebar from "./components/Sidebar";
import UploadPanel from "./components/UploadPanel";
import ChatInterface from "./components/ChatInterface";
import DashboardView from "./components/DashboardView";
import TaskFlowView from "./components/TaskFlowView";
import InsightsPanel from "./components/InsightsPanel";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

/* ======================================================================
   ROOT — State management (unchanged logic, new UI)
   ====================================================================== */
export default function Home() {
  const [currentView, setCurrentView] = useState("landing");
  const [datasetInfo, setDatasetInfo] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isQuerying, setIsQuerying] = useState(false);
  const [dashboardData, setDashboardData] = useState(null);
  const [taskPlan, setTaskPlan] = useState(null);
  const [insights, setInsights] = useState([]);
  const [clarificationNeeded, setClarificationNeeded] = useState(null);
  const [chatHistory, setChatHistory] = useState([]);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("chat");

  const handleReset = useCallback(() => {
    setCurrentView("landing");
    setDatasetInfo(null);
    setDashboardData(null);
    setTaskPlan(null);
    setInsights([]);
    setChatHistory([]);
    setClarificationNeeded(null);
    setError(null);
    setActiveTab("chat");
  }, []);

  const handleFileUpload = useCallback(async (file) => {
    setIsUploading(true);
    setError(null);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch(`${API_BASE}/data/upload`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Upload failed");
      }
      const data = await res.json();
      setDatasetInfo(data);
      setCurrentView("workspace");
      setActiveTab("chat");
      setChatHistory([
        {
          role: "system",
          content: `Dataset "${data.filename}" loaded! ${data.profile.row_count} rows × ${data.profile.column_count} columns detected. Ask me anything about your data.`,
        },
      ]);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsUploading(false);
    }
  }, []);

  const handleSQLConnect = useCallback(async (connectionString, tableName) => {
    setIsUploading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/data/connect-sql`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          connection_string: connectionString,
          table_name: tableName || null,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Connection failed");
      }
      const data = await res.json();
      setDatasetInfo(data);
      setCurrentView("workspace");
      setActiveTab("chat");
      setChatHistory([
        {
          role: "system",
          content: `Connected! Table "${data.source_table}" loaded with ${data.profile.row_count} rows × ${data.profile.column_count} columns. Ask me anything.`,
        },
      ]);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsUploading(false);
    }
  }, []);

  const handleQuery = useCallback(
    async (query) => {
      if (!datasetInfo) return;
      setIsQuerying(true);
      setError(null);
      setClarificationNeeded(null);
      setChatHistory((prev) => [...prev, { role: "user", content: query }]);
      try {
        const res = await fetch(`${API_BASE}/query/ask`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query, dataset_id: datasetInfo.dataset_id }),
        });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || "Query failed");
        }
        const data = await res.json();
        if (data.status === "chat_reply") {
          setChatHistory((prev) => [
            ...prev,
            {
              role: "assistant",
              content: data.message,
              type: "chat",
            },
          ]);
        } else if (data.status === "clarification_needed") {
          setClarificationNeeded(data);
          setChatHistory((prev) => [
            ...prev,
            {
              role: "assistant",
              content: `I need a bit more clarity:\n${data.questions.map((q) => `• ${q}`).join("\n")}`,
              type: "clarification",
            },
          ]);
        } else if (data.status === "success") {
          setDashboardData(data.charts);
          setTaskPlan(data.task_plan);
          setInsights(data.insights || []);
          setChatHistory((prev) => [
            ...prev,
            {
              role: "assistant",
              content: `Dashboard generated! Domain: **${data.domain}**. Created ${data.charts?.length || 0} visualizations with ${data.insights?.length || 0} insights.`,
              type: "success",
            },
          ]);
          // Auto-switch to dashboard tab after results arrive
          setActiveTab("dashboard");
        } else {
          throw new Error(data.message || "Unknown error");
        }
      } catch (err) {
        setError(err.message);
        setChatHistory((prev) => [
          ...prev,
          {
            role: "assistant",
            content: `Error: ${err.message}`,
            type: "error",
          },
        ]);
      } finally {
        setIsQuerying(false);
      }
    },
    [datasetInfo]
  );

  return (
    <div className="app-shell">
      <Navbar
        currentView={currentView}
        onReset={handleReset}
        onUpload={handleReset}
        datasetInfo={datasetInfo}
      />

      <AnimatePresence mode="wait">
        {currentView === "landing" ? (
          <motion.div
            key="landing"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.3 }}
            style={{ flex: 1 }}
          >
            <LandingView
              onFileUpload={handleFileUpload}
              onSQLConnect={handleSQLConnect}
              isUploading={isUploading}
              error={error}
            />
          </motion.div>
        ) : (
          <motion.div
            key="workspace"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="workspace-layout"
          >
            <WorkspaceView
              datasetInfo={datasetInfo}
              chatHistory={chatHistory}
              onQuery={handleQuery}
              isQuerying={isQuerying}
              dashboardData={dashboardData}
              taskPlan={taskPlan}
              insights={insights}
              error={error}
              datasetId={datasetInfo?.dataset_id}
              activeTab={activeTab}
              onTabChange={setActiveTab}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ======================================================================
   LANDING VIEW
   ====================================================================== */
function LandingView({ onFileUpload, onSQLConnect, isUploading, error }) {
  const FEATURES = [
    { icon: Brain,  label: "6-Agent AI Pipeline" },
    { icon: Eye,    label: "Ambiguity Detection" },
    { icon: Shield, label: "Self-Correcting" },
    { icon: Target, label: "Domain-Aware" },
  ];

  const HOW_IT_WORKS = [
    {
      step: "01",
      icon: Upload,
      title: "Upload Your Data",
      desc: "Drop a CSV, Excel, JSON, or Parquet file. Or connect directly to a SQL database.",
    },
    {
      step: "02",
      icon: Brain,
      title: "Ask in Plain English",
      desc: "Type your question naturally. Our 6-agent AI pipeline understands your intent.",
    },
    {
      step: "03",
      icon: BarChart3,
      title: "Get Your Dashboard",
      desc: "Receive interactive visualizations and AI-generated insights instantly.",
    },
  ];

  return (
    <main
      style={{
        maxWidth: 900,
        margin: "0 auto",
        padding: "72px 24px 96px",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 64,
      }}
    >
      {/* ── Hero ── */}
      <section
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          textAlign: "center",
          gap: 24,
          width: "100%",
        }}
      >
        {/* Badge */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <span className="hero-badge">
            <Sparkles size={12} />
            Powered by Multi-Agent AI
          </span>
        </motion.div>

        {/* Heading */}
        <motion.h1
          className="hero-heading"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, delay: 0.08 }}
        >
          Talk to Your Data
          <br />
          <span className="gradient-word">with AI</span>
        </motion.h1>

        {/* Subtitle */}
        <motion.p
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.16 }}
          style={{
            fontSize: 17,
            color: "var(--text-secondary)",
            maxWidth: 540,
            lineHeight: 1.7,
          }}
        >
          Upload your Excel, CSV, JSON, or connect your SQL database and
          instantly generate AI-powered insights and interactive dashboards.
        </motion.p>

        {/* Feature pills */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "center",
            gap: 8,
          }}
        >
          {FEATURES.map(({ icon: Icon, label }) => (
            <div key={label} className="feature-pill">
              <span className="feature-pill-icon">
                <Icon size={10} color="white" />
              </span>
              {label}
            </div>
          ))}
        </motion.div>
      </section>

      {/* ── Upload panel ── */}
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.35 }}
        style={{
          width: "100%",
          display: "flex",
          justifyContent: "center",
        }}
      >
        <UploadPanel
          onFileUpload={onFileUpload}
          onSQLConnect={onSQLConnect}
          isUploading={isUploading}
          error={error}
        />
      </motion.div>

      {/* ── How it works ── */}
      <motion.section
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.5 }}
        style={{ width: "100%" }}
      >
        <p
          className="section-label"
          style={{ textAlign: "center", marginBottom: 28 }}
        >
          How it works
        </p>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
            gap: 16,
          }}
        >
          {HOW_IT_WORKS.map(({ step, icon: Icon, title, desc }, i) => (
            <motion.div
              key={step}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.55 + i * 0.1 }}
              className="card card-hover"
              style={{ padding: 24 }}
            >
              {/* Step number + icon row */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 16,
                }}
              >
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 800,
                    letterSpacing: "0.06em",
                    color: "var(--accent-light)",
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {step}
                </span>
                <div
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: 10,
                    background: "var(--gradient-subtle)",
                    border: "1px solid rgba(99,102,241,0.2)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <Icon size={17} color="var(--accent-light)" />
                </div>
              </div>
              <h3
                style={{
                  fontWeight: 700,
                  fontSize: 14,
                  color: "var(--text-primary)",
                  marginBottom: 8,
                }}
              >
                {title}
              </h3>
              <p style={{ fontSize: 13, color: "var(--text-muted)", lineHeight: 1.65 }}>
                {desc}
              </p>
            </motion.div>
          ))}
        </div>
      </motion.section>
    </main>
  );
}

/* ======================================================================
   WORKSPACE VIEW
   ====================================================================== */
function WorkspaceView({
  datasetInfo,
  chatHistory,
  onQuery,
  isQuerying,
  dashboardData,
  taskPlan,
  insights,
  error,
  datasetId,
  activeTab,
  onTabChange,
}) {
  return (
    <>
      {/* Sidebar */}
      <Sidebar
        activeTab={activeTab}
        onTabChange={onTabChange}
        insightCount={insights.length}
      />

      {/* Main content area */}
      <div
        className="main-content"
        style={{
          display: "flex",
          flexDirection: "column",
          height: "100%",
          background: "var(--bg-base)",
        }}
      >
        {/* Inner panel with smooth tab switching */}
        <AnimatePresence mode="wait">
          {activeTab === "chat" && (
            <motion.div
              key="chat"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              style={{ height: "100%", display: "flex", flexDirection: "column" }}
            >
              <ChatPanel
                chatHistory={chatHistory}
                onQuery={onQuery}
                isQuerying={isQuerying}
                datasetInfo={datasetInfo}
                error={error}
                hasDashboard={!!dashboardData}
                onViewDashboard={() => onTabChange("dashboard")}
              />
            </motion.div>
          )}

          {activeTab === "dashboard" && (
            <motion.div
              key="dashboard"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              style={{ height: "100%", overflowY: "auto" }}
            >
              {/* Dataset summary bar */}
              {datasetInfo && (
                <DatasetSummaryBar datasetInfo={datasetInfo} />
              )}
              <DashboardView charts={dashboardData} datasetId={datasetInfo?.dataset_id} />
            </motion.div>
          )}

          {activeTab === "insights" && (
            <motion.div
              key="insights"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              style={{ height: "100%", overflowY: "auto" }}
            >
              <InsightsPanel insights={insights} />
            </motion.div>
          )}

          {activeTab === "taskflow" && (
            <motion.div
              key="taskflow"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              style={{ height: "100%", overflowY: "auto" }}
            >
              <TaskFlowView taskPlan={taskPlan} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </>
  );
}

/* ======================================================================
   CHAT PANEL — wraps ChatInterface with contextual header
   ====================================================================== */
function ChatPanel({
  chatHistory,
  onQuery,
  isQuerying,
  datasetInfo,
  error,
  hasDashboard,
  onViewDashboard,
}) {
  return (
    <div
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        maxWidth: 720,
        margin: "0 auto",
        width: "100%",
        padding: "0 0",
      }}
    >
      {/* Dashboard ready nudge banner */}
      <AnimatePresence>
        {hasDashboard && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "10px 20px",
              background: "rgba(99,102,241,0.08)",
              borderBottom: "1px solid rgba(99,102,241,0.18)",
              flexShrink: 0,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <CheckCircle2 size={14} color="var(--accent-light)" />
              <span style={{ fontSize: 12.5, color: "var(--accent-light)", fontWeight: 600 }}>
                Dashboard is ready
              </span>
            </div>
            <button
              onClick={onViewDashboard}
              className="btn btn-primary btn-sm"
              style={{ gap: 5 }}
            >
              View Dashboard
              <ArrowRight size={12} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Error banner */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="notification notification-error"
            style={{
              margin: "12px 16px 0",
              borderRadius: "var(--radius-md)",
            }}
          >
            <AlertCircle size={14} style={{ flexShrink: 0 }} />
            <span style={{ fontSize: 12.5 }}>{error}</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Chat */}
      <div style={{ flex: 1, overflow: "hidden" }}>
        <ChatInterface
          chatHistory={chatHistory}
          onQuery={onQuery}
          isQuerying={isQuerying}
          datasetInfo={datasetInfo}
        />
      </div>
    </div>
  );
}

/* ======================================================================
   DATASET SUMMARY BAR
   ====================================================================== */
function DatasetSummaryBar({ datasetInfo }) {
  const profile = datasetInfo.profile || {};

  const stats = [
    {
      icon: FileSpreadsheet,
      label: "Dataset",
      value: datasetInfo.filename || datasetInfo.source_table || "SQL Table",
    },
    {
      icon: Rows,
      label: "Rows",
      value: profile.row_count?.toLocaleString() ?? "—",
    },
    {
      icon: Columns,
      label: "Columns",
      value: profile.column_count ?? "—",
    },
    {
      icon: HardDrive,
      label: "Size",
      value: profile.file_size_mb
        ? `${profile.file_size_mb.toFixed(1)} MB`
        : "—",
    },
    {
      icon: Clock,
      label: "Loaded",
      value: "Just now",
    },
  ];

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 0,
        padding: "0 24px",
        borderBottom: "1px solid var(--border)",
        background: "var(--bg-surface)",
        overflowX: "auto",
        flexShrink: 0,
      }}
    >
      {stats.map(({ icon: Icon, label, value }, i) => (
        <div
          key={label}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "12px 20px",
            borderRight: i < stats.length - 1 ? "1px solid var(--border)" : "none",
            flexShrink: 0,
          }}
        >
          <Icon size={13} color="var(--accent-light)" />
          <div>
            <p style={{ fontSize: 10.5, color: "var(--text-muted)", fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", lineHeight: 1.2 }}>
              {label}
            </p>
            <p style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)", lineHeight: 1.4 }}>
              {value}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}
