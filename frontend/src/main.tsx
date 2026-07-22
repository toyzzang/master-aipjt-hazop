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
  agent_id?: string;
  phase?: "start" | "progress" | "finish";
  emphasis?: boolean;
  parent_kind?: LogKind;
  parent_event_key?: string;
  event_key?: string;
};

type RunMode = "pending" | "deepagent" | "demo";
type LogFilter = "all" | "planning" | "tool" | "self-correction";

type LogKind =
  | "system"
  | "workflow"
  | "planning"
  | "agent"
  | "skill"
  | "tool"
  | "validation"
  | "self-correction"
  | "replanning"
  | "result"
  | "warning"
  | "error";

type LogGroup = {
  id: string;
  title: string;
  detail: string;
  kind: LogKind;
  loading?: boolean;
  emphasis?: boolean;
  children: ChildLog[];
};

type ChildLog = {
  id: string;
  title: string;
  detail: string;
  kind: LogKind;
  loading?: boolean;
  emphasis?: boolean;
  eventKey?: string;
  children: ChildLog[];
};

type RiskRow = Record<string, unknown>;
type ActionRow = Record<string, unknown>;
type ReviewFinding = Record<string, unknown>;

type HazopResult = {
  risk_rows: RiskRow[];
  action_rows: ActionRow[];
  review_findings: ReviewFinding[];
  execution_plan?: Record<string, unknown>;
  output_excel?: string;
  mode?: string;
};

const ASM_DEMO_DEFAULTS = {
  maker: "ASM",
  model: "Epsilon3200",
  similarHazopId: "STD-HAZOP-SPECIALTY-GAS-2026-001",
  operationIntent:
    "ASM Epsilon3200 공정에 Silane과 Hydrogen을 정해진 유량으로 공급하고 Nitrogen으로 Purge하는 운전입니다.\nGas Cabinet 누출·파열, 배관 역류·공급 저하, MFC 유량·신호 이상, Purge 실패·과다 시 위험을 검토합니다.",
  incidentHistory:
    "최근 3년간 화재·폭발 및 인적 재해 없음.\n최근 1년간 Gas Cabinet 누출감지 경보 2회, MFC High Flow Alarm 2회, Purge 시작 실패로 완료 신호가 들어오지 않은 Near Miss 3회가 있었음.\n세 유형 모두 실제 화재·폭발 및 인적 피해로 이어지지 않았고 누설시험, MFC 교정, Purge Sequence 점검을 수행함.",
} as const;

const ASM_NODE_MATERIAL_DEFAULTS: Record<string, string> = {
  "Gas Cabinet": "Silane, Hydrogen",
  "VMB 및 공급 배관": "",
  "MFC 유량 제어 구간": "Silane",
  "Purge 및 Scrubber 구간": "Nitrogen, Silane, Hydrogen",
};

