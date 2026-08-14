import {
  ApiError,
  createApi,
  fromWareki,
  sanitizeUiState,
  toWareki,
} from "/assets/api.js";
import {
  baseSelection,
  createGenerationGate,
  createSerialExecutor,
  createTransitionGate,
  storeBaseSelection,
} from "/assets/workbench-state.js";
import {
  answerPayload,
  defaultZhVersionName,
  normalizeChips,
  periodExtra,
} from "/assets/questionnaire.js";

const STORAGE_KEY = "resume-agent-ui-v1";
const LANGUAGE_LABELS = {
  zh: "中文简历",
  ja: "日文简历",
  en: "English Resume",
};
const LANGUAGE_ORDER = ["zh", "ja", "en"];
const DIMENSIONS = [
  ["context", "背景"],
  ["responsibility", "我的职责"],
  ["action", "具体行动"],
  ["method", "方法与工具"],
  ["result", "结果"],
  ["evidence", "证明与数据"],
];
const STYLE_CATALOG = {
  zh: ["藏青现代", "经典墨色", "清新青碧"],
  ja: ["藏青JIS", "墨黑JIS", "蓝灰JIS"],
  en: ["青灰Teal", "经典黑白", "现代蓝"],
};
const api = createApi();

function readState() {
  try {
    return {
      locale: "zh",
      tab: "chat",
      ...sanitizeUiState(JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}")),
    };
  } catch {
    return { locale: "zh", tab: "chat" };
  }
}

const state = readState();
let bases = [];
let currentBase = null;
let currentSession = null;
let currentExperienceQuality = null;
let versions = [];
let currentVersion = null;
let capabilitiesState = null;
let currentRendered = null;
let questionnaireState = null;
let editMode = false;
let editorView = "visual";
let editorTarget = null;
let currentRenderedVersionId = null;
let documentCommitGeneration = 0;
let versionTransitioning = false;
let languageTransitioning = false;
let languageIntentLocale = state.locale;
const baseActivationGate = createGenerationGate();
const experienceGate = createGenerationGate();
const versionGate = createGenerationGate();
const previewGate = createGenerationGate();
const languageGate = createGenerationGate();
const sessionTransitionGate = createTransitionGate();
const activateVersionSerially = createSerialExecutor();

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sanitizeUiState(state)));
}

function byId(id) {
  return document.getElementById(id);
}

function element(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function showToast(message) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toast.hideTimer);
  toast.hideTimer = setTimeout(() => toast.classList.remove("show"), 2400);
}

function setServiceStatus(capabilities) {
  const status = byId("service-status");
  const available = capabilities?.status === "ready";
  status.className = `service-status ${available ? "ready" : "offline"}`;
  status.lastElementChild.textContent = available ? "导师可用" : "仅离线功能";
}

function selectTab(name) {
  const selected = ["chat", "facts", "jd", "tools"].includes(name) ? name : "chat";
  for (const button of byId("primary-tabs").querySelectorAll("button")) {
    const isSelected = button.dataset.tab === selected;
    button.setAttribute("aria-selected", String(isSelected));
    button.tabIndex = isSelected ? 0 : -1;
  }
  for (const panel of document.querySelectorAll("[data-panel]")) {
    panel.hidden = panel.dataset.panel !== selected;
  }
  byId("chat-composer").hidden = selected !== "chat" || !currentBase;
  state.tab = selected;
  saveState();
}

function field(label, name, placeholder = "", value = "", type = "input") {
  const wrapper = element("label", "form-field");
  wrapper.append(element("span", "", label));
  const input = document.createElement(type);
  input.name = name;
  input.placeholder = placeholder;
  input.value = value;
  wrapper.append(input);
  return wrapper;
}

function replaceBase(updated) {
  const index = bases.findIndex((base) => base.id === updated.id);
  if (index >= 0) bases[index] = updated;
  else bases.push(updated);
  currentBase = updated;
}

function cacheBase(updated) {
  const index = bases.findIndex((base) => base.id === updated.id);
  if (index >= 0) bases[index] = updated;
  else bases.push(updated);
}

function commitSelection(baseId, selection) {
  const saved = storeBaseSelection(state, baseId, selection);
  state.factBaseId = baseId;
  for (const key of ["experienceId", "sessionId", "versionId"]) {
    if (saved[key]) state[key] = saved[key];
    else delete state[key];
  }
  saveState();
}

function resetEditorState() {
  editMode = false;
  editorView = "visual";
  editorTarget = null;
  currentRendered = null;
  currentRenderedVersionId = null;
  const markdown = byId("markdown-editor");
  if (markdown) markdown.value = "";
  const frame = byId("preview-frame");
  if (frame?.contentDocument) frame.contentDocument.designMode = "off";
}

function resetComposerAction() {
  const submit = byId("chat-composer")?.querySelector('button[type="submit"]');
  if (submit) {
    submit.disabled = false;
    submit.textContent = "发送回答";
  }
}

function setSessionTransitionUi() {
  const transitioning = sessionTransitionGate.isTransitioning();
  const panel = byId("chat-panel");
  const composer = byId("chat-composer");
  panel.toggleAttribute("aria-busy", transitioning);
  composer.toggleAttribute("aria-busy", transitioning);
  for (const control of panel.querySelectorAll("button, select")) {
    control.disabled = transitioning || control.disabled;
  }
  for (const control of composer.querySelectorAll("button, textarea")) {
    control.disabled = transitioning;
  }
  byId("base-select").disabled = transitioning || bases.length === 0;
  byId("new-base-button").disabled = transitioning || (bases.length > 0 && !currentBase);
}

function beginSessionTransition() {
  const token = sessionTransitionGate.begin();
  setSessionTransitionUi();
  renderDocumentToolbar();
  byId("reset-draft-button").disabled = true;
  return token;
}

function finishSessionTransition(token) {
  if (!sessionTransitionGate.finish(token)) return false;
  renderBaseSwitcher();
  renderConversation();
  renderDocumentToolbar();
  byId("reset-draft-button").disabled = false;
  return true;
}

function cancelSessionTransitions() {
  sessionTransitionGate.cancel();
  setSessionTransitionUi();
}

function documentIsTransitioning() {
  return sessionTransitionGate.isTransitioning() || versionTransitioning || languageTransitioning;
}

function renderBaseSwitcher() {
  const select = byId("base-select");
  const sampleButton = byId("sample-button");
  const newButton = byId("new-base-button");
  const hasBases = bases.length > 0;
  select.replaceChildren();

  if (!hasBases) {
    select.append(new Option("暂无档案", ""));
    select.disabled = true;
  } else {
    if (!currentBase) select.append(new Option("新档案（尚未保存）", "", true, true));
    for (const base of bases) {
      const role = base.target?.role?.trim() || "未命名岗位";
      select.append(new Option(role, base.id, false, base.id === currentBase?.id));
    }
    select.disabled = sessionTransitionGate.isTransitioning();
  }

  sampleButton.hidden = hasBases;
  newButton.hidden = !hasBases;
  newButton.disabled = sessionTransitionGate.isTransitioning() || (hasBases && !currentBase);
  newButton.textContent = currentBase ? "新建档案" : "正在新建档案";
}

async function recoverSession(baseId, experienceId, preferredSessionId = "") {
  if (!experienceId) return null;
  const sessions = await api.listSessions(baseId, experienceId);
  return sessions.find((session) => session.id === preferredSessionId)
    || sessions.at(-1)
    || null;
}

async function loadVersions(baseId, preferredVersionId = "", locale = state.locale) {
  const loaded = await api.listVersions(baseId);
  const selected = loaded.find((item) => item.id === preferredVersionId)
    || loaded.find((item) => item.is_active && item.locale === locale)
    || loaded.find((item) => item.locale === locale)
    || loaded.find((item) => item.is_active)
    || loaded.at(-1)
    || null;
  return { versions: loaded, currentVersion: selected };
}

async function loadCurrentExperienceQuality(baseId, experienceId) {
  return experienceId ? api.experienceQuality(baseId, experienceId) : null;
}

async function activateBase(base) {
  const generation = baseActivationGate.next();
  experienceGate.next();
  versionGate.next();
  languageGate.next();
  versionTransitioning = false;
  languageTransitioning = false;
  languageIntentLocale = state.locale;
  byId("language-button").textContent = LANGUAGE_LABELS[state.locale];
  const transition = beginSessionTransition();
  const saved = baseSelection(state, base.id);
  const selectedExperience = base.experiences.find((item) => item.id === saved.experienceId)
    || base.experiences.at(-1)
    || null;
  const experienceId = selectedExperience?.id || "";

  try {
    const [session, versionState, quality] = await Promise.all([
      recoverSession(base.id, experienceId, saved.sessionId),
      loadVersions(base.id, saved.versionId),
      loadCurrentExperienceQuality(base.id, experienceId),
    ]);
    if (!baseActivationGate.isCurrent(generation)
      || !sessionTransitionGate.isCurrent(transition)) return false;

    cacheBase(base);
    currentBase = base;
    currentSession = session;
    currentExperienceQuality = quality;
    versions = versionState.versions;
    currentVersion = versionState.currentVersion;
    if (currentVersion) state.locale = currentVersion.locale;
    languageIntentLocale = state.locale;
    documentCommitGeneration += 1;
    resetEditorState();
    commitSelection(base.id, {
      experienceId,
      sessionId: session?.id || "",
      versionId: currentVersion?.id || "",
    });
    await refreshQuestionnaire();
    resetComposerAction();
    presentQuestionCard(questionnaireState?.next || null);
    byId("language-button").textContent = LANGUAGE_LABELS[state.locale];
    finishSessionTransition(transition);
    renderJdTab();
    renderToolsTab();
    await Promise.all([
      renderFactBase(generation),
      renderDocument(),
    ]);
    return true;
  } catch (error) {
    if (!baseActivationGate.isCurrent(generation)
      || !sessionTransitionGate.isCurrent(transition)) return false;
    finishSessionTransition(transition);
    renderJdTab();
    renderToolsTab();
    await renderFactBase(baseActivationGate.current());
    throw error;
  }
}

