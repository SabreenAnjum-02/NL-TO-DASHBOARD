"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Send,
  Loader2,
  Bot,
  User,
  Sparkles,
  AlertCircle,
  CheckCircle2,
  TrendingUp,
  BarChart3,
  Search,
  Zap,
} from "lucide-react";

const SUGGESTED = [
  { icon: TrendingUp, text: "Show me the overall trends in this data" },
  { icon: BarChart3,  text: "What are the top performing categories?" },
  { icon: Zap,        text: "Give me a complete analysis dashboard" },
  { icon: Search,     text: "Find correlations between numeric columns" },
];

export default function ChatInterface({ chatHistory, onQuery, isQuerying, datasetInfo }) {
  const [input, setInput] = useState("");
  const chatEndRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatHistory, isQuerying]);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const handleSubmit = (e) => {
    e?.preventDefault();
    if (!input.trim() || isQuerying) return;
    onQuery(input.trim());
    setInput("");
    // reset textarea height
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleTextareaInput = (e) => {
    const ta = e.target;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 120)}px`;
    setInput(ta.value);
  };

  const isEmpty = chatHistory.length === 0;

  return (
    <div className="chat-container" style={{ height: "100%" }}>
      {/* Chat header */}
      <div
        style={{
          padding: "14px 16px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          gap: 8,
          flexShrink: 0,
        }}
      >
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: 8,
            background: "var(--gradient-accent)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            boxShadow: "0 0 10px rgba(99,102,241,0.3)",
          }}
        >
          <Sparkles size={14} color="white" />
        </div>
        <div>
          <p style={{ fontWeight: 700, fontSize: 13.5, color: "var(--text-primary)" }}>
            AI Chat
          </p>
          <p style={{ fontSize: 11, color: "var(--text-muted)" }}>
            {datasetInfo
              ? `${datasetInfo.filename || datasetInfo.source_table || "Dataset"} • ${datasetInfo.profile?.row_count?.toLocaleString()} rows`
              : "Ask anything about your data"}
          </p>
        </div>
      </div>

      {/* Messages area */}
      <div className="chat-messages" style={{ flex: 1, overflowY: "auto" }}>
        {/* Empty state */}
        {isEmpty && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              height: "100%",
              textAlign: "center",
              gap: 12,
              padding: "32px 16px",
            }}
          >
            <div
              style={{
                width: 52,
                height: 52,
                borderRadius: 16,
                background: "var(--gradient-subtle)",
                border: "1px solid rgba(99,102,241,0.2)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Bot size={24} color="var(--accent-light)" />
            </div>
            <div>
              <p style={{ fontWeight: 700, fontSize: 14, color: "var(--text-primary)", marginBottom: 4 }}>
                Ready to analyze
              </p>
              <p style={{ fontSize: 12.5, color: "var(--text-muted)", maxWidth: 220, lineHeight: 1.55 }}>
                Ask me anything about your data in plain English
              </p>
            </div>
          </div>
        )}

        {/* Messages */}
        {chatHistory.map((msg, i) => (
          <ChatMessage key={i} msg={msg} index={i} />
        ))}

        {/* Typing indicator */}
        <AnimatePresence>
          {isQuerying && (
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="chat-bubble"
            >
              <div className="chat-avatar ai">
                <Bot size={13} color="white" />
              </div>
              <div className="chat-message-body ai" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Analyzing</span>
                <div style={{ display: "flex", gap: 4 }}>
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div ref={chatEndRef} />
      </div>

      {/* Suggested prompts */}
      <AnimatePresence>
        {chatHistory.length <= 1 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{
              padding: "10px 16px",
              display: "flex",
              flexDirection: "column",
              gap: 6,
              borderTop: "1px solid var(--border)",
            }}
          >
            <p
              style={{
                fontSize: 10.5,
                fontWeight: 700,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                color: "var(--text-muted)",
                marginBottom: 2,
              }}
            >
              Try asking
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {SUGGESTED.map(({ icon: Icon, text }) => (
                <button
                  key={text}
                  onClick={() => {
                    setInput(text);
                    textareaRef.current?.focus();
                  }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "8px 10px",
                    borderRadius: 10,
                    background: "transparent",
                    border: "1px solid var(--border)",
                    color: "var(--text-secondary)",
                    fontSize: 12,
                    fontWeight: 500,
                    fontFamily: "inherit",
                    cursor: "pointer",
                    textAlign: "left",
                    transition: "all 0.15s",
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = "var(--border-hover)";
                    e.currentTarget.style.color = "var(--text-primary)";
                    e.currentTarget.style.background = "rgba(255,255,255,0.03)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = "var(--border)";
                    e.currentTarget.style.color = "var(--text-secondary)";
                    e.currentTarget.style.background = "transparent";
                  }}
                >
                  <Icon size={12} style={{ flexShrink: 0, color: "var(--accent-light)" }} />
                  {text}
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Input bar */}
      <div className="chat-input-bar">
        <form onSubmit={handleSubmit}>
          <div className="chat-input-wrap">
            <textarea
              ref={textareaRef}
              className="chat-textarea"
              value={input}
              onInput={handleTextareaInput}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question about your data…"
              rows={1}
              disabled={isQuerying}
            />
            <button
              type="submit"
              className="chat-send-btn"
              disabled={!input.trim() || isQuerying}
            >
              {isQuerying ? (
                <Loader2 size={14} color="white" style={{ animation: "spin 1s linear infinite" }} />
              ) : (
                <Send size={14} color="white" />
              )}
            </button>
          </div>
        </form>
        <p
          style={{
            fontSize: 10.5,
            color: "var(--text-muted)",
            marginTop: 6,
            textAlign: "center",
          }}
        >
          Press <kbd style={{ padding: "1px 4px", borderRadius: 4, background: "var(--bg-elevated)", border: "1px solid var(--border)", fontSize: 10 }}>Enter</kbd> to send,{" "}
          <kbd style={{ padding: "1px 4px", borderRadius: 4, background: "var(--bg-elevated)", border: "1px solid var(--border)", fontSize: 10 }}>Shift+Enter</kbd> for new line
        </p>
      </div>
    </div>
  );
}

function ChatMessage({ msg, index }) {
  const isUser = msg.role === "user";
  const isSystem = msg.role === "system";

  if (isSystem) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: index * 0.04 }}
        className="notification notification-success"
        style={{ borderRadius: "var(--radius-md)" }}
      >
        <CheckCircle2 size={14} style={{ flexShrink: 0, marginTop: 1 }} />
        <span style={{ fontSize: 12.5 }}>{msg.content}</span>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04 }}
      className={`chat-bubble ${isUser ? "user" : ""}`}
    >
      {/* Avatar */}
      <div className={`chat-avatar ${isUser ? "user-av" : "ai"}`}>
        {isUser ? (
          <User size={13} color="var(--text-secondary)" />
        ) : (
          <Bot size={13} color="white" />
        )}
      </div>

      {/* Message body */}
      <div
        className={`chat-message-body ${
          isUser ? "user" : msg.type === "error" ? "error-msg" : "ai"
        }`}
      >
        {msg.type === "error" && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 5,
              fontSize: 11,
              fontWeight: 700,
              color: "var(--danger)",
              marginBottom: 5,
            }}
          >
            <AlertCircle size={11} />
            Error
          </div>
        )}
        {msg.type === "success" && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 5,
              fontSize: 11,
              fontWeight: 700,
              color: "var(--success)",
              marginBottom: 5,
            }}
          >
            <CheckCircle2 size={11} />
            Dashboard Ready
          </div>
        )}
        <div style={{ whiteSpace: "pre-wrap" }}>{msg.content}</div>
      </div>
    </motion.div>
  );
}
