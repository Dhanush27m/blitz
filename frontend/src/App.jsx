import React, { useState } from "react";
import axios from "axios";
import CytoscapeComponent from "react-cytoscapejs";

const API_BASE = "http://localhost:8000";

function buildElements(graph) {
  if (!graph) return [];
  const elements = [];
  for (const node of graph.nodes) {
    elements.push({
      data: {
        id: node.id,
        label: node.label,
        suspicion_score: node.suspicion_score ?? 0,
        patterns: (node.detected_patterns || []).join(", "),
      },
    });
  }
  for (const edge of graph.edges) {
    elements.push({
      data: {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        amount: edge.amount,
        timestamp: edge.timestamp,
      },
    });
  }
  return elements;
}

const layout = { name: "cose", animate: false };

const stylesheet = [
  {
    selector: "node",
    style: {
      label: "data(label)",
      "font-size": 10,
      "text-valign": "center",
      "text-halign": "center",
      "background-color": (ele) =>
        (ele.data("suspicion_score") || 0) > 0 ? "#e74c3c" : "#3498db",
      "border-width": (ele) =>
        (ele.data("suspicion_score") || 0) > 0 ? 2 : 0,
      "border-color": "#2c3e50",
      width: (ele) => {
        const s = ele.data("suspicion_score") || 0;
        return 20 + Math.min(s, 100) * 0.3;
      },
      height: (ele) => {
        const s = ele.data("suspicion_score") || 0;
        return 20 + Math.min(s, 100) * 0.3;
      },
    },
  },
  {
    selector: "edge",
    style: {
      width: 1,
      "line-color": "#bdc3c7",
      "target-arrow-color": "#7f8c8d",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
    },
  },
];

export default function App() {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [analysis, setAnalysis] = useState(null);
  const [graph, setGraph] = useState(null);

  const onFileChange = (e) => {
    setFile(e.target.files[0] || null);
  };

  const onUpload = async () => {
    if (!file) return;
    setLoading(true);
    setError("");
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await axios.post(`${API_BASE}/analyze`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setAnalysis(res.data.result);
      setGraph(res.data.graph);
    } catch (err) {
      console.error(err);
      const msg =
        err.response?.data?.detail ||
        err.message ||
        "Unexpected error while analyzing CSV";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const onDownloadJson = () => {
    if (!analysis) return;
    const blob = new Blob([JSON.stringify(analysis, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "money_muling_analysis.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  const elements = buildElements(graph);

  return (
    <div className="app">
      <header className="header">
        <h1>Money Muling Detection Engine</h1>
        <p>Graph-based analysis for cycles, smurfing, and shell networks.</p>
      </header>

      <section className="upload-section">
        <div className="upload-controls">
          <input type="file" accept=".csv" onChange={onFileChange} />
          <button onClick={onUpload} disabled={!file || loading}>
            {loading ? "Processing..." : "Analyze CSV"}
          </button>
          <button onClick={onDownloadJson} disabled={!analysis}>
            Download JSON
          </button>
        </div>
        {error && <div className="error">{error}</div>}
      </section>

      {analysis && (
        <section className="summary-section">
          <h2>Summary</h2>
          <div className="summary-grid">
            <div className="summary-card">
              <span>Total accounts analyzed</span>
              <strong>{analysis.summary.total_accounts_analyzed}</strong>
            </div>
            <div className="summary-card">
              <span>Suspicious accounts flagged</span>
              <strong>{analysis.summary.suspicious_accounts_flagged}</strong>
            </div>
            <div className="summary-card">
              <span>Fraud rings detected</span>
              <strong>{analysis.summary.fraud_rings_detected}</strong>
            </div>
            <div className="summary-card">
              <span>Processing time (s)</span>
              <strong>{analysis.summary.processing_time_seconds}</strong>
            </div>
          </div>
        </section>
      )}

      <main className="main-layout">
        <section className="graph-section">
          <h2>Interactive Graph Viewer</h2>
          {elements.length > 0 ? (
            <CytoscapeComponent
              elements={elements}
              style={{ width: "100%", height: "500px", borderRadius: 8 }}
              layout={layout}
              stylesheet={stylesheet}
            />
          ) : (
            <div className="placeholder">
              Upload and analyze a CSV to see the transaction graph.
            </div>
          )}
        </section>

        <section className="table-section">
          <h2>Fraud Ring Table</h2>
          {analysis && analysis.fraud_rings.length > 0 ? (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Ring ID</th>
                    <th>Pattern Type</th>
                    <th>Member Count</th>
                    <th>Risk Score</th>
                    <th>Member Accounts</th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.fraud_rings.map((ring) => (
                    <tr key={ring.ring_id}>
                      <td>{ring.ring_id}</td>
                      <td>{ring.pattern_type}</td>
                      <td>{ring.member_accounts.length}</td>
                      <td>{ring.risk_score}</td>
                      <td>{ring.member_accounts.join(", ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="placeholder">
              No fraud rings detected for the current dataset.
            </div>
          )}

          <h2>Suspicious Accounts</h2>
          {analysis && analysis.suspicious_accounts.length > 0 ? (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Account ID</th>
                    <th>Suspicion Score</th>
                    <th>Detected Patterns</th>
                    <th>Ring ID</th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.suspicious_accounts.map((acc) => (
                    <tr key={acc.account_id}>
                      <td>{acc.account_id}</td>
                      <td>{acc.suspicion_score}</td>
                      <td>{acc.detected_patterns.join(", ")}</td>
                      <td>{acc.ring_id}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="placeholder">
              No suspicious accounts detected for the current dataset.
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