function startNewBase() {
  baseActivationGate.next();
  experienceGate.next();
  versionGate.next();
  previewGate.next();
  languageGate.next();
  cancelSessionTransitions();
  versionTransitioning = false;
  languageTransitioning = false;
  documentCommitGeneration += 1;
  resetEditorState();
  resetComposerAction();
  currentBase = null;
  currentSession = null;
  currentExperienceQuality = null;
  versions = [];
  currentVersion = null;
  for (const key of ["factBaseId", "experienceId", "sessionId", "versionId"]) {
    delete state[key];
  }
  saveState();
  languageIntentLocale = state.locale;
  byId("language-button").textContent = LANGUAGE_LABELS[state.locale];
  renderBaseSwitcher();
  selectTab("chat");
  renderOnboarding();
  renderFactBase();
  renderJdTab();
  renderToolsTab();
  renderDocument();
}

function captureExperienceContext() {
  return {
    baseGeneration: baseActivationGate.current(),
    experienceGeneration: experienceGate.current(),
    baseId: currentBase?.id || "",
    experienceId: state.experienceId || "",
  };
}

function isCurrentExperienceContext(context) {
  return baseActivationGate.isCurrent(context.baseGeneration)
    && experienceGate.isCurrent(context.experienceGeneration)
    && !sessionTransitionGate.isTransitioning()
    && currentBase?.id === context.baseId
    && state.experienceId === context.experienceId;
}

async function activateExperience(experienceId) {
  if (!currentBase || !currentBase.experiences.some((item) => item.id === experienceId)) {
    return false;
  }
  const baseId = currentBase.id;
  const baseGeneration = baseActivationGate.current();
  const generation = experienceGate.next();
  const transition = beginSessionTransition();
  const saved = baseSelection(state, baseId);
  const preferredSessionId = saved.experienceId === experienceId ? saved.sessionId : "";
  try {
    const [session, quality] = await Promise.all([
      recoverSession(baseId, experienceId, preferredSessionId),
      loadCurrentExperienceQuality(baseId, experienceId),
    ]);
    if (!baseActivationGate.isCurrent(baseGeneration)
      || !experienceGate.isCurrent(generation)
      || !sessionTransitionGate.isCurrent(transition)
      || currentBase?.id !== baseId) return false;
    currentSession = session;
    currentExperienceQuality = quality;
    commitSelection(baseId, {
      ...saved,
      experienceId,
      sessionId: session?.id || "",
    });
    resetComposerAction();
    finishSessionTransition(transition);
    return true;
  } catch (error) {
    if (!baseActivationGate.isCurrent(baseGeneration)
      || !experienceGate.isCurrent(generation)
      || !sessionTransitionGate.isCurrent(transition)
      || currentBase?.id !== baseId) return false;
    finishSessionTransition(transition);
    showToast(error instanceof ApiError ? error.message : "经历读取失败");
    return false;
  }
}

function renderOnboarding() {
  currentSession = null;
  const panel = byId("chat-panel");
  panel.replaceChildren();
  const heading = element("div", "section-heading");
  heading.append(
    element("h2", "", "你要做一份什么样的简历？"),
    element("p", "", "先选择简历语言。中文向导已就绪，日文与英文即将支持。"),
  );

  const choices = element("div", "language-choices");
  for (const [locale, label] of [
    ["zh", "中文简历"],
    ["ja", "日文简历"],
    ["en", "英文简历"],
  ]) {
    const button = element("button", "primary language-choice", label);
    button.type = "button";
    button.addEventListener("click", () => chooseLanguage(locale));
    choices.append(button);
  }
  panel.append(heading, choices);
  byId("chat-composer").hidden = true;
}

async function chooseLanguage(locale) {
  if (locale !== "zh") {
    showToast("日文与英文向导即将支持，敬请期待");
    return;
  }
  state.locale = "zh";
  saveState();
  const panel = byId("chat-panel");
  panel.replaceChildren();
  const heading = element("div", "section-heading");
  heading.append(
    element("h2", "", "你想应聘什么岗位？"),
    element("p", "", "导师会根据这个岗位，一步步问你、帮你把简历问出来。"),
  );
  const form = element("form", "onboarding-form");
  form.id = "onboarding-form";
  form.append(field("目标岗位", "role", "例如：产品经理"));
  const submit = element("button", "primary", "开始，让导师来问我");
  submit.type = "submit";
  form.append(submit);
  form.addEventListener("submit", startMentorSession);
  panel.append(heading, form);
  byId("chat-composer").hidden = true;
}

async function startMentorSession(event) {
  event.preventDefault();
  const role = String(new FormData(event.currentTarget).get("role") || "").trim();
  if (!role) {
    showToast("请填写目标岗位");
    return;
  }
  const submit = event.currentTarget.querySelector("button[type=submit]");
  submit.disabled = true;
  try {
    const base = await api.createFactBase({
      role,
      country: "",
      languages: ["zh", "ja", "en"],
    });
    await activateBase(base);
    if (currentBase?.id === base.id && versions.length === 0) {
      const version = await api.createVersion(base.id, {
        name: defaultZhVersionName(role),
        target_role: role,
        company: "",
        raw_jd: "",
        locale: "zh",
        selected_experience_ids: [],
      });
      versions = [...versions.filter((item) => item.id !== version.id), version];
      await chooseVersion(version.id);
    }
    await refreshQuestionnaire();
    appendJobAnalysis();
    renderConversation();
    presentQuestionCard(questionnaireState?.next || null);
  } catch (error) {
    showToast(error instanceof ApiError ? error.message : "档案创建失败");
    submit.disabled = false;
  }
}

function appendJobAnalysis() {
  const analysis = questionnaireState?.jobAnalysis;
  if (!analysis || !analysis.length) return;
  const messagesBox = byId("chat-messages");
  if (!messagesBox) return;
  const intro = element("div", "message assistant-message mentor-analysis");
  const heading = element("strong", "", "关于「" + (currentBase?.target?.role || "这个岗位") + "」，导师想说：");
  const list = document.createElement("ul");
  for (const item of analysis) list.append(element("li", "", item));
  intro.append(heading, list);
  messagesBox.append(intro);
  messagesBox.scrollTop = messagesBox.scrollHeight;
}

function experienceSelector() {
  const wrapper = element("label", "compact-field");
  wrapper.append(element("span", "", "当前经历"));
  const select = document.createElement("select");
  select.id = "experience-select";
  for (const experience of currentBase.experiences) {
    const option = document.createElement("option");
    option.value = experience.id;
    option.textContent = `${experience.organization} · ${experience.role}`;
    option.selected = experience.id === state.experienceId;
    select.append(option);
  }
  select.addEventListener("change", async () => {
    await activateExperience(select.value);
  });
  wrapper.append(select);
  return wrapper;
}

function renderInterviewProgress() {
  const progress = element("div", "interview-progress");
  progress.id = "interview-progress";
  progress.setAttribute("role", "status");
  progress.setAttribute("aria-label", "访谈证据进度");

  const completed = currentExperienceQuality?.present_dimensions;
  const pending = currentSession
    ? Object.values(currentSession.pending_proposals || {}).at(-1)
    : null;
  const focusKey = pending?.dimension
    || currentSession?.current_question?.dimension
    || DIMENSIONS.find(([key]) => currentExperienceQuality?.scores?.[key] === 0)?.[0];
  const focus = DIMENSIONS.find(([key]) => key === focusKey)?.[1]
    || (currentExperienceQuality?.passes_gate ? "证据已达到可写门槛" : "开始访谈");

  const summary = element("div", "progress-summary");
  summary.append(
    element("strong", "", "证据进度"),
    element("span", "", Number.isInteger(completed) ? `${completed}/6 个维度` : "正在读取"),
  );
  const track = element("div", "progress-track");
  track.setAttribute("aria-hidden", "true");
  for (let index = 0; index < 6; index += 1) {
    track.append(element("span", index < (completed || 0) ? "complete" : ""));
  }
  progress.append(summary, track, element("span", "progress-focus", `当前重点：${focus}`));
  return progress;
}

