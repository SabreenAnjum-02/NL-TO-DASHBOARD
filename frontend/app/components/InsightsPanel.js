"use client";

import { motion } from "framer-motion";
import {
  Lightbulb,
  TrendingUp,
  ArrowRight,
  Zap,
  Target,
  Search,
} from "lucide-react";

const ICONS = [TrendingUp, Lightbulb, Zap, Target, Search, ArrowRight];
const ACCENT_COLORS = [
  { bg: "rgba(99,102,241,0.1)", border: "rgba(99,102,241,0.25)", text: "#A5B4FC" },
  { bg: "rgba(16,185,129,0.1)", border: "rgba(16,185,129,0.25)", text: "#6EE7B7" },
  { bg: "rgba(245,158,11,0.1)", border: "rgba(245,158,11,0.25)", text: "#FCD34D" },
  { bg: "rgba(139,92,246,0.1)", border: "rgba(139,92,246,0.25)", text: "#C4B5FD" },
  { bg: "rgba(6,182,212,0.1)",  border: "rgba(6,182,212,0.25)",  text: "#67E8F9" },
];

export default function InsightsPanel({ insights }) {
  if (!insights || insights.length === 0) {
    return (
      <div
        style={{
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
          gap: 16,
          padding: 40,
        }}
      >
        <div
          style={{
            width: 72,
            height: 72,
            borderRadius: 20,
            background: "var(--gradient-subtle)",
            border: "1px solid rgba(99,102,241,0.15)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Lightbulb size={32} color="var(--text-muted)" />
        </div>
        <div>
          <p style={{ fontWeight: 700, fontSize: 15, color: "var(--text-secondary)", marginBottom: 6 }}>
            No insights yet
          </p>
          <p style={{ fontSize: 13, color: "var(--text-muted)", maxWidth: 280, lineHeight: 1.6 }}>
            AI-generated business insights will appear here after you run an analysis.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: 24, display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: 10,
            background: "rgba(245,158,11,0.12)",
            border: "1px solid rgba(245,158,11,0.25)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Lightbulb size={16} color="#FCD34D" />
        </div>
        <div>
          <h2 style={{ fontWeight: 700, fontSize: 15, color: "var(--text-primary)" }}>
            AI Insights
          </h2>
          <p style={{ fontSize: 12, color: "var(--text-muted)" }}>
            {insights.length} finding{insights.length !== 1 ? "s" : ""} generated
          </p>
        </div>
        <span className="badge badge-warning" style={{ marginLeft: "auto" }}>
          {insights.length} found
        </span>
      </div>

      {/* Insight cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {insights.map((insight, i) => {
          const Icon = ICONS[i % ICONS.length];
          const accent = ACCENT_COLORS[i % ACCENT_COLORS.length];

          return (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -16 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.08, duration: 0.3 }}
              className="insight-card"
            >
              {/* Number badge */}
              <div className="insight-number">{i + 1}</div>

              {/* Icon */}
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: 9,
                  background: accent.bg,
                  border: `1px solid ${accent.border}`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                }}
              >
                <Icon size={15} color={accent.text} />
              </div>

              {/* Text */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <p
                  style={{
                    fontSize: 13.5,
                    color: "var(--text-secondary)",
                    lineHeight: 1.65,
                  }}
                >
                  {insight}
                </p>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
