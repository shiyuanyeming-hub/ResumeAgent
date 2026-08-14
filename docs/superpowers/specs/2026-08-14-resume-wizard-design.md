# ResumeAgent 向导式问答重构设计（中文简历优先）

日期：2026-08-14
状态：已获用户认可（三部分设计逐节确认）

## 1. 背景与目标

ResumeAgent 目前是「证据优先」的简历导师：一次一问、六维证据、候选事实需用户确认后才进事实库，简历版本从已确认事实自动渲染。现有痛点与用户诉求：

1. **慢**：每轮经历追问要串行两次 LLM（提炼事实、写下一问），确认后还要再等一次写问题。
2. **收集方式单调**：基本信息是表单，教育背景、时间等信息没有问答入口，也没有选项式交互。
3. **无卡片交互**：事实库只是列表，无法把「可写片段」直接拖到预览上写入。
4. **缺章节**：没有教育背景、核心课程、技能、自我评价章节；自我评价无生成能力。

**目标形态**：把简历做成「向导式问答」——简历上需要的一切都靠问答收集，尽量用选项交互；按中文简历常规结构顺序提问；完成后预览可微调并导出。**本阶段只完善中文简历**，日/英入口保留但不再投入。

## 2. 范围与非目标

**范围内**：
- 访谈提速（合并 LLM 调用 + 前端乐观渲染）
- 档案级问卷引擎（章节顺序、选项式问题卡片、年月选择器）
- 教育背景章节（学校/专业/学历/起止年月/核心课程智能推荐）
- 经历类型（实习/工作/项目/校园）与年月起止时间
- 技能章节（从事实提炼候选 + 手动添加）
- 自我评价章节（LLM 生成 3~5 个备选，用户勾选确认后写入）
- 片段卡生成与拖拽写入预览（版本级呈现层）
- 中文渲染器接入新章节；预览编辑与四格式导出保留

**非目标**（本阶段明确不做）：
- 日/英简历的新功能与模板完善
- 已有简历的 PDF/DOCX 导入
- 多用户、登录、托管部署
- LLM 流式输出（合并调用已满足提速目标；流式留作后续）
- 简历照片、完整 JIS 履歴書字段

## 3. 总体架构

采用 **方案 C：确定性骨架 + LLM 出候选**。

- 章节顺序、问题顺序、选项校验、跳过/回退策略全部由确定性代码（问卷状态机）控制。
- LLM 只承担四类「生成候选」职责：事实提炼、下一问措辞、核心课程推荐、自我评价备选、片段润色。所有 LLM 产物均为**候选**，用户确认后才生效。
- 离线时全部退化为确定性模板/内置词典，功能可用但候选质量降低。
- 延续现有分层：Browser(ES modules) → FastAPI → application services → 确定性 planner/renderer + HelloAgents 适配器 → SQLite。

现有 `InterviewSession`（经历级六维追问）保持不变，作为问卷「经历」章节的子流程复用。

## 4. 数据模型变更

存储层是 JSON payload 快照（`fact_bases` / `resume_versions` / `interview_sessions` 表），Pydantic 模型加带默认值的字段即可平滑兼容，**无需迁移脚本**。

### 4.1 新模型

```python
class YearMonth(str):  # "YYYY-MM" 校验的字符串类型，pydantic 约束实现
    ...

class Education(BaseModel):
    id: UUID
    school: str            # 必填
    major: str = ""        # 专业，选项或自由输入
    degree: str = ""       # 学历：高中/大专/本科/硕士/博士（单选）
    start: YearMonth = ""
    end: Optional[YearMonth] = None   # None 表示「至今」
    core_courses: List[str] = []
    created_at / updated_at

class ExperienceType(str, Enum):
    INTERNSHIP = "internship"   # 实习
    WORK = "work"               # 工作
    PROJECT = "project"         # 项目
    CAMPUS = "campus"           # 校园
```

### 4.2 扩展模型