function renderConversation() {
  if (!currentBase) {
    renderOnboarding();
    return;
  }
  const panel = byId("chat-panel");
  panel.replaceChildren();
  panel.append(sectionNavElement(), questionAreaElement(), experienceSelector(), renderInterviewProgress());

  const hasPendingOrQuestion = Boolean(currentSession)
    && (Object.values(currentSession.pending_proposals || {}).length > 0
      || currentSession.current_question);
  if (hasPendingOrQuestion) {
    const actions = element("div", "panel-actions");
    const resume = element("button", "primary", "继续导师追问");
    resume.type = "button";
    resume.addEventListener("click", () => presentInterviewFlow({
      step_id: `experience:${currentSession.active_experience_id}:interview`,
    }));
    actions.append(resume);
    panel.append(actions);
  }

  const messages = element("div", "chat-messages");
  messages.id = "chat-messages";
  if (!currentSession) {
    const experience = currentBase.experiences.find((item) => item.id === state.experienceId);
    messages.append(element(
      "div",
      "message system-message",
      experience
        ? `当前经历：${experience.organization} · ${experience.role}。导师会一次问一个问题，你只需要点选或按真实情况回答。`
        : "先添加一段经历，再开始访谈。",
    ));
  } else {
    for (const message of currentSession.messages) {
      messages.append(element(
        "div",
        `message ${message.role === "user" ? "user-message" : "assistant-message"}`,
        message.content,
      ));
    }
  }
  panel.append(messages);
  byId("chat-composer").hidden = state.tab !== "chat";
  messages.scrollTop = messages.scrollHeight;
  setSessionTransitionUi();
}

function sectionNavElement() {
  const nav = element("nav", "section-nav");
  nav.setAttribute("aria-label", "简历章节");
  const progress = questionnaireState?.progress || [];
  for (const item of progress) {
    const chip = element(
      "button",
      `section-chip${item.done ? " done" : ""}${item.current ? " current" : ""}`,
      item.label,
    );
    chip.type = "button";
    chip.title = item.done ? "已完成" : "待完善";
    nav.append(chip);
  }
  return nav;
}

function questionAreaElement() {
  return element("div", "question-area");
}

function presentQuestionCard(card) {
  const dialog = byId("question-dialog");
  const body = byId("question-dialog-body");
  if (card) {
    if (card.kind === "interview") {
      presentInterviewFlow(card);
      return;
    }
    body.replaceChildren(renderQuestionCard(card));
    if (!dialog.open) dialog.showModal();
    return;
  }
  const progress = questionnaireState?.progress || [];
  if (progress.length && progress.every((item) => item.done)) {
    const done = element("article", "question-card complete-card");
    done.append(element(
      "p", "question-prompt",
      "🎉 各章节已收集完毕，可在右侧预览微调并导出 PDF 等格式。",
    ));
    body.replaceChildren(done);
    if (!dialog.open) dialog.showModal();
    return;
  }
  const unfinished = progress.filter((item) => item.section !== "summary" && !item.done);
  const summary = progress.find((item) => item.section === "summary");
  if (summary && !summary.done && currentVersion && unfinished.length === 0) {
    body.replaceChildren(summaryGenerateCard());
    if (!dialog.open) dialog.showModal();
    return;
  }
  if (dialog.open) dialog.close();
}

function summaryGenerateCard() {
  const article = element("article", "question-card");
  article.append(element(
    "p", "question-prompt",
    "最后一步：生成自我评价备选，勾选 1~2 条写入简历；措辞可在预览编辑模式中微调。",
  ));
  const button = element("button", "primary", "生成自我评价备选");
  button.type = "button";
  button.addEventListener("click", generateSummaryOptions);
  article.append(button);
  return article;
}

async function generateSummaryOptions() {
  if (!currentBase || !currentVersion || sessionTransitionGate.isTransitioning()) return;
  const versionId = currentVersion.id;
  const baseGeneration = baseActivationGate.current();
  try {
    await api.generateSummaryOptions(versionId);
    if (!baseActivationGate.isCurrent(baseGeneration)) return;
    const loaded = await api.listVersions(currentBase.id);
    versions = loaded;
    currentVersion = loaded.find((item) => item.id === versionId) || currentVersion;
    await refreshQuestionnaire();
    renderConversation();
    presentQuestionCard(questionnaireState?.next || null);
  } catch (error) {
    if (!baseActivationGate.isCurrent(baseGeneration)) return;
    showToast(error instanceof ApiError ? error.message : "自我评价生成失败");
  }
}

function yearMonthField(initial = "") {
  const input = document.createElement("input");
  input.type = "month";
  if (input.type !== "month") {
    const wrap = element("span", "year-month-fallback");
    const year = document.createElement("select");
    const currentYear = new Date().getFullYear();
    for (let y = currentYear; y >= currentYear - 40; y -= 1) {
      year.append(new Option(`${y}年`, String(y)));
    }
    const month = document.createElement("select");
    for (let m = 1; m <= 12; m += 1) {
      month.append(new Option(`${m}月`, String(m).padStart(2, "0")));
    }
    const value = String(initial || "");
    if (/^\d{4}-\d{2}$/.test(value)) {
      year.value = value.slice(0, 4);
      month.value = value.slice(5, 7);
    }
    wrap.append(year, month);
    wrap.getValue = () => `${year.value}-${month.value}`;
    return wrap;
  }
  input.value = String(initial || "");
  input.min = "1990-01";
  input.max = "2035-12";
  return input;
}

function readYearMonth(field) {
  return field.type === "month" ? field.value : field.getValue();
}

function yearMonthRangeField(card) {
  const wrap = element("div", "year-month-range");
  const start = yearMonthField(card.value || "");
  const end = yearMonthField((card.extra && card.extra.end) || "");
  const presentLabel = element("label", "check-row", "至今");
  const present = document.createElement("input");
  present.type = "checkbox";
  present.checked = !card.extra || !card.extra.end;
  presentLabel.prepend(present);
  present.addEventListener("change", () => {
    end.hidden = present.checked;
  });
  end.hidden = present.checked;
  wrap.append(
    element("span", "", "开始"),
    start,
    element("span", "", "结束"),
    end,
    presentLabel,
  );
  wrap.readValue = () => ({
    start: readYearMonth(start),
    end: present.checked ? "" : readYearMonth(end),
  });
  return wrap;
}

function addFreeChip(chipsBox, text) {
  const exists = [...chipsBox.querySelectorAll('input[type="checkbox"]')]
    .some((box) => box.value === text);
  if (exists) return;
  const label = element("label", "check-row chip");
  const box = document.createElement("input");
  box.type = "checkbox";
  box.value = text;
  box.checked = true;
  label.append(box, document.createTextNode(text));
  chipsBox.append(label);
}

function collectChips(chipsBox) {
  return [...chipsBox.querySelectorAll('input[type="checkbox"]:checked')]
    .map((box) => box.value);
}

function renderQuestionCard(card) {
  const article = element("article", "question-card");
  article.dataset.stepId = card.step_id;
  article.append(element("p", "question-prompt", card.prompt));
  const form = element("form", "question-card-form");
  let readValue = null;

  if (card.kind === "text") {
    const isMultiline = card.step_id.includes("links");
    const input = document.createElement(isMultiline ? "textarea" : "input");
    input.value = card.value || "";
    if (isMultiline) input.rows = 3;
    input.placeholder = "输入后点确定";
    form.append(input);
    readValue = () => ({ value: input.value.trim() });
  } else if (card.kind === "choice" || card.kind === "choice_free") {
    const optionsBox = element("div", "choice-options");
    const optionCount = (card.options || []).length;
    for (const option of card.options || []) {
      const label = element("label", "check-row");
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = `choice-${card.step_id}`;
      radio.value = option;
      if (optionCount === 1) radio.checked = true;
      label.append(radio, document.createTextNode(option));
      optionsBox.append(label);
    }
    let freeInput = null;
    if (card.kind === "choice_free") {
      freeInput = document.createElement("input");
      freeInput.placeholder = "其他，自己填写";
      optionsBox.append(freeInput);
    }
    form.append(optionsBox);
    readValue = () => {
      const checked = form.querySelector('input[type="radio"]:checked');
      if (checked) return { value: checked.value };
      return { value: freeInput ? freeInput.value.trim() : "" };
    };
  } else if (card.kind === "multi_choice") {
    const chips = element("div", "choice-options chips");
    const selected = new Set(card.values || []);
    for (const option of card.options || []) {
      const label = element("label", "check-row chip");
      const box = document.createElement("input");
      box.type = "checkbox";
      box.value = option;
      box.checked = selected.has(option);
      label.append(box, document.createTextNode(option));
      chips.append(label);
    }
    const free = document.createElement("input");
    free.placeholder = "添加自定义项，点右侧添加";
    const add = element("button", "text-button", "添加");
    add.type = "button";
    add.addEventListener("click", () => {
      const text = free.value.trim();
      if (!text) return;
      addFreeChip(chips, text);
      free.value = "";
    });
    const freeRow = element("div", "chip-free-row");
    freeRow.append(free, add);
    form.append(chips, freeRow);
    readValue = () => ({ values: normalizeChips(collectChips(chips)) });
  } else if (card.kind === "year_month_range") {
    const range = yearMonthRangeField(card);
    form.append(range);
    readValue = () => ({ extra: periodExtra(range.readValue().start, range.readValue().end) });
  }

  const actions = element("div", "question-actions");
  const submit = element("button", "primary", "确定");
  submit.type = "submit";
  actions.append(submit);
  if (card.skippable) {
    const skip = element("button", "text-button", "跳过");
    skip.type = "button";
    skip.addEventListener("click", () => skipQuestionCard(card));
    actions.append(skip);
  }
  form.append(actions);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const result = readValue ? readValue() : {};
    answerQuestionCard(card, result);
  });
  article.append(form);
  return article;
}

