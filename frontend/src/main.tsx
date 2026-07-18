import React, { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "biings-ds/build/bds.css";
import "./styles.css";

type NodeRow = {
  node_order: number;
  node_name: string;
};

type GuidewordRow = {
  node_order: number;
  node_name: string;
  parameter: string;
  guideword: string;
};

type PreviewData = {
  nodes: NodeRow[];
  guidewords: GuidewordRow[];
};

type AgentEvent = {
  title?: string;
  detail?: string;
  kind?: LogKind;
  message?: string;
  loading?: boolean;
};

type LogKind = "system" | "agent" | "skill" | "tool" | "result" | "warning" | "error";

type LogGroup = {
  id: string;
  title: string;
  detail: string;
  kind: LogKind;
  loading?: boolean;
  children: ChildLog[];
};

type ChildLog = {
  id: string;
  title: string;
  detail: string;
  kind: LogKind;
  loading?: boolean;
};

type RiskRow = Record<string, unknown>;
type ActionRow = Record<string, unknown>;

type HazopResult = {
  risk_rows: RiskRow[];
  action_rows: ActionRow[];
  output_excel?: string;
};

function App() {
  const [file, setFile] = useState<File | null>(null);
  const [maker, setMaker] = useState("CleanTech");
  const [model, setModel] = useState("CT-DIW-100");
  const [similarHazopId, setSimilarHazopId] = useState("STD-HAZOP-DIW-UTILITY-2026-001");
  const [operationIntent, setOperationIntent] = useState(
    "CleanTech CT-DIW-100 신규 도입 PoC 검토용 입력입니다.\nDI Water 공급 중단, 유량 저하, 누수 중심으로 초안을 생성합니다.",
  );
  const [incidentHistory, setIncidentHistory] = useState("최근 3년간 중대 사고 없음");
  const [preview, setPreview] = useState<PreviewData>({ nodes: [], guidewords: [] });
  const [nodeMaterials, setNodeMaterials] = useState<Record<string, string>>({});
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [logs, setLogs] = useState<LogGroup[]>([]);
  const [status, setStatus] = useState("대기 중");
  const [result, setResult] = useState<HazopResult | null>(null);
  const [downloadPath, setDownloadPath] = useState("");
  const [error, setError] = useState("");
  const currentSubAgentId = useRef<string | null>(null);
  const logScrollRef = useRef<HTMLDivElement | null>(null);
  const shouldStickToBottom = useRef(true);

  const guidewordsByNode = useMemo(() => {
    const grouped = new Map<string, GuidewordRow[]>();
    preview.guidewords.forEach((item) => {
      const key = nodeKey(item.node_order, item.node_name);
      grouped.set(key, [...(grouped.get(key) || []), item]);
    });
    return grouped;
  }, [preview.guidewords]);

  const isRunning = ["업로드 중", "Agent 실행 중"].includes(status);
  const generationStage = useMemo(() => getGenerationStage(logs, status), [logs, status]);

  useEffect(() => {
    if (!shouldStickToBottom.current || !logScrollRef.current) return;
    logScrollRef.current.scrollTop = logScrollRef.current.scrollHeight;
  }, [logs]);

  async function handleFileChange(nextFile: File | null) {
    setFile(nextFile);
    setError("");
    if (!nextFile) {
      setPreview({ nodes: [], guidewords: [] });
      setNodeMaterials({});
      return;
    }

    setIsPreviewLoading(true);
    const startedAt = Date.now();
    const formData = new FormData();
    formData.append("file", nextFile);

    try {
      const response = await fetch("/api/excel/nodes", { method: "POST", body: formData });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Node List를 읽지 못했습니다.");
      await waitAtLeast(startedAt, 1000);
      const nextPreview = {
        nodes: data.nodes || [],
        guidewords: data.guidewords || [],
      };
      setPreview(nextPreview);
      const nextMaterials: Record<string, string> = {};
      nextPreview.nodes.forEach((node: NodeRow) => {
        nextMaterials[node.node_name] = nodeMaterials[node.node_name] || "";
      });
      setNodeMaterials(nextMaterials);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Node List를 읽지 못했습니다.");
    } finally {
      setIsPreviewLoading(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setResult(null);
    setDownloadPath("");
    setLogs([]);
    currentSubAgentId.current = null;
    shouldStickToBottom.current = true;

    if (!file) {
      setError("xlsx 파일을 먼저 업로드해 주세요.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    formData.append("maker", maker);
    formData.append("model", model);
    formData.append("materials", uniqueMaterials(nodeMaterials));
    formData.append("node_materials", nodeMaterialText(nodeMaterials));
    formData.append("standard_hazop_link", similarHazopId);
    formData.append("notes", operationIntent);
    formData.append("incident_maintenance_history", incidentHistory);

    setStatus("업로드 중");
    const response = await fetch("/api/jobs", { method: "POST", body: formData });
    if (!response.ok) {
      const data = await response.json();
      setError(data.detail || "작업 생성 실패");
      setStatus("실패");
      return;
    }

    const { job_id } = await response.json();
    appendLog({ title: "작업 생성 완료", detail: `job_id=${job_id}`, kind: "system" });
    setStatus("Agent 실행 중");

    const source = new EventSource(`/api/jobs/${job_id}/events`);
    source.addEventListener("log", (message) => appendLog(JSON.parse((message as MessageEvent).data)));
    source.addEventListener("error", (message) => {
      const event = message as MessageEvent;
      if (event.data) {
        const data = JSON.parse(event.data);
        appendLog({ title: "오류", detail: data.message, kind: "error" });
      }
      setStatus("실패");
      source.close();
    });
    source.addEventListener("done", (message) => {
      const data = JSON.parse((message as MessageEvent).data);
      setResult({ risk_rows: data.risk_rows || [], action_rows: data.action_rows || [], output_excel: data.output_excel });
      setDownloadPath(data.output_excel || "");
      appendLog({ title: "생성 완료", detail: "#3/#4 초안과 결과 Excel이 준비되었습니다.", kind: "result" });
      setStatus("완료");
      source.close();
    });
  }

  function appendLog(event: AgentEvent) {
    const title = describeAgentRoles(event.title || event.message || "Agent 로그");
    const detail = describeAgentRoles(event.detail || "");
    const kind = event.kind || "agent";
    const loading = Boolean(event.loading) || title === "Deepagent가 초안을 생성 중입니다.";
    const progressLog = title === "Deepagent가 초안을 생성 중입니다.";

    setLogs((previous) => {
      const next = [...previous];
      const subAgentStart = title.includes("Sub Agent") || title.includes("Sub Agent 흐름");
      const childCandidate = currentSubAgentId.current && ["skill", "tool", "result"].includes(kind);

      if (progressLog) {
        const progressIndex = next.findIndex((item) => item.title === title && item.loading);
        if (progressIndex >= 0) {
          next[progressIndex] = { ...next[progressIndex], detail, kind, loading: true };
          return next;
        }
        return [...next, makeLogGroup(title, detail, kind, true)];
      }

      if (subAgentStart) {
        const group = makeLogGroup(title, detail, kind, true);
        currentSubAgentId.current = group.id;
        return [...next, group];
      }

      if (childCandidate) {
        const targetIndex = next.findIndex((item) => item.id === currentSubAgentId.current);
        if (targetIndex >= 0) {
          const target = next[targetIndex];
          const baseChildren = loading ? [...target.children] : target.children.map((child) => ({ ...child, loading: false }));
          const sameLoadingChildIndex = baseChildren.findIndex((child) => child.title === title && child.loading);
          const nextParentLoading = loading ? target.loading : kind === "result" ? false : target.loading;
          if (sameLoadingChildIndex >= 0) {
            baseChildren[sameLoadingChildIndex] = { ...baseChildren[sameLoadingChildIndex], detail, kind, loading };
            next[targetIndex] = { ...target, loading: nextParentLoading, children: baseChildren };
            return next;
          }
          next[targetIndex] = {
            ...target,
            loading: nextParentLoading,
            children: [...baseChildren, makeChildLog(title, detail, kind, loading)],
          };
          return next;
        }
      }

      next.push(makeLogGroup(title, detail, kind));
      return next;
    });
  }

  function handleLogScroll() {
    const element = logScrollRef.current;
    if (!element) return;
    const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
    shouldStickToBottom.current = distanceFromBottom < 32;
  }

  return (
    <main className="app-shell">
      <section className="workspace">
        <header className="hero">
          <p className="eyebrow">HAZOP Draft Workspace</p>
          <h1>HAZOP AI Agent PoC</h1>
          <p>업로드 Excel의 #1 노드리스트와 #2 가이드워드만 기준으로 #3/#4 초안을 생성합니다.</p>
        </header>

        <form className="work-grid" onSubmit={handleSubmit}>
          <section className="panel input-panel">
            <div className="panel-title">
              <span>01</span>
              <h2>파일 및 입력</h2>
            </div>
            <div className="panel-scroll input-scroll">
              <label className="file-drop">
                <input type="file" accept=".xlsx" onChange={(event) => handleFileChange(event.target.files?.[0] || null)} />
                <strong>{file ? file.name : "Excel 파일 선택"}</strong>
                <span>xlsx 파일을 업로드하면 Node List를 자동으로 읽습니다.</span>
              </label>
              <div className="field-grid two">
                <Field label="Maker" value={maker} onChange={setMaker} />
                <Field label="Model" value={model} onChange={setModel} />
              </div>
              <Field label="유사 HAZOP 문서 ID" value={similarHazopId} onChange={setSimilarHazopId} />
              <Textarea label="운전 의도" value={operationIntent} onChange={setOperationIntent} rows={4} />
              <Textarea label="사고 정비 이력" value={incidentHistory} onChange={setIncidentHistory} rows={4} />
              {error ? <div className="error-message">{error}</div> : null}
              <button className="primary-button" type="submit">
                AI 초안생성
              </button>
            </div>
          </section>

          <section className="panel node-panel">
            <div className="panel-title">
              <span>02</span>
              <h2>Node List</h2>
            </div>
            <div className="panel-scroll node-scroll">
              {isPreviewLoading ? (
                <div className="node-loading">
                  <div className="progress-ring" />
                  <strong>노드를 불러오는 중입니다.</strong>
                  <span>#1 노드리스트와 #2 가이드워드를 읽고 있습니다.</span>
                </div>
              ) : preview.nodes.length === 0 ? (
                <div className="empty-node">
                  <strong>아직 불러온 Node가 없습니다.</strong>
                  <span>왼쪽에서 Excel을 업로드하면 #1 노드리스트가 여기에 표시됩니다.</span>
                </div>
              ) : (
                <div className="node-table">
                  <div className="node-table-head">
                    <span>Node</span>
                    <span>Guideword</span>
                    <span>물질</span>
                  </div>
                  {preview.nodes.map((node) => {
                    const key = nodeKey(node.node_order, node.node_name);
                    const guidewords = guidewordsByNode.get(key) || [];
                    return (
                      <div className="node-row" key={key}>
                        <div className="node-name">
                          <span>NODE {String(node.node_order).padStart(2, "0")}</span>
                          <strong>{node.node_name}</strong>
                        </div>
                        <div className="chip-list">
                          {guidewords.map((item) => (
                            <span className="guideword-chip" key={`${item.parameter}-${item.guideword}`}>
                              {item.parameter} / {item.guideword}
                            </span>
                          ))}
                        </div>
                        <input
                          aria-label={`${node.node_name} 물질`}
                          placeholder="물질 key-in"
                          value={nodeMaterials[node.node_name] || ""}
                          onChange={(event) =>
                            setNodeMaterials((previous) => ({
                              ...previous,
                              [node.node_name]: event.target.value,
                            }))
                          }
                        />
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </section>

        </form>

        <section className="output-grid">
          <section className="result-panel">
            <div className="result-header">
              <div>
                <span>Result</span>
                <h2>#3 위험성평가 / #4 조치계획서</h2>
              </div>
              {downloadPath ? (
                <a className="download-button" href={`/api/download?path=${encodeURIComponent(downloadPath)}`}>
                  결과 Excel 다운로드
                </a>
              ) : null}
            </div>
            {!result ? (
              isRunning ? (
                <div className="result-progress" role="status" aria-live="polite" aria-busy="true">
                  <div className="result-wait-indicator" aria-hidden="true">
                    <span />
                    <span />
                    <span />
                  </div>
                  <div>
                    <strong>{generationStage.title}</strong>
                    <p>{generationStage.detail}</p>
                  </div>
                </div>
              ) : (
                <div className="empty-result">초안 생성이 완료되면 결과 테이블이 이 영역에 표시됩니다.</div>
              )
            ) : (
              <div className="result-tables">
                <ResultTable title="#3 위험성평가" rows={result.risk_rows} />
                <ResultTable title="#4 조치계획서" rows={result.action_rows} emptyText="위험도 9 이상 항목이 없어 별도 조치계획서가 생성되지 않았습니다." />
              </div>
            )}
          </section>

          <section className="panel log-panel-wrap">
            <div className="panel-title">
              <span>03</span>
              <h2>Agent 로그</h2>
            </div>
            <div className="status-row">
              <span className={isRunning ? "status-pill is-running" : "status-pill"}>
                {isRunning ? <i aria-hidden="true" /> : null}
                {status}
              </span>
              <small>맨 아래에 있을 때만 자동 스크롤됩니다.</small>
            </div>
            <div className="log-box" ref={logScrollRef} onScroll={handleLogScroll}>
              {logs.length === 0 ? (
                <div className="empty-log">AI 초안생성을 누르면 Agent 로그가 여기에 쌓입니다.</div>
              ) : (
                logs.map((item, index) => <LogCard item={item} index={index} key={item.id} />)
              )}
            </div>
          </section>
        </section>
      </section>
    </main>
  );
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function Textarea({ label, value, onChange, rows }: { label: string; value: string; onChange: (value: string) => void; rows: number }) {
  return (
    <label className="field">
      <span>{label}</span>
      <textarea value={value} rows={rows} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function LogCard({ item, index }: { item: LogGroup; index: number }) {
  return (
    <article className={`log-card kind-${item.kind}`}>
      <div className="log-card-top">
        <span className="log-kind">{logKindLabel(item.kind)}</span>
        <span className="log-step">STEP {String(index + 1).padStart(2, "0")}</span>
      </div>
      <div className="log-title-line">
        {item.loading ? <i aria-hidden="true" /> : null}
        <strong>{item.title}</strong>
      </div>
      {item.detail ? <p>{item.detail}</p> : null}
      {item.children.length ? (
        <div className="child-logs">
          {item.children.map((child) => (
            <div className={`child-log kind-${child.kind}`} key={child.id}>
              <span>{child.loading ? <i aria-hidden="true" /> : logKindLabel(child.kind)}</span>
              <div>
                <strong>{child.title}</strong>
                {child.detail ? <p>{child.detail}</p> : null}
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function ResultTable({ title, rows, emptyText }: { title: string; rows: RiskRow[]; emptyText?: string }) {
  if (!rows.length) {
    return (
      <div className="table-card">
        <h3>{title}</h3>
        <p className="empty-result">{emptyText || "생성된 Row가 없습니다."}</p>
      </div>
    );
  }
  const headers = Object.keys(rows[0]);
  return (
    <div className="table-card">
      <h3>{title}</h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {headers.map((header) => (
                <th className={columnClassName(header)} key={header}>
                  {displayColumnName(header)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {headers.map((header) => (
                  <td className={columnClassName(header)} key={header}>
                    {formatCell(row[header])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function makeLogGroup(title: string, detail: string, kind: LogKind, loading = false): LogGroup {
  return { id: crypto.randomUUID(), title, detail, kind, loading, children: [] };
}

function makeChildLog(title: string, detail: string, kind: LogKind, loading = false): ChildLog {
  return { id: crypto.randomUUID(), title, detail, kind, loading };
}

function nodeKey(order: number, name: string) {
  return `${order}:${name}`;
}

function nodeMaterialText(values: Record<string, string>) {
  return Object.entries(values)
    .filter(([, material]) => material.trim())
    .map(([nodeName, material]) => `${nodeName}: ${material.trim()}`)
    .join("\n");
}

function uniqueMaterials(values: Record<string, string>) {
  const materials = new Set(Object.values(values).map((value) => value.trim()).filter(Boolean));
  return Array.from(materials).join("\n") || "확인 필요";
}

function waitAtLeast(startedAt: number, ms: number) {
  const remaining = ms - (Date.now() - startedAt);
  return new Promise((resolve) => window.setTimeout(resolve, Math.max(0, remaining)));
}

function logKindLabel(kind: LogKind) {
  return {
    system: "시스템",
    agent: "Agent",
    skill: "Skill",
    tool: "Tool",
    result: "Result",
    warning: "주의",
    error: "Error",
  }[kind];
}

function describeAgentRoles(value: string) {
  const roles: Array<[string, string]> = [
    ["risk-draft-agent", "risk-draft-agent (위험성평가 초안 작성)"],
    ["risk-review-agent", "risk-review-agent (위험도 계산·근거 검토)"],
    ["action-plan-agent", "action-plan-agent (고위험 항목 조치계획 작성)"],
  ];

  return roles.reduce((text, [agentName, label]) => {
    if (text.includes(label)) return text;
    return text.replaceAll(agentName, label);
  }, value);
}

function formatCell(value: unknown) {
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (item && typeof item === "object" && "reason" in item) {
          return String((item as { reason?: unknown }).reason || "");
        }
        return String(item);
      })
      .filter(Boolean)
      .join("\n");
  }
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value ?? "");
}

function displayColumnName(header: string) {
  const labels: Record<string, string> = {
    no: "No.",
    node_order: "Node 순번",
    node_name: "Node명",
    parameter: "변수",
    guideword: "Guideword",
    deviation: "이탈",
    possible_causes: "가능 원인",
    causes: "원인",
    consequences: "예상 결과",
    consequence: "결과",
    safeguards: "현재 안전조치",
    existing_safeguards: "기존 안전조치",
    frequency: "빈도",
    severity: "강도",
    risk_score: "위험도",
    risk_level: "위험 등급",
    recommendations: "권고 조치",
    recommendation: "권고 조치",
    action_item: "조치 내용",
    action_owner: "담당 부서",
    owner: "담당",
    due_date: "완료 기한",
    completion_criteria: "완료 기준",
    basis: "근거",
    rationale: "판단 근거",
    msds_basis: "MSDS 근거",
    material: "물질",
    priority: "우선순위",
    status: "상태",
  };
  return labels[header] || header.replaceAll("_", " ");
}

function columnClassName(header: string) {
  const compactColumns = new Set(["no", "node_order", "frequency", "severity", "risk_score"]);
  return compactColumns.has(header) ? "numeric-column" : undefined;
}

function getGenerationStage(logs: LogGroup[], status: string) {
  if (status === "업로드 중") {
    return {
      title: "Excel 입력값을 확인하는 중입니다.",
      detail: "#1 노드리스트와 #2 가이드워드가 초안 생성 기준에 맞는지 점검하고 있습니다.",
    };
  }

  const recentText = [...logs]
    .reverse()
    .flatMap((group) => [
      `${group.title} ${group.detail}`,
      ...[...group.children].reverse().map((child) => `${child.title} ${child.detail}`),
    ])
    .join("\n");

  if (recentText.includes("action-plan-agent") || recentText.includes("hazop_action_plan") || recentText.includes("#4 조치계획서")) {
    return {
      title: "#4 조치계획서를 작성하는 중입니다.",
      detail: "위험도 9 이상 항목을 기준으로 권고 조치, 담당 부서, 완료 기준을 정리하고 있습니다.",
    };
  }

  if (recentText.includes("risk-review-agent") || recentText.includes("calculate_hazop_risk") || recentText.includes("검토")) {
    return {
      title: "#3 위험도 계산과 검토를 진행 중입니다.",
      detail: "AI가 쓴 빈도와 강도를 시스템 규칙으로 다시 계산하고, 빠진 근거가 없는지 확인하고 있습니다.",
    };
  }

  if (recentText.includes("frequency_estimation") || recentText.includes("빈도") || recentText.includes("강도")) {
    return {
      title: "#3 빈도와 강도 근거를 정리하는 중입니다.",
      detail: "각 Guideword별 발생 가능성과 영향도를 HAZOP 초안 형식에 맞춰 채우고 있습니다.",
    };
  }

  if (recentText.includes("risk-draft-agent") || recentText.includes("hazop_risk_draft") || recentText.includes("모델 응답 대기")) {
    return {
      title: "#3 원인과 결과를 분석하는 중입니다.",
      detail: "Node와 Guideword 기준으로 이탈 원인, 예상 결과, 현재 안전조치를 작성하고 있습니다.",
    };
  }

  return {
    title: "#3/#4 초안 생성을 준비하는 중입니다.",
    detail: "입력 정보와 Agent 실행 흐름을 정리한 뒤 위험성평가 초안 생성을 시작합니다.",
  };
}

createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
