"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  MessageSquare,
  BarChart3,
  Lightbulb,
  GitBranch,
  ChevronLeft,
  ChevronRight,
  Settings,
  History,
} from "lucide-react";

const NAV_ITEMS = [
  { id: "chat",      label: "Chat",       icon: MessageSquare, desc: "Talk to your data" },
  { id: "dashboard", label: "Dashboard",  icon: BarChart3,     desc: "Visual analytics" },
  { id: "insights",  label: "Insights",   icon: Lightbulb,     desc: "AI-generated insights" },
  { id: "taskflow",  label: "Task Flow",  icon: GitBranch,     desc: "Agent reasoning chain" },
];

const FOOTER_ITEMS = [
  { id: "history",  label: "History",  icon: History },
  { id: "settings", label: "Settings", icon: Settings },
];

export default function Sidebar({ activeTab, onTabChange, insightCount }) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <motion.aside
      animate={{ width: collapsed ? 64 : 240 }}
      transition={{ duration: 0.22, ease: [0.4, 0, 0.2, 1] }}
      className="sidebar"
      style={{ overflow: "hidden", flexShrink: 0 }}
    >
      {/* Header with collapse toggle */}
      <div className="sidebar-header">
        <button
          className="sidebar-toggle"
          onClick={() => setCollapsed(!collapsed)}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronRight size={13} /> : <ChevronLeft size={13} />}
        </button>
      </div>

      {/* Main navigation */}
      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          const badge = item.id === "insights" && insightCount > 0 ? insightCount : null;

          return (
            <button
              key={item.id}
              className={`sidebar-item ${isActive ? "active" : ""}`}
              onClick={() => onTabChange(item.id)}
              title={collapsed ? item.label : ""}
            >
              <span className="sidebar-icon">
                <Icon
                  size={17}
                  strokeWidth={isActive ? 2.2 : 1.8}
                />
              </span>

              <AnimatePresence>
                {!collapsed && (
                  <motion.span
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.15 }}
                    className="sidebar-label"
                    style={{ fontSize: 13.5, whiteSpace: "nowrap" }}
                  >
                    {item.label}
                  </motion.span>
                )}
              </AnimatePresence>

              {!collapsed && badge && (
                <span className="sidebar-badge">{badge}</span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Footer navigation */}
      <div className="sidebar-footer">
        {FOOTER_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              className="sidebar-item"
              title={collapsed ? item.label : ""}
            >
              <span className="sidebar-icon">
                <Icon size={17} strokeWidth={1.8} />
              </span>
              <AnimatePresence>
                {!collapsed && (
                  <motion.span
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.15 }}
                    className="sidebar-label"
                    style={{ fontSize: 13.5, whiteSpace: "nowrap" }}
                  >
                    {item.label}
                  </motion.span>
                )}
              </AnimatePresence>
            </button>
          );
        })}
      </div>
    </motion.aside>
  );
}