async function refreshQuestionnaire() {
  if (!currentBase) return;
  const baseId = currentBase.id;
  const baseGeneration = baseActivationGate.current();
  const [view, base] = await Promise.all([
    api.questionnaire(baseId),
    api.getFactBase(baseId),
  ]);
  if (!baseActivationGate.isCurrent(baseGeneration) || currentBase?.id !== baseId) return;
  questionnaireState = {
    progress: view.sections,
    next: view.next,
    jobAnalysis: view.job_analysis || [],
  };
  cacheBase(base);
}

async function answerQuestionCard(card, result) {
  if (!currentBase || sessionTransitionGate.isTransitioning()) return;
  const baseId = currentBase.id;
  const baseGeneration = baseActivationGate.current();
  try {
    await api.answerQuestion(baseId, answerPayload(card.step_id, result));
    if (!baseActivationGate.isCurrent(baseGeneration) || currentBase?.id !== baseId) return;
    await refreshQuestionnaire();
    await renderDocument();
    renderConversation();
    presentQuestionCard(questionnaireState?.next || null);
  } catch (error) {
    if (!baseActivationGate.isCurrent(baseGeneration) || currentBase?.id !== baseId) return;
    showToast(error instanceof ApiError ? error.message : "回答保存失败");
    renderConversation();
    presentQuestionCard(card);
  }
}

async function skipQuestionCard(card) {
  if (!currentBase || sessionTransitionGate.isTransitioning()) return;
  const baseId = currentBase.id;
  const baseGeneration = baseActivationGate.current();
  try {
    await api.skipQuestion(baseId, card.step_id);
    if (!baseActivationGate.isCurrent(baseGeneration) || currentBase?.id !== baseId) return;
    await refreshQuestionnaire();
    renderConversation();
    presentQuestionCard(questionnaireState?.next || null);
  } catch (error) {
    if (!baseActivationGate.isCurrent(baseGeneration) || currentBase?.id !== baseId) return;
    showToast(error instanceof ApiError ? error.message : "跳过失败");
    presentQuestionCard(card);
  }
}

let interviewBusy = false;

function interviewExperienceId(card) {
  return String(card?.step_id || "").split(":")[1] || "";
}

function showDialogCard(node) {
  const dialog = byId("question-dialog");
  byId("question-dialog-body").replaceChildren(node);
  if (!dialog.open) dialog.showModal();
}

function interviewContext() {
  return {
    baseGeneration: baseActivationGate.current(),
    baseId: currentBase?.id || "",
    experienceId: currentSession?.active_experience_id || "",
    sessionId: currentSession?.id || "",
  };
}

function isInterviewContext(context) {
  return baseActivationGate.isCurrent(context.baseGeneration)
    && currentBase?.id === context.baseId
    && currentSession?.id === context.sessionId;
}

function setInterviewBusy(busy) {
  interviewBusy = busy;
  const dialog = byId("question-dialog");
  for (const control of dialog.querySelectorAll("button, input, textarea")) {
    control.disabled = busy;
  }
}

function presentInterviewFlow(card) {
  const experienceId = interviewExperienceId(card);
  if (!experienceId) return;
  if (currentSession && currentSession.active_experience_id === experienceId) {
    const pending = Object.values(currentSession.pending_proposals || {});
    if (pending.length) {
      showDialogCard(interviewProposalCard(pending.at(-1)));
      return;
    }
    if (currentSession.current_question) {
      showDialogCard(interviewQuestionCard(currentSession.current_question));
      return;
    }
    showDialogCard(interviewDoneCard(card));
    return;
  }
  showDialogCard(interviewStartCard(card));
}

function interviewStartCard(card) {
  const article = element("article", "question-card");
  article.dataset.stepId = card.step_id;
  article.append(
    element("p", "question-prompt", card.prompt),
    element(
      "p", "question-hint",
      "导师会一步步追问：做了什么、怎么做的、结果如何。每个问题都有选项，点选即可，也可以自己写。",
    ),
  );
  const actions = element("div", "question-actions");
  const start = element("button", "primary", "开始访谈");
  start.type = "button";
  start.addEventListener("click", () => beginInterviewFlow(card));
  const skip = element("button", "text-button", "先跳过这段");
  skip.type = "button";
  skip.addEventListener("click", () => skipQuestionCard(card));
  actions.append(start, skip);
  article.append(actions);
  return article;
}

async function ensureInterviewSession(experienceId) {
  if (!currentBase) return null;
  if (currentSession && currentSession.active_experience_id === experienceId) {
    return currentSession;
  }
  const saved = baseSelection(state, currentBase.id);
  const preferred = saved.experienceId === experienceId ? saved.sessionId : "";
  const existing = await recoverSession(currentBase.id, experienceId, preferred);
  let session = existing;
  if (!session) session = await api.createSession(currentBase.id, experienceId);
  currentSession = session;
  commitSelection(currentBase.id, { ...saved, experienceId, sessionId: session.id });
  return session;
}

async function beginInterviewFlow(card) {
  if (!currentBase || interviewBusy) return;
  const experienceId = interviewExperienceId(card);
  if (!experienceId) return;
  const start = byId("question-dialog-body").querySelector("button.primary");
  if (start) {
    start.disabled = true;
    start.textContent = "正在准备问题…";
  }
  try {
    const session = await ensureInterviewSession(experienceId);
    if (!session || !currentBase) return;
    const question = await api.currentQuestion(session.id);
    if (!currentBase || currentSession?.id !== session.id) return;
    currentSession = await api.getSession(session.id);
    currentExperienceQuality = await loadCurrentExperienceQuality(currentBase.id, experienceId);
    renderConversation();
    if (question) showDialogCard(interviewQuestionCard(question));
    else showDialogCard(interviewDoneCard(card));
  } catch (error) {
    showToast(error instanceof ApiError ? error.message : "访谈启动失败");
    const fresh = byId("question-dialog-body").querySelector("button.primary");
    if (fresh) {
      fresh.disabled = false;
      fresh.textContent = "开始访谈";
    }
  }
}

function interviewQuestionCard(question) {
  const article = element("article", "question-card interview-card");
  const dim = DIMENSIONS.find(([key]) => key === question.dimension);
  article.append(
    element("p", "question-prompt", question.text),
    element("p", "question-hint", `当前追问：${dim ? dim[1] : question.dimension}`),
  );
  const options = question.options || [];
  if (options.length) {
    const chips = element("div", "choice-options chips");
    for (const option of options) {
      const chip = element("button", "chip-button option-chip", option);
      chip.type = "button";
      chip.addEventListener("click", () => submitInterviewAnswer(option));
      chips.append(chip);
    }
    article.append(chips);
  }
  const freeRow = element("div", "chip-free-row");
  const input = document.createElement("input");
  input.placeholder = "或者自己写一段";
  const send = element("button", "primary", "回答");
  send.type = "button";
  const sendFree = () => {
    const text = input.value.trim();
    if (text) submitInterviewAnswer(text);
  };
  send.addEventListener("click", sendFree);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") sendFree();
  });
  freeRow.append(input, send);
  article.append(freeRow);
  const actions = element("div", "question-actions");
  const unknown = element("button", "text-button", "暂时想不到");
  unknown.type = "button";
  unknown.addEventListener("click", () => interviewUnknown(question.dimension));
  actions.append(unknown);
  article.append(actions);
  return article;
}

function interviewProposalCard(proposal) {
  const article = element("article", "question-card proposal-card");
  const dim = DIMENSIONS.find(([key]) => key === proposal.dimension);
  article.append(element(
    "p", "question-prompt",
    `导师把刚才的回答整理成以下事实（${dim ? dim[1] : proposal.dimension}），确认后写入这段经历：`,
  ));
  const list = element("ul", "proposal-values");
  for (const value of proposal.values || []) {
    const item = element("li", "", value.text);
    if (value.confidence === "estimated") item.append(element("span", "badge", "估算"));
    if (value.sensitive) item.append(element("span", "badge warning", "敏感"));
    list.append(item);
  }
  article.append(list);
  const actions = element("div", "question-actions");
  const confirm = element("button", "primary", "确认事实，继续追问");
  confirm.type = "button";
  confirm.addEventListener("click", () => confirmInterviewProposal(proposal.id));
  const reject = element("button", "", "这不是我的意思");
  reject.type = "button";
  reject.addEventListener("click", () => rejectInterviewProposal(proposal.id));
  actions.append(confirm, reject);
  article.append(actions);
  return article;
}

function interviewDoneCard(card) {
  const article = element("article", "question-card complete-card");
  const completed = currentExperienceQuality?.present_dimensions;
  article.append(element(
    "p", "question-prompt",
    Number.isInteger(completed)
      ? `这段经历目前收集到 ${completed}/6 个维度的事实。可以继续补充，也可以先跳过。`
      : "这段经历暂时聊到这里。可以继续补充，也可以先跳过。",
  ));
  const actions = element("div", "question-actions");
  const more = element("button", "primary", "再补充一点");
  more.type = "button";
  more.addEventListener("click", async () => {
    if (!currentSession || interviewBusy) return;
    more.disabled = true;
    try {
      const question = await api.currentQuestion(currentSession.id);
      if (!currentBase || !currentSession) return;
      currentSession = await api.getSession(currentSession.id);
      if (question) showDialogCard(interviewQuestionCard(question));
      else {
        more.disabled = false;
        showToast("暂时没有更多可追问的维度了");
      }
    } catch (error) {
      more.disabled = false;
      showToast(error instanceof ApiError ? error.message : "追问失败");
    }
  });
  const skip = element("button", "text-button", "先跳过，继续下一项");
  skip.type = "button";
  skip.addEventListener("click", () => skipQuestionCard(card));
  actions.append(more, skip);
  article.append(actions);
  return article;
}