- `Experience`：新增 `type: ExperienceType = PROJECT`、`linked_skills` 保留；`start`/`end` 语义收紧为 `YYYY-MM` 或空（旧数据保留原字符串，新写入校验年月格式）。
- `CandidateProfile`：新增 `skills: List[str] = []`（档案级技能）。
- `CareerFactBase`：新增 `educations: List[Education] = []`。
- `ResumeVersion`：新增
  - `summary_options: List[str] = []`（自我评价备选，展示态）
  - `selected_summary: str = ""`（用户勾选/编辑后确认的最终文本）
  - `snippets: Dict[UUID, List[VersionSnippet]] = {}`（经历级片段呈现覆盖，见 §8）
  - `custom_sections: List[VersionSnippet] = []`（「自定义片段」区）

```python
class VersionSnippet(BaseModel):
    id: UUID
    text: str              # 润色后的简历语言片段
    source_fact_ids: List[UUID] = []   # 溯源，用于无幻觉检查与去重
    created_at: datetime
```

### 4.3 章节完整度（确定性）

`domain/quality.py` 新增 `evaluate_profile_completeness(base) -> ProfileReport`，按章节输出完成状态（驱动问卷进度条与「完成」判定）：

- 基本信息：姓名、邮箱、电话非空
- 求职意向：`target.role` 非空
- 教育背景：至少 1 条，且 school、major、start 非空
- 经历：至少 1 条通过六维质量门槛（现有 `evaluate_experience`）
- 技能：`profile.skills` 非空
- 自我评价：当前激活版本 `selected_summary` 非空

## 5. 问卷引擎

### 5.1 章节与问题顺序（中文简历常规结构）

```
① 基本信息  姓名 → 邮箱 → 电话 → 所在地 → 个人链接（可跳过）
② 求职意向  目标岗位 → 目标城市（可跳过；城市写入 `target.country` 字段，语义为求职地）
③ 教育背景  （可多段，循环）学校 → 专业 → 学历 → 起止年月（含「至今」）→ 核心课程
④ 经历      （可多段，循环）类型 → 名称/组织 → 角色 → 起始年月 → 结束年月/至今 → 六维追问（复用 InterviewSession）
⑤ 技能      从经历提炼候选 chips + 手动添加
⑥ 自我评价  生成备选 → 勾选/微调 → 确认写入
⑦ 完成提示 → 预览微调 → 导出
```

- 每章可「跳过 / 稍后补」；章节导航可回跳补答；重复回答覆盖旧值。
- 回答即时写入模型（profile/education/experience 是唯一真相源），问卷状态只记录「哪些题已答/已跳」，章节完成度由 §4.3 确定性推导，避免双写。

### 5.2 问题卡片类型（QuestionKind）

| kind | 交互 | 校验 | 用于 |
|---|---|---|---|
| `text` | 单行/多行输入 | 非空/格式（邮箱等） | 姓名、邮箱、学校 |
| `choice` | 单选选项按钮 | 必选一 | 学历、经历类型 |
| `choice_free` | 单选 + 「其他，自己填」 | 必选一 | 专业、目标岗位 |
| `multi_choice` | 多选 chips + 自定义添加 | 至少一 | 核心课程、技能 |
| `year_month_range` | 起止年月选择器（含「至今」） | 起 ≤ 止（起必填） | 教育起止、经历起止 |

### 5.3 后端组件

- `application/questionnaire.py`：`QuestionnaireEngine`，按章节顺序产出下一步 `QuestionCard(section, step_id, kind, prompt, options, value, skipped)`；`answer(step_id, value)` 校验并写入模型；`skip(step_id)`。
- 步骤定义集中在一个数据表 `domain/questionnaire_steps.py`（章节、顺序、kind、目标字段映射、选项提供器、可跳过性），便于单测与调整顺序。
- 前端 `app.js` 新增问题卡片渲染器与年月选择器组件；顶部 tabs 改为章节导航（基本信息/求职意向/教育/经历/技能/评价/片段），带完成度徽标。

## 6. 提速：合并 LLM 调用

### 6.1 调用结构

