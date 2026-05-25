"use client";

import { useState, useEffect, useRef } from "react";
import { v4 as uuidv4 } from "uuid";
import PlotlyRenderer from "@/components/PlotlyRenderer";

// ── API Types ────────────────────────────────────────────────────────

interface SchemaProfile {
  column: string;
  dtype: string;
  null_count: number;
  unique_count: number;
  sample_values: any[];
}

interface CleaningReportSummary {
  nulls_filled: number;
  date_columns_converted: string[];
  outliers_flagged: number;
  string_columns_normalised: string[];
}

interface FileProcessed {
  filename: string;
  rows: number;
  columns: number;
  cleaning_report: CleaningReportSummary;
  schema: SchemaProfile[];
}

interface DetectedRelationship {
  file_a: string;
  file_b: string;
  join_column: string;
  overlap_ratio: number;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  type?: "text" | "chart";
  figure?: any;
  latency_ms?: number;
}

export default function Dashboard() {
  const [sessionId, setSessionId] = useState<string>("");
  const [files, setFiles] = useState<FileProcessed[]>([]);
  const [relationships, setRelationships] = useState<DetectedRelationship[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isQuerying, setIsQuerying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Accordion state
  const [expandedFile, setExpandedFile] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"cleaning" | "schema">("cleaning");

  const chatEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Initialise session UUID on client mount
  useEffect(() => {
    setSessionId(uuidv4());
  }, []);

  // Smooth scroll to latest chat bubble
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isQuerying]);

  const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

  // ── Handlers ────────────────────────────────────────────────────────

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = event.target.files;
    if (!selectedFiles || selectedFiles.length === 0) return;

    setIsUploading(true);
    setError(null);

    const formData = new FormData();
    formData.append("session_id", sessionId);
    for (let i = 0; i < selectedFiles.length; i++) {
      formData.append("files", selectedFiles[i]);
    }

    try {
      const response = await fetch(`${BACKEND_URL}/upload`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || "Failed to process files");
      }

      const data = await response.json();
      setFiles(data.files_processed);
      setRelationships(data.detected_relationships);
      if (data.files_processed.length > 0) {
        setExpandedFile(data.files_processed[0].filename);
      }
      
      // Seed first message with assistant instructions
      setMessages([
        {
          role: "assistant",
          content: `Data parsed and cleaned successfully! I have loaded ${data.files_processed.length} file(s) and auto-detected ${data.detected_relationships.length} relationship(s). Ask me anything about your datasets.`,
        },
      ]);
    } catch (err: any) {
      setError(err.message || "An error occurred during file upload.");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() || isQuerying) return;

    const userMessage = inputValue.trim();
    setInputValue("");
    setError(null);

    // Append user message immediately to chat UI
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setIsQuerying(true);

    try {
      const response = await fetch(`${BACKEND_URL}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          question: userMessage,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || "AI was unable to answer your query.");
      }

      const data = await response.json();
      
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer || "Chart generated below:",
          type: data.type,
          figure: data.figure,
          latency_ms: data.latency_ms,
        },
      ]);
    } catch (err: any) {
      setError(err.message || "Failed to submit query.");
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `⚠️ Error: ${err.message || "Failed to process query."}`,
        },
      ]);
    } finally {
      setIsQuerying(false);
    }
  };

  const handleClearSession = async () => {
    if (!confirm("Are you sure you want to clear this session? This deletes all files and memory.")) return;
    
    setError(null);
    try {
      await fetch(`${BACKEND_URL}/session/${sessionId}`, { method: "DELETE" });
      setFiles([]);
      setRelationships([]);
      setMessages([]);
      setExpandedFile(null);
      // Reset session ID
      setSessionId(uuidv4());
    } catch (err) {
      console.error("Failed to clear session:", err);
    }
  };

  return (
    <div className="dashboard-container">
      
      {/* ── LEFT SIDEBAR (UPLOADS & METADATA) ────────────────────────── */}
      <aside className="sidebar">
        
        {/* Header Title */}
        <div style={{ marginBottom: "2rem" }}>
          <h1 className="gradient-text" style={{ fontSize: "1.5rem", marginBottom: "0.25rem" }}>
            CDAS.ai
          </h1>
          <p style={{ fontSize: "0.75rem", color: "rgba(255,255,255,0.45)", fontWeight: 500 }}>
            Conversational Data Analysis System
          </p>
        </div>

        {error && (
          <div style={{ 
            background: "rgba(239, 68, 68, 0.1)", 
            border: "1px solid rgba(239, 68, 68, 0.2)",
            color: "#f87171",
            padding: "0.75rem 1rem",
            borderRadius: "0.5rem",
            fontSize: "0.8rem",
            marginBottom: "1.5rem"
          }}>
            {error}
          </div>
        )}

        {/* Upload Zone */}
        {files.length === 0 ? (
          <div 
            className="glass-panel" 
            style={{ display: "flex", flexDirection: "column", gap: "1rem", flex: 1 }}
          >
            <div 
              className="dropzone"
              onClick={() => fileInputRef.current?.click()}
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: "#a78bfa" }}>
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
              </svg>
              <div>
                <p style={{ fontWeight: 600, fontSize: "0.9rem", color: "#f3f4f6" }}>Upload CSV Files</p>
                <p style={{ fontSize: "0.75rem", color: "rgba(255,255,255,0.4)" }}>Select multiple files to join them</p>
              </div>
              <input 
                type="file" 
                ref={fileInputRef} 
                onChange={handleFileUpload} 
                multiple 
                accept=".csv" 
                style={{ display: "none" }}
              />
            </div>
            
            {isUploading && (
              <div className="pulse" style={{ textAlign: "center", color: "#a78bfa", fontSize: "0.85rem" }}>
                Analyzing and cleaning files...
              </div>
            )}
          </div>
        ) : (
          /* Processing Results */
          <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", flex: 1, overflowY: "auto" }}>
            
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.5)", fontWeight: 600 }}>
                ACTIVE DATASETS ({files.length})
              </span>
              <button 
                onClick={handleClearSession}
                style={{ 
                  background: "transparent", 
                  border: "none", 
                  color: "#f87171", 
                  fontSize: "0.75rem", 
                  cursor: "pointer",
                  fontWeight: 600
                }}
              >
                Clear All
              </button>
            </div>

            {/* Uploaded File Accordions */}
            {files.map((file) => (
              <div key={file.filename} className="accordion">
                <div 
                  className="accordion-header"
                  onClick={() => setExpandedFile(expandedFile === file.filename ? null : file.filename)}
                >
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.1rem" }}>
                    <span style={{ color: "#f3f4f6", fontSize: "0.85rem", fontWeight: 600 }}>{file.filename}</span>
                    <span style={{ color: "rgba(255,255,255,0.4)", fontSize: "0.7rem" }}>
                      {file.rows} rows • {file.columns} columns
                    </span>
                  </div>
                  <span style={{ fontSize: "0.7rem", color: "rgba(255,255,255,0.3)" }}>
                    {expandedFile === file.filename ? "▲" : "▼"}
                  </span>
                </div>

                {expandedFile === file.filename && (
                  <div className="accordion-content">
                    
                    {/* Inner Tabs */}
                    <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: "0.5rem" }}>
                      <button 
                        onClick={() => setActiveTab("cleaning")}
                        style={{
                          background: "transparent",
                          border: "none",
                          color: activeTab === "cleaning" ? "#c084fc" : "rgba(255,255,255,0.4)",
                          fontSize: "0.75rem",
                          cursor: "pointer",
                          fontWeight: 600
                        }}
                      >
                        Cleaning Log
                      </button>
                      <button 
                        onClick={() => setActiveTab("schema")}
                        style={{
                          background: "transparent",
                          border: "none",
                          color: activeTab === "schema" ? "#c084fc" : "rgba(255,255,255,0.4)",
                          fontSize: "0.75rem",
                          cursor: "pointer",
                          fontWeight: 600
                        }}
                      >
                        Data Profile
                      </button>
                    </div>

                    {/* Tab 1: Cleaning Summary */}
                    {activeTab === "cleaning" && (
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", fontSize: "0.8rem", color: "rgba(255,255,255,0.7)" }}>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span>Nulls Filled:</span>
                          <span style={{ color: "#a78bfa", fontWeight: 600 }}>{file.cleaning_report.nulls_filled}</span>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span>Outliers Flagged (IQR):</span>
                          <span style={{ color: "#a78bfa", fontWeight: 600 }}>{file.cleaning_report.outliers_flagged}</span>
                        </div>
                        <div>
                          <p style={{ marginBottom: "0.25rem" }}>String Columns Trimmed:</p>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem" }}>
                            {file.cleaning_report.string_columns_normalised.map(c => (
                              <span key={c} style={{ background: "rgba(255,255,255,0.05)", padding: "0.1rem 0.4rem", borderRadius: "0.25rem", fontSize: "0.7rem" }}>
                                {c}
                              </span>
                            )) || <span style={{ color: "rgba(255,255,255,0.3)" }}>None</span>}
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Tab 2: Column Schema Profiles */}
                    {activeTab === "schema" && (
                      <div style={{ overflowX: "auto" }}>
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Column</th>
                              <th>Type</th>
                              <th>Nulls</th>
                              <th>Unique</th>
                            </tr>
                          </thead>
                          <tbody>
                            {file.schema.map((col) => (
                              <tr key={col.column}>
                                <td style={{ color: "#f3f4f6", fontWeight: 500 }}>{col.column}</td>
                                <td><span className="mono" style={{ fontSize: "0.7rem", color: "rgba(255,255,255,0.5)" }}>{col.dtype}</span></td>
                                <td>{col.null_count}</td>
                                <td>{col.unique_count}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                  </div>
                )}
              </div>
            ))}

            {/* Detected Joins Section */}
            {relationships.length > 0 && (
              <div className="glass-panel" style={{ background: "rgba(20, 20, 28, 0.25)" }}>
                <p style={{ fontSize: "0.8rem", fontWeight: 600, color: "#c084fc", marginBottom: "0.75rem" }}>
                  AUTO-DETECTED RELATIONSHIPS
                </p>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  {relationships.map((rel, idx) => (
                    <div 
                      key={idx} 
                      className="relationship-badge"
                      style={{ justifyContent: "space-between", width: "100%" }}
                    >
                      <span>
                        {rel.file_a.replace("_csv", "")} ↔ {rel.file_b.replace("_csv", "")}
                      </span>
                      <span className="mono" style={{ color: "#f3f4f6", fontSize: "0.7rem", fontWeight: 600 }}>
                        {rel.join_column} ({Math.round(rel.overlap_ratio * 100)}%)
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

          </div>
        )}

      </aside>

      {/* ── RIGHT CHAT INTERFACE ─────────────────────────────────────── */}
      <main className="chat-container">
        
        {/* Chat History Messages */}
        <div className="chat-messages">
          {messages.length === 0 ? (
            <div style={{ 
              flex: 1, 
              display: "flex", 
              flexDirection: "column", 
              alignItems: "center", 
              justifyContent: "center",
              opacity: 0.6,
              textAlign: "center"
            }}>
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ color: "#a78bfa", marginBottom: "1rem" }}>
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
              <h2 style={{ fontSize: "1.2rem", fontWeight: 600, color: "white", marginBottom: "0.25rem" }}>
                No active data conversation
              </h2>
              <p style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.45)" }}>
                Upload one or more CSV files in the sidebar to begin interactive analysis.
              </p>
            </div>
          ) : (
            messages.map((msg, index) => (
              <div 
                key={index} 
                className={`chat-bubble ${msg.role}`}
              >
                {/* Text Response */}
                <div style={{ whiteSpace: "pre-line" }}>
                  {msg.content}
                </div>

                {/* Plotly Chart Response */}
                {msg.type === "chart" && msg.figure && (
                  <div style={{ marginTop: "1rem", background: "rgba(0,0,0,0.2)", borderRadius: "0.5rem", padding: "0.5rem", border: "1px solid rgba(255,255,255,0.04)" }}>
                    <PlotlyRenderer 
                      figure={msg.figure} 
                      chartId={`plotly-chart-${index}`} 
                    />
                  </div>
                )}

                {/* Micro Metadata */}
                {msg.latency_ms !== undefined && (
                  <div style={{ 
                    marginTop: "0.5rem", 
                    fontSize: "0.65rem", 
                    color: "rgba(255,255,255,0.3)", 
                    textAlign: "right",
                    fontWeight: 500
                  }}>
                    Latency: {msg.latency_ms}ms
                  </div>
                )}
              </div>
            ))
          )}

          {/* Thinking Indicator */}
          {isQuerying && (
            <div className="chat-bubble assistant pulse">
              <div style={{ display: "flex", gap: "0.3rem", alignItems: "center" }}>
                <div style={{ width: "6px", height: "6px", background: "#8b5cf6", borderRadius: "50%" }}/>
                <div style={{ width: "6px", height: "6px", background: "#a78bfa", borderRadius: "50%" }}/>
                <div style={{ width: "6px", height: "6px", background: "#c084fc", borderRadius: "50%" }}/>
                <span style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.5)", marginLeft: "0.25rem" }}>
                  Analyzing data...
                </span>
              </div>
            </div>
          )}

          <div ref={chatEndRef} />
        </div>

        {/* Input Bar Form */}
        <div className="chat-input-container">
          <form onSubmit={handleSendMessage} className="chat-input-wrapper">
            <textarea
              className="chat-textarea"
              placeholder={files.length === 0 ? "Upload datasets to start querying..." : "Ask a question about the datasets (e.g. show a line chart of sales)..."}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              disabled={files.length === 0 || isQuerying}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSendMessage(e);
                }
              }}
              rows={1}
            />
            <button 
              type="submit"
              className="btn-primary"
              disabled={!inputValue.trim() || isQuerying || files.length === 0}
              style={{ padding: "0 1.25rem", borderRadius: "0.75rem" }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <line x1="22" y1="2" x2="11" y2="13"/>
                <polygon points="22 2 15 22 11 13 2 9 22 2"/>
              </svg>
            </button>
          </form>
        </div>

      </main>

    </div>
  );
}