async function refreshAfterInterviewTurn() {
  const experienceId = currentSession?.active_experience_id;
  if (currentBase && experienceId) {
    const [base, quality] = await Promise.all([
      api.getFactBase(currentBase.id),
      loadCurrentExperienceQuality(currentBase.id, experienceId),
    ]);
    replaceBase(base);
    currentExperienceQuality = quality;
    await renderFactBase();
  }
  renderConversation();
}

async function submitInterviewAnswer(message) {
  if (!currentBase || !currentSession || interviewBusy) return;
  const context = interviewContext();
  setInterviewBusy(true);
  try {
    const turn = await api.answer(context.sessionId, message);
    if (!isInterviewContext(context)) return;
    currentSession = await api.getSession(context.sessionId);
    await refreshAfterInterviewTurn();
    if (turn.proposal) {
      showDialogCard(interviewProposalCard(turn.proposal));
      return;
    }
    const question = await api.currentQuestion(context.sessionId);
    if (!isInterviewContext(context)) return;
    currentSession = await api.getSession(context.sessionId);
    await refreshAfterInterviewTurn();
    if (question) showDialogCard(interviewQuestionCard(question));
    else await finishInterviewFlow(context.experienceId);
  } catch (error) {
    if (!isInterviewContext(context)) return;
    showToast(error instanceof ApiError ? error.message : "回答保存失败");
  } finally {
    if (isInterviewContext(context)) setInterviewBusy(false);
  }
}

async function confirmInterviewProposal(proposalId) {
  if (!currentBase || !currentSession || interviewBusy) return;
  const context = interviewContext();
  setInterviewBusy(true);
  try {
    const turn = await api.confirmProposal(context.sessionId, proposalId);
    if (!isInterviewContext(context)) return;
    currentSession = await api.getSession(context.sessionId);
    await refreshAfterInterviewTurn();
    if (turn.question) {
      showDialogCard(interviewQuestionCard(turn.question));
      return;
    }
    await finishInterviewFlow(context.experienceId);
  } catch (error) {
    if (!isInterviewContext(context)) return;
    showToast(error instanceof ApiError ? error.message : "事实确认失败");
  } finally {
    if (isInterviewContext(context)) setInterviewBusy(false);
  }
}

async function rejectInterviewProposal(proposalId) {
  if (!currentBase || !currentSession || interviewBusy) return;
  const context = interviewContext();
  setInterviewBusy(true);
  try {
    await api.rejectProposal(context.sessionId, proposalId);
    if (!isInterviewContext(context)) return;
    currentSession = await api.getSession(context.sessionId);
    const question = await api.currentQuestion(context.sessionId);
    if (!isInterviewContext(context)) return;
    currentSession = await api.getSession(context.sessionId);
    await refreshAfterInterviewTurn();
    if (question) showDialogCard(interviewQuestionCard(question));
    else await finishInterviewFlow(context.experienceId);
  } catch (error) {
    if (!isInterviewContext(context)) return;
    showToast(error instanceof ApiError ? error.message : "事实退回失败");
  } finally {
    if (isInterviewContext(context)) setInterviewBusy(false);
  }
}

async function interviewUnknown(dimension) {
  if (!currentBase || !currentSession || interviewBusy) return;
  const context = interviewContext();
  setInterviewBusy(true);
  try {
    await api.recordUnknown(context.sessionId, dimension);
    if (!isInterviewContext(context)) return;
    const question = await api.currentQuestion(context.sessionId);
    if (!isInterviewContext(context)) return;
    currentSession = await api.getSession(context.sessionId);
    await refreshAfterInterviewTurn();
    if (question) showDialogCard(interviewQuestionCard(question));
    else await finishInterviewFlow(context.experienceId);
  } catch (error) {
    if (!isInterviewContext(context)) return;
    showToast(error instanceof ApiError ? error.message : "暂时无法跳过这个问题");
  } finally {
    if (isInterviewContext(context)) setInterviewBusy(false);
  }
}

async function finishInterviewFlow(experienceId) {
  await refreshQuestionnaire();
  if (!currentBase) return;
  renderConversation();
  const next = questionnaireState?.next || null;
  if (next && next.kind === "interview" && interviewExperienceId(next) === experienceId) {
    showDialogCard(interviewDoneCard(next));
    return;
  }
  presentQuestionCard(next);
}

async function submitAnswer(event) {
  event.preventDefault();
  if (!currentBase || interviewBusy) return;
  const input = byId("chat-input");
  const message = input.value.trim();
  if (!message) return;
  const submit = event.currentTarget.querySelector("button[type=submit]");
  submit.disabled = true;
  submit.textContent = "正在发送…";
  try {
    if (!currentSession) {
      const experienceId = state.experienceId
        || currentBase.experiences.at(-1)?.id
        || "";
      if (!experienceId) {
        showToast("先添加一段经历，再开始访谈");
        return;
      }
      const session = await ensureInterviewSession(experienceId);
      if (!session) return;
    }
    input.value = "";
    await submitInterviewAnswer(message);
  } catch (error) {
    showToast(error instanceof ApiError ? error.message : "回答发送失败");
  } finally {
    const fresh = byId("chat-composer")?.querySelector('button[type="submit"]');
    if (fresh) {
      fresh.disabled = false;
      fresh.textContent = "发送回答";
    }
  }
}

function profileForm() {
  const form = element("form", "profile-form");
  const profile = currentBase.profile || {};
  const baseId = currentBase.id;
  const baseGeneration = baseActivationGate.current();
  form.append(
    field("姓名", "name", "", profile.name || ""),
    field("邮箱", "email", "", profile.email || ""),
    field("电话", "phone", "", profile.phone || ""),
    field("所在地", "location", "", profile.location || ""),
    field("个人链接（每行一个）", "links", "", (profile.links || []).join("\n"), "textarea"),
  );
  const save = element("button", "primary", "保存基本信息");
  save.type = "submit";
  form.append(save);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    save.disabled = true;
    try {
      const updated = await api.updateProfile(baseId, {
        name: String(data.get("name") || "").trim(),
        email: String(data.get("email") || "").trim(),
        phone: String(data.get("phone") || "").trim(),
        location: String(data.get("location") || "").trim(),
        links: String(data.get("links") || "").split("\n").map((item) => item.trim()).filter(Boolean),
      });
      if (!baseActivationGate.isCurrent(baseGeneration) || currentBase?.id !== baseId) return;
      replaceBase(updated);
      showToast("基本信息已保存");
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : "基本信息保存失败");
    } finally {
      save.disabled = false;
    }
  });
  return form;
}

function factValue(value) {
  const row = element("li", "fact-value", value.text);
  if (value.confidence === "estimated") row.append(element("span", "badge", "估算"));
  if (value.sensitive) row.append(element("span", "badge warning", "敏感"));
  return row;
}

async function renderFactBase(expectedGeneration = baseActivationGate.current()) {
  const root = byId("facts-content");
  root.className = "facts-content";
  root.replaceChildren();
  if (!currentBase) {
    root.className = "empty-state";
    root.textContent = "建立档案后可在这里查看经历证据。";
    return;
  }
  const base = currentBase;
  const profileDetails = element("details", "profile-details");
  profileDetails.open = false;
  profileDetails.append(element("summary", "", "候选人基本信息"), profileForm());
  root.append(profileDetails);

  const qualityReports = await Promise.all(base.experiences.map(async (experience) => {
    try {
      return await api.experienceQuality(base.id, experience.id);
    } catch {
      return null;
    }
  }));
  if (!baseActivationGate.isCurrent(expectedGeneration) || currentBase?.id !== base.id) return;
  base.experiences.forEach((experience, index) => {
    const card = element("article", "experience-card");
    card.append(element("h3", "", `${experience.organization} · ${experience.role}`));
    const quality = qualityReports[index];
    card.append(element(
      "p",
      "quality-caption",
      quality?.passes_gate
        ? "证据已达到可写门槛"
        : `已整理 ${quality?.present_dimensions || 0}/6 个证据维度`,
    ));
    const grid = element("div", "dimension-list");
    for (const [key, label] of DIMENSIONS) {
      const group = element("details", "dimension-group");
      const values = experience.statements?.[key] || [];
      group.append(element("summary", "", `${label} · ${values.length} 条`));
      if (!values.length) group.append(element("p", "empty-copy", "还没有确认事实"));
      else {
        const list = document.createElement("ul");
        for (const value of values) list.append(factValue(value));
        group.append(list);
      }
      grid.append(group);
    }
    const deepen = element("button", "", "继续访谈");
    deepen.type = "button";
    deepen.addEventListener("click", async () => {
      selectTab("chat");
      await activateExperience(experience.id);
    });
    card.append(grid, deepen, snippetCardSection(base, experience));
    root.append(card);
  });
}