- 用户回答经历追问后，**一次** LLM 调用返回组合 payload：

```json
{
  "dimension": "action",
  "values": [{"text": "...", "confidence": "unverified", "specificity": "concrete", "sensitive": false}],
  "rationale": "...",
  "next_question": "下一步……（问句）？"
}
```

- 预判逻辑（确定性）：回答前由 `QuestionPlanner` 计算「排除当前维度后缺口最高、未跳过的维度」作为预判维度；prompt 中告知模型预判维度与缺口排行，模型只负责写问句。
- 确认事实后：planner 重新计算下一维度；**与预判维度一致 → 直接使用预写问句（零等待）**；不一致（用户拒绝、维度被填满等）→ 补一次 LLM 写问句，离线时用 `DeterministicQuestionWriter` 兜底。
- `InterviewSession` 新增 `pending_next_question: Optional[InterviewQuestion]` 存储预写问句。
- 离线模式：事实提炼不可用时维持现状（回答落库、提示稍后继续），问题全部模板化。

### 6.2 前端

- 发送回答后立即乐观渲染用户消息 + 「导师正在提炼…」状态（按钮禁用），响应到达后一次刷新会话视图；不再二次拉取。
- 确认事实时若服务端返回即用预写问句，UI 无需再等待。

**验收**：每轮交互最多 1 个 LLM 等待点；确认路径典型情况下 0 个。

## 7. 章节功能

### 7.1 教育背景与核心课程智能推荐

- 新增内置资源 `domain/course_catalog.py`：8~10 个常见专业（计算机/软件工程、数据科学、电子信息、机械、经管、金融、医学、法学、新闻中文、设计等）→ 核心课程清单（每个专业 8~12 门）。
- 交互：专业题（`choice_free`，选项来自课程词典的专业列表，可「其他，自己填」）→ 选专业后立即展示推荐课程 chips：词典推荐默认勾选（可取消）；配置 LLM 时追加 5~8 门「AI 推荐」课程（不默认勾选，勾选才生效），来源有标记；支持自由添加。
- LLM 课程推荐为独立小 Agent（`CourseRecommendationAgent`），仅当专业不在词典或需增强时调用；失败静默降级为仅词典。
- 课程全部存入该 `Education.core_courses`，渲染为「教育背景」条目内一行（如「核心课程：数据结构、操作系统、……」）。

### 7.2 经历类型与时间

- 新经历向导：类型（`choice`：实习/工作/项目/校园）→ 名称/组织 → 角色 → 起止年月（`year_month_range`，含「至今」）→ 进入六维追问。
- 六维追问沿用现有 `InterviewService`（合并调用见 §6）。
- 校园/项目类型经历在中英文语境渲染为「校园及项目经历」小节；实习/工作渲染为「实习/工作经历」小节（渲染规则见 §9）。

### 7.3 技能

- 来源：`profile.skills` 的候选由两部分构成：已确认事实的 `linked_skills` 与 LLM 从事实文本中提炼的技能词（仅建议、勾选生效）；手动添加 chips。
- 渲染：中文简历「技能」章节为标签云样式（现有 `.skill` 样式复用）。

### 7.4 自我评价备选

- 触发：六章完成自动进入，或章节导航手动点「生成自我评价」。
- 输入：已确认事实（当前版本所选经历）、经历类型/角色、技能、目标岗位。
- LLM 输出 3~5 条备选（每条 40~70 字，风格错开：稳重/进取/技术驱动），**严格基于已确认内容**；输出校验：备选中不得出现事实库之外的具体数字、公司名、职位名（`grounding_check`，P4 实现）。
- 交互：chips 多选（1~2 条）+ 可编辑合并文本 → 确认写入 `selected_summary`；离线时用确定性模板（目标岗位 + 技能 + 经历数）生成 3 条备选。
- 渲染：中文简历「自我评价」章节（技能之后）。

## 8. 片段卡与拖拽

### 8.1 关键概念：事实与呈现分层

