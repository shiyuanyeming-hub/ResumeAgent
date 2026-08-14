export function answerPayload(stepId, { value = "", values = [], extra = {} } = {}) {
  return { step_id: stepId, value, values, extra };
}

export function periodExtra(start, end) {
  return { start: String(start || ""), end: String(end || "") };
}

export function sectionFromStep(stepId) {
  const [section] = String(stepId || "").split(":");
  return section || "";
}

export function normalizeChips(values) {
  const seen = new Set();
  const result = [];
  for (const item of values || []) {
    const normalized = String(item).trim();
    if (normalized && !seen.has(normalized)) {
      seen.add(normalized);
      result.push(normalized);
    }
  }
  return result;
}