function snippetCardSection(base, experience) {
  const section = element("div", "snippet-cards");
  const heading = element("h4", "", "片段卡");
  const hint = element(
    "p", "quality-caption",
    editMode
      ? "退出编辑模式后可拖拽卡片到右侧预览。"
      : "拖拽卡片到右侧预览的经历段落或底部自定义片段区。",
  );
  const generate = element("button", "", "生成片段卡");
  generate.type = "button";
  generate.addEventListener("click", async () => {
    generate.disabled = true;
    try {
      const result = await api.generateSnippets(base.id, experience.id);
      if (!result.snippets.length) {
        showToast("这段经历还没有可用的已确认事实");
        return;
      }
      for (const snippet of result.snippets) {
        section.append(snippetCard(experience.id, snippet));
      }
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : "片段生成失败");
    } finally {
      generate.disabled = false;
    }
  });
  section.append(heading, hint, generate);
  return section;
}

function snippetCard(experienceId, snippet) {
  const card = element("article", "snippet-card");
  card.draggable = true;
  card.append(element("p", "", snippet.text));
  card.addEventListener("dragstart", (event) => {
    if (editMode) {
      event.preventDefault();
      showToast("请先退出编辑模式再拖拽片段");
      return;
    }
    event.dataTransfer.setData(
      "application/x-resume-snippet",
      JSON.stringify({
        experience_id: experienceId,
        text: snippet.text,
        source_fact_ids: snippet.source_fact_ids || [],
      }),
    );
    event.dataTransfer.effectAllowed = "copy";
  });
  return card;
}

function wirePreviewDropTargets() {
  const doc = byId("preview-frame").contentDocument;
  if (!doc) return;
  for (const target of doc.querySelectorAll("[data-section]")) {
    if (target.dataset.dropWired) continue;
    target.dataset.dropWired = "true";
    target.addEventListener("dragover", (event) => {
      if (!event.dataTransfer.types.includes("application/x-resume-snippet")) return;
      event.preventDefault();
      target.classList.add("drop-active");
    });
    target.addEventListener("dragleave", () => target.classList.remove("drop-active"));
    target.addEventListener("drop", (event) => {
      event.preventDefault();
      target.classList.remove("drop-active");
      const raw = event.dataTransfer.getData("application/x-resume-snippet");
      if (raw) dropSnippet(target, raw);
    });
  }
  doc.addEventListener("click", (event) => {
    const button = event.target.closest(".snippet-remove");
    if (!button) return;
    removeVersionSnippet(button.dataset.snippetId);
  });
}

async function dropSnippet(target, raw) {
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch {
    return;
  }
  if (!currentVersion || editMode) {
    showToast("当前无法拖入片段");
    return;
  }
  const experienceId = target.dataset.section === "custom"
    ? null
    : target.dataset.section.split(":")[1];
  const renderedTexts = (currentRendered?.experiences || [])
    .flatMap((item) => item.bullets || []);
  const customTexts = (currentRendered?.custom_snippets || [])
    .map((item) => item.text);
  if (renderedTexts.includes(payload.text) || customTexts.includes(payload.text)) {
    showToast("该片段已在简历中");
    return;
  }
  try {
    const updated = await api.addVersionSnippet(currentVersion.id, {
      experience_id: experienceId,
      text: payload.text,
      source_fact_ids: payload.source_fact_ids,
    });
    versions = versions.map((item) => item.id === updated.id ? updated : item);
    currentVersion = updated;
    await renderDocument();
    showToast("片段已写入简历");
  } catch (error) {
    showToast(error instanceof ApiError ? error.message : "片段写入失败");
  }
}

async function removeVersionSnippet(snippetId) {
  if (!currentVersion || editMode) return;
  const versionId = currentVersion.id;
  try {
    const updated = await api.deleteVersionSnippet(versionId, snippetId);
    versions = versions.map((item) => item.id === updated.id ? updated : item);
    currentVersion = updated;
    await renderDocument();
    showToast("片段已移除");
  } catch (error) {
    showToast(error instanceof ApiError ? error.message : "片段移除失败");
  }
}

async function chooseVersion(versionId, { languageGeneration = null } = {}) {
  if (!currentBase || !versions.some((item) => item.id === versionId)) return false;
  if (languageGeneration === null) {
    languageGate.next();
    languageTransitioning = false;
    languageIntentLocale = state.locale;
    byId("language-button").textContent = LANGUAGE_LABELS[state.locale];
  }
  const baseId = currentBase.id;
  const baseGeneration = baseActivationGate.current();
  const generation = versionGate.next();
  const intentIsCurrent = () => languageGeneration === null
    || languageGate.isCurrent(languageGeneration);
  versionTransitioning = true;
  renderJdTab();
  renderDocumentToolbar();
  try {
    await activateVersionSerially(() => api.activateVersion(versionId));
    if (!baseActivationGate.isCurrent(baseGeneration)
      || !versionGate.isCurrent(generation)
      || !intentIsCurrent()
      || currentBase?.id !== baseId) return false;
    const versionState = await loadVersions(baseId, versionId);
    if (!baseActivationGate.isCurrent(baseGeneration)
      || !versionGate.isCurrent(generation)
      || !intentIsCurrent()
      || currentBase?.id !== baseId) return false;
    documentCommitGeneration += 1;
    resetEditorState();
    versions = versionState.versions;
    currentVersion = versionState.currentVersion;
    if (currentVersion) state.locale = currentVersion.locale;
    languageIntentLocale = state.locale;
    commitSelection(baseId, {
      ...baseSelection(state, baseId),
      versionId: currentVersion?.id || "",
    });
    versionTransitioning = false;
    byId("language-button").textContent = LANGUAGE_LABELS[state.locale];
    renderJdTab();
    renderToolsTab();
    await renderDocument();
    return true;
  } catch (error) {
    if (!baseActivationGate.isCurrent(baseGeneration)
      || !versionGate.isCurrent(generation)
      || !intentIsCurrent()
      || currentBase?.id !== baseId) return false;
    versionTransitioning = false;
    renderJdTab();
    renderToolsTab();
    renderDocumentToolbar();
    showToast(error instanceof ApiError ? error.message : "版本切换失败");
    return false;
  }
}

function versionMeta(version) {
  const language = LANGUAGE_LABELS[version.locale] || version.locale;
  const company = version.company || "通用公司";
  const role = version.target_role || "通用岗位";
  return `${company} · ${role} · ${language}`;
}

function renderJdTab() {
  const root = byId("jd-content");
  root.className = "jd-content";
  root.replaceChildren();
  if (!currentBase) {
    root.className = "empty-state";
    root.textContent = "建立档案后可以创建岗位版本。";
    return;
  }

  const createDetails = element("details", "version-create");
  createDetails.open = versions.length === 0;
  createDetails.append(element("summary", "", versions.length ? "新建岗位版本" : "创建第一个岗位版本"));
  const form = element("form", "version-form");
  form.append(
    field("版本名称", "name", "例如：东京数据分析师", `${currentBase.target?.role || "通用"}版本`),
    field("目标岗位", "targetRole", "职位名称", currentBase.target?.role || ""),
    field("目标公司（可选）", "company", "公司名称"),
    field("岗位描述 JD", "rawJd", "粘贴岗位职责和要求", "", "textarea"),
  );
  const experienceGroup = element("fieldset", "experience-choice");
  experienceGroup.append(element("legend", "", "用于此版本的经历"));
  for (const experience of currentBase.experiences) {
    const label = element("label", "check-row");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.name = "experienceIds";
    checkbox.value = experience.id;
    checkbox.checked = true;
    label.append(checkbox, document.createTextNode(`${experience.organization} · ${experience.role}`));
    experienceGroup.append(label);
  }
  form.append(experienceGroup);
  const submit = element("button", "primary", "创建并预览");
  submit.type = "submit";
  form.append(submit);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const name = String(data.get("name") || "").trim();
    if (!name) {
      showToast("请填写版本名称");
      return;
    }
    submit.disabled = true;
    const baseId = currentBase.id;
    const baseGeneration = baseActivationGate.current();
    try {
      const version = await api.createVersion(baseId, {
        name,
        target_role: String(data.get("targetRole") || "").trim(),
        company: String(data.get("company") || "").trim(),
        raw_jd: String(data.get("rawJd") || "").trim(),
        locale: state.locale,
        selected_experience_ids: data.getAll("experienceIds").map(String),
      });
      if (!baseActivationGate.isCurrent(baseGeneration) || currentBase?.id !== baseId) return;
      versions = [...versions.filter((item) => item.id !== version.id), version];
      await chooseVersion(version.id);
      if (baseActivationGate.isCurrent(baseGeneration) && currentBase?.id === baseId) {
        showToast("岗位版本已创建");
      }
    } catch (error) {
      if (!baseActivationGate.isCurrent(baseGeneration) || currentBase?.id !== baseId) return;
      showToast(error instanceof ApiError ? error.message : "版本创建失败");
      submit.disabled = false;
    }
  });
  createDetails.append(form);
  root.append(createDetails);

  const list = element("div", "version-list");
  for (const version of versions) {
    const card = element("article", `version-card${version.id === currentVersion?.id ? " selected" : ""}`);
    const heading = element("div", "version-card-heading");
    heading.append(element("strong", "", version.name));
    if (version.id === currentVersion?.id) heading.append(element("span", "badge", "当前"));
    if (version.status === "stale") heading.append(element("span", "badge warning", "事实已更新"));
    card.append(heading, element("p", "", versionMeta(version)));
    const use = element("button", "", version.id === currentVersion?.id ? "正在使用" : "使用此版本");
    use.type = "button";
    use.disabled = documentIsTransitioning() || version.id === currentVersion?.id;
    use.addEventListener("click", () => chooseVersion(version.id));
    card.append(use);
    list.append(card);
  }
  if (versions.length) root.append(list);
}