- 事实库保存**用户原话事实**（确认制，真相源）。
- **片段卡**是呈现层生成物：LLM 把某段经历已确认事实润色合并为 1~3 条简历语言片段（每条一张卡）。生成触发：该经历六维达标后自动生成，或手动点「生成片段」。
- 离线降级：片段卡退化为「事实原话卡」（每条已确认事实一张），仍可拖入。
- 片段卡**只影响版本呈现**，不改事实库；可溯源（`source_fact_ids`）。

### 8.2 经历在版本中的两种呈现模式

- **自动模式（默认）**：渲染该经历已确认事实原话 bullets（现状行为）。
- **片段模式**：渲染该版本 `snippets[experience_id]` 中的润色片段（按加入顺序）。
- 拖入该经历的第一张片段卡 → 切换为片段模式；继续拖入 → 追加；删除某条 → 从列表移除；列表清空 → 回退自动模式。
- 这样拖拽「写上去」有真实效果：拖入的是润色片段而非事实原文，不会与自动渲染重复；不同版本可拖不同子集/顺序，赋予版本差异化价值。

### 8.3 落点与规则

- 左侧章节导航新增「片段」面板：全部已确认事实按经历分组，每经历显示其片段卡（生成状态）。
- 预览 iframe 各章节渲染 `data-section` 锚点（教育、各经历段落、技能、自我评价、文档底部「自定义片段」区），拖拽悬停时高亮。
- 落点规则：
  - 拖到**对应经历段落** → 该经历进入/追加片段模式（§8.2）；经历未选入当前版本则先自动选入。
  - 拖到**自定义片段区** → 写入 `custom_sections`，渲染在文档末尾「自定义片段」小节。
  - 其他章节落点（教育/技能/自我评价）不接受拖入，悬停无高亮。
- 重复校验：片段文本与当前版本渲染内容相同时提示「该片段已在简历中」，不写入。
- 已写入片段可单独删除（预览中版本级片段带 ✕，或片段面板「已加入本版本」分组中移除）。
- 手工编辑模式（designMode/Markdown）打开时拖拽停用并提示，避免双写；保存或恢复自动生成后恢复。

### 8.4 数据与 API

- `ResumeVersion.snippets: Dict[experience_id, List[VersionSnippet]]`、`custom_sections: List[VersionSnippet]`。
- API：`POST /versions/{id}/snippets`（{experience_id|null, snippet_id}）→ 返回更新后版本；`DELETE /versions/{id}/snippets/{snippet_id}`。
- 片段卡本身由 `POST /fact-bases/{id}/experiences/{experience_id}/snippets/generate` 生成（LLM），返回候选卡片列表（可重新生成，不自动生效）。

## 9. 渲染与导出变更（仅中文）

- `ResumeRenderer` 中文分支新增章节与顺序：基本信息头 → 求职意向 → 自我评价 → 教育背景（含核心课程）→ 实习/工作经历 → 校园及项目经历 → 技能 → 自定义片段。
- 经历小节按 `type` 分组；每组内按 §8.2 模式渲染。
- 自我评价：`selected_summary` 非空才渲染该节。
- `RenderedResume` 增补 education/summary 字段；导出（HTML/Markdown/DOCX/PDF）与预览共用同一渲染结果，保证一致。
- 预览 iframe 输出增加 `data-section` 锚点与版本级片段的删除标记。
- 日/英渲染器不改动。

## 10. API 变更汇总

新增/修改（均在 `resume_agent/api/`）：

