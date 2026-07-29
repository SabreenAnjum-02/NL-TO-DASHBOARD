"use client";

import { motion } from "framer-motion";
import { GitBranch, CheckCircle2, Zap } from "lucide-react";

const TYPE_STYLES = {
  data_transform: { bg: "rgba(99,102,241,0.1)",  border: "rgba(99,102,241,0.25)",  text: "#A5B4FC", label: "Transform" },
  aggregation:    { bg: "rgba(16,185,129,0.1)",  border: "rgba(16,185,129,0.25)",  text: "#6EE7B7", label: "Aggregate" },
  filtering:      { bg: "rgba(245,158,11,0.1)",  border: "rgba(245,158,11,0.25)",  text: "#FCD34D", label: "Filter" },
  visualization:  { bg: "rgba(139,92,246,0.1)",  border: "rgba(139,92,246,0.25)",  text: "#C4B5FD", label: "Visualize" },
  insight:        { bg: "rgba(6,182,212,0.1)",   border: "rgba(6,182,212,0.25)",   text: "#67E8F9", label: "Insight" },
};

const DEFAULT_TYPE = TYPE_STYLES.data_transform;

export default function TaskFlowView({ taskPlan }) {
  if (!taskPlan) {
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
          <GitBranch size={32} color="var(--text-muted)" />
        </div>
        <div>
          <p style={{ fontWeight: 700, fontSize: 15, color: "var(--text-secondary)", marginBottom: 6 }}>
            No task plan yet
          </p>
          <p style={{ fontSize: 13, color: "var(--text-muted)", maxWidth: 280, lineHeight: 1.6 }}>
            The AI agent&apos;s reasoning chain will appear here after you ask a question.
          </p>
        </div>
      </div>
    );
  }

  const tasks = taskPlan.tasks || [];

  return (
    <div style={{ padding: 24, display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Goal card */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        style={{
          background: "var(--bg-card)",
          border: "1px solid rgba(99,102,241,0.25)",
          borderRadius: "var(--radius-lg)",
          padding: "14px 18px",
          boxShadow: "0 0 0 1px rgba(99,102,241,0.08)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 7,
            marginBottom: 6,
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            color: "var(--accent-light)",
          }}
        >
          <Zap size={12} />
          Goal
        </div>
        <p style={{ fontSize: 13.5, color: "var(--text-secondary)", lineHeight: 1.6 }}>
          {taskPlan.goal}
        </p>
      </motion.div>

      {/* Pipeline */}
      <div>
        <p
          style={{
            fontSize: 10.5,
            fontWeight: 700,
            letterSpacing: "0.07em",
            textTransform: "uppercase",
            color: "var(--text-muted)",
            marginBottom: 12,
          }}
        >
          Task Pipeline — {tasks.length} steps
        </p>

        <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
          {tasks.map((task, index) => {
            const style = TYPE_STYLES[task.type] || DEFAULT_TYPE;
            const isLast = index === tasks.length - 1;

            return (
              <motion.div
                key={task.id || index}
                initial={{ opacity: 0, x: -16 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.1, duration: 0.3 }}
                style={{ display: "flex", gap: 14 }}
              >
                {/* Timeline column */}
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 32 }}>
                  <div
                    style={{
                      width: 32,
                      height: 32,
                      borderRadius: 9,
                      background: style.bg,
                      border: `1px solid ${style.border}`,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                    }}
                  >
                    <CheckCircle2 size={14} color={style.text} />
                  </div>
                  {!isLast && (
                    <div
                      style={{
                        width: 1,
                        flex: 1,
                        minHeight: 20,
                        background: "linear-gradient(to bottom, rgba(99,102,241,0.3), rgba(99,102,241,0.05))",
                        marginTop: 4,
                        marginBottom: 4,
                      }}
                    />
                  )}
                </div>

                {/* Task node */}
                <div
                  style={{
                    flex: 1,
                    paddingBottom: isLast ? 0 : 16,
                  }}
                >
                  <div className="dag-node completed">
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                      {/* Type badge */}
                      <span
                        style={{
                          padding: "2px 8px",
                          borderRadius: "var(--radius-full)",
                          fontSize: 10.5,
                          fontWeight: 700,
                          letterSpacing: "0.04em",
                          background: style.bg,
                          color: style.text,
                          border: `1px solid ${style.border}`,
                        }}
                      >
                        {style.label}
                      </span>
                      <span style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "monospace" }}>
                        {task.id}
                      </span>
                    </div>
                    <p style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.6 }}>
                      {task.description}
                    </p>
                    {task.depends_on?.length > 0 && (
                      <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 5 }}>
                        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Depends on:</span>
                        {task.depends_on.map((dep) => (
                          <span
                            key={dep}
                            style={{
                              padding: "1px 7px",
                              borderRadius: "var(--radius-full)",
                              background: "var(--accent-dim)",
                              color: "var(--accent-light)",
                              fontSize: 11,
                              fontWeight: 600,
                              fontFamily: "monospace",
                            }}
                          >
                            {dep}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