function configureExportLink(id, format, version) {
  const link = byId(id);
  if (!version) {
    link.removeAttribute("href");
    link.classList.add("disabled");
    link.setAttribute("aria-disabled", "true");
    link.setAttribute("aria-describedby", "export-prerequisite");
    link.setAttribute("tabindex", "0");
    link.title = "请先创建岗位版本";
    return;
  }
  link.href = api.exportUrl(version.id, format);
  link.classList.remove("disabled");
  link.setAttribute("aria-disabled", "false");
  link.removeAttribute("aria-describedby");
  link.removeAttribute("tabindex");
  link.removeAttribute("title");
}

function renderDocumentToolbar() {
  const switcher = byId("document-switcher");
  switcher.replaceChildren();
  const styleSelect = byId("style-select");
  styleSelect.replaceChildren();

  if (!currentVersion) {
    styleSelect.append(new Option("先创建岗位版本"));
    styleSelect.disabled = true;
  } else {
    const versionSelect = document.createElement("select");
    versionSelect.setAttribute("aria-label", "岗位版本");
    for (const version of versions) {
      const option = new Option(version.name, version.id, false, version.id === currentVersion.id);
      versionSelect.append(option);
    }
    versionSelect.addEventListener("change", () => chooseVersion(versionSelect.value));
    versionSelect.disabled = editMode || documentIsTransitioning();
    switcher.append(versionSelect);
    if (currentVersion.locale === "ja") {
      const documentTypes = element("div", "document-types");
      const rirekisho = element("button", "selected", "履歴書");
      const workHistory = element("button", "", "職務経歴書");
      rirekisho.type = workHistory.type = "button";
      rirekisho.disabled = true;
      workHistory.addEventListener("click", () => showToast("当前导出会同时保留日文履历所需信息"));
      documentTypes.append(rirekisho, workHistory);
      switcher.append(documentTypes);
    }
    const styleNames = STYLE_CATALOG[currentVersion.locale] || STYLE_CATALOG.zh;
    const selectedStyle = currentVersion.styles?.[currentVersion.locale] || styleNames[0];
    for (const style of styleNames) {
      styleSelect.append(new Option(style, style, false, style === selectedStyle));
    }
    styleSelect.disabled = editMode || documentIsTransitioning();
    styleSelect.onchange = async () => {
      const baseId = currentBase?.id;
      const versionId = currentVersion.id;
      const baseGeneration = baseActivationGate.current();
      const versionGeneration = versionGate.current();
      styleSelect.disabled = true;
      try {
        const updated = await api.setVersionStyle(versionId, styleSelect.value);
        if (!baseActivationGate.isCurrent(baseGeneration)
          || !versionGate.isCurrent(versionGeneration)
          || currentBase?.id !== baseId
          || currentVersion?.id !== versionId) return;
        versions = versions.map((item) => item.id === updated.id ? updated : item);
        currentVersion = updated;
        await renderDocument();
        showToast("版式已保存");
      } catch (error) {
        if (!baseActivationGate.isCurrent(baseGeneration)
          || !versionGate.isCurrent(versionGeneration)
          || currentBase?.id !== baseId
          || currentVersion?.id !== versionId) return;
        showToast(error instanceof ApiError ? error.message : "版式保存失败");
        styleSelect.disabled = false;
      }
    };
  }

  const editButton = byId("edit-button");
  editButton.disabled = !currentVersion || documentIsTransitioning();
  editButton.textContent = !currentVersion ? "先创建岗位版本" : editMode ? "保存编辑" : "编辑简历";
  editButton.title = currentVersion ? "编辑当前简历草稿" : "请先创建岗位版本";
  const draftBadge = byId("draft-badge");
  draftBadge.hidden = !currentVersion?.manual_html && !currentVersion?.manual_markdown;
  byId("export-prerequisite").hidden = Boolean(currentVersion);
  configureExportLink("export-pdf", "pdf", currentVersion);
  configureExportLink("export-html", "html", currentVersion);
  configureExportLink("export-markdown", "md", currentVersion);
  configureExportLink("export-docx", "docx", currentVersion);
}

async function renderDocument() {
  const previewGeneration = previewGate.next();
  renderDocumentToolbar();
  const empty = byId("preview-empty");
  const frame = byId("preview-frame");
  const warnings = byId("preview-warnings");
  byId("preview-editor-bar").hidden = !editMode;
  byId("markdown-editor").hidden = true;
  warnings.replaceChildren();
  currentRendered = null;
  currentRenderedVersionId = null;
  frame.hidden = true;
  frame.removeAttribute("srcdoc");
  empty.hidden = false;
  const placeholder = empty.querySelector(".paper-placeholder span");
  if (!currentVersion) {
    placeholder.textContent = "创建岗位版本后，简历会显示在这里。";
    return;
  }

  const requestedId = currentVersion.id;
  const requestedBaseId = currentBase?.id;
  const requestedDocumentGeneration = documentCommitGeneration;
  placeholder.textContent = "正在生成预览…";
  try {
    const rendered = await api.previewVersion(requestedId);
    if (!previewGate.isCurrent(previewGeneration)
      || documentCommitGeneration !== requestedDocumentGeneration
      || currentBase?.id !== requestedBaseId
      || currentVersion?.id !== requestedId) return;
    currentRendered = rendered;
    currentRenderedVersionId = requestedId;
    for (const warning of rendered.warnings || []) {
      warnings.append(element("div", "preview-warning", warning.message));
    }
    frame.srcdoc = rendered.html;
    empty.hidden = true;
    frame.hidden = false;
  } catch (error) {
    if (!previewGate.isCurrent(previewGeneration)
      || documentCommitGeneration !== requestedDocumentGeneration
      || currentBase?.id !== requestedBaseId
      || currentVersion?.id !== requestedId) return;
    placeholder.textContent = error instanceof ApiError ? error.message : "预览生成失败";
  }
}

function setEditorView(view) {
  editorView = view === "markdown" ? "markdown" : "visual";
  const frame = byId("preview-frame");
  const markdown = byId("markdown-editor");
  const visualButton = byId("visual-editor-button");
  const markdownButton = byId("markdown-editor-button");
  frame.hidden = editorView !== "visual";
  markdown.hidden = editorView !== "markdown";
  visualButton.classList.toggle("selected", editorView === "visual");
  markdownButton.classList.toggle("selected", editorView === "markdown");
  if (frame.contentDocument) {
    frame.contentDocument.designMode = editMode && editorView === "visual" ? "on" : "off";
  }
}

function beginEditor() {
  if (!currentVersion || !currentRendered || currentRenderedVersionId !== currentVersion.id) {
    showToast("预览尚未准备好");
    return;
  }
  editMode = true;
  editorView = "visual";
  editorTarget = {
    baseId: currentBase.id,
    versionId: currentVersion.id,
    documentGeneration: documentCommitGeneration,
  };
  byId("markdown-editor").value = currentRendered.markdown;
  byId("preview-editor-bar").hidden = false;
  renderDocumentToolbar();
  setEditorView("visual");
  showToast("可以直接修改右侧文字，也可以编辑 Markdown");
}

function editedHtml() {
  const documentRoot = byId("preview-frame").contentDocument?.documentElement;
  return documentRoot ? `<!DOCTYPE html>\n${documentRoot.outerHTML}` : currentRendered?.html || "";
}

async function saveEditor() {
  if (documentIsTransitioning()) return;
  const button = byId("edit-button");
  const target = editorTarget;
  if (!target
    || documentCommitGeneration !== target.documentGeneration
    || currentBase?.id !== target.baseId
    || currentVersion?.id !== target.versionId) {
    resetEditorState();
    await renderDocument();
    showToast("版本已切换，请重新编辑");
    return;
  }
  const draft = {
    markdown: byId("markdown-editor").value,
    html: editedHtml(),
  };
  button.disabled = true;
  try {
    const updated = await api.setVersionDraft(target.versionId, draft);
    if (editorTarget !== target
      || documentCommitGeneration !== target.documentGeneration
      || currentBase?.id !== target.baseId
      || currentVersion?.id !== target.versionId) return;
    versions = versions.map((item) => item.id === updated.id ? updated : item);
    currentVersion = updated;
    resetEditorState();
    await renderDocument();
    renderToolsTab();
    showToast("编辑稿已保存到服务端");
  } catch (error) {
    if (editorTarget !== target
      || documentCommitGeneration !== target.documentGeneration
      || currentBase?.id !== target.baseId
      || currentVersion?.id !== target.versionId) return;
    showToast(error instanceof ApiError ? error.message : "编辑稿保存失败");
    button.disabled = false;
  }
}