function App() {
  // 일반 접속은 빠른 로컬 테스트를 위해 ASM 예시값을 실제 기본값으로 사용합니다.
  // 영상 촬영은 /?recording=1로 접속해 빈 입력 화면에서 시작합니다.
  const isRecordingMode = new URLSearchParams(window.location.search).get("recording") === "1";
  const [file, setFile] = useState<File | null>(null);
  const [maker, setMaker] = useState(isRecordingMode ? "" : ASM_DEMO_DEFAULTS.maker);
  const [model, setModel] = useState(isRecordingMode ? "" : ASM_DEMO_DEFAULTS.model);
  const [similarHazopId, setSimilarHazopId] = useState(isRecordingMode ? "" : ASM_DEMO_DEFAULTS.similarHazopId);
  const [operationIntent, setOperationIntent] = useState(isRecordingMode ? "" : ASM_DEMO_DEFAULTS.operationIntent);
  const [incidentHistory, setIncidentHistory] = useState(isRecordingMode ? "" : ASM_DEMO_DEFAULTS.incidentHistory);
  const [preview, setPreview] = useState<PreviewData>({ nodes: [], guidewords: [] });
  const [nodeMaterials, setNodeMaterials] = useState<Record<string, string>>({});
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [logs, setLogs] = useState<LogGroup[]>([]);
  const [status, setStatus] = useState("대기 중");
  const [result, setResult] = useState<HazopResult | null>(null);
  const [downloadPath, setDownloadPath] = useState("");
  const [error, setError] = useState("");
  const [runMode, setRunMode] = useState<RunMode>("pending");
  const [runModeLabel, setRunModeLabel] = useState("실행 모드 확인 전");
  const [logFilter, setLogFilter] = useState<LogFilter>("all");
  const [isLogExpanded, setIsLogExpanded] = useState(false);
  const currentSubAgentId = useRef<string | null>(null);
  const agentGroupIds = useRef<Record<string, string>>({});
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
  const visibleLogs = useMemo(() => filterLogs(logs, logFilter), [logs, logFilter]);

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
        nextMaterials[node.node_name] =
          nodeMaterials[node.node_name] || (isRecordingMode ? "" : ASM_NODE_MATERIAL_DEFAULTS[node.node_name] || "");
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
    setRunMode("pending");
    setRunModeLabel("실행 모드 확인 중");
    currentSubAgentId.current = null;
    agentGroupIds.current = {};
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
    source.addEventListener("run_mode", (message) => {
      const data = JSON.parse((message as MessageEvent).data);
      setRunMode(data.mode === "deepagent" ? "deepagent" : "demo");
      setRunModeLabel(data.label || (data.mode === "deepagent" ? "DeepAgent" : "규칙 기반 Demo"));
    });
    let terminalErrorHandled = false;
    source.addEventListener("agent_error", (message) => {
      terminalErrorHandled = true;
      const data = JSON.parse((message as MessageEvent).data);
      const reason = data.message || "서버가 상세 오류 메시지를 보내지 않았습니다.";
      appendLog({
        title: data.title || "초안 생성에 실패했습니다.",
        detail: `실패 단계: ${data.stage || "확인 필요"}\n원인: ${reason}`,
        kind: "error",
      });
      setError(reason);
      stopAllLogSpinners();
      setStatus("실패");
      source.close();
    });
    source.onerror = () => {
      if (terminalErrorHandled) return;
      terminalErrorHandled = true;
      appendLog({
        title: "실시간 Agent 로그 연결이 끊겼습니다.",
        detail: "Agent 판단 실패가 아니라 브라우저와 서버 사이의 SSE 통신이 종료된 상태입니다. 중복 실행을 막기 위해 자동 재연결을 중지했습니다.",
        kind: "error",
      });
      setError("실시간 로그 연결이 끊겼습니다. 작업을 다시 실행해 주세요.");
      stopAllLogSpinners();
      setStatus("연결 끊김");
      source.close();
    };
    source.addEventListener("done", (message) => {
      const data = JSON.parse((message as MessageEvent).data);
      setResult({
        risk_rows: data.risk_rows || [],
        action_rows: data.action_rows || [],
        review_findings: data.review_findings || [],
        execution_plan: data.execution_plan,
        output_excel: data.output_excel,
        mode: data.mode,
      });
      if (data.mode) {
        setRunMode(data.mode === "deepagent" ? "deepagent" : "demo");
        setRunModeLabel(data.mode === "deepagent" ? "DeepAgent" : "규칙 기반 Demo");
      }
      setDownloadPath(data.output_excel || "");
      stopAllLogSpinners();
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
    const agentId = event.agent_id;
    const phase = event.phase;
    const emphasis = Boolean(event.emphasis);
    const parentKind = event.parent_kind;
    const parentEventKey = event.parent_event_key;
    const eventKey = event.event_key;

    setLogs((previous) => {
      const next = [...previous];

      // 새 Workflow는 각 로그에 정확한 Agent ID와 실행 단계를 보냅니다.
      // 제목 문자열에 의존하지 않고 해당 Agent 부모 블록 안에 로그를 모읍니다.
      if (agentId) {
        let groupId = agentGroupIds.current[agentId];
        let targetIndex = next.findIndex((item) => item.id === groupId);

        if (phase === "start" || targetIndex < 0) {
          if (targetIndex >= 0) {
            next[targetIndex] = { ...next[targetIndex], title, detail, kind, loading: true };
            return next;
          }
          const group = makeLogGroup(title, detail, kind, true, emphasis);
          agentGroupIds.current[agentId] = group.id;
          currentSubAgentId.current = group.id;
          return [...next, group];
        }

        const target = next[targetIndex];
        const finishing = phase === "finish";
        const stoppedChildren = finishing
          ? target.children.map(stopChildSpinner)
          : [...target.children];

        // 각 Agent 작업 중 실행된 근거 조회는 평평한 형제 로그가 아니라
        // 현재 작업(Self-Correction/초안 생성 등) 블록 아래에 묶습니다. 같은 event_key의 시작/완료 이벤트는
        // 새 줄을 추가하지 않고 같은 Tool 상태를 갱신합니다.
        if (parentKind) {
          const parentIndex = stoppedChildren.findIndex((child) =>
            parentEventKey ? child.eventKey === parentEventKey : child.kind === parentKind,
          );
          if (parentIndex >= 0) {
            const parent = stoppedChildren[parentIndex];
            const nestedChildren = [...parent.children];
            const nestedIndex = nestedChildren.findIndex((child) =>
              eventKey ? child.eventKey === eventKey : child.title === title,
            );
            const nestedLog = makeChildLog(title, detail, kind, loading && !finishing, emphasis, eventKey);
            if (nestedIndex >= 0) {
              nestedChildren[nestedIndex] = { ...nestedChildren[nestedIndex], ...nestedLog, id: nestedChildren[nestedIndex].id };
            } else {
              nestedChildren.push(nestedLog);
            }
            stoppedChildren[parentIndex] = { ...parent, children: nestedChildren };
            next[targetIndex] = { ...target, loading: !finishing, children: stoppedChildren };
            return next;
          }
        }
        // Planning은 '수립 중 → 수립 완료'라는 하나의 상태이므로 같은 블록을
        // 갱신합니다. Skill/Tool의 준비와 실제 적용 결과는 별도 사실이므로
        // 새 블록으로 추가하여 실행 증거가 사라지지 않게 합니다.
        const singletonKind = kind === "planning" || Boolean(eventKey);
        const duplicateIndex = stoppedChildren.findIndex((child) =>
          singletonKind
            ? eventKey
              ? child.eventKey === eventKey || (kind === "planning" && child.kind === "planning" && !child.eventKey)
              : child.kind === kind
            : child.title === title && child.detail === detail,
        );

        if (duplicateIndex >= 0) {
          stoppedChildren[duplicateIndex] = {
            ...stoppedChildren[duplicateIndex],
            title,
            detail,
            kind,
            loading: loading && !finishing,
            emphasis: stoppedChildren[duplicateIndex].emphasis || emphasis,
            eventKey: stoppedChildren[duplicateIndex].eventKey || eventKey,
          };
        } else {
          stoppedChildren.push(makeChildLog(title, detail, kind, loading && !finishing, emphasis, eventKey));
        }

        next[targetIndex] = {
          ...target,
          loading: !finishing,
          children: stoppedChildren,
        };
        if (finishing && currentSubAgentId.current === target.id) currentSubAgentId.current = null;
        return next;
      }

      const agentStart = title.includes("Agent를 실행합니다");
      const childCandidate = currentSubAgentId.current && ["skill", "tool", "result"].includes(kind);

      if (progressLog) {
        const progressIndex = next.findIndex((item) => item.title === title && item.loading);
        if (progressIndex >= 0) {
          next[progressIndex] = { ...next[progressIndex], detail, kind, loading: true };
          return next;
        }
        return [...next, makeLogGroup(title, detail, kind, true, emphasis)];
      }

      if (agentStart) {
        const group = makeLogGroup(title, detail, kind, true, emphasis);
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
            children: [...baseChildren, makeChildLog(title, detail, kind, loading, emphasis)],
          };
          return next;
        }
      }

      next.push(makeLogGroup(title, detail, kind, false, emphasis));
      return next;
    });
  }

  function handleLogScroll() {
    const element = logScrollRef.current;
    if (!element) return;
    const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
    shouldStickToBottom.current = distanceFromBottom < 32;
  }

  function stopAllLogSpinners() {
    setLogs((previous) =>
      previous.map((group) => ({
        ...group,
        loading: false,
        children: group.children.map(stopChildSpinner),
      })),
    );
    currentSubAgentId.current = null;
  }

  return (
    <main className="app-shell">
      <section className="workspace">
        <header className="hero">
          <p className="eyebrow">HAZOP Draft Workspace</p>
          <h1>공정위험평가서(HAZOP) 초안 작성 AI Agent</h1>
          <p>업로드 Excel의 #1 노드리스트와 #2 가이드워드를 기준으로 #3/#4 초안을 생성합니다.</p>
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
                <Field label="Maker" value={maker} placeholder="예: ASM" onChange={setMaker} />
                <Field label="Model" value={model} placeholder="예: Epsilon3200" onChange={setModel} />
              </div>
              <Field
                label="유사 HAZOP 문서 ID"
                value={similarHazopId}
                placeholder="예: STD-HAZOP-SPECIALTY-GAS-2026-001"
                onChange={setSimilarHazopId}
              />
              <Textarea
                label="운전 의도"
                value={operationIntent}
                placeholder="예: ASM Epsilon3200 공정에 Silane과 Hydrogen을 정해진 유량으로 공급하고 Nitrogen으로 Purge하는 운전입니다."
                onChange={setOperationIntent}
                rows={4}
              />
              <Textarea
                label="사고 정비 이력"
                value={incidentHistory}
                placeholder="예: 최근 1년간 Gas Cabinet 누출감지 경보 2회, MFC High Flow Alarm 2회, Purge 시작 실패 Near Miss 3회가 있었습니다."
                onChange={setIncidentHistory}
                rows={4}
              />
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
                        placeholder={`예: ${recommendedNodeMaterial(node.node_name)}`}
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
                <ResultTable
                  title="초안 검토 및 보완 내역"
                  rows={result.review_findings}
                  emptyText="초안 검토 과정에서 별도 보완 내역이 없습니다."
                />
              </div>
            )}
          </section>

          <section className={`panel log-panel-wrap${isLogExpanded ? " is-expanded" : ""}`}>
            <div className="panel-title">
              <span>03</span>
              <h2>Agent 로그</h2>
              <button
                className="log-expand-button"
                type="button"
                onClick={() => setIsLogExpanded((value) => !value)}
              >
                {isLogExpanded ? "확대 닫기" : "로그 확대"}
              </button>
            </div>
            <div className="status-row">
              <span className={isRunning ? "status-pill is-running" : "status-pill"}>
                {isRunning ? <i aria-hidden="true" /> : null}
                {status}
              </span>
            </div>
            <div className="log-filters" aria-label="Agent 로그 필터">
              {([
                ["all", "전체"],
                ["planning", "Planning"],
                ["tool", "Tool"],
                ["self-correction", "Self-Correction"],
              ] as Array<[LogFilter, string]>).map(([value, label]) => (
                <button
                  className={logFilter === value ? "is-active" : ""}
                  type="button"
                  onClick={() => setLogFilter(value)}
                  key={value}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="log-box" ref={logScrollRef} onScroll={handleLogScroll}>
              {visibleLogs.length === 0 ? (
                <div className="empty-log">AI 초안생성을 누르면 Agent 로그가 여기에 쌓입니다.</div>
              ) : (
                visibleLogs.map((item, index) => <LogCard item={item} index={index} key={item.id} />)
              )}
            </div>
          </section>
        </section>
      </section>
    </main>
  );
}

function Field({
  label,
  value,
  placeholder,
  onChange,
}: {
  label: string;
  value: string;
  placeholder?: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function Textarea({
  label,
  value,
  placeholder,
  onChange,
  rows,
}: {
  label: string;
  value: string;
  placeholder?: string;
  onChange: (value: string) => void;
  rows: number;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <textarea value={value} placeholder={placeholder} rows={rows} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function LogCard({ item, index }: { item: LogGroup; index: number }) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const planningStatus = item.children.find((child) => child.kind === "planning");
  return (
    <article className={`log-card kind-${item.kind}${item.emphasis ? " is-emphasis" : ""}`}>
      <div className={item.children.length ? "log-card-header is-sticky" : "log-card-header"}>
        <div className="log-card-top">
          <span className="log-kind">{logKindLabel(item.kind)}</span>
          <span className="log-step">STEP {String(index + 1).padStart(2, "0")}</span>
          {item.children.length ? (
            <button className="log-toggle" type="button" onClick={() => setIsCollapsed((value) => !value)}>
              {isCollapsed ? `펼치기 (${item.children.length})` : "접기"}
            </button>
          ) : null}
        </div>
        <div className="log-title-line">
          {item.loading ? <i aria-hidden="true" /> : null}
          <strong>{item.title}</strong>
        </div>
        {planningStatus ? (
          <div className="log-card-planning-status">
            <span aria-hidden="true">{planningStatus.loading ? "↻" : "✓"}</span>
            <strong>{planningStatus.title}</strong>
          </div>
        ) : null}
      </div>
      {item.detail ? <p>{item.detail}</p> : null}
      {item.children.length && !isCollapsed ? (
        <div className="child-logs">
          {item.children.map((child) => <ChildLogCard child={child} key={child.id} />)}
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
                    {formatCell(row[header], header)}
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

function makeLogGroup(title: string, detail: string, kind: LogKind, loading = false, emphasis = false): LogGroup {
  return { id: crypto.randomUUID(), title, detail, kind, loading, emphasis, children: [] };
}

function ChildLogCard({ child, nested = false }: { child: ChildLog; nested?: boolean }) {
  const stickyCurrentWork = !nested && child.loading && child.children.length > 0;
  return (
    <div className={`child-log kind-${child.kind}${child.emphasis ? " is-emphasis" : ""}${nested ? " is-nested" : ""}`}>
      <div className={`child-log-summary${stickyCurrentWork ? " is-current-sticky" : ""}`}>
        <span>{child.loading ? <i aria-hidden="true" /> : logKindLabel(child.kind)}</span>
        <div>
          <strong>{child.title}</strong>
          {child.detail ? <p>{child.detail}</p> : null}
        </div>
      </div>
      {child.children.length ? (
        <div className="nested-child-logs">
          {child.children.map((nestedChild) => <ChildLogCard child={nestedChild} nested key={nestedChild.id} />)}
        </div>
      ) : null}
    </div>
  );
}

function makeChildLog(
  title: string,
  detail: string,
  kind: LogKind,
  loading = false,
  emphasis = false,
  eventKey?: string,
): ChildLog {
  return { id: crypto.randomUUID(), title, detail, kind, loading, emphasis, eventKey, children: [] };
}

function stopChildSpinner(child: ChildLog): ChildLog {
  return { ...child, loading: false, children: child.children.map(stopChildSpinner) };
}

function filterLogs(logs: LogGroup[], filter: LogFilter): LogGroup[] {
  if (filter === "all") return logs;
  const matches = (kind: LogKind) => {
    if (filter === "planning") return kind === "planning";
    return kind === filter;
  };
  const filterChildren = (children: ChildLog[]): ChildLog[] => children.flatMap((child) => {
    const nested = filterChildren(child.children);
    return matches(child.kind) ? [{ ...child, children: child.children }] : nested.length ? [{ ...child, children: nested }] : [];
  });
  return logs.flatMap((group) => {
    if (matches(group.kind)) return [group];
    const children = filterChildren(group.children);
    return children.length ? [{ ...group, children }] : [];
  });
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

const NODE_MATERIAL_EXAMPLES: Record<string, string> = {
  "DI Water 공급 탱크": "DI Water",
  "DI Water 이송 펌프": "DI Water",
  "Wet 장비 공급 배관": "DI Water",
  "Gas Cabinet": "Silane, Hydrogen",
  "VMB 및 공급 배관": "입력하지 않음",
  "MFC 유량 제어 구간": "Silane",
  "Purge 및 Scrubber 구간": "Nitrogen, Silane, Hydrogen",
  "Etch Chamber": "HF, Nitrogen",
  "Vacuum Pump Line": "HF, Nitrogen",
  "Exhaust Scrubber": "HF",
  "HF Chemical Supply": "HF",
  "NH3 Receiver": "Ammonia",
  "NH3 Compressor": "Ammonia",
  "Oil Separator": "Ammonia",
  Condenser: "Ammonia",
  "Expansion Valve": "Ammonia",
  "Evaporator 및 Machine Room": "Ammonia",
  "IPA Drum Unloading": "Isopropyl alcohol",
  "IPA Day Tank": "Isopropyl alcohol",
  "Transfer Pump": "Isopropyl alcohol",
  "Tool Supply Header": "Isopropyl alcohol",
  "Waste Solvent Return": "Isopropyl alcohol",
  "Chlorine Ton Container": "Chlorine",
  Evaporator: "Chlorine",
  "Vacuum Regulator": "Chlorine",
  Chlorinator: "Chlorine",
  "Injector 및 Contact Basin": "Chlorine",
  "Emergency Scrubber": "Chlorine",
  "Solvent Storage": "Ethylene carbonate, Dimethyl carbonate",
  "LiPF6 Charging Booth": "Lithium hexafluorophosphate",
  "Mixing Reactor": "Lithium hexafluorophosphate, Ethylene carbonate, Dimethyl carbonate",
  "Heating/Cooling Jacket": "Lithium hexafluorophosphate, Ethylene carbonate, Dimethyl carbonate",
  "Nitrogen Blanketing": "Nitrogen",
  Filtration: "Lithium hexafluorophosphate, Ethylene carbonate, Dimethyl carbonate",
  "Filling Line": "Lithium hexafluorophosphate, Ethylene carbonate, Dimethyl carbonate",
  "Hydrogen Gas Cabinet": "Hydrogen, Nitrogen",
  "Hydrogen VMB": "Hydrogen, Nitrogen",
  "Ammonia Storage": "Ammonia",
  "Ammonia Vaporizer": "Ammonia",
  "Solvent Distribution": "Isopropyl alcohol",
  "Nitrogen Purge Header": "Nitrogen",
  "DI Water Cooling Loop": "DI Water",
  "Process Reactor": "Hydrogen, Ammonia, Isopropyl alcohol, Nitrogen",
  "Abatement 및 Exhaust": "Hydrogen, Ammonia, Isopropyl alcohol, Nitrogen",
};

function recommendedNodeMaterial(nodeName: string) {
  return NODE_MATERIAL_EXAMPLES[nodeName] || "물질명 또는 CAS 번호";
}

function waitAtLeast(startedAt: number, ms: number) {
  const remaining = ms - (Date.now() - startedAt);
  return new Promise((resolve) => window.setTimeout(resolve, Math.max(0, remaining)));
}

function logKindLabel(kind: LogKind) {
  return {
    system: "시스템",
    workflow: "Workflow",
    planning: "Planning",
    agent: "Agent",
    skill: "Skill",
    tool: "Tool",
    validation: "검증",
    "self-correction": "Self-Correction",
    replanning: "Replanning",
    result: "Result",
    warning: "주의",
    error: "Error",
  }[kind];
}

function describeAgentRoles(value: string) {
  const roles: Array<[string, string]> = [
    ["risk-draft-agent", "risk-draft-agent (위험성평가 초안 작성)"],
    ["risk-review-agent", "risk-review-agent (초안 검토 및 보완)"],
    ["action-plan-agent", "action-plan-agent (고위험 항목 조치계획 작성)"],
  ];

  return roles.reduce((text, [agentName, label]) => {
    if (text.includes(label)) return text;
    return text.replaceAll(agentName, label);
  }, value);
}

function formatCell(value: unknown, header?: string): React.ReactNode {
  if (header === "requires_confirmation" && value === true) {
    return <strong className="confirmation-required">True</strong>;
  }
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
    no: "번호",
    node_order: "노드 순번",
    node_name: "노드명",
    parameter: "변수",
    guideword: "가이드워드",
    deviation: "이탈",
    cause: "원인",
    possible_causes: "가능 원인",
    causes: "원인",
    consequences: "예상 결과",
    consequence: "결과",
    safeguards: "현재 안전조치",
    existing_safeguard: "현재 안전조치",
    existing_safeguards: "기존 안전조치",
    frequency: "빈도",
    severity: "강도",
    risk_score: "위험도",
    risk_level: "위험 등급",
    action_required: "조치 필요 여부",
    decision_evidence: "판단 근거",
    severity_evidence: "강도 판단 근거",
    frequency_evidence: "빈도 판단 근거",
    note: "비고",
    recommendations: "권고 조치",
    recommendation: "권고 조치",
    action_item: "조치 내용",
    action_owner: "담당 부서",
    owner: "담당",
    due_date: "완료 기한",
    completion_criteria: "완료 기준",
    after_frequency: "조치 후 빈도",
    after_severity: "조치 후 강도",
    after_risk_score: "조치 후 위험도",
    evidence: "조치 판단 근거",
    basis: "근거",
    rationale: "판단 근거",
    msds_basis: "MSDS 근거",
    material: "물질",
    priority: "우선순위",
    status: "상태",
    risk_assessment_no: "위험성평가 번호",
    category: "검토 구분",
    message: "발견 내용",
    resolution: "반영 내용",
    requires_confirmation: "담당자 확인 필요",
  };
  return labels[header] || header.replaceAll("_", " ");
}

function columnClassName(header: string) {
  const compactColumns = new Set(["no", "node_order", "frequency", "severity", "risk_score"]);
  const evidenceColumns = new Set([
    "decision_evidence",
    "severity_evidence",
    "frequency_evidence",
    "evidence",
    "basis",
    "rationale",
    "msds_basis",
  ]);
  if (evidenceColumns.has(header)) return "evidence-column";
  return compactColumns.has(header) ? "numeric-column" : undefined;
}

function getGenerationStage(logs: LogGroup[], status: string) {
  if (status === "업로드 중") {
    return {
      title: "Excel 입력값을 확인하는 중입니다.",
      detail: "#1 노드리스트와 #2 가이드워드가 초안 생성 기준에 맞는지 점검하고 있습니다.",
    };
  }

  // 완료된 과거 Agent가 아니라 현재 스피너가 돌고 있는 Agent만 표시합니다.
  const activeAgent = [...logs].reverse().find((group) => group.loading);
  const activeText = activeAgent ? `${activeAgent.title} ${activeAgent.detail}` : "";

  if (activeText.includes("action-plan-agent")) {
    return {
      title: "#4 고위험 항목의 조치계획을 작성하고 있습니다.",
      detail: "위험도 9 이상 항목을 골라 원인을 줄일 수 있는 권고 조치와 완료 기준을 정리하고 있습니다.",
    };
  }

  if (activeText.includes("risk-review-agent")) {
    return {
      title: "#3 위험도 계산과 검토를 진행 중입니다.",
      detail: "AI가 쓴 빈도와 강도를 시스템 규칙으로 다시 계산하고, 빠진 근거가 없는지 확인하고 있습니다.",
    };
  }

  if (activeText.includes("risk-draft-agent")) {
    return {
      title: "#3 위험성평가 초안을 작성하고 있습니다.",
      detail: "Node와 Guideword를 기준으로 가능한 원인, 예상 결과, 현재 안전조치와 빈도·강도 근거를 정리하고 있습니다.",
    };
  }

  const latest = logs.at(-1);
  if (latest?.kind === "validation") {
    return {
      title: "시스템이 최종 결과를 확인하고 있습니다.",
      detail: "위험도 계산값과 결과 Excel 저장 내용을 점검하고 있습니다.",
    };
  }

  return {
    title: "다음 처리 단계를 준비하고 있습니다.",
    detail: "현재 단계가 끝나면 자동으로 다음 Workflow 단계로 이동합니다.",
  };
}

createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