- `GET /fact-bases/{id}/questionnaire` → 当前章节进度 + 下一步问题卡片
- `POST /fact-bases/{id}/questionnaire/answer` {step_id, value} → 更新后档案 + 下一卡片
- `POST /fact-bases/{id}/questionnaire/skip` {step_id}
- `POST /fact-bases/{id}/educations`（新增教育条目，含课程）
- `PATCH /fact-bases/{id}/educations/{education_id}`、`DELETE ...`
- `PATCH /fact-bases/{id}/profile`（扩展 skills 字段）
- `PATCH /fact-bases/{id}/experiences/{experience_id}`（类型、年月、技能链接）
- `POST /fact-bases/{id}/experiences/{experience_id}/snippets/generate` → 片段卡候选
- `POST /versions/{id}/summary-options/generate` → 自我评价备选
- `PUT /versions/{id}/summary` {text} → 确认写入 selected_summary
- `POST /versions/{id}/snippets`、`DELETE /versions/{id}/snippets/{snippet_id}`
- 修改 `POST /sessions/{id}/answer` 返回组合 payload（事实 + 预写问句）
- `GET /capabilities` 扩展：course_recommendation、summary_options、snippet_writer 能力标志

## 11. 前端结构

- 章节导航替代现有 4 个 tabs（访谈/事实库/JD/工具）：
  - 问答主面板：问题卡片流（按 §5 类型渲染）、章节进度
  - 片段面板：片段卡 + 拖拽源
  - 版本面板（原 JD 定制收敛于此）、工具面板保留
- 现有 `app.js` 的 generation gate / serial executor / 会话过渡机制全部复用，新增问卷状态与拖拽状态并入同一套并发防护。
- 年月选择器：无依赖原生组件（弹层 + 年/月列），仅 zh 文案。
- 预览 iframe 同源，拖拽事件在 iframe document 上处理（现有 `sandbox="allow-same-origin"` 已支持）。

## 12. 分阶段实施

每阶段独立可验证、测试通过后进入下一阶段：

| 阶段 | 内容 | 验收 |
|---|---|---|
| P1 提速 | 合并调用（事实+预判下一问）、前端乐观渲染 | 每轮 ≤1 个 LLM 等待点；离线无回归；现有评测集通过 |
| P2 问卷引擎 | 问卷状态机、6 类问题卡片、章节导航、年月选择器；数据模型落地 | 全章节问答走通；刷新恢复；旧档案兼容 |
| P3 章节内容 | 教育问答+课程词典推荐、经历类型/年月、技能候选；中文渲染接入教育/技能章节 | 中文简历含教育/技能章节；导出含新章节 |
| P4 自我评价 | 备选生成（LLM+离线模板）、grounding 校验、勾选确认、渲染 | 备选严格基于已确认内容（无幻觉断言） |
| P5 卡片拖拽 | 片段卡生成、素材面板、落点、snippets 合并渲染、删除/去重 | 拖入即写、可删、预览导出一致 |

## 13. 测试与评测

- **Python 单测**（延续 tests/ 结构）：
  - 问卷状态机：顺序、跳过、回退、重复回答覆盖、完成度推导
  - YearMonth 校验、起止年月不变量（起 ≤ 止）
  - 课程词典：专业命中、默认勾选集合、AI 推荐合并与降级
  - 合并调用：payload 校验、预判一致路径 0 调用、不一致路径补调用、离线降级
  - 自我评价 grounding：备选不得含事实库外数字/实体（构造反例断言拒绝）
  - 渲染：中文章节顺序、类型分组、片段模式/自动模式切换、custom_sections 合并、去重
- **浏览器测试**（tests/web/*.test.mjs 模式）：6 类问题卡片交互、年月选择器、章节导航跳转、拖拽落点与去重提示、片段删除回退自动模式
- **合成评测集**（evaluation/）：扩展中文选项问答路径、课程推荐、自我评价约束、片段卡溯源

## 14. 风险与边界

- **LLM 依赖**：所有生成类节点均有确定性降级（词典/模板/手动输入），离线可用性不回退。
- **拖拽与手工编辑冲突**：通过「编辑模式停用拖拽」规则规避双写；spec 不引入撤销栈（YAGNI，删除即恢复）。
- **自我评价幻觉**：以 grounding 校验 + 候选确认制兜底；不承诺自动翻译（事实仍为用户原话）。
- **旧数据兼容**：所有新字段带默认值；旧经历 start/end 自由字符串保留渲染，新写入走年月校验。
- **日/英范围**：本阶段仅中文完善；日/英保持现状（README 限制条目同步更新）。