async function resetDraft() {
  if (!currentVersion || documentIsTransitioning()) return;
  const target = {
    baseId: currentBase.id,
    versionId: currentVersion.id,
    documentGeneration: documentCommitGeneration,
  };
  const button = byId("reset-draft-button");
  button.disabled = true;
  try {
    const updated = await api.setVersionDraft(target.versionId, { markdown: "", html: "" });
    if (documentCommitGeneration !== target.documentGeneration
      || currentBase?.id !== target.baseId
      || currentVersion?.id !== target.versionId) return;
    versions = versions.map((item) => item.id === updated.id ? updated : item);
    currentVersion = updated;
    resetEditorState();
    await renderDocument();
    renderToolsTab();
    showToast("已恢复为事实库自动生成的版本");
  } catch (error) {
    if (documentCommitGeneration !== target.documentGeneration
      || currentBase?.id !== target.baseId
      || currentVersion?.id !== target.versionId) return;
    showToast(error instanceof ApiError ? error.message : "恢复失败");
    button.disabled = false;
  }
}

function toolExportLink(label, format, prerequisiteId) {
  const link = element("a", "button-link", label);
  link.setAttribute("role", "link");
  if (currentVersion) link.href = api.exportUrl(currentVersion.id, format);
  else {
    link.classList.add("disabled");
    link.setAttribute("aria-disabled", "true");
    link.setAttribute("aria-describedby", prerequisiteId);
    link.setAttribute("tabindex", "0");
  }
  return link;
}

function renderToolsTab() {
  const root = byId("tools-content");
  root.className = "tools-content";
  root.replaceChildren();

  const service = element("section", "tool-card");
  service.append(
    element("h3", "", "运行状态"),
    element("p", "", capabilitiesState?.status === "ready"
      ? "导师访谈与事实提炼可用。"
      : "导师当前离线，事实库、版本与导出仍可使用。"),
  );
  root.append(service);

  const exports = element("section", "tool-card");
  exports.append(element("h3", "", "当前版本导出"));
  const prerequisite = element("p", "export-prerequisite", "请先创建岗位版本后再导出。 ");
  prerequisite.id = "tools-export-prerequisite";
  prerequisite.hidden = Boolean(currentVersion);
  exports.append(prerequisite);
  const exportActions = element("div", "tool-actions");
  exportActions.append(
    toolExportLink("HTML", "html", prerequisite.id),
    toolExportLink("Markdown", "md", prerequisite.id),
    toolExportLink("DOCX", "docx", prerequisite.id),
    toolExportLink("PDF", "pdf", prerequisite.id),
  );
  exports.append(exportActions);
  root.append(exports);

  const wareki = element("section", "tool-card");
  wareki.append(element("h3", "", "和暦换算"));
  const form = element("form", "wareki-form");
  const western = field("公历日期", "western", "2019-05-01");
  const japanese = field("和暦日期", "japanese", "平成31年4月30日");
  const result = element("output", "conversion-result", "输入一侧日期后换算");
  const actions = element("div", "tool-actions");
  const toJapanese = element("button", "", "转为和暦");
  const toWestern = element("button", "", "转为公历");
  toJapanese.type = toWestern.type = "button";
  toJapanese.addEventListener("click", () => {
    result.textContent = toWareki(western.querySelector("input").value) || "日期格式不正确";
  });
  toWestern.addEventListener("click", () => {
    result.textContent = fromWareki(japanese.querySelector("input").value) || "和暦格式或日期不正确";
  });
  actions.append(toJapanese, toWestern);
  form.append(western, japanese, actions, result);
  wareki.append(form);
  root.append(wareki);
}

async function createSample() {
  const button = byId("sample-button");
  button.disabled = true;
  button.textContent = "正在创建…";
  try {
    let base = await api.createFactBase({
      role: "数据分析师",
      country: "日本",
      languages: ["zh", "ja", "en"],
    });
    base = await api.addExperience(base.id, {
      organization: "星河科技",
      role: "数据分析实习生",
    });
    selectTab("chat");
    await activateBase(base);
    showToast("已创建示例档案");
  } catch (error) {
    showToast(error instanceof ApiError ? error.message : "示例档案创建失败");
  } finally {
    button.disabled = false;
    button.textContent = "示例档案";
  }
}

async function cycleLanguage() {
  const index = LANGUAGE_ORDER.indexOf(languageIntentLocale);
  const desiredLocale = LANGUAGE_ORDER[(index + 1) % LANGUAGE_ORDER.length];
  languageIntentLocale = desiredLocale;
  const generation = languageGate.next();
  versionGate.next();
  versionTransitioning = false;
  byId("language-button").textContent = LANGUAGE_LABELS[desiredLocale];
  if (!currentBase) {
    state.locale = desiredLocale;
    saveState();
    return;
  }
  const baseId = currentBase.id;
  const baseGeneration = baseActivationGate.current();
  const experienceIds = currentBase.experiences.map((item) => item.id);
  const intentIsCurrent = () => languageGate.isCurrent(generation)
    && baseActivationGate.isCurrent(baseGeneration)
    && currentBase?.id === baseId;
  languageTransitioning = true;
  byId("language-button").setAttribute("aria-busy", "true");
  renderJdTab();
  renderDocumentToolbar();
  try {
    let version = versions.find((item) => item.locale === desiredLocale);
    if (!version) {
      const role = currentBase.target?.role || "通用";
      version = await api.createVersion(baseId, {
        name: `${LANGUAGE_LABELS[desiredLocale]} · ${role}`,
        target_role: role,
        company: "",
        raw_jd: "",
        locale: desiredLocale,
        selected_experience_ids: experienceIds,
      });
      if (!intentIsCurrent()) return;
      versions = [...versions.filter((item) => item.id !== version.id), version];
    }
    const selected = await chooseVersion(version.id, { languageGeneration: generation });
    if (!intentIsCurrent()) return;
    languageTransitioning = false;
    languageIntentLocale = state.locale;
    if (!selected) byId("language-button").textContent = LANGUAGE_LABELS[state.locale];
    renderJdTab();
    renderDocumentToolbar();
  } catch (error) {
    if (!intentIsCurrent()) return;
    languageTransitioning = false;
    languageIntentLocale = state.locale;
    byId("language-button").textContent = LANGUAGE_LABELS[state.locale];
    renderJdTab();
    renderDocumentToolbar();
    showToast(error instanceof ApiError ? error.message : "语言版本切换失败");
  } finally {
    if (languageGate.isCurrent(generation)) {
      byId("language-button").removeAttribute("aria-busy");
    }
  }
}

async function boot() {
  byId("language-button").textContent = LANGUAGE_LABELS[state.locale];
  selectTab(state.tab);
  try {
    const [, capabilities, loadedBases] = await Promise.all([
      api.health(),
      api.capabilities(),
      api.listFactBases(),
    ]);
    bases = loadedBases;
    renderBaseSwitcher();
    capabilitiesState = capabilities;
    setServiceStatus(capabilities);
    const base = bases.find((item) => item.id === state.factBaseId) || bases.at(-1) || null;
    if (base) await activateBase(base);
    else renderOnboarding();
  } catch (error) {
    capabilitiesState = null;
    setServiceStatus(null);
    renderBaseSwitcher();
    renderOnboarding();
    showToast(error instanceof ApiError ? error.message : "页面初始化失败");
  }
}

byId("primary-tabs").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-tab]");
  if (!button) return;
  selectTab(button.dataset.tab);
  if (button.dataset.tab === "facts") renderFactBase();
  if (button.dataset.tab === "jd") renderJdTab();
  if (button.dataset.tab === "tools") renderToolsTab();
});
byId("primary-tabs").addEventListener("keydown", (event) => {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  const tabs = [...event.currentTarget.querySelectorAll('[role="tab"]')];
  const currentIndex = tabs.indexOf(document.activeElement);
  if (currentIndex < 0) return;
  event.preventDefault();
  let nextIndex = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : currentIndex;
  if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
  if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % tabs.length;
  tabs[nextIndex].focus();
  tabs[nextIndex].click();
});
byId("settings-button").addEventListener("click", () => byId("settings-dialog").showModal());
byId("base-select").addEventListener("change", async (event) => {
  const select = event.currentTarget;
  const base = bases.find((item) => item.id === select.value);
  if (!base) return;
  select.setAttribute("aria-busy", "true");
  try {
    await activateBase(base);
  } catch (error) {
    showToast(error instanceof ApiError ? error.message : "档案切换失败");
    renderBaseSwitcher();
  } finally {
    select.removeAttribute("aria-busy");
  }
});
byId("sample-button").addEventListener("click", createSample);
byId("new-base-button").addEventListener("click", startNewBase);
byId("language-button").addEventListener("click", cycleLanguage);
byId("chat-composer").addEventListener("submit", submitAnswer);
byId("edit-button").addEventListener("click", () => {
  if (editMode) saveEditor();
  else beginEditor();
});
byId("visual-editor-button").addEventListener("click", () => setEditorView("visual"));
byId("markdown-editor-button").addEventListener("click", () => setEditorView("markdown"));
byId("reset-draft-button").addEventListener("click", resetDraft);
byId("preview-frame").addEventListener("load", () => {
  if (editMode && editorView === "visual") setEditorView("visual");
  wirePreviewDropTargets();
});

boot();
