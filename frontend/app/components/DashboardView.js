"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  BarChart3,
  Maximize2,
  Minimize2,
  TrendingUp,
  RefreshCw,
} from "lucide-react";

const API_BASE = "http://localhost:8000/api";

export default function DashboardView({ charts, datasetId }) {
  const [dataRows, setDataRows] = useState(null);
  const [loadingData, setLoadingData] = useState(false);

  useEffect(() => {
    if (!datasetId || !charts || charts.length === 0) return;
    setLoadingData(true);
    fetch(`${API_BASE}/data/rows/${datasetId}?limit=5000`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setDataRows(data.rows || []);
        setLoadingData(false);
      })
      .catch((err) => {
        console.error("Failed to load data rows:", err);
        setDataRows([]);
        setLoadingData(false);
      });
  }, [datasetId, charts]);

  /* ── Empty State ── */
  if (!charts || charts.length === 0) {
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
          <BarChart3 size={32} color="var(--text-muted)" />
        </div>
        <div>
          <p style={{ fontWeight: 700, fontSize: 15, color: "var(--text-secondary)", marginBottom: 6 }}>
            No visualizations yet
          </p>
          <p style={{ fontSize: 13, color: "var(--text-muted)", maxWidth: 300, lineHeight: 1.6 }}>
            Ask a question in Chat and the AI will generate interactive charts here.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "center", marginTop: 8 }}>
          {[
            "Show sales trends",
            "Compare categories",
            "Top 10 items",
          ].map((ex) => (
            <span
              key={ex}
              style={{
                padding: "5px 12px",
                borderRadius: "var(--radius-full)",
                background: "var(--bg-elevated)",
                border: "1px solid var(--border-strong)",
                fontSize: 11.5,
                color: "var(--text-muted)",
              }}
            >
              "{ex}"
            </span>
          ))}
        </div>
      </div>
    );
  }

  /* ── Loading State ── */
  if (loadingData) {
    return (
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(380px, 1fr))",
          gap: 20,
          padding: 24,
        }}
      >
        {charts.map((_, i) => (
          <ChartSkeleton key={i} />
        ))}
      </div>
    );
  }

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(380px, 1fr))",
        gap: 20,
        padding: 24,
        alignItems: "start",
      }}
    >
      {charts.map((chart, i) => (
        <ChartCard key={i} chart={chart} index={i} dataRows={dataRows} />
      ))}
    </div>
  );
}

/* ── Chart Skeleton ── */
function ChartSkeleton() {
  return (
    <div className="chart-card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <div className="skeleton" style={{ width: 160, height: 14 }} />
          <div className="skeleton" style={{ width: 100, height: 11 }} />
        </div>
        <div className="skeleton" style={{ width: 50, height: 20, borderRadius: "var(--radius-full)" }} />
      </div>
      <div className="skeleton" style={{ width: "100%", height: 240 }} />
    </div>
  );
}

/* ── Single Chart Card ── */
function ChartCard({ chart, index, dataRows }) {
  const containerRef = useRef(null);
  const [expanded, setExpanded] = useState(false);
  const [renderError, setRenderError] = useState(null);

  useEffect(() => {
    if (!chart?.vega_lite_spec || !containerRef.current) return;
    let isMounted = true;
    setRenderError(null);

    import("vega-embed").then(({ default: vegaEmbed }) => {
      if (!isMounted || !containerRef.current) return;
      const spec = {
        $schema: "https://vega.github.io/schema/vega-lite/v5.json",
        autosize: { type: "fit", contains: "padding" },
        ...chart.vega_lite_spec,
        width: "container",
        height: expanded ? 480 : 260,
        background: "transparent",
        data:
          dataRows && dataRows.length > 0
            ? { values: dataRows }
            : chart.vega_lite_spec.data || { values: [] },
        config: {
          axis: {
            labelColor: "#94A3B8",
            titleColor: "#CBD5E1",
            gridColor: "rgba(255,255,255,0.04)",
            domainColor: "rgba(255,255,255,0.08)",
            tickColor: "rgba(255,255,255,0.08)",
            labelFont: "Plus Jakarta Sans, sans-serif",
            titleFont: "Plus Jakarta Sans, sans-serif",
            labelFontSize: 11,
            titleFontSize: 12,
            titleFontWeight: 600,
          },
          legend: {
            labelColor: "#94A3B8",
            titleColor: "#CBD5E1",
            labelFont: "Plus Jakarta Sans, sans-serif",
            titleFont: "Plus Jakarta Sans, sans-serif",
            labelFontSize: 11,
            titleFontSize: 11,
          },
          title: {
            color: "#F1F5F9",
            fontSize: 13,
            fontWeight: 700,
            font: "Plus Jakarta Sans, sans-serif",
            anchor: "start",
            offset: 8,
          },
          view: { stroke: "transparent" },
          range: {
            category: [
              "#6366F1", "#8B5CF6", "#10B981",
              "#F59E0B", "#EF4444", "#06B6D4",
              "#EC4899", "#84CC16",
            ],
          },
          mark: { tooltip: true },
          ...(chart.vega_lite_spec.config || {}),
        },
      };

      if (!containerRef.current) return;
      vegaEmbed(containerRef.current, spec, {
        actions: false,
        renderer: "svg",
        theme: "dark",
      }).catch((err) => {
        if (isMounted) {
          console.error("Vega render error:", err);
          setRenderError(err.message || "Failed to render chart");
        }
      });
    });

    return () => {
      isMounted = false;
    };
  }, [chart, dataRows, expanded]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.08, duration: 0.35 }}
      className="chart-card"
      style={{ gridColumn: expanded ? "1 / -1" : "auto" }}
    >
      {/* Card header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 16 }}>
        <div style={{ flex: 1, minWidth: 0, marginRight: 12 }}>
          <h3
            style={{
              fontWeight: 700,
              fontSize: 14,
              color: "var(--text-primary)",
              lineHeight: 1.3,
              marginBottom: 3,
            }}
          >
            {chart.title || "Visualization"}
          </h3>
          {chart.description && (
            <p
              style={{
                fontSize: 12,
                color: "var(--text-muted)",
                display: "-webkit-box",
                WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
              }}
            >
              {chart.description}
            </p>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
          <span className="badge badge-info">
            <TrendingUp size={9} />
            Live
          </span>
          <button
            onClick={() => setExpanded(!expanded)}
            className="btn btn-ghost btn-icon btn-sm"
            title={expanded ? "Collapse" : "Expand"}
          >
            {expanded ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
          </button>
        </div>
      </div>

      {/* Chart area */}
      {renderError ? (
        <div
          style={{
            minHeight: 220,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 8,
            background: "var(--bg-surface)",
            borderRadius: "var(--radius-md)",
            padding: 24,
          }}
        >
          <RefreshCw size={20} color="var(--text-muted)" />
          <p style={{ fontSize: 12, color: "var(--danger)", fontWeight: 600 }}>Render error</p>
          <p style={{ fontSize: 11, color: "var(--text-muted)", textAlign: "center", maxWidth: 280 }}>
            {renderError}
          </p>
        </div>
      ) : (
        <div
          ref={containerRef}
          style={{
            width: "100%",
            minHeight: expanded ? 480 : 260,
            transition: "min-height 0.3s ease",
          }}
        />
      )}
    </motion.div>
  );
}
