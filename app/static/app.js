const form = document.querySelector("#hazop-form");
const logs = document.querySelector("#logs");
const statusBadge = document.querySelector("#status");
const riskTable = document.querySelector("#risk-table");
const actionTable = document.querySelector("#action-table");
const fileInput = document.querySelector('input[name="file"]');
const materialsInput = document.querySelector('input[name="materials"]');
const nodeMaterialFields = document.querySelector("#node-material-fields");
const nodeMaterialsText = document.querySelector("#node-materials");
const nodePreviewStatus = document.querySelector("#node-preview-status");

fileInput.addEventListener("change", async () => {
  const file = fileInput.files?.[0];
  if (!file) {
    nodePreviewStatus.textContent = "Excel을 선택하면 Node별 입력칸이 표시됩니다.";
    return;
  }

  nodePreviewStatus.textContent = "#1 노드리스트를 읽는 중입니다.";
  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch("/api/excel/nodes", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Node 목록을 읽지 못했습니다.");
    }
    renderNodeMaterialFields(data.nodes || []);
  } catch (error) {
    nodeMaterialFields.innerHTML = "";
    nodeMaterialsText.value = "";
    nodePreviewStatus.textContent = error.message;
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  updateNodeMaterialsValue();
  logs.innerHTML = "";
  riskTable.innerHTML = "";
  actionTable.innerHTML = "";
  statusBadge.textContent = "업로드 중";

  const formData = new FormData(form);
  const response = await fetch("/api/jobs", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json();
    addLog("오류", error.detail || "작업 생성 실패");
    statusBadge.textContent = "실패";
    return;
  }

  const { job_id } = await response.json();
  statusBadge.textContent = "Agent 실행 중";
  addLog("작업 생성 완료", `job_id=${job_id}`);

  const source = new EventSource(`/api/jobs/${job_id}/events`);
  source.addEventListener("log", (event) => {
    const data = JSON.parse(event.data);
    addLog(data.title, data.detail);
  });
  source.addEventListener("error", (event) => {
    if (event.data) {
      const data = JSON.parse(event.data);
      addLog("오류", data.message);
    }
    statusBadge.textContent = "실패";
    source.close();
  });
  source.addEventListener("done", (event) => {
    const data = JSON.parse(event.data);
    statusBadge.textContent = "완료";
    renderRiskRows(data.risk_rows || []);
    renderActionRows(data.action_rows || []);
    if (data.output_excel) {
      const link = document.createElement("a");
      link.href = `/api/download?path=${encodeURIComponent(data.output_excel)}`;
      link.textContent = "결과 Excel 다운로드";
      link.className = "download";
      actionTable.appendChild(link);
    }
    source.close();
  });
});

nodeMaterialFields.addEventListener("input", () => {
  updateNodeMaterialsValue();
});

function renderNodeMaterialFields(nodes) {
  const previousValues = nodeMaterialValuesByName();
  const defaultMaterial = materialsInput.value.trim();
  nodeMaterialFields.innerHTML = "";

  nodes.forEach((node) => {
    const label = document.createElement("label");
    const input = document.createElement("input");
    const nodeName = String(node.node_name || "").trim();

    label.textContent = `${node.node_order}. ${nodeName}`;
    input.type = "text";
    input.dataset.nodeName = nodeName;
    input.value = previousValues[nodeName] || defaultMaterial;
    label.appendChild(input);
    nodeMaterialFields.appendChild(label);
  });

  updateNodeMaterialsValue();
  nodePreviewStatus.textContent = `Excel에서 Node ${nodes.length}개를 읽었습니다.`;
}

function nodeMaterialValuesByName() {
  const values = {};
  nodeMaterialFields.querySelectorAll("input[data-node-name]").forEach((input) => {
    const nodeName = input.dataset.nodeName;
    if (nodeName) {
      values[nodeName] = input.value.trim();
    }
  });
  return values;
}

function updateNodeMaterialsValue() {
  const lines = [];
  nodeMaterialFields.querySelectorAll("input[data-node-name]").forEach((input) => {
    const nodeName = input.dataset.nodeName;
    const material = input.value.trim();
    if (nodeName && material) {
      lines.push(`${nodeName}: ${material}`);
    }
  });
  nodeMaterialsText.value = lines.join("\n");
}

function addLog(title, detail) {
  const item = document.createElement("div");
  item.className = "log-item";
  item.innerHTML = `<strong>${escapeHtml(title)}</strong><span>${escapeHtml(detail)}</span>`;
  logs.appendChild(item);
  logs.scrollTop = logs.scrollHeight;
}

function renderRiskRows(rows) {
  const headers = ["No", "Node", "변수", "가이드워드", "일탈", "원인", "결과", "안전조치", "빈도", "강도", "위험도", "판단", "조치"];
  const values = rows.map((row) => [
    row.no,
    row.node_name,
    row.parameter,
    row.guideword,
    row.deviation,
    row.cause,
    row.consequence,
    row.existing_safeguard,
    row.frequency,
    row.severity,
    row.risk_score,
    row.risk_level,
    row.action_required,
  ]);
  riskTable.innerHTML = tableHtml(headers, values);
}

function renderActionRows(rows) {
  if (!rows.length) {
    actionTable.innerHTML = "<p>위험도 9 이상 항목이 없어 별도 조치계획서가 생성되지 않았습니다.</p>";
    return;
  }
  const headers = ["No", "위험성평가No", "Node", "개선권고사항", "조치후빈도", "조치후강도", "조치후위험도", "비고"];
  const values = rows.map((row) => [
    row.no,
    row.risk_assessment_no,
    row.node_name,
    row.recommendation,
    row.after_frequency,
    row.after_severity,
    row.after_risk_score,
    row.note,
  ]);
  actionTable.innerHTML = tableHtml(headers, values);
}

function tableHtml(headers, rows) {
  return `
    <table>
      <thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead>
      <tbody>
        ${rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(String(cell ?? ""))}</td>`).join("")}</tr>`).join("")}
      </tbody>
    </table>
  `;
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
