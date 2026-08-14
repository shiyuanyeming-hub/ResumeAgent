# 向导式问答重构（中文优先）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 ResumeAgent 升级为中文优先的向导式问答简历工作台：合并 LLM 调用提速、选项式问卷引擎（教育/经历/年月选择器/课程推荐/技能）、自我评价备选勾选、片段卡拖拽写入预览，全部保留离线降级。

**Architecture:** 沿用「确定性骨架 + LLM 出候选」：问卷状态机（章节顺序/问题卡片/校验）与渲染全部确定性代码；LLM 只在生成类节点出候选（事实提炼、课程推荐、自我评价备选、片段润色），用户确认才生效。后端 FastAPI + SQLite JSON payload 快照；前端原生 ES modules（无构建步骤）。

**Tech Stack:** Python 3.10+ / pydantic v2 / FastAPI / SQLite；前端 vanilla JS + HTML5 drag & drop；pytest + node:test。

**Spec:** `docs/superpowers/specs/2026-08-14-resume-wizard-design.md`（已批准，commit `a20e80d`）。

## Global Constraints

- 本阶段只完善中文简历；日/英渲染器与模板一律不改动。
- LLM 产物一律是**候选**：事实提炼、课程推荐、自我评价备选、片段润色都必须经用户确认/勾选后才写入；离线时全部有确定性降级。
- 存储是 JSON payload 快照（`fact_bases`/`resume_versions`/`interview_sessions` 表）：所有新增模型字段必须带默认值，**不得**引入会拒绝旧 payload 的必填校验；旧数据可加载是硬约束。
- 与 spec 的一处偏差：`Experience.type` 默认值取 `WORK`（spec 写 PROJECT）。原因：旧数据没有 type，取 WORK 可让旧经历继续渲染在「实习/工作经历」节，保持既有预览不变。
- 经验证的年月格式 `YYYY-MM` 按字典序比较即可判断先后（字符串比较），不得引入日期库。
- 测试命令：`.venv/bin/python -m pytest -q`（后端）、`node --test tests/web/*.test.mjs`（前端纯函数）。
- 提交信息沿用仓库风格：`feat:`/`fix:`/`docs:` + 中文短句；每个任务独立提交。
- 前端并发防护沿用 `app.js` 现有的 generation gate / `createSerialExecutor` / `sessionTransitionGate`，新交互必须并入同一套防护，不得另起炉灶。

## File Structure

**新建：**
- `resume_agent/domain/year_month.py` — 年月格式校验与比较（`YEAR_MONTH_RE`、`is_year_month`、`year_month_le`）
- `resume_agent/domain/course_catalog.py` — 内置专业→核心课程词典（P3）
- `resume_agent/domain/grounding.py` — 数字提取与自我评价无幻觉校验（P4）
- `resume_agent/domain/questionnaire_steps.py` — 章节顺序与步骤定义（P2）
- `resume_agent/application/questionnaire.py` — 问卷引擎 + 问卷服务（P2）
- `resume_agent/agents/specialists.py` — 课程/自我评价/片段三类生成 Agent（P3/P4/P5）
- `resume_agent/web/questionnaire.js` — 前端纯函数（卡片答案 payload 构建、进度计算、拖拽序列化、去重判断），可被 node:test 覆盖
- `tests/web/questionnaire.test.mjs` — 上述纯函数的 node 测试

**修改：**
- `resume_agent/domain/models.py` — FactProposal/InterviewSession/Education/Experience/CandidateProfile/CareerFactBase/VersionSnippet/ResumeVersion
- `resume_agent/domain/quality.py` — 档案级完整度评估
- `resume_agent/application/ports.py` — FactAuditAgent 签名、QuestionnaireRepository 端口
- `resume_agent/application/interview_service.py` — 合并调用（预判维度、pending 下一问）
- `resume_agent/application/fact_base_service.py` — 教育 CRUD、经历更新
- `resume_agent/application/version_service.py` — 自我评价、片段增删
- `resume_agent/agents/prompts.py`、`resume_agent/agents/mentor.py`、`resume_agent/agents/unavailable.py`、`resume_agent/agents/runtime.py`、`resume_agent/agents/hello_agents_adapter.py` — Agent 契约与能力装配
- `resume_agent/infrastructure/sqlite_repositories.py` — 问卷状态表与仓库
- `resume_agent/api/schemas.py`、`resume_agent/api/app.py` — 新端点与请求模型
- `resume_agent/rendering/models.py`、`resume_agent/rendering/renderer.py` — 中文新章节、类型分组、片段模式、拖拽锚点
- `resume_agent/web/api.js`、`resume_agent/web/app.js`、`resume_agent/web/index.html`、`resume_agent/web/styles.css`、`resume_agent/web/workbench-state.js` — 问卷 UI、章节导航、拖拽
- `tests/fakes.py`、`tests/test_models.py`、`tests/test_question_planner.py` 等既有测试与新增测试
- `README.md` — 功能与限制条目更新（最后任务）

---

### Task 1: 合并调用契约 —— 领域字段与 Agent 接口

**Files:**
- Modify: `resume_agent/domain/models.py`（FactProposal、InterviewSession）
- Modify: `resume_agent/application/ports.py`（FactAuditAgent）
- Modify: `resume_agent/agents/prompts.py`（FACT_AUDIT_PROMPT）
- Modify: `resume_agent/agents/mentor.py`（FactAuditPayload、StructuredFactAuditAgent）
- Modify: `resume_agent/agents/unavailable.py`（UnavailableFactAuditAgent）
- Modify: `tests/fakes.py`（StubAuditAgent）
- Test: `tests/test_models.py`、`tests/test_mentor_agents.py`

**Interfaces:**
- Consumes: 无（第一个任务）
- Produces（后续任务依赖）：
  - `FactProposal.next_question: str = ""`
  - `InterviewSession.pending_next_text: str = ""`、`InterviewSession.pending_next_dimension: Optional[QualityDimension] = None`
  - `FactAuditAgent.propose(message, session, base, predicted_dimension: Optional[QualityDimension] = None) -> FactProposal`

- [ ] **Step 1: 写失败测试（模型默认值）**

在 `tests/test_models.py` 末尾追加：

```python
def test_fact_proposal_defaults_next_question():
    proposal = FactProposal(
        fact_base_revision=0,
        experience_id=uuid4(),
        dimension=QualityDimension.ACTION,
        values=[FactValue(text="搭建了看板")],
    )
    assert proposal.next_question == ""


def test_interview_session_pending_next_defaults():
    session = InterviewSession(fact_base_id=uuid4())
    assert session.pending_next_text == ""
    assert session.pending_next_dimension is None
```

（确认文件顶部已 `from uuid import uuid4` 并导入 `InterviewSession`，若缺则补 import。）

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_models.py -q`
Expected: FAIL（`FactProposal` 没有 `next_question` 属性 / `InterviewSession` 没有 `pending_next_text`）

- [ ] **Step 3: 实现模型字段**

`resume_agent/domain/models.py`：

```python
class FactProposal(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    fact_base_revision: int = Field(ge=0)
    experience_id: UUID
    dimension: QualityDimension
    values: List[FactValue] = Field(min_length=1)
    rationale: str = ""
    next_question: str = ""          # 新增：预写的下一轮问句（可为空）
    created_at: datetime = Field(default_factory=utc_now)
```

```python
class InterviewSession(BaseModel):
    ...
    current_question: Optional[InterviewQuestion] = None
    pending_next_text: str = ""                              # 新增
    pending_next_dimension: Optional[QualityDimension] = None  # 新增
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_models.py -q`
Expected: PASS

- [ ] **Step 5: 更新端口签名**

`resume_agent/application/ports.py`：

```python
class FactAuditAgent(Protocol):
    def propose(
        self,
        message: str,
        session: InterviewSession,
        base: CareerFactBase,
        predicted_dimension: Optional[QualityDimension] = None,
    ) -> FactProposal: ...
```

（文件顶部补 `from typing import List, Optional, Protocol`，若已有 `List` 则只补 `Optional`；`QualityDimension` 已导入。）

`resume_agent/agents/unavailable.py`：

```python
class UnavailableFactAuditAgent:
    def propose(self, message, session, base, predicted_dimension=None):
        raise AgentUnavailableError(
            "fact-audit agent is not configured; connect a HelloAgents agent first"
        )
```

`tests/fakes.py` 的 `StubAuditAgent`：

```python
class StubAuditAgent:
    def propose(
        self,
        message: str,
        session: InterviewSession,
        base: CareerFactBase,
        predicted_dimension=None,
    ) -> FactProposal:
        return FactProposal(
            fact_base_revision=base.revision,
            experience_id=session.active_experience_id,
            dimension=QualityDimension.ACTION,
            values=[FactValue(text=message)],
            next_question=f"下一轮请补充{predicted_dimension.value}？" if predicted_dimension else "",
        )
```

- [ ] **Step 6: 写失败测试（结构化审计产出 next_question）**

在 `tests/test_mentor_agents.py` 末尾追加（文件已导入 `StructuredFactAuditAgent`、`run_structured` 等，若无则参照既有用例补 import）：

```python
from uuid import uuid4

from resume_agent.agents.mentor import StructuredFactAuditAgent
from resume_agent.domain.models import (
    CareerFactBase, InterviewSession, QualityDimension,
)


class QueueRunner:
    def __init__(self, responses):
        self.responses = list(responses)

    def run(self, prompt):
        return self.responses.pop(0)


def make_session_and_base():
    base = CareerFactBase()
    experience = base.add_experience("星河科技", "数据分析实习生")
    session = InterviewSession(
        fact_base_id=base.id, active_experience_id=experience.id
    )
    return session, base


def test_structured_audit_returns_next_question():
    runner = QueueRunner([
        '{"dimension":"action","values":[{"text":"搭建了留存看板"}],'
        '"rationale":"","next_question":"那这个看板多久更新一次？"}',
    ])
    agent = StructuredFactAuditAgent(runner)
    session, base = make_session_and_base()
    proposal = agent.propose(
        "我搭建了留存看板", session, base,
        predicted_dimension=QualityDimension.RESULT,
    )
    assert proposal.next_question == "那这个看板多久更新一次？"
    assert proposal.dimension is QualityDimension.ACTION


def test_structured_audit_rejects_next_question_with_two_marks():
    from resume_agent.agents.structured import AgentOutputError
    runner = QueueRunner([
        '{"dimension":"action","values":[{"text":"a"}],'
        '"next_question":"第一问？第二问？"}',
        '{"dimension":"action","values":[{"text":"a"}],"next_question":""}',
    ])
    agent = StructuredFactAuditAgent(runner)
    session, base = make_session_and_base()
    proposal = agent.propose("a", session, base, predicted_dimension=QualityDimension.RESULT)
    assert proposal.next_question == ""
```

- [ ] **Step 7: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_mentor_agents.py -q`
Expected: FAIL（`FactAuditPayload` 无 `next_question`；`propose` 不接受 `predicted_dimension`）

- [ ] **Step 8: 实现结构化审计变更**

`resume_agent/agents/prompts.py`，替换 `FACT_AUDIT_PROMPT` 末尾规则：

```python
FACT_AUDIT_PROMPT = """你是简历事实审计 Agent。你的任务是从用户本轮回答中提出候选事实，不是替用户润色简历。

严格规则：
1. 只提取用户明确表达的信息，禁止补全常识、推测结果或编造数字。
2. 区分用户个人行动与团队整体成果；没有说明个人贡献时，不得归到个人名下。
3. 数字只有在用户明确确认时才能标为 unverified；用户使用“大约、差不多、可能”等表达时必须标为 estimated。
4. 敏感性 sensitive 与可信度是两个独立字段。
5. specificity 仅可为 present 或 concrete；含明确步骤、工具、数字、频率、对象或产物时可为 concrete。
6. confidence 仅可为 unverified 或 estimated。Agent 没有确认事实的权限。
7. 本轮只归入最主要的一个维度：context、responsibility、action、method、result、evidence。
8. 只输出一个 JSON 对象，不要输出解释性文字。
9. 若提供了「预判下一维度」，同时输出 next_question 字段：针对该维度写下一轮唯一的问题（只能有一个问号）；未提供预判维度时 next_question 输出空字符串。
"""
```

`resume_agent/agents/mentor.py`：

```python
class FactAuditPayload(BaseModel):
    dimension: QualityDimension
    values: List[ProposedFactPayload] = Field(min_length=1)
    rationale: str = ""
    next_question: str = ""

    @field_validator("next_question")
    @classmethod
    def validate_single_next_question(cls, value: str) -> str:
        stripped = value.strip()
        if stripped and stripped.count("?") + stripped.count("？") != 1:
            raise ValueError("next_question must contain exactly one question mark")
        return stripped
```

`StructuredFactAuditAgent.propose` 改为：

```python
    def propose(
        self,
        message: str,
        session: InterviewSession,
        base: CareerFactBase,
        predicted_dimension: Optional[QualityDimension] = None,
    ) -> FactProposal:
        if session.active_experience_id is None:
            raise ValueError("fact audit requires an active experience")
        experience = base.get_experience(session.active_experience_id)
        predicted_text = predicted_dimension.value if predicted_dimension else "无"
        prompt = (
            f"{FACT_AUDIT_PROMPT}\n"
            f"目标岗位：{base.target.model_dump_json()}\n"
            f"当前经历：{experience.model_dump_json()}\n"
            f"用户本轮回答：{message}\n"
            f"预判下一维度：{predicted_text}\n"
            "输出字段：dimension、values、rationale、next_question。"
        )
        payload = run_structured(self.runner, prompt, FactAuditPayload)
        source_ids = [
            item.id for item in session.messages[-1:] if item.role == "user"
        ]
        values = [
            FactValue(
                text=value.text,
                confidence=ConfidenceStatus(value.confidence),
                specificity=value.specificity,
                sensitive=value.sensitive,
                source_message_ids=source_ids,
            )
            for value in payload.values
        ]
        return FactProposal(
            fact_base_revision=base.revision,
            experience_id=session.active_experience_id,
            dimension=payload.dimension,
            values=values,
            rationale=payload.rationale,
            next_question=payload.next_question,
        )
```

（`mentor.py` 顶部 import 已有 `Optional`？若没有，`from typing import List, Literal` 改为 `from typing import List, Literal, Optional`。）

- [ ] **Step 9: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_mentor_agents.py tests/test_models.py tests/test_interview_service.py tests/test_api_interviews.py -q`
Expected: PASS（Stub 已同步签名；其余未动）

- [ ] **Step 10: 提交**

```bash
git add resume_agent/domain/models.py resume_agent/application/ports.py resume_agent/agents/prompts.py resume_agent/agents/mentor.py resume_agent/agents/unavailable.py tests/fakes.py tests/test_models.py tests/test_mentor_agents.py
git commit -m "feat: carry predicted next question through fact audit contract"
```

---

### Task 2: InterviewService 预判与 pending 消费

**Files:**
- Modify: `resume_agent/application/interview_service.py`
- Test: `tests/test_interview_service.py`

**Interfaces:**
- Consumes: Task 1 的 `FactProposal.next_question`、`InterviewSession.pending_next_*`、`propose(..., predicted_dimension=...)`
- Produces（Task 3 依赖）：`answer()` 在提案中携带 `next_question`；`confirm()` 在预判命中时零 LLM 调用返回问句；`reject()` 清空 pending

- [ ] **Step 1: 写失败测试**

在 `tests/test_interview_service.py` 末尾追加（文件已导入 `InterviewService`、fakes 中的仓库；补需要的 import）：

```python
from resume_agent.application.interview_service import InterviewService
from resume_agent.application.question_planner import QuestionPlanner
from resume_agent.domain.models import (
    CareerFactBase, FactProposal, FactValue, InterviewQuestion,
    InterviewSession, QualityDimension,
)
from tests.fakes import (
    InMemoryFactBaseRepository, InMemorySessionRepository,
)


class RecordingAudit:
    def __init__(self):
        self.predicted = []

    def propose(self, message, session, base, predicted_dimension=None):
        self.predicted.append(predicted_dimension)
        return FactProposal(
            fact_base_revision=base.revision,
            experience_id=session.active_experience_id,
            dimension=QualityDimension.ACTION,
            values=[FactValue(text=message)],
            next_question="这条行动的结果是什么？",
        )


class RecordingWriter:
    def __init__(self):
        self.calls = 0

    def write(self, plan, experience, target):
        self.calls += 1
        return f"请补充{plan.dimension.value}。"


def interview_fixture():
    base = CareerFactBase()
    experience = base.add_experience("星河科技", "实习生")
    session = InterviewSession(
        fact_base_id=base.id, active_experience_id=experience.id
    )
    audit = RecordingAudit()
    writer = RecordingWriter()
    service = InterviewService(
        InMemoryFactBaseRepository([base]),
        InMemorySessionRepository([session]),
        audit,
        writer,
        QuestionPlanner(),
    )
    return service, session, audit, writer


def test_answer_receives_predicted_dimension_excluding_asked():
    service, session, audit, _ = interview_fixture()
    session.current_question = InterviewQuestion(
        dimension=QualityDimension.ACTION, text="你做了什么？", priority=1.0, escalation="direct"
    )
    service.sessions.save(session)
    service.answer(session.id, "我搭了看板")
    assert audit.predicted == [QualityDimension.RESULT] or audit.predicted[0] != QualityDimension.ACTION
    assert audit.predicted[0] is not None


def test_confirm_uses_prewritten_question_without_writer_call():
    service, session, _, writer = interview_fixture()
    service.answer(session.id, "我搭了看板")
    stored = service.get_session(session.id)
    proposal = list(stored.pending_proposals.values())[0]
    turn = service.confirm(stored.id, proposal.id)
    assert turn.question is not None
    assert turn.question.text == "这条行动的结果是什么？"
    assert writer.calls == 0
    updated = service.get_session(session.id)
    assert updated.pending_next_text == ""
    assert updated.pending_next_dimension is None


def test_reject_clears_pending_next_question():
    service, session, _, writer = interview_fixture()
    service.answer(session.id, "我搭了看板")
    stored = service.get_session(session.id)
    proposal = list(stored.pending_proposals.values())[0]
    service.reject(stored.id, proposal.id)
    service.next_question(session.id)
    assert writer.calls == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_interview_service.py -q`
Expected: FAIL（`propose` 收到多余参数 / `confirm` 返回的问题来自 writer 而非预写 / `reject` 后仍使用预写）

- [ ] **Step 3: 实现服务变更**

`resume_agent/application/interview_service.py`：

`answer()` 中替换 audit 调用与 pending 写入：

```python
        session.messages.append(InterviewMessage(role="user", content=message))
        session.current_question = None
        session.updated_at = utc_now()
        self.sessions.save(session)
        predicted = self._predict_next_dimension(session, base, asked_dimension)
        proposal = self.audit_agent.propose(
            message, session, base, predicted_dimension=predicted
        )
        if proposal.experience_id != session.active_experience_id:
            raise ValueError("agent proposal targeted a different experience")
        if proposal.fact_base_revision != base.revision:
            raise ValueError("agent proposal used a stale fact-base revision")

        if (
            asked_dimension is not None
            and proposal.dimension is not asked_dimension
        ):
            session.attempts[asked_dimension] = (
                session.attempts.get(asked_dimension, 0) + 1
            )
        session.pending_proposals[proposal.id] = proposal
        session.pending_next_text = proposal.next_question
        session.pending_next_dimension = predicted
        session.updated_at = utc_now()
        self.sessions.save(session)
        return InterviewTurn(proposal=proposal)
```

新增方法（放在 `answer` 之后）：

```python
    def _predict_next_dimension(
        self,
        session: InterviewSession,
        base: CareerFactBase,
        asked_dimension: Optional[QualityDimension],
    ) -> Optional[QualityDimension]:
        if session.active_experience_id is None:
            return None
        experience = base.get_experience(session.active_experience_id)
        history = QuestionHistory(
            attempts=session.attempts,
            skipped=session.skipped_dimensions,
        )
        ranked = self.planner.rank(experience, PlanningSignals(), history)
        candidates = {
            dimension: priority
            for dimension, priority in ranked.items()
            if dimension is not asked_dimension
        }
        if not candidates:
            return None
        return max(candidates, key=candidates.get)
```

`_make_question()` 中替换问题文本来源：

```python
        if plan is None:
            return None
        if (
            session.pending_next_text
            and plan.dimension == session.pending_next_dimension
        ):
            text = session.pending_next_text
        else:
            text = self.question_writer.write(plan, experience, base.target).strip()
            if not text:
                raise ValueError("question writer returned an empty question")
        session.pending_next_text = ""
        session.pending_next_dimension = None
        return MentorQuestion(
            dimension=plan.dimension,
            text=text,
            priority=plan.priority,
            escalation=plan.escalation,
        )
```

`reject()` 中在删除提案后清空 pending：

```python
        del session.pending_proposals[proposal_id]
        session.pending_next_text = ""
        session.pending_next_dimension = None
        session.updated_at = utc_now()
```

（`PlanningSignals`、`QuestionHistory` 已在文件顶部导入，无需改 import。）

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_interview_service.py tests/test_api_interviews.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add resume_agent/application/interview_service.py tests/test_interview_service.py
git commit -m "feat: consume prewritten next question on confirm path"
```

---

### Task 3: 前端乐观渲染与「提炼中」状态

**Files:**
- Modify: `resume_agent/web/app.js`（`submitAnswer`）
- Modify: `resume_agent/web/styles.css`（typing 指示样式）
- Test: `tests/web/api.test.mjs` 无需改（API 层无契约变化，仅确认 `answer` 返回值含 `proposal.next_question` 时前端渲染——见 Step 1 的说明）

**Interfaces:**
- Consumes: Task 2 的 `answer` 响应（`proposal` 带 `next_question`）、`getSession` 返回 `pending_next_text`
- Produces: 发送回答后即时可见用户消息与「导师正在提炼…」指示；结果到达后单次 `renderConversation()` 覆盖

- [ ] **Step 1: 写失败测试（会话字段透传检查）**

在 `tests/web/api.test.mjs` 末尾追加：

```js
test("answer returns proposal with optional next_question", async () => {
  const api = createApi(async (url, init) => {
    if (url.endsWith("/answers")) {
      return new Response(JSON.stringify({
        proposal: {
          id: "p-1",
          dimension: "action",
          values: [{ text: "搭建看板" }],
          next_question: "结果是什么？",
        },
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    throw new Error(`unexpected url ${url}`);
  });

  const turn = await api.answer("s-1", "我搭了看板");
  assert.equal(turn.proposal.next_question, "结果是什么？");
});
```

- [ ] **Step 2: 运行确认通过（该测试验证契约，不涉及实现代码）**

Run: `node --test tests/web/api.test.mjs`
Expected: PASS（`createApi.answer` 已存在，透传 JSON）

- [ ] **Step 3: 实现乐观渲染**

`resume_agent/web/app.js` 的 `submitAnswer` 中，在 `try` 块内、`const session = await ensureSession(context);` 之后、`await api.answer(session.id, message);` 之前插入：

```javascript
    const messagesBox = byId("chat-messages");
    messagesBox.append(element("div", "message user-message", message));
    const typing = element("div", "message assistant-message typing-message", "导师正在提炼…");
    typing.setAttribute("aria-live", "polite");
    messagesBox.append(typing);
    messagesBox.scrollTop = messagesBox.scrollHeight;
```

（`renderConversation()` 在结果到达后会整体重建 `chat-messages`，typing 节点随之消失，无需手动移除。）

`resume_agent/web/styles.css` 末尾追加：

```css
.typing-message {
  opacity: 0.75;
}
.typing-message::after {
  content: "";
  display: inline-block;
  width: 1em;
  text-align: left;
  animation: typing-dots 1.2s steps(4, end) infinite;
}
@keyframes typing-dots {
  0% { content: ""; }
  25% { content: "."; }
  50% { content: ".."; }
  75% { content: "..."; }
}
```

- [ ] **Step 4: 人工验证**

启动 `.venv/bin/uvicorn resume_agent.api.main:app --reload`，打开 <http://127.0.0.1:8000/>：发送回答后立即出现自己的消息与「导师正在提炼…」；配置模型时提案返回后正常渲染候选事实卡。

- [ ] **Step 5: 回归并提交**

Run: `.venv/bin/python -m pytest -q` 和 `node --test tests/web/*.test.mjs`
Expected: 全绿

```bash
git add resume_agent/web/app.js resume_agent/web/styles.css tests/web/api.test.mjs
git commit -m "feat: optimistic chat rendering while mentor refines"
```

### Task 4: 领域模型扩展（年月、教育、类型、技能、片段、自我评价字段）

**Files:**
- Create: `resume_agent/domain/year_month.py`
- Modify: `resume_agent/domain/models.py`
- Modify: `resume_agent/domain/quality.py`（档案级完整度）
- Test: `tests/test_models.py`、`tests/test_quality.py`

**Interfaces:**
- Consumes: 无
- Produces（后续任务依赖）：
  - `is_year_month(value: str) -> bool`、`year_month_le(start: str, end: str) -> bool`
  - `ExperienceType`（internship/work/project/campus）；`Experience.type` 默认 `WORK`
  - `Education(id, school, major, degree, start, end, core_courses, created_at, updated_at)`
  - `CandidateProfile.skills: List[str]`；`CareerFactBase.educations: List[Education]`
  - `VersionSnippet(id, text, source_fact_ids, created_at)`
  - `ResumeVersion.summary_options / selected_summary / snippets / custom_sections`
  - `evaluate_profile_completeness(base, selected_summary="") -> ProfileCompleteness`

- [ ] **Step 1: 写失败测试**

`tests/test_models.py` 末尾追加：

```python
from resume_agent.domain.models import Education, ExperienceType, VersionSnippet
from resume_agent.domain.year_month import is_year_month, year_month_le


def test_year_month_helpers():
    assert is_year_month("2023-09")
    assert not is_year_month("2023-9")
    assert not is_year_month("2023/09")
    assert not is_year_month("2023-13")
    assert year_month_le("2023-09", "2024-01")


def test_experience_defaults_to_work_type():
    base = CareerFactBase()
    experience = base.add_experience("星河科技", "实习生")
    assert experience.type is ExperienceType.WORK


def test_education_validates_year_month_fields():
    with pytest.raises(ValidationError):
        Education(school="某大学", start="2023-9")


def test_version_carries_snippet_and_summary_fields():
    version = ResumeVersion(fact_base_id=uuid4(), name="默认版本")
    assert version.summary_options == []
    assert version.selected_summary == ""
    assert version.snippets == {}
    assert version.custom_sections == []


def test_version_snippet_requires_text():
    with pytest.raises(ValidationError):
        VersionSnippet(text=" ")
```

（若文件未导入 `pytest` 与 `ValidationError`，在顶部补 `import pytest` 和 `from pydantic import ValidationError`；`CareerFactBase`、`ResumeVersion` 已导入则复用。）

`tests/test_quality.py` 末尾追加：

```python
from resume_agent.domain.models import (
    CareerFactBase, Education, QualityDimension, FactValue, ConfidenceStatus,
)
from resume_agent.domain.quality import evaluate_profile_completeness


def test_profile_completeness_zh_sections():
    base = CareerFactBase()
    report = evaluate_profile_completeness(base)
    assert report.sections == {
        "profile": False, "target": False, "education": False,
        "experience": False, "skills": False, "summary": False,
    }
    assert report.complete is False


def test_profile_completeness_reflects_filled_sections():
    base = CareerFactBase()
    base.profile.name = "王明"
    base.profile.email = "wang@example.com"
    base.profile.phone = "138-0000-0000"
    base.target.role = "数据分析师"
    base.educations.append(Education(school="某大学", major="统计学", start="2020-09"))
    experience = base.add_experience("星河科技", "实习生")
    experience.statements[QualityDimension.ACTION] = [
        FactValue(text="搭建看板", confidence=ConfidenceStatus.CONFIRMED)
    ]
    experience.statements[QualityDimension.RESULT] = [
        FactValue(text="看板被团队采用", confidence=ConfidenceStatus.CONFIRMED)
    ]
    base.profile.skills = ["SQL"]
    report = evaluate_profile_completeness(base, selected_summary="稳重可靠。")
    assert report.sections == {
        "profile": True, "target": True, "education": True,
        "experience": True, "skills": True, "summary": True,
    }
    assert report.complete is True
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_models.py tests/test_quality.py -q`
Expected: FAIL（`year_month` 模块不存在 / `Education` 不存在等）

- [ ] **Step 3: 实现年月模块与模型扩展**

创建 `resume_agent/domain/year_month.py`：

```python
"""Year-month value helpers for resume periods."""

import re

YEAR_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def is_year_month(value: str) -> bool:
    """Return True when value matches YYYY-MM (lexicographic == chronological)."""
    return bool(YEAR_MONTH_RE.fullmatch(value))


def year_month_le(start: str, end: str) -> bool:
    """Compare two valid YYYY-MM strings; returns start <= end."""
    return start <= end
```

`resume_agent/domain/models.py` 修改（顶部 import 区补 `from resume_agent.domain.year_month import is_year_month`）：

新增枚举（放在 `QualityDimension` 之后）：

```python
class ExperienceType(str, Enum):
    INTERNSHIP = "internship"
    WORK = "work"
    PROJECT = "project"
    CAMPUS = "campus"
```

`Experience` 增加字段（放在 `statements` 之后）：

```python
    type: ExperienceType = ExperienceType.WORK
```

`CandidateProfile` 增加：

```python
    skills: List[str] = Field(default_factory=list)
```

新增 `Education`（放在 `Experience` 之后）：

```python
class Education(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    school: str
    major: str = ""
    degree: str = ""
    start: str = ""
    end: Optional[str] = None
    core_courses: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("school")
    @classmethod
    def validate_school(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("school must not be empty")
        return stripped

    @field_validator("start")
    @classmethod
    def validate_start(cls, value: str) -> str:
        if value and not is_year_month(value):
            raise ValueError("start must be YYYY-MM")
        return value

    @field_validator("end")
    @classmethod
    def validate_end(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value and not is_year_month(value):
            raise ValueError("end must be YYYY-MM or empty")
        return value
```

`CareerFactBase` 增加：

```python
    educations: List[Education] = Field(default_factory=list)
```

新增 `VersionSnippet`（放在 `ResumeVersion` 之前）：

```python
class VersionSnippet(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    text: str
    source_fact_ids: List[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("snippet text must not be empty")
        return stripped
```

`ResumeVersion` 增加字段（放在 `manual_html` 之后、`base_revision` 之前）：

```python
    summary_options: List[str] = Field(default_factory=list)
    selected_summary: str = ""
    snippets: Dict[UUID, List[VersionSnippet]] = Field(default_factory=dict)
    custom_sections: List[VersionSnippet] = Field(default_factory=list)
```

- [ ] **Step 4: 实现完整度评估**

`resume_agent/domain/quality.py`：既有 import 行补 `CareerFactBase`，追加：

```python
class ProfileCompleteness(BaseModel):
    model_config = ConfigDict(frozen=True)

    sections: Dict[str, bool]
    complete: bool


def evaluate_profile_completeness(
    base: CareerFactBase,
    selected_summary: str = "",
) -> ProfileCompleteness:
    sections = {
        "profile": bool(base.profile.name and base.profile.email and base.profile.phone),
        "target": bool(base.target.role),
        "education": any(
            education.school and education.major and education.start
            for education in base.educations
        ),
        "experience": any(
            evaluate_experience(experience).passes_gate
            for experience in base.experiences
        ),
        "skills": bool(base.profile.skills),
        "summary": bool(selected_summary),
    }
    return ProfileCompleteness(sections=sections, complete=all(sections.values()))
```

- [ ] **Step 5: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_models.py tests/test_quality.py tests/test_resume_renderer.py tests/test_sqlite_repositories.py -q`
Expected: PASS（旧 payload 加载不受影响——所有新字段有默认值）

- [ ] **Step 6: 提交**

```bash
git add resume_agent/domain/year_month.py resume_agent/domain/models.py resume_agent/domain/quality.py tests/test_models.py tests/test_quality.py
git commit -m "feat: add education, experience type, skills and snippet domain models"
```

---

### Task 5: 问卷状态存储

**Files:**
- Modify: `resume_agent/domain/models.py`（`QuestionnaireState`）
- Modify: `resume_agent/application/ports.py`（`QuestionnaireRepository`）
- Modify: `resume_agent/infrastructure/sqlite_repositories.py`（表 + 仓库）
- Modify: `tests/fakes.py`（`InMemoryQuestionnaireRepository`）
- Test: `tests/test_sqlite_repositories.py`

**Interfaces:**
- Consumes: Task 4
- Produces：
  - `QuestionnaireState(fact_base_id, skipped, completed_sections, edited_education_id, edited_experience_id, updated_at)`
  - `QuestionnaireRepository.get(fact_base_id) -> QuestionnaireState`（不存在时 `KeyError`）、`.save(state)`
  - `SQLiteQuestionnaireRepository(store)`（构造参数与现有 SQLite 仓库一致）

- [ ] **Step 1: 写失败测试**

`tests/test_sqlite_repositories.py` 末尾追加：

```python
from resume_agent.domain.models import QuestionnaireState
from resume_agent.infrastructure.sqlite_repositories import SQLiteQuestionnaireRepository


def test_questionnaire_state_roundtrip(tmp_path):
    from resume_agent.infrastructure.sqlite_repositories import SQLiteStore
    store = SQLiteStore(tmp_path / "resume-agent.db")
    repository = SQLiteQuestionnaireRepository(store)
    fact_base_id = uuid4()
    with pytest.raises(KeyError):
        repository.get(fact_base_id)
    state = QuestionnaireState(fact_base_id=fact_base_id)
    state.skipped.append("profile:links")
    state.completed_sections.append("education")
    repository.save(state)
    loaded = repository.get(fact_base_id)
    assert loaded.skipped == ["profile:links"]
    assert loaded.completed_sections == ["education"]
```

（`uuid4`、`pytest` 若未导入则补；`tmp_path` 用法与文件内既有用例一致。）

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_sqlite_repositories.py -q`
Expected: FAIL（`QuestionnaireState` 不存在）

- [ ] **Step 3: 实现状态模型与仓库**

`resume_agent/domain/models.py` 追加（放在 `InterviewSession` 之后）：

```python
class QuestionnaireState(BaseModel):
    fact_base_id: UUID
    skipped: List[str] = Field(default_factory=list)
    completed_sections: List[str] = Field(default_factory=list)
    edited_education_id: Optional[UUID] = None
    edited_experience_id: Optional[UUID] = None
    updated_at: datetime = Field(default_factory=utc_now)
```

`resume_agent/application/ports.py`：import 行补 `QuestionnaireState`，追加：

```python
class QuestionnaireRepository(Protocol):
    def get(self, fact_base_id: UUID) -> QuestionnaireState: ...

    def save(self, state: QuestionnaireState) -> None: ...
```

`resume_agent/infrastructure/sqlite_repositories.py`：

`SQLiteStore._initialize` 的 `executescript` 中追加：

```sql
                CREATE TABLE IF NOT EXISTS questionnaires (
                    fact_base_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
```

文件末尾新增：

```python
class SQLiteQuestionnaireRepository:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def get(self, fact_base_id: UUID) -> QuestionnaireState:
        with self.store.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM questionnaires WHERE fact_base_id = ?",
                (str(fact_base_id),),
            ).fetchone()
        if row is None:
            raise KeyError(f"questionnaire state not found: {fact_base_id}")
        return QuestionnaireState.model_validate_json(row["payload"])

    def save(self, state: QuestionnaireState) -> None:
        with self.store.connect() as connection:
            connection.execute(
                """
                INSERT INTO questionnaires (fact_base_id, payload)
                VALUES (?, ?)
                ON CONFLICT(fact_base_id) DO UPDATE SET
                    payload = excluded.payload
                """,
                (str(state.fact_base_id), state.model_dump_json()),
            )
```

（顶部 import 补 `QuestionnaireState`。）

`tests/fakes.py` 追加：

```python
class InMemoryQuestionnaireRepository:
    def __init__(self, states=()):
        self.items = {state.fact_base_id: deepcopy(state) for state in states}

    def get(self, fact_base_id: UUID):
        if fact_base_id not in self.items:
            raise KeyError(f"questionnaire state not found: {fact_base_id}")
        return deepcopy(self.items[fact_base_id])

    def save(self, state) -> None:
        self.items[state.fact_base_id] = deepcopy(state)
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_sqlite_repositories.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add resume_agent/domain/models.py resume_agent/application/ports.py resume_agent/infrastructure/sqlite_repositories.py tests/fakes.py tests/test_sqlite_repositories.py
git commit -m "feat: persist questionnaire state per fact base"
```

---

### Task 6: 问卷引擎与问卷服务

**Files:**
- Create: `resume_agent/domain/questionnaire_steps.py`
- Create: `resume_agent/application/questionnaire.py`
- Modify: `resume_agent/domain/models.py`（放松 `Experience` 组织/角色空值校验）
- Modify: `resume_agent/application/fact_base_service.py`（`save`、教育 CRUD、经历更新）
- Test: `tests/test_questionnaire.py`（新建）

**Interfaces:**
- Consumes: Task 4、Task 5
- Produces（Task 7 依赖）：
  - `QuestionnaireEngine(options_providers=None)`：`next_card(base, state, version=None) -> Optional[QuestionCard]`
  - `QuestionCard(step_id, section, kind, prompt, options, value, values, extra, skippable)`
  - `QuestionKind`：text/choice/choice_free/multi_choice/year_month_range/interview
  - `QuestionnaireService(fact_bases, repository, engine)`：`next_card(fact_base_id, version=None)`、`answer(fact_base_id, step_id, value, values, extra)`、`skip(fact_base_id, step_id)`、`progress(fact_base_id, version=None) -> List[SectionProgress]`
  - `FactBaseService.save(base, expected_revision)`、`add_education / update_education / remove_education / update_experience`
  - 步骤 id 约定：`profile:{field}`、`target:{field}`、`education:add`、`education:new:school`、`education:{uuid}:{field}`、`education:more`、`experience:add`、`experience:{uuid}:{field}`、`experience:more`、`skills:tags`、`summary:pick`

- [ ] **Step 1: 写失败测试（引擎顺序与跳过）**

创建 `tests/test_questionnaire.py`：

```python
from uuid import uuid4

import pytest

from resume_agent.application.fact_base_service import FactBaseService
from resume_agent.application.questionnaire import (
    QuestionKind, QuestionnaireEngine, QuestionnaireService,
)
from resume_agent.domain.models import (
    CareerFactBase, ConfidenceStatus, Education, ExperienceType,
    FactValue, QualityDimension, QuestionnaireState, ResumeVersion,
)
from tests.fakes import (
    InMemoryFactBaseRepository, InMemoryQuestionnaireRepository,
)


engine = QuestionnaireEngine()


def make_base():
    base = CareerFactBase()
    base.target.role = "数据分析师"
    base.target.country = "东京"
    base.profile.name = "王明"
    base.profile.email = "wang@example.com"
    base.profile.phone = "13800000000"
    base.profile.location = "东京"
    base.profile.links = ["https://example.com"]
    return base


def test_engine_starts_with_profile_name():
    engine = QuestionnaireEngine()
    card = engine.next_card(
        CareerFactBase(), QuestionnaireState(fact_base_id=uuid4())
    )
    assert card.step_id == "profile:name"


def test_engine_skips_steps_marked_skipped():
    base = make_base()
    base.target.role = ""  # 目标岗位未填，验证跳过基本信息后停在 target:role
    state = QuestionnaireState(fact_base_id=base.id)
    state.skipped = [
        f"profile:{field}" for field in ("name", "email", "phone", "location", "links")
    ]
    card = engine.next_card(base, state)
    assert card.step_id == "target:role"


def test_engine_walks_section_order_to_education():
    base = make_base()
    state = QuestionnaireState(fact_base_id=base.id)
    card = engine.next_card(base, state)
    assert card.step_id == "education:add"
    assert card.section == "education"


def test_engine_asks_experience_type_first():
    base = make_base()
    base.educations.append(Education(school="某大学", major="统计", start="2020-09"))
    state = QuestionnaireState(fact_base_id=base.id)
    state.completed_sections = ["education"]
    card = engine.next_card(base, state)
    assert card.step_id == "experience:add"
    assert card.options == ["实习", "工作", "项目", "校园经历"]


def test_engine_returns_interview_card_when_basics_filled():
    base = make_base()
    base.educations.append(Education(school="某大学", major="统计", start="2020-09"))
    experience = base.add_experience("星河科技", "实习生")
    experience.type = ExperienceType.INTERNSHIP
    experience.start = "2024-06"
    state = QuestionnaireState(fact_base_id=base.id)
    state.completed_sections = ["education"]
    card = engine.next_card(base, state)
    assert card.step_id == f"experience:{experience.id}:interview"
    assert card.kind is QuestionKind.INTERVIEW


def test_engine_summary_card_reads_version_options():
    base = make_base()
    base.educations.append(Education(school="某大学", major="统计", start="2020-09"))
    experience = base.add_experience("星河科技", "实习生")
    experience.start = "2024-06"
    experience.statements[QualityDimension.CONTEXT] = [
        FactValue(text="业务需要留存分析", confidence=ConfidenceStatus.CONFIRMED)
    ]
    experience.statements[QualityDimension.RESPONSIBILITY] = [
        FactValue(text="负责看板搭建", confidence=ConfidenceStatus.CONFIRMED)
    ]
    experience.statements[QualityDimension.ACTION] = [
        FactValue(text="搭建看板", confidence=ConfidenceStatus.CONFIRMED)
    ]
    experience.statements[QualityDimension.RESULT] = [
        FactValue(text="被团队采用", confidence=ConfidenceStatus.CONFIRMED)
    ]
    base.profile.skills = ["SQL"]
    state = QuestionnaireState(fact_base_id=base.id)
    state.completed_sections = ["education", "experience"]
    version = ResumeVersion(
        fact_base_id=base.id, name="默认版本", base_revision=0,
        summary_options=["稳重可靠，善于协作。", "目标导向，数据驱动。"],
    )
    card = engine.next_card(base, state, version=version)
    assert card.step_id == "summary:pick"
    assert card.options == version.summary_options


def make_service():
    fact_bases = FactBaseService(InMemoryFactBaseRepository())
    base = fact_bases.create()
    questionnaire = QuestionnaireService(
        fact_bases, InMemoryQuestionnaireRepository(), QuestionnaireEngine(),
    )
    return questionnaire, base


def test_service_answer_persists_profile_and_advances():
    questionnaire, base = make_service()
    questionnaire.answer(base.id, "profile:name", value="王明")
    questionnaire.answer(base.id, "profile:email", value="wang@example.com")
    questionnaire.answer(base.id, "profile:phone", value="13800000000")
    questionnaire.skip(base.id, "profile:location")
    questionnaire.skip(base.id, "profile:links")
    card = questionnaire.next_card(base.id)
    assert card.step_id == "target:role"
    loaded = questionnaire.fact_bases.get(base.id)
    assert loaded.profile.name == "王明"
    assert loaded.revision == 3


def test_skip_advances_card():
    questionnaire, base = make_service()
    card = questionnaire.next_card(base.id)
    assert card.step_id == "profile:name"
    card = questionnaire.skip(base.id, "profile:name")
    assert card.step_id == "profile:email"


def test_answer_rejects_bad_period():
    questionnaire, base = make_service()
    questionnaire.answer(base.id, "profile:name", value="王明")
    questionnaire.answer(base.id, "profile:email", value="wang@example.com")
    questionnaire.answer(base.id, "profile:phone", value="13800000000")
    questionnaire.answer(base.id, "target:role", value="数据分析师")
    questionnaire.answer(base.id, "education:add", value="开始填写")
    questionnaire.answer(base.id, "education:new:school", value="某大学")
    loaded = questionnaire.fact_bases.get(base.id)
    education_id = loaded.educations[0].id
    with pytest.raises(ValueError):
        questionnaire.answer(
            base.id, f"education:{education_id}:period",
            extra={"start": "2024-13", "end": ""},
        )


def test_experience_choice_creates_typed_experience():
    questionnaire, base = make_service()
    for step_id, value in [
        ("profile:name", "王明"),
        ("profile:email", "wang@example.com"),
        ("profile:phone", "13800000000"),
        ("target:role", "数据分析师"),
    ]:
        questionnaire.answer(base.id, step_id, value=value)
    questionnaire.skip(base.id, "profile:location")
    questionnaire.skip(base.id, "profile:links")
    questionnaire.skip(base.id, "target:city")
    questionnaire.skip(base.id, "education:add")
    card = questionnaire.next_card(base.id)
    assert card.step_id == "experience:add"
    questionnaire.answer(base.id, "experience:add", value="实习")
    loaded = questionnaire.fact_bases.get(base.id)
    assert loaded.experiences[0].type is ExperienceType.INTERNSHIP
    card = questionnaire.next_card(base.id)
    assert card.step_id == f"experience:{loaded.experiences[0].id}:organization"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_questionnaire.py -q`
Expected: FAIL（`resume_agent.application.questionnaire` 不存在）

- [ ] **Step 3: 放松经历组织/角色空值校验**

`resume_agent/domain/models.py` 的 `Experience.validate_required_text` 改为：

```python
    @field_validator("organization", "role")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        # 问卷流会先创建带类型的空白经历再逐项填写；非空由问卷与 API 层保证。
        return value.strip()
```

（全仓没有依赖「空组织名抛错」的既有测试；API 的 `ExperienceCreateRequest` 仍有 `min_length=1` 约束。）

- [ ] **Step 4: 实现步骤表**

创建 `resume_agent/domain/questionnaire_steps.py`：

```python
"""Questionnaire section order and static option tables (zh-first)."""

SECTION_ORDER = ["profile", "target", "education", "experience", "skills", "summary"]

SECTION_LABELS = {
    "profile": "基本信息",
    "target": "求职意向",
    "education": "教育背景",
    "experience": "经历",
    "skills": "技能",
    "summary": "自我评价",
}

PROFILE_STEPS = [
    ("name", "你的姓名是？"),
    ("email", "常用邮箱是？（会出现在简历联系信息里）"),
    ("phone", "联系电话是？"),
    ("location", "目前所在地？（可跳过）"),
    ("links", "个人链接，每行一个，如 GitHub、作品集（可跳过）"),
]

TARGET_STEPS = [
    ("role", "目标岗位是？（例如：数据分析师）"),
    ("city", "目标工作城市？（可跳过）"),
]

DEGREE_OPTIONS = ["高中", "大专", "本科", "硕士", "博士"]

EXPERIENCE_TYPE_OPTIONS = [
    ("internship", "实习"),
    ("work", "工作"),
    ("project", "项目"),
    ("campus", "校园经历"),
]

EXPERIENCE_DONE_OPTION = "经历填写完成"
EDUCATION_DONE_OPTION = "教育填写完成"
```

- [ ] **Step 5: 实现问卷引擎**

创建 `resume_agent/application/questionnaire.py`：

```python
"""Deterministic section-ordered questionnaire (zh-first wizard)."""

from enum import Enum
from typing import Callable, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from resume_agent.domain.models import (
    CareerFactBase,
    Education,
    Experience,
    ExperienceType,
    QuestionnaireState,
    ResumeVersion,
    utc_now,
)
from resume_agent.domain.quality import evaluate_experience, evaluate_profile_completeness
from resume_agent.domain.questionnaire_steps import (
    DEGREE_OPTIONS,
    EDUCATION_DONE_OPTION,
    EXPERIENCE_DONE_OPTION,
    EXPERIENCE_TYPE_OPTIONS,
    PROFILE_STEPS,
    SECTION_LABELS,
    SECTION_ORDER,
    TARGET_STEPS,
)
from resume_agent.domain.year_month import is_year_month, year_month_le


class QuestionKind(str, Enum):
    TEXT = "text"
    CHOICE = "choice"
    CHOICE_FREE = "choice_free"
    MULTI_CHOICE = "multi_choice"
    YEAR_MONTH_RANGE = "year_month_range"
    INTERVIEW = "interview"


class QuestionCard(BaseModel):
    step_id: str
    section: str
    kind: QuestionKind
    prompt: str
    options: List[str] = Field(default_factory=list)
    value: str = ""
    values: List[str] = Field(default_factory=list)
    extra: Dict[str, str] = Field(default_factory=dict)
    skippable: bool = True


class SectionProgress(BaseModel):
    section: str
    label: str
    done: bool
    current: bool = False


class QuestionnaireEngine:
    """Choose the next unsatisfied question in section order."""

    def __init__(self, options_providers: Optional[Dict[str, Callable]] = None):
        self.options_providers = options_providers or {}

    def next_card(self, base, state, version=None):
        for section in SECTION_ORDER:
            card = self._section_card(base, state, section, version)
            if card is not None:
                return card
        return None

    @staticmethod
    def _card(step_id, section, kind, prompt, **fields):
        return QuestionCard(
            step_id=step_id, section=section, kind=kind, prompt=prompt, **fields
        )

    @staticmethod
    def _skipped(state, step_id):
        return step_id in state.skipped

    def _provider(self, name, base, state):
        provider = self.options_providers.get(name)
        return provider(base, state) if provider else []

    def _section_card(self, base, state, section, version):
        if section == "profile":
            return self._profile_card(base, state)
        if section == "target":
            return self._target_card(base, state)
        if section == "education":
            return self._education_card(base, state)
        if section == "experience":
            return self._experience_card(base, state)
        if section == "skills":
            return self._skills_card(base, state)
        return self._summary_card(state, version)

    def _profile_card(self, base, state):
        for field, prompt in PROFILE_STEPS:
            step_id = f"profile:{field}"
            if self._skipped(state, step_id):
                continue
            value = getattr(base.profile, field, "") or ""
            if field == "links":
                value = "\n".join(base.profile.links)
            if not value:
                return self._card(
                    step_id, "profile", QuestionKind.TEXT, prompt,
                    skippable=field in ("location", "links"),
                )
        return None

    def _target_card(self, base, state):
        steps = [
            ("role", base.target.role, TARGET_STEPS[0][1], False),
            ("city", base.target.country, TARGET_STEPS[1][1], True),
        ]
        for field, value, prompt, skippable in steps:
            step_id = f"target:{field}"
            if self._skipped(state, step_id):
                continue
            if not value:
                return self._card(
                    step_id, "target", QuestionKind.TEXT, prompt, skippable=skippable
                )
        return None

    def _education_card(self, base, state):
        if not base.educations:
            if self._skipped(state, "education:add"):
                return None
            return self._card(
                "education:add", "education", QuestionKind.CHOICE,
                "开始填写教育背景？", options=["开始填写"],
            )
        if "education" in state.completed_sections:
            return None
        education = self._edited_education(base, state)
        if education is None:
            return self._card(
                "education:new:school", "education", QuestionKind.TEXT,
                "学校名称是？", skippable=False,
            )
        if not education.school and not self._skipped(state, f"education:{education.id}:school"):
            return self._card(
                f"education:{education.id}:school", "education", QuestionKind.TEXT,
                "学校名称是？", skippable=False,
            )
        if not education.major and not self._skipped(state, f"education:{education.id}:major"):
            return self._card(
                f"education:{education.id}:major", "education", QuestionKind.CHOICE_FREE,
                "所学专业是？（可选推荐项，也可以自己填）",
                options=self._provider("majors", base, state),
            )
        if not education.degree and not self._skipped(state, f"education:{education.id}:degree"):
            return self._card(
                f"education:{education.id}:degree", "education", QuestionKind.CHOICE,
                "最高学历是？", options=DEGREE_OPTIONS,
            )
        if not education.start and not self._skipped(state, f"education:{education.id}:period"):
            return self._card(
                f"education:{education.id}:period", "education",
                QuestionKind.YEAR_MONTH_RANGE,
                "这段教育的起止时间是？（结束留空表示至今）",
                extra={"end": education.end or ""},
            )
        if not education.core_courses and not self._skipped(state, f"education:{education.id}:courses"):
            return self._card(
                f"education:{education.id}:courses", "education",
                QuestionKind.MULTI_CHOICE, "勾选或添加核心课程（可跳过）",
                options=self._provider("courses", base, state),
            )
        return self._card(
            "education:more", "education", QuestionKind.CHOICE,
            "是否还有下一段教育经历？",
            options=["添加下一段教育", EDUCATION_DONE_OPTION],
        )

    def _experience_card(self, base, state):
        if not base.experiences:
            if self._skipped(state, "experience:add"):
                return None
            return self._card(
                "experience:add", "experience", QuestionKind.CHOICE,
                "先添加一段经历，你想写哪类？",
                options=[label for _, label in EXPERIENCE_TYPE_OPTIONS],
            )
        for experience in base.experiences:
            card = self._experience_field_card(base, state, experience)
            if card is not None:
                return card
        if "experience" in state.completed_sections:
            return None
        return self._card(
            "experience:more", "experience", QuestionKind.CHOICE,
            "是否还有下一段经历？",
            options=[label for _, label in EXPERIENCE_TYPE_OPTIONS] + [EXPERIENCE_DONE_OPTION],
        )

    def _experience_field_card(self, base, state, experience):
        if not experience.organization and not self._skipped(state, f"experience:{experience.id}:organization"):
            return self._card(
                f"experience:{experience.id}:organization", "experience",
                QuestionKind.TEXT, "这段经历的公司、组织或项目名称是？", skippable=False,
            )
        if not experience.role and not self._skipped(state, f"experience:{experience.id}:role"):
            return self._card(
                f"experience:{experience.id}:role", "experience",
                QuestionKind.TEXT, "你当时的角色是？（例如：数据分析实习生）", skippable=False,
            )
        if not experience.start and not self._skipped(state, f"experience:{experience.id}:period"):
            return self._card(
                f"experience:{experience.id}:period", "experience",
                QuestionKind.YEAR_MONTH_RANGE,
                "这段经历的起止时间是？（结束留空表示至今）",
                extra={"end": experience.end or ""},
            )
        if (
            not evaluate_experience(experience).passes_gate
            and not self._skipped(state, f"experience:{experience.id}:interview")
        ):
            return self._card(
                f"experience:{experience.id}:interview", "experience",
                QuestionKind.INTERVIEW,
                "导师会继续追问这段经历的具体内容，请回答左侧问题。", skippable=False,
            )
        return None

    def _skills_card(self, base, state):
        if base.profile.skills or self._skipped(state, "skills:tags"):
            return None
        return self._card(
            "skills:tags", "skills", QuestionKind.MULTI_CHOICE,
            "勾选或添加你的技能标签（可跳过）",
            options=self._provider("skills", base, state),
            values=list(base.profile.skills),
        )

    def _summary_card(self, state, version):
        if version is None or not version.summary_options or self._skipped(state, "summary:pick"):
            return None
        return self._card(
            "summary:pick", "summary", QuestionKind.MULTI_CHOICE,
            "从备选中勾选 1~2 条自我评价（可稍后重新生成）",
            options=list(version.summary_options),
            values=[version.selected_summary] if version.selected_summary else [],
        )

    @staticmethod
    def _edited_education(base, state):
        for education in base.educations:
            if education.id == state.edited_education_id:
                return education
        return None
```

- [ ] **Step 6: 实现 FactBaseService 新方法**

`resume_agent/application/fact_base_service.py`：import 行补 `Education`、`ExperienceType`，追加：

```python
    def save(self, base: CareerFactBase, expected_revision: int) -> None:
        self.repository.save(base, expected_revision=expected_revision)

    def add_education(self, fact_base_id: UUID, education: Education) -> CareerFactBase:
        base = self.repository.get(fact_base_id)
        expected_revision = base.revision
        base.educations.append(education)
        return self._commit(base, expected_revision)

    def update_education(self, fact_base_id: UUID, education: Education) -> CareerFactBase:
        base = self.repository.get(fact_base_id)
        expected_revision = base.revision
        for index, item in enumerate(base.educations):
            if item.id == education.id:
                education.updated_at = utc_now()
                base.educations[index] = education
                return self._commit(base, expected_revision)
        raise KeyError(f"education not found: {education.id}")

    def remove_education(self, fact_base_id: UUID, education_id: UUID) -> CareerFactBase:
        base = self.repository.get(fact_base_id)
        expected_revision = base.revision
        base.educations = [
            item for item in base.educations if item.id != education_id
        ]
        return self._commit(base, expected_revision)

    def update_experience(
        self,
        fact_base_id: UUID,
        experience_id: UUID,
        *,
        organization: Optional[str] = None,
        role: Optional[str] = None,
        experience_type: Optional[ExperienceType] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        linked_skills: Optional[List[str]] = None,
    ) -> CareerFactBase:
        base = self.repository.get(fact_base_id)
        expected_revision = base.revision
        experience = base.get_experience(experience_id)
        if organization is not None:
            experience.organization = organization
        if role is not None:
            experience.role = role
        if experience_type is not None:
            experience.type = experience_type
        if start is not None:
            experience.start = start
        if end is not None:
            experience.end = end
        if linked_skills is not None:
            experience.linked_skills = linked_skills
        experience.updated_at = utc_now()
        return self._commit(base, expected_revision)

    def _commit(self, base: CareerFactBase, expected_revision: int) -> CareerFactBase:
        base.revision += 1
        base.updated_at = utc_now()
        self.repository.save(base, expected_revision=expected_revision)
        return self.repository.get(base.id)
```

- [ ] **Step 7: 实现问卷服务**

`resume_agent/application/questionnaire.py` 追加：

```python
class QuestionnaireService:
    """Side-effecting orchestration: writes answers into models, returns next card."""

    def __init__(self, fact_bases, repository, engine):
        self.fact_bases = fact_bases
        self.repository = repository
        self.engine = engine

    def _state(self, fact_base_id):
        try:
            return self.repository.get(fact_base_id)
        except KeyError:
            state = QuestionnaireState(fact_base_id=fact_base_id)
            self.repository.save(state)
            return state

    def next_card(self, fact_base_id, version=None):
        base = self.fact_bases.get(fact_base_id)
        return self.engine.next_card(base, self._state(fact_base_id), version=version)

    def progress(self, fact_base_id, version=None):
        base = self.fact_bases.get(fact_base_id)
        state = self._state(fact_base_id)
        completeness = evaluate_profile_completeness(
            base, version.selected_summary if version else ""
        )
        card = self.engine.next_card(base, state, version=version)
        current_section = card.section if card else ""
        return [
            SectionProgress(
                section=section,
                label=SECTION_LABELS[section],
                done=completeness.sections[section],
                current=section == current_section,
            )
            for section in SECTION_ORDER
        ]

    def answer(self, fact_base_id, step_id, value="", values=None, extra=None):
        values = list(values or [])
        extra = dict(extra or {})
        base = self.fact_bases.get(fact_base_id)
        state = self._state(fact_base_id)
        self._dispatch(base, state, step_id, value, values, extra)
        state.updated_at = utc_now()
        self.repository.save(state)
        return self.fact_bases.get(base.id)

    def skip(self, fact_base_id, step_id):
        self.fact_bases.get(fact_base_id)
        state = self._state(fact_base_id)
        if step_id not in state.skipped:
            state.skipped.append(step_id)
        state.updated_at = utc_now()
        self.repository.save(state)
        return self.next_card(fact_base_id)

    def _bump(self, base):
        expected_revision = base.revision
        base.revision += 1
        base.updated_at = utc_now()
        self.fact_bases.save(base, expected_revision=expected_revision)
        return self.fact_bases.get(base.id)

    def _dispatch(self, base, state, step_id, value, values, extra):
        value = value.strip()
        if step_id.startswith("profile:"):
            return self._answer_profile(base, step_id, value)
        if step_id.startswith("target:"):
            return self._answer_target(base, step_id, value)
        if step_id == "education:add":
            if value != "开始填写":
                raise ValueError("选项不正确")
            return base
        if step_id == "education:more":
            return self._education_more(base, state, value)
        if step_id.startswith("education:"):
            return self._answer_education(base, state, step_id, value, values, extra)
        if step_id in ("experience:add", "experience:more"):
            return self._experience_choice(base, state, value)
        if step_id.startswith("experience:"):
            return self._answer_experience(base, state, step_id, value, extra)
        if step_id == "skills:tags":
            return self._answer_skills(base, values)
        if step_id == "summary:pick":
            return base  # 自我评价写入在 Task 15 实现
        raise ValueError(f"unknown questionnaire step: {step_id}")

    def _answer_profile(self, base, step_id, value):
        field = step_id.split(":", 1)[1]
        if field == "name":
            if not value:
                raise ValueError("姓名不能为空")
            base.profile.name = value
        elif field == "email":
            if "@" not in value:
                raise ValueError("邮箱格式不正确")
            base.profile.email = value
        elif field == "phone":
            if not value:
                raise ValueError("电话不能为空")
            base.profile.phone = value
        elif field == "location":
            base.profile.location = value
        elif field == "links":
            base.profile.links = [
                line.strip() for line in value.splitlines() if line.strip()
            ]
        else:
            raise ValueError(f"unknown profile step: {step_id}")
        return self._bump(base)

    def _answer_target(self, base, step_id, value):
        field = step_id.split(":", 1)[1]
        if field == "role":
            if not value:
                raise ValueError("目标岗位不能为空")
            base.target.role = value
        elif field == "city":
            base.target.country = value
        else:
            raise ValueError(f"unknown target step: {step_id}")
        return self._bump(base)

    def _answer_education(self, base, state, step_id, value, values, extra):
        parts = step_id.split(":")
        if parts[1] == "new" and parts[2] == "school":
            if not value:
                raise ValueError("学校名称不能为空")
            education = Education(school=value)
            base.educations.append(education)
            state.edited_education_id = education.id
            return self._bump(base)
        education_id = UUID(parts[1])
        education = next(
            item for item in base.educations if item.id == education_id
        )
        field = parts[2]
        if field == "school":
            if not value:
                raise ValueError("学校名称不能为空")
            education.school = value
        elif field == "major":
            if not value:
                raise ValueError("专业不能为空")
            education.major = value
        elif field == "degree":
            if value not in DEGREE_OPTIONS:
                raise ValueError("学历选项不正确")
            education.degree = value
        elif field == "period":
            start, end = self._period(extra)
            education.start = start
            education.end = end
        elif field == "courses":
            education.core_courses = [
                item.strip() for item in values if item.strip()
            ]
        else:
            raise ValueError(f"unknown education step: {step_id}")
        education.updated_at = utc_now()
        return self._bump(base)

    def _education_more(self, base, state, value):
        if value == EDUCATION_DONE_OPTION:
            if "education" not in state.completed_sections:
                state.completed_sections.append("education")
            state.edited_education_id = None
            return base
        if value == "添加下一段教育":
            state.edited_education_id = None
            return base
        raise ValueError("选项不正确")

    def _experience_choice(self, base, state, value):
        if value == EXPERIENCE_DONE_OPTION:
            if "experience" not in state.completed_sections:
                state.completed_sections.append("experience")
            return base
        kind = {label: code for code, label in EXPERIENCE_TYPE_OPTIONS}.get(value)
        if kind is None:
            raise ValueError("经历类型不正确")
        experience = Experience(
            organization="", role="", type=ExperienceType(kind)
        )
        base.experiences.append(experience)
        state.edited_experience_id = experience.id
        return self._bump(base)

    def _answer_experience(self, base, state, step_id, value, extra):
        _, experience_id_text, field = step_id.split(":")
        if field == "interview":
            raise ValueError("该步骤请通过访谈流程完成")
        experience = base.get_experience(UUID(experience_id_text))
        if field == "organization":
            if not value:
                raise ValueError("组织名称不能为空")
            experience.organization = value
        elif field == "role":
            if not value:
                raise ValueError("角色不能为空")
            experience.role = value
        elif field == "period":
            start, end = self._period(extra)
            experience.start = start
            experience.end = end
        else:
            raise ValueError(f"unknown experience step: {step_id}")
        experience.updated_at = utc_now()
        return self._bump(base)

    def _answer_skills(self, base, values):
        base.profile.skills = [item.strip() for item in values if item.strip()]
        return self._bump(base)

    @staticmethod
    def _period(extra):
        start = extra.get("start", "").strip()
        end = extra.get("end", "").strip()
        if not is_year_month(start):
            raise ValueError("起始年月格式不正确（YYYY-MM）")
        if end and not is_year_month(end):
            raise ValueError("结束年月格式不正确（YYYY-MM）")
        if end and not year_month_le(start, end):
            raise ValueError("结束时间不能早于开始时间")
        return start, (end or None)
```

- [ ] **Step 8: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_questionnaire.py tests/test_api_fact_bases.py tests/test_interview_service.py -q`
Expected: PASS

- [ ] **Step 9: 提交**

```bash
git add resume_agent/domain/questionnaire_steps.py resume_agent/application/questionnaire.py resume_agent/domain/models.py resume_agent/application/fact_base_service.py tests/test_questionnaire.py
git commit -m "feat: deterministic section-ordered questionnaire engine and service"
```

### Task 7: 问卷 API 与容器装配

**Files:**
- Modify: `resume_agent/api/schemas.py`（问卷/教育/经历更新请求模型）
- Modify: `resume_agent/api/app.py`（容器字段与 6 个新端点）
- Test: `tests/test_api_questionnaire.py`（新建）

**Interfaces:**
- Consumes: Task 6 的 `QuestionnaireService`、`FactBaseService` 新方法
- Produces（Task 8 依赖的 HTTP 契约）：
  - `GET /fact-bases/{id}/questionnaire` → `{"sections": [{section, label, done, current}], "next": QuestionCard|null}`
  - `POST /fact-bases/{id}/questionnaire/answer` → `{"base": CareerFactBase, "next": QuestionCard|null}`；请求体 `{step_id, value, values, extra}`
  - `POST /fact-bases/{id}/questionnaire/skip` → `{"next": QuestionCard|null}`；请求体 `{step_id}`
  - `POST /fact-bases/{id}/educations`（201）→ CareerFactBase；`PATCH/DELETE /fact-bases/{id}/educations/{education_id}` → CareerFactBase
  - `PATCH /fact-bases/{id}/experiences/{experience_id}` → CareerFactBase；请求体字段全部可选：`{organization, role, type, start, end, linked_skills}`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_api_questionnaire.py`：

```python
from fastapi.testclient import TestClient

from resume_agent.api.app import create_app


def test_questionnaire_returns_sections_and_first_card(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post(
            "/fact-bases", json={"target": {"role": "数据分析师"}}
        ).json()
        response = client.get(f"/fact-bases/{base['id']}/questionnaire")
    assert response.status_code == 200
    body = response.json()
    assert [item["section"] for item in body["sections"]] == [
        "profile", "target", "education", "experience", "skills", "summary",
    ]
    assert body["next"]["step_id"] == "profile:name"


def test_questionnaire_answer_advances_card(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post(
            "/fact-bases", json={"target": {"role": "数据分析师"}}
        ).json()
        answer = client.post(
            f"/fact-bases/{base['id']}/questionnaire/answer",
            json={"step_id": "profile:name", "value": "王明"},
        )
        assert answer.status_code == 200
        assert answer.json()["next"]["step_id"] == "profile:email"
        fetched = client.get(f"/fact-bases/{base['id']}").json()
        assert fetched["profile"]["name"] == "王明"


def test_questionnaire_answer_validates_email(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post(
            "/fact-bases", json={"target": {"role": "数据分析师"}}
        ).json()
        answer = client.post(
            f"/fact-bases/{base['id']}/questionnaire/answer",
            json={"step_id": "profile:email", "value": "not-an-email"},
        )
        assert answer.status_code == 422


def test_questionnaire_skip_advances(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post(
            "/fact-bases", json={"target": {"role": "数据分析师"}}
        ).json()
        skip = client.post(
            f"/fact-bases/{base['id']}/questionnaire/skip",
            json={"step_id": "profile:name"},
        )
        assert skip.status_code == 200
        assert skip.json()["next"]["step_id"] == "profile:email"


def test_education_crud(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post(
            "/fact-bases", json={"target": {"role": "数据分析师"}}
        ).json()
        created = client.post(
            f"/fact-bases/{base['id']}/educations",
            json={"school": "某大学", "major": "统计", "start": "2020-09"},
        )
        assert created.status_code == 201
        education = created.json()["educations"][0]
        patched = client.patch(
            f"/fact-bases/{base['id']}/educations/{education['id']}",
            json={"school": "某大学", "major": "统计", "start": "2020-09", "degree": "本科"},
        )
        assert patched.status_code == 200
        assert patched.json()["educations"][0]["degree"] == "本科"
        removed = client.delete(
            f"/fact-bases/{base['id']}/educations/{education['id']}"
        )
        assert removed.status_code == 200
        assert removed.json()["educations"] == []


def test_experience_patch_updates_type_and_period(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post(
            "/fact-bases", json={"target": {"role": "数据分析师"}}
        ).json()
        base = client.post(
            f"/fact-bases/{base['id']}/experiences",
            json={"organization": "星河科技", "role": "实习生"},
        ).json()
        experience = base["experiences"][0]
        patched = client.patch(
            f"/fact-bases/{base['id']}/experiences/{experience['id']}",
            json={"type": "internship", "start": "2024-06", "end": "2024-09"},
        )
        assert patched.status_code == 200
        updated = patched.json()["experiences"][0]
        assert updated["type"] == "internship"
        assert updated["start"] == "2024-06"
        assert updated["end"] == "2024-09"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_api_questionnaire.py -q`
Expected: FAIL（404 路由不存在）

- [ ] **Step 3: 请求模型**

`resume_agent/api/schemas.py`：顶部 import 补 `Dict, Optional` 与 `Education`、`ExperienceType`，追加：

```python
class QuestionnaireAnswerRequest(BaseModel):
    step_id: str = Field(min_length=1)
    value: str = ""
    values: List[str] = Field(default_factory=list)
    extra: Dict[str, str] = Field(default_factory=dict)


class QuestionnaireSkipRequest(BaseModel):
    step_id: str = Field(min_length=1)


class EducationCreateRequest(BaseModel):
    school: str = Field(min_length=1)
    major: str = ""
    degree: str = ""
    start: str = ""
    end: Optional[str] = None
    core_courses: List[str] = Field(default_factory=list)


class ExperienceUpdateRequest(BaseModel):
    organization: Optional[str] = None
    role: Optional[str] = None
    type: Optional[ExperienceType] = None
    start: Optional[str] = None
    end: Optional[str] = None
    linked_skills: Optional[List[str]] = None
```

- [ ] **Step 4: 容器与端点**

`resume_agent/api/app.py`：

import 区补：

```python
from resume_agent.api.schemas import (
    ...
    EducationCreateRequest,
    ExperienceUpdateRequest,
    QuestionnaireAnswerRequest,
    QuestionnaireSkipRequest,
)
from resume_agent.application.questionnaire import (
    QuestionnaireEngine,
    QuestionnaireService,
)
from resume_agent.domain.models import (
    ...,
    Education,
)
from resume_agent.infrastructure.sqlite_repositories import (
    ...,
    SQLiteQuestionnaireRepository,
)
```

`ServiceContainer` 增加字段：

```python
    questionnaires: QuestionnaireService
```

`create_app` 内，`fact_bases=...` 的位置改为：

```python
    fact_base_service = FactBaseService(fact_base_repository)
    questionnaire_service = QuestionnaireService(
        fact_base_service,
        SQLiteQuestionnaireRepository(store),
        QuestionnaireEngine(),
    )
```

并把 `fact_bases=FactBaseService(fact_base_repository),` 替换为 `fact_bases=fact_base_service,`，新增 `questionnaires=questionnaire_service,`。

在 `create_app` 内、`app.state.container = container` 之后追加辅助函数与路由：

```python
    def _current_version(fact_base_id: UUID) -> Optional[ResumeVersion]:
        versions = container.version_repository.list(fact_base_id)
        if not versions:
            return None
        for version in versions:
            if version.is_active:
                return version
        return versions[-1]

    @app.get("/fact-bases/{fact_base_id}/questionnaire")
    def questionnaire_view(fact_base_id: UUID):
        version = _current_version(fact_base_id)
        return {
            "sections": container.questionnaires.progress(fact_base_id, version),
            "next": container.questionnaires.next_card(fact_base_id, version),
        }

    @app.post("/fact-bases/{fact_base_id}/questionnaire/answer")
    def questionnaire_answer(fact_base_id: UUID, payload: QuestionnaireAnswerRequest):
        base = container.questionnaires.answer(
            fact_base_id,
            payload.step_id,
            value=payload.value,
            values=payload.values,
            extra=payload.extra,
        )
        version = _current_version(fact_base_id)
        return {
            "base": base,
            "next": container.questionnaires.next_card(fact_base_id, version),
        }

    @app.post("/fact-bases/{fact_base_id}/questionnaire/skip")
    def questionnaire_skip(fact_base_id: UUID, payload: QuestionnaireSkipRequest):
        return {
            "next": container.questionnaires.skip(fact_base_id, payload.step_id),
        }

    @app.post("/fact-bases/{fact_base_id}/educations", status_code=201)
    def create_education(fact_base_id: UUID, payload: EducationCreateRequest):
        education = Education(
            school=payload.school,
            major=payload.major,
            degree=payload.degree,
            start=payload.start,
            end=payload.end,
            core_courses=payload.core_courses,
        )
        return container.fact_bases.add_education(fact_base_id, education)

    @app.patch("/fact-bases/{fact_base_id}/educations/{education_id}")
    def update_education(
        fact_base_id: UUID,
        education_id: UUID,
        payload: EducationCreateRequest,
    ):
        base = container.fact_bases.get(fact_base_id)
        current = next(
            item for item in base.educations if item.id == education_id
        )
        updated = Education(
            id=education_id,
            school=payload.school,
            major=payload.major,
            degree=payload.degree,
            start=payload.start,
            end=payload.end,
            core_courses=payload.core_courses,
            created_at=current.created_at,
            updated_at=utc_now(),
        )
        return container.fact_bases.update_education(fact_base_id, updated)

    @app.delete("/fact-bases/{fact_base_id}/educations/{education_id}")
    def delete_education(fact_base_id: UUID, education_id: UUID):
        return container.fact_bases.remove_education(fact_base_id, education_id)

    @app.patch("/fact-bases/{fact_base_id}/experiences/{experience_id}")
    def update_experience(
        fact_base_id: UUID,
        experience_id: UUID,
        payload: ExperienceUpdateRequest,
    ):
        return container.fact_bases.update_experience(
            fact_base_id,
            experience_id,
            organization=payload.organization,
            role=payload.role,
            experience_type=payload.type,
            start=payload.start,
            end=payload.end,
            linked_skills=payload.linked_skills,
        )
```

（`utc_now` 从 domain.models 导入，若 app.py 尚未导入则补。）

- [ ] **Step 5: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_api_questionnaire.py tests/test_api_fact_bases.py -q`
Expected: PASS（`ValueError` 已有 422 异常处理器，仓库惯例）

- [ ] **Step 6: 提交**

```bash
git add resume_agent/api/schemas.py resume_agent/api/app.py tests/test_api_questionnaire.py
git commit -m "feat: expose questionnaire and education endpoints"
```

---

### Task 8: 前端 API 方法与纯函数模块

**Files:**
- Modify: `resume_agent/web/api.js`（4 个新方法）
- Create: `resume_agent/web/questionnaire.js`
- Test: `tests/web/api.test.mjs`（追加）、`tests/web/questionnaire.test.mjs`（新建）

**Interfaces:**
- Consumes: Task 7 的 HTTP 契约
- Produces（Task 9 依赖）：
  - `api.questionnaire(factBaseId)`、`api.answerQuestion(factBaseId, payload)`、`api.skipQuestion(factBaseId, stepId)`
  - `answerPayload(stepId, result)`、`periodExtra(start, end)`、`sectionFromStep(stepId)`、`normalizeChips(values)`

- [ ] **Step 1: 写失败测试**

`tests/web/api.test.mjs` 末尾追加：

```js
test("questionnaire methods post the right contracts", async () => {
  const calls = [];
  const api = createApi(async (url, init) => {
    calls.push([url, init]);
    return new Response(JSON.stringify({ next: { step_id: "profile:email" } }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });

  await api.questionnaire("base-1");
  await api.answerQuestion("base-1", { step_id: "profile:name", value: "王明" });
  await api.skipQuestion("base-1", "profile:links");

  assert.equal(calls[0][0], "/fact-bases/base-1/questionnaire");
  assert.equal(calls[1][0], "/fact-bases/base-1/questionnaire/answer");
  assert.equal(calls[1][1].method, "POST");
  assert.deepEqual(JSON.parse(calls[1][1].body), { step_id: "profile:name", value: "王明" });
  assert.equal(calls[2][0], "/fact-bases/base-1/questionnaire/skip");
  assert.deepEqual(JSON.parse(calls[2][1].body), { step_id: "profile:links" });
});
```

创建 `tests/web/questionnaire.test.mjs`：

```js
import test from "node:test";
import assert from "node:assert/strict";

import {
  answerPayload,
  normalizeChips,
  periodExtra,
  sectionFromStep,
} from "../../resume_agent/web/questionnaire.js";


test("answerPayload builds the transport shape", () => {
  assert.deepEqual(answerPayload("profile:name", { value: "王明" }), {
    step_id: "profile:name",
    value: "王明",
    values: [],
    extra: {},
  });
  assert.deepEqual(answerPayload("education:x:period", {
    extra: { start: "2020-09", end: "" },
  }), {
    step_id: "education:x:period",
    value: "",
    values: [],
    extra: { start: "2020-09", end: "" },
  });
});


test("periodExtra normalizes period values", () => {
  assert.deepEqual(periodExtra("2020-09", ""), { start: "2020-09", end: "" });
  assert.deepEqual(periodExtra("", "至今"), { start: "", end: "至今" });
});


test("sectionFromStep parses the leading section", () => {
  assert.equal(sectionFromStep("profile:name"), "profile");
  assert.equal(sectionFromStep("experience:abc:role"), "experience");
  assert.equal(sectionFromStep(""), "");
});


test("normalizeChips dedupes and trims", () => {
  assert.deepEqual(normalizeChips(["SQL", " SQL ", "SQL", ""]), ["SQL"]);
});
```

- [ ] **Step 2: 运行确认失败**

Run: `node --test tests/web/*.test.mjs`
Expected: FAIL（`questionnaire` 方法不存在 / 模块不存在）

- [ ] **Step 3: 实现**

`resume_agent/web/api.js` 的 `return {` 对象中追加（放在 `experienceQuality` 之后）：

```javascript
    questionnaire: (factBaseId) => request(`/fact-bases/${factBaseId}/questionnaire`),
    answerQuestion: (factBaseId, payload) => request(
      `/fact-bases/${factBaseId}/questionnaire/answer`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
    skipQuestion: (factBaseId, stepId) => request(
      `/fact-bases/${factBaseId}/questionnaire/skip`,
      { method: "POST", body: JSON.stringify({ step_id: stepId }) },
    ),
```

创建 `resume_agent/web/questionnaire.js`：

```javascript
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
```

- [ ] **Step 4: 运行确认通过**

Run: `node --test tests/web/*.test.mjs`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add resume_agent/web/api.js resume_agent/web/questionnaire.js tests/web/api.test.mjs tests/web/questionnaire.test.mjs
git commit -m "feat: frontend api methods and pure helpers for questionnaire"
```

---

### Task 9: 前端问卷 UI（章节导航、问题卡片、年月选择器）

**Files:**
- Modify: `resume_agent/web/index.html`（tab 文案、chat-panel 结构）
- Modify: `resume_agent/web/app.js`（导入、状态、卡片渲染、问答/跳过、onboarding 简化、activateBase 接入）
- Modify: `resume_agent/web/styles.css`（问题卡片/章节导航/年月选择器样式）

**Interfaces:**
- Consumes: Task 8 的 `api` 方法与 `questionnaire.js` 纯函数
- Produces（P3~P5 前端依赖）：`renderQuestionCard(card)`、`refreshQuestionnaire()`、`questionnaireState`（模块内状态）、`sectionNavElement()`、`yearMonthRangeField(card)`

- [ ] **Step 1: 修改 index.html**

`resume_agent/web/index.html`：

- 三个 tab 文案改为：`访谈` → `问答`；`事实库` → `片段`；`JD 定制` → `版本`（保持 `id` 与 `data-tab` 不变，避免 `sanitizeUiState` 白名单改动）。

- `chat-panel` 内、`panel-actions` 之前插入：

```html
            <nav id="section-nav" class="section-nav" aria-label="简历章节"></nav>
            <div id="question-area" class="question-area" aria-live="polite"></div>
```

（原 `interview-progress` 与 `chat-messages` 保留原位。）

- [ ] **Step 2: 实现年月选择器与问题卡片（app.js 追加）**

`resume_agent/web/app.js` 顶部 import 追加：

```javascript
import {
  answerPayload,
  normalizeChips,
  periodExtra,
} from "/assets/questionnaire.js";
```

模块状态区（`let currentRendered = null;` 附近）追加：

```javascript
let questionnaireState = null;
```

`renderOnboarding()` 替换为（只问目标岗位，其余交给向导）：

```javascript
function renderOnboarding() {
  currentSession = null;
  const panel = byId("chat-panel");
  panel.replaceChildren();
  const heading = element("div", "section-heading");
  heading.append(
    element("h2", "", "先建立一份档案"),
    element("p", "", "只需填目标岗位；其余信息由向导逐步提问收集。"),
  );

  const form = element("form", "onboarding-form");
  form.id = "onboarding-form";
  form.append(
    field("目标岗位", "role", "例如：数据分析师"),
    field("目标国家或地区（可选）", "country", "例如：日本"),
  );
  const submit = element("button", "primary", "创建档案并开始");
  submit.type = "submit";
  form.append(submit);
  form.addEventListener("submit", handleOnboarding);
  panel.append(heading, form);
  byId("chat-composer").hidden = true;
}
```

`handleOnboarding` 替换为：

```javascript
async function handleOnboarding(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const role = String(form.get("role") || "").trim();
  const country = String(form.get("country") || "").trim();
  if (!role) {
    showToast("请填写目标岗位");
    return;
  }
  const submit = event.currentTarget.querySelector("button[type=submit]");
  submit.disabled = true;
  try {
    const base = await api.createFactBase({
      role,
      country,
      languages: ["zh", "ja", "en"],
    });
    await activateBase(base);
  } catch (error) {
    showToast(error instanceof ApiError ? error.message : "档案创建失败");
    submit.disabled = false;
  }
}
```

`activateBase` 中，在 `resetComposerAction();` 之前插入 `await refreshQuestionnaire();`：

```javascript
    commitSelection(base.id, {
      experienceId,
      sessionId: session?.id || "",
      versionId: currentVersion?.id || "",
    });
    await refreshQuestionnaire();
    resetComposerAction();
```

（`refreshQuestionnaire` 定义见 Step 3；此时若 `currentBase` 尚未赋值会直接返回，因此在其后的 `currentBase = base;` 赋值行之后调用同样可接受——按上面位置插入时把该调用放在 `currentBase = base;` 与 `commitSelection` 之后的顺序执行即可。）

在 `renderConversation()` 函数开头（`if (!currentBase) {` 之后）追加两个调用，并在 `panel.replaceChildren();` 之后追加两个节点：

```javascript
function renderConversation() {
  if (!currentBase) {
    renderOnboarding();
    return;
  }
  const panel = byId("chat-panel");
  panel.replaceChildren();
  panel.append(sectionNavElement(), questionAreaElement());
```

（其后原有 `panel.append(experienceSelector(), renderInterviewProgress());` 等逻辑不变。）

- [ ] **Step 3: 实现渲染与交互函数（app.js 追加）**

```javascript
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
  const area = element("div", "question-area");
  const card = questionnaireState?.next;
  if (card) area.append(renderQuestionCard(card));
  return area;
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
  if (card.kind === "interview") {
    const start = element("button", "primary", "开始追问这段经历");
    start.type = "button";
    start.addEventListener("click", () => startInterviewForCard(card));
    article.append(start);
    return article;
  }
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
    for (const option of card.options || []) {
      const label = element("label", "check-row");
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = `choice-${card.step_id}`;
      radio.value = option;
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
  questionnaireState = { progress: view.sections, next: view.next };
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
    renderConversation();
  } catch (error) {
    if (!baseActivationGate.isCurrent(baseGeneration) || currentBase?.id !== baseId) return;
    showToast(error instanceof ApiError ? error.message : "回答保存失败");
    renderConversation();
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
  } catch (error) {
    if (!baseActivationGate.isCurrent(baseGeneration) || currentBase?.id !== baseId) return;
    showToast(error instanceof ApiError ? error.message : "跳过失败");
  }
}

async function startInterviewForCard(card) {
  const experienceId = String(card.step_id || "").split(":")[1];
  if (!currentBase || !experienceId) return;
  try {
    if (state.experienceId !== experienceId) {
      await activateExperience(experienceId);
      if (!currentBase || state.experienceId !== experienceId) return;
    }
    await refreshQuestionnaire();
    renderConversation();
  } catch (error) {
    showToast(error instanceof ApiError ? error.message : "经历切换失败");
  }
}
```

- [ ] **Step 4: 样式**

`resume_agent/web/styles.css` 末尾追加：

```css
.section-nav { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.section-chip { border: 1px solid var(--border, #d8dde5); border-radius: 999px; padding: 3px 12px; background: #fff; cursor: default; }
.section-chip.done { color: #166534; background: #ecfdf3; border-color: #bbe7c8; }
.section-chip.current { border-color: var(--accent, #1d4ed8); box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent, #1d4ed8) 20%, transparent); }

.question-area { margin-bottom: 12px; }
.question-card { border: 1px solid var(--border, #d8dde5); border-radius: 10px; padding: 12px 14px; background: #fff; }
.question-prompt { margin: 0 0 10px; font-weight: 600; }
.question-card-form input[type="text"], .question-card-form input:not([type]), .question-card-form textarea,
.chip-free-row input { width: 100%; padding: 7px 9px; border: 1px solid var(--border, #d8dde5); border-radius: 6px; }
.choice-options { display: flex; flex-direction: column; gap: 6px; }
.choice-options.chips { flex-direction: row; flex-wrap: wrap; }
.chip { display: inline-flex; gap: 6px; align-items: center; border: 1px solid var(--border, #d8dde5); border-radius: 999px; padding: 4px 10px; }
.chip:has(input:checked) { background: #eff6ff; border-color: var(--accent, #1d4ed8); }
.chip-free-row { display: flex; gap: 8px; margin-top: 8px; align-items: center; }
.question-actions { display: flex; gap: 8px; margin-top: 10px; justify-content: flex-end; }
.year-month-range { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.year-month-fallback { display: inline-flex; gap: 4px; }
```

- [ ] **Step 5: 回归验证**

Run: `.venv/bin/python -m pytest -q` 和 `node --test tests/web/*.test.mjs`
Expected: 全绿。

启动 `.venv/bin/uvicorn resume_agent.api.main:app --reload`，手动验证：新建档案 → 只填目标岗位 → 出现章节导航与「你的姓名是？」卡片 → 依次回答，教育章出现学校/专业/学历/年月选择器 → 经历章出现类型选项 → 年月选择器可用（Chrome 原生月选择器）→ 刷新页面恢复进度。

- [ ] **Step 6: 提交**

```bash
git add resume_agent/web/index.html resume_agent/web/app.js resume_agent/web/styles.css
git commit -m "feat: wizard-style question cards with section progress and month pickers"
```

### Task 10: 课程词典与候选提供器（专业/课程/技能）

**Files:**
- Create: `resume_agent/domain/course_catalog.py`
- Create: `resume_agent/agents/specialists.py`（课程与技能 Agent）
- Modify: `resume_agent/domain/models.py`（`QuestionnaireState.course_options / skill_options`）
- Modify: `resume_agent/application/questionnaire.py`（服务注入顾问、选项填充、课程去后缀）
- Modify: `resume_agent/agents/runtime.py`（`course_advisor`、`skill_advisor`、能力标志）
- Modify: `resume_agent/api/app.py`（providers 接线与顾问注入）
- Modify: `resume_agent/api/main.py`（传递新 agent）
- Test: `tests/test_course_catalog.py`（新建）、`tests/test_specialists.py`（新建）、`tests/test_questionnaire.py`（追加）

**Interfaces:**
- Consumes: Task 6、Task 7
- Produces（P3~P5 依赖）：
  - `catalog_majors() -> List[str]`、`courses_for_major(major) -> List[str]`
  - `StructuredCourseAgent.recommend(major) -> List[str]`、`StructuredSkillAgent.extract(facts_text) -> List[str]`
  - `QuestionnaireService(..., course_advisor=None, skill_advisor=None)`
  - AI 课程选项以 `「课程名（AI 推荐）」` 后缀标记，写入时由服务剥掉后缀

- [ ] **Step 1: 写失败测试**

创建 `tests/test_course_catalog.py`：

```python
from resume_agent.domain.course_catalog import catalog_majors, courses_for_major


def test_catalog_has_expected_majors():
    majors = catalog_majors()
    assert "计算机科学与技术" in majors
    assert len(majors) >= 8


def test_courses_for_known_major():
    courses = courses_for_major("计算机科学与技术")
    assert "数据结构" in courses
    assert len(courses) >= 8


def test_courses_for_unknown_major_empty():
    assert courses_for_major("不存在的专业") == []
```

创建 `tests/test_specialists.py`：

```python
from resume_agent.agents.specialists import (
    StructuredCourseAgent,
    StructuredSkillAgent,
)


class QueueRunner:
    def __init__(self, responses):
        self.responses = list(responses)

    def run(self, prompt):
        return self.responses.pop(0)


def test_course_agent_returns_courses():
    agent = StructuredCourseAgent(
        QueueRunner(['{"courses": ["数据结构", "操作系统"]}'])
    )
    assert agent.recommend("计算机科学与技术") == ["数据结构", "操作系统"]


def test_skill_agent_returns_skills():
    agent = StructuredSkillAgent(
        QueueRunner(['{"skills": ["SQL", "Python"]}'])
    )
    assert agent.extract("用 SQL 和 Python 搭建看板") == ["SQL", "Python"]
```

`tests/test_questionnaire.py` 末尾追加：

```python
class FakeCourseAdvisor:
    def recommend(self, major):
        return ["机器学习"]


class FakeSkillAdvisor:
    def extract(self, facts_text):
        return ["SQL", "Python"]


def test_course_options_merge_catalog_and_advisor():
    fact_bases = FactBaseService(InMemoryFactBaseRepository())
    base = fact_bases.create()
    questionnaire = QuestionnaireService(
        fact_bases, InMemoryQuestionnaireRepository(), QuestionnaireEngine(),
        course_advisor=FakeCourseAdvisor(),
    )
    questionnaire.answer(base.id, "profile:name", value="王明")
    questionnaire.answer(base.id, "profile:email", value="wang@example.com")
    questionnaire.answer(base.id, "profile:phone", value="13800000000")
    questionnaire.skip(base.id, "profile:location")
    questionnaire.skip(base.id, "profile:links")
    questionnaire.answer(base.id, "target:role", value="数据分析师")
    questionnaire.skip(base.id, "target:city")
    questionnaire.answer(base.id, "education:add", value="开始填写")
    questionnaire.answer(base.id, "education:new:school", value="某大学")
    loaded = questionnaire.fact_bases.get(base.id)
    education_id = loaded.educations[0].id
    questionnaire.answer(
        base.id, f"education:{education_id}:major", value="计算机科学与技术"
    )
    questionnaire.answer(base.id, f"education:{education_id}:degree", value="本科")
    questionnaire.answer(
        base.id, f"education:{education_id}:period",
        extra={"start": "2020-09", "end": ""},
    )
    card = questionnaire.next_card(base.id)
    assert card.step_id == f"education:{education_id}:courses"
    assert "数据结构" in card.options
    assert "机器学习（AI 推荐）" in card.options


def test_course_answer_strips_ai_suffix():
    fact_bases = FactBaseService(InMemoryFactBaseRepository())
    base = fact_bases.create()
    questionnaire = QuestionnaireService(
        fact_bases, InMemoryQuestionnaireRepository(), QuestionnaireEngine(),
        course_advisor=FakeCourseAdvisor(),
    )
    questionnaire.answer(base.id, "profile:name", value="王明")
    questionnaire.answer(base.id, "profile:email", value="wang@example.com")
    questionnaire.answer(base.id, "profile:phone", value="13800000000")
    questionnaire.answer(base.id, "target:role", value="数据分析师")
    questionnaire.answer(base.id, "education:add", value="开始填写")
    questionnaire.answer(base.id, "education:new:school", value="某大学")
    loaded = questionnaire.fact_bases.get(base.id)
    education_id = loaded.educations[0].id
    questionnaire.answer(
        base.id, f"education:{education_id}:major", value="计算机科学与技术"
    )
    questionnaire.answer(
        base.id, f"education:{education_id}:courses",
        values=["数据结构", "机器学习（AI 推荐）"],
    )
    loaded = questionnaire.fact_bases.get(base.id)
    assert loaded.educations[0].core_courses == ["数据结构", "机器学习"]


def test_skills_options_merge_linked_and_advisor():
    base = CareerFactBase()
    base.target.role = "数据分析师"
    base.target.country = "东京"
    base.profile.name = "王明"
    base.profile.email = "wang@example.com"
    base.profile.phone = "13800000000"
    base.profile.location = "东京"
    base.profile.links = ["https://example.com"]
    base.educations.append(Education(school="某大学", major="统计", start="2020-09"))
    experience = base.add_experience("星河科技", "实习生")
    experience.linked_skills = ["Excel"]
    experience.start = "2024-06"
    experience.statements[QualityDimension.ACTION] = [
        FactValue(text="用 SQL 写查询", confidence=ConfidenceStatus.CONFIRMED)
    ]
    experience.statements[QualityDimension.RESULT] = [
        FactValue(text="被团队采用", confidence=ConfidenceStatus.CONFIRMED)
    ]
    state = QuestionnaireState(
        fact_base_id=base.id, completed_sections=["education", "experience"]
    )
    repository = InMemoryQuestionnaireRepository([state])
    questionnaire = QuestionnaireService(
        FactBaseService(InMemoryFactBaseRepository([base])),
        repository,
        QuestionnaireEngine(),
        skill_advisor=FakeSkillAdvisor(),
    )
    card = questionnaire.next_card(base.id)
    assert card.step_id == "skills:tags"
    assert "Excel" in card.options
    assert "SQL" in card.options
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_course_catalog.py tests/test_specialists.py tests/test_questionnaire.py -q`
Expected: FAIL（模块/类不存在）

- [ ] **Step 3: 实现课程词典**

创建 `resume_agent/domain/course_catalog.py`：

```python
"""Built-in major → core courses catalog for the zh wizard."""

MAJOR_COURSES = {
    "计算机科学与技术": ["数据结构", "操作系统", "计算机网络", "数据库原理", "计算机组成原理", "算法设计与分析", "软件工程", "离散数学", "编译原理", "人工智能导论"],
    "软件工程": ["数据结构", "操作系统", "计算机网络", "数据库原理", "软件工程", "面向对象程序设计", "软件测试", "软件项目管理", "Web 开发", "人机交互"],
    "数据科学与大数据技术": ["Python 程序设计", "数据结构", "数据库原理", "概率论与数理统计", "机器学习", "数据挖掘", "大数据技术", "数据可视化", "统计分析", "分布式计算"],
    "电子信息工程": ["电路分析", "模拟电子技术", "数字电子技术", "信号与系统", "通信原理", "电磁场与电磁波", "数字信号处理", "单片机原理", "嵌入式系统", "高频电子线路"],
    "机械工程": ["理论力学", "材料力学", "机械原理", "机械设计", "工程材料", "机械制造技术", "控制工程基础", "工程热力学", "机械制图", "机电传动控制"],
    "工商管理": ["管理学原理", "微观经济学", "宏观经济学", "会计学原理", "市场营销学", "组织行为学", "财务管理", "人力资源管理", "战略管理", "运营管理"],
    "金融学": ["微观经济学", "宏观经济学", "会计学原理", "货币银行学", "国际金融", "证券投资学", "公司金融", "金融风险管理", "计量经济学", "保险学"],
    "临床医学": ["人体解剖学", "生理学", "生物化学", "病理学", "药理学", "诊断学", "内科学", "外科学", "医学免疫学", "医学统计学"],
    "法学": ["法理学", "宪法学", "民法学", "刑法学", "行政法学", "民事诉讼法学", "刑事诉讼法学", "经济法学", "国际法学", "商法学"],
    "新闻传播学": ["新闻学概论", "传播学概论", "新闻采访与写作", "新闻编辑", "新闻评论", "媒介经营管理", "广告学", "公共关系学", "摄影摄像", "新媒体概论"],
    "设计学": ["设计概论", "设计素描", "色彩构成", "平面构成", "图形创意", "版式设计", "品牌设计", "交互设计", "设计软件应用", "设计史"],
}


def catalog_majors():
    return list(MAJOR_COURSES.keys())


def courses_for_major(major):
    return list(MAJOR_COURSES.get(major.strip(), []))
```

- [ ] **Step 4: 实现课程/技能 Agent**

创建 `resume_agent/agents/specialists.py`：

```python
"""Generation specialists for courses, skills, summaries and snippets."""

from typing import List

from pydantic import BaseModel, Field

from resume_agent.agents.structured import run_structured


class CoursePayload(BaseModel):
    courses: List[str] = Field(min_length=1)


class SkillsPayload(BaseModel):
    skills: List[str] = Field(min_length=1)


COURSE_RECOMMEND_PROMPT = """你是高校课程顾问。给定专业名称，推荐 5~8 门该专业最核心、最常见的本科课程名称（只输出课程名，不要编号、不要解释）。只输出 JSON：{"courses": ["课程1", "课程2", ...]}"""

SKILL_EXTRACT_PROMPT = """你是简历技能提炼员。从给定的事实文本中提取 3~8 个技能关键词（工具、语言、方法均可）。只输出事实中已出现或可直接推断的技能词，禁止编造。只输出 JSON：{"skills": ["技能1", ...]}"""


class StructuredCourseAgent:
    def __init__(self, runner) -> None:
        self.runner = runner

    def recommend(self, major: str) -> List[str]:
        prompt = f"{COURSE_RECOMMEND_PROMPT}\n专业：{major}"
        payload = run_structured(self.runner, prompt, CoursePayload)
        return [item.strip() for item in payload.courses if item.strip()]


class StructuredSkillAgent:
    def __init__(self, runner) -> None:
        self.runner = runner

    def extract(self, facts_text: str) -> List[str]:
        prompt = f"{SKILL_EXTRACT_PROMPT}\n事实文本：\n{facts_text}"
        payload = run_structured(self.runner, prompt, SkillsPayload)
        return [item.strip() for item in payload.skills if item.strip()]
```

- [ ] **Step 5: 状态字段与问卷服务顾问**

`resume_agent/domain/models.py` 的 `QuestionnaireState` 追加：

```python
    course_options: List[str] = Field(default_factory=list)
    skill_options: List[str] = Field(default_factory=list)
```

`resume_agent/application/questionnaire.py`：

`QuestionnaireService.__init__` 改为：

```python
    def __init__(
        self,
        fact_bases,
        repository,
        engine,
        course_advisor=None,
        skill_advisor=None,
    ):
        self.fact_bases = fact_bases
        self.repository = repository
        self.engine = engine
        self.course_advisor = course_advisor
        self.skill_advisor = skill_advisor
```

`next_card` 改为（skills 候选惰性填充）：

```python
    def next_card(self, fact_base_id, version=None):
        base = self.fact_bases.get(fact_base_id)
        state = self._state(fact_base_id)
        if not state.skill_options and not base.profile.skills:
            state.skill_options = self._skill_options(base)
            state.updated_at = utc_now()
            self.repository.save(state)
        return self.engine.next_card(base, state, version=version)
```

`_answer_education` 的 `major` 分支改为（填充课程候选）：

```python
        elif field == "major":
            if not value:
                raise ValueError("专业不能为空")
            education.major = value
            state.course_options = self._course_options(value)
```

`_answer_education` 的 `courses` 分支改为（剥离 AI 后缀）：

```python
        elif field == "courses":
            education.core_courses = [
                item.replace("（AI 推荐）", "").strip()
                for item in values
                if item.strip()
            ]
```

类内追加：

```python
    def _course_options(self, major):
        options = list(courses_for_major(major))
        if self.course_advisor is not None:
            try:
                for item in self.course_advisor.recommend(major):
                    if item and item not in options:
                        options.append(f"{item}（AI 推荐）")
            except Exception:
                pass  # AI 推荐失败时静默降级为词典
        return options

    def _skill_options(self, base):
        options = []
        for experience in base.experiences:
            for skill in experience.linked_skills:
                if skill and skill not in options:
                    options.append(skill)
        if self.skill_advisor is not None:
            facts_text = "\n".join(
                value.text
                for experience in base.experiences
                for values in experience.statements.values()
                for value in values
            )
            try:
                for skill in self.skill_advisor.extract(facts_text):
                    if skill and skill not in options:
                        options.append(skill)
            except Exception:
                pass
        return options
```

（顶部 import 补 `from resume_agent.domain.course_catalog import courses_for_major`。）

- [ ] **Step 6: 运行时与装配**

`resume_agent/agents/runtime.py`：

`AgentCapabilityStatus` 追加：

```python
    course_recommendation: bool = False
    skill_suggestions: bool = False
```

`ready()` 类方法中相应字段置 `True`：

```python
        return cls(
            status="ready",
            mentor=True,
            fact_audit=True,
            question_writer=True,
            course_recommendation=True,
            skill_suggestions=True,
            model=model,
        )
```

import 补 `from resume_agent.agents.specialists import StructuredCourseAgent, StructuredSkillAgent`。

`MentorRuntime` 追加字段：

```python
    course_advisor: Optional[StructuredCourseAgent] = None
    skill_advisor: Optional[StructuredSkillAgent] = None
```

`build_mentor_runtime` 中在 `question_runner` 之后追加：

```python
    course_runner = FreshAgentRunner(
        lambda: framework.SimpleAgent(
            name="核心课程推荐",
            llm=llm,
            system_prompt=COURSE_RECOMMEND_PROMPT,
            config=_private_agent_config(framework),
        )
    )
    skill_runner = FreshAgentRunner(
        lambda: framework.SimpleAgent(
            name="技能关键词提炼",
            llm=llm,
            system_prompt=SKILL_EXTRACT_PROMPT,
            config=_private_agent_config(framework),
        )
    )
```

（import 补 `COURSE_RECOMMEND_PROMPT`、`SKILL_EXTRACT_PROMPT`。）

`MentorRuntime(...)` 构造调用追加：

```python
        course_advisor=StructuredCourseAgent(course_runner),
        skill_advisor=StructuredSkillAgent(skill_runner),
```

`resume_agent/api/app.py`：

`create_app` 签名追加 `course_advisor=None, skill_advisor=None`；`QuestionnaireEngine()` 构造改为：

```python
    questionnaire_service = QuestionnaireService(
        fact_base_service,
        SQLiteQuestionnaireRepository(store),
        QuestionnaireEngine(
            options_providers={
                "majors": lambda base, state: catalog_majors(),
                "courses": lambda base, state: list(state.course_options),
                "skills": lambda base, state: list(state.skill_options),
            }
        ),
        course_advisor=course_advisor,
        skill_advisor=skill_advisor,
    )
```

（import 补 `catalog_majors`。）

`resume_agent/api/main.py` 的 `create_default_app` 追加：

```python
        course_advisor=runtime.course_advisor,
        skill_advisor=runtime.skill_advisor,
```

- [ ] **Step 7: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_course_catalog.py tests/test_specialists.py tests/test_questionnaire.py tests/test_agent_runtime.py tests/test_api_capabilities.py -q`
Expected: PASS

- [ ] **Step 8: 提交**

```bash
git add resume_agent/domain/course_catalog.py resume_agent/agents/specialists.py resume_agent/domain/models.py resume_agent/application/questionnaire.py resume_agent/agents/runtime.py resume_agent/api/app.py resume_agent/api/main.py tests/test_course_catalog.py tests/test_specialists.py tests/test_questionnaire.py
git commit -m "feat: course catalog with ai-recommended course and skill candidates"
```

---

### Task 11: 中文渲染新章节（教育、技能、类型分组）

**Files:**
- Modify: `resume_agent/rendering/models.py`（`RenderedEducation`、`RenderedExperience.type`、`RenderedResume.educations`）
- Modify: `resume_agent/rendering/renderer.py`（zh 布局）
- Modify: `tests/test_resume_renderer.py`（zh 标题断言更新 + 新增用例）

**Interfaces:**
- Consumes: Task 4（Education、ExperienceType、profile.skills）
- Produces（Task 14/17 依赖）：`_zh_markdown(...)`、`_zh_html(...)` 独立方法；`RenderedEducation(school, major, degree, period, courses)`；`RenderedExperience.type`

- [ ] **Step 1: 写失败测试**

`tests/test_resume_renderer.py` 末尾追加：

```python
from resume_agent.domain.models import Education, ExperienceType
from resume_agent.rendering.models import RenderedEducation


def test_zh_renders_education_section():
    base, first, _ = evidence_fixture()
    base.educations.append(
        Education(school="某大学", major="统计学", degree="本科",
                  start="2020-09", core_courses=["概率论", "数理统计"])
    )
    version = make_version(base, [first], locale="zh")
    rendered = ResumeRenderer().render(base, version)
    assert "## 教育背景" in rendered.markdown
    assert "某大学" in rendered.markdown
    assert "核心课程：概率论、数理统计" in rendered.markdown
    assert "教育背景" in rendered.html
    assert any(item.school == "某大学" for item in rendered.educations)


def test_zh_groups_experiences_by_type():
    base, first, second = evidence_fixture()
    second.type = ExperienceType.CAMPUS
    version = make_version(base, [first, second], locale="zh")
    rendered = ResumeRenderer().render(base, version)
    assert "## 实习/工作经历" in rendered.markdown
    assert "## 校园及项目经历" in rendered.markdown
    assert "校园及项目经历" in rendered.html


def test_zh_skills_section_uses_profile_skills():
    base, first, _ = evidence_fixture()
    base.profile.skills = ["SQL", "Python"]
    first.linked_skills = []
    version = make_version(base, [first], locale="zh")
    rendered = ResumeRenderer().render(base, version)
    assert "## 技能" in rendered.markdown
    assert "SQL · Python" in rendered.markdown
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_resume_renderer.py -q`
Expected: FAIL（`RenderedEducation` 不存在 / 教育章节未渲染）

- [ ] **Step 3: 渲染模型**

`resume_agent/rendering/models.py`：import 补 `ExperienceType`、`VersionSnippet`，追加：

```python
class RenderedEducation(BaseModel):
    school: str
    major: str = ""
    degree: str = ""
    period: str = ""
    courses: List[str] = Field(default_factory=list)
```

`RenderedExperience` 追加：

```python
    id: UUID = Field(default_factory=uuid4)
    type: ExperienceType = ExperienceType.WORK
```

`RenderedResume` 追加：

```python
    educations: List[RenderedEducation] = Field(default_factory=list)
    self_summary: str = ""
    custom_snippets: List[VersionSnippet] = Field(default_factory=list)
```

（`self_summary`、`custom_snippets` 由 Task 14/17 使用，此处先带默认值落地；`RenderedExperience.id` 为经历 UUID，供 Task 17 的 `data-section="experience:{uuid}"` 落点使用。）

- [ ] **Step 4: 渲染器 zh 布局**

`resume_agent/rendering/renderer.py`：

import 补 `ExperienceType`、`RenderedEducation`。

`COPY["zh"]` 增加（并删除旧 `"experience"` 键值以强制分支）：

```python
    "zh": {
        "title": "简历",
        "education": "教育背景",
        "internshipWork": "实习/工作经历",
        "campusProjects": "校园及项目经历",
        "skills": "技能",
        "courses": "核心课程",
        "summary": "职业概述",
        "target": "求职意向",
        "present": "至今",
    },
```

`render()` 中，在 `experiences, has_estimates = ...` 之后追加：

```python
        educations = self._resolve_educations(base)
```

`RenderedExperience` 构造中补 `id=experience.id, type=experience.type,`；返回的 `RenderedResume(...)` 构造中补 `educations=educations,`。

`_markdown` 开头改为分支：

```python
        copy = COPY[locale]
        if locale == "zh":
            return self._zh_markdown(
                candidate_name, headline, contact_line, summary,
                experiences, skills, educations, version,
            )
```

`_html` 末尾 `return (...)` 之前改为分支（`experience_html`/`skills_html` 计算保留，新增 zh 分支）：

```python
        if locale == "zh":
            return self._zh_html(
                theme, candidate_name, headline, contact_line,
                experiences, skills, educations, version,
            )
```

新增方法（放在 `_markdown` 之前）：

```python
    def _resolve_educations(self, base):
        return [
            RenderedEducation(
                school=education.school,
                major=education.major,
                degree=education.degree,
                period=self._period(education.start, education.end or "", "zh"),
                courses=list(education.core_courses),
            )
            for education in base.educations
        ]

    @staticmethod
    def _zh_group(experiences):
        work = [
            item for item in experiences
            if item.type in (ExperienceType.WORK, ExperienceType.INTERNSHIP)
        ]
        campus = [
            item for item in experiences
            if item.type not in (ExperienceType.WORK, ExperienceType.INTERNSHIP)
        ]
        return work, campus

    def _zh_markdown(self, candidate_name, headline, contact_line, summary,
                     experiences, skills, educations, version):
        copy = COPY["zh"]
        lines = [f"# {self._markdown_escape(candidate_name)}", ""]
        if headline:
            lines.append(f"**{copy['target']}：** {self._markdown_escape(headline)}")
            lines.append("")
        if contact_line:
            lines.append(self._markdown_escape(contact_line))
            lines.append("")
        if educations:
            lines.append(f"## {copy['education']}")
            lines.append("")
            for education in educations:
                meta = " | ".join(
                    item for item in (education.major, education.degree, education.period) if item
                )
                heading = education.school + (f" | {meta}" if meta else "")
                lines.append(f"### {self._markdown_escape(heading)}")
                lines.append("")
                if education.courses:
                    lines.append(
                        f"{copy['courses']}："
                        + "、".join(self._markdown_escape(item) for item in education.courses)
                    )
                    lines.append("")
        work, campus = self._zh_group(experiences)
        for heading, group in ((copy["internshipWork"], work), (copy["campusProjects"], campus)):
            if not group:
                continue
            lines.append(f"## {heading}")
            lines.append("")
            for experience in group:
                experience_heading = f"{experience.role} — {experience.organization}"
                if experience.period:
                    experience_heading += f" | {experience.period}"
                lines.append(f"### {self._markdown_escape(experience_heading)}")
                lines.append("")
                lines.extend(f"- {self._markdown_escape(item)}" for item in experience.bullets)
                lines.append("")
        if skills:
            lines.append(f"## {copy['skills']}")
            lines.append("")
            lines.append(" · ".join(self._markdown_escape(item) for item in skills))
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    def _zh_html(self, theme, candidate_name, headline, contact_line,
                 experiences, skills, educations, version):
        copy = COPY["zh"]
        escape = lambda value: html.escape(value, quote=True)
        css = f"""
        :root {{--accent:{theme.accent};--secondary:{theme.secondary};--tint:{theme.tint};--border:{theme.border};}}
        @page {{ size: A4; margin: 14mm 16mm; }}
        * {{ box-sizing: border-box; }}
        body {{ font-family:{theme.font_family}; color:#1f2937; font-size:10pt; line-height:1.58; margin:0; }}
        header {{ border-bottom:2.2pt solid var(--accent); padding-bottom:3mm; margin-bottom:5mm; }}
        h1 {{ color:var(--accent); font-size:21pt; margin:0; letter-spacing:.4px; }}
        .headline {{ color:var(--secondary); font-size:10.5pt; margin:1mm 0; }}
        .contact,.meta {{ color:#5f6772; font-size:9pt; margin:.8mm 0; }}
        h2 {{ color:var(--accent); font-size:11.5pt; border-left:3.5pt solid var(--accent); padding-left:2.5mm; margin:5mm 0 2mm; }}
        h3 {{ font-size:10.5pt; margin:2.5mm 0 .5mm; color:#20252b; }}
        p {{ margin:1mm 0; }}
        ul {{ margin:1mm 0 2mm; padding-left:5mm; }}
        li {{ margin:.7mm 0; }}
        li::marker {{ color:var(--accent); }}
        .skill {{ display:inline-block; background:var(--tint); border:.5pt solid var(--border); border-radius:2.5mm; padding:.5mm 2.2mm; margin:.5mm; color:var(--accent); font-size:9pt; }}
        .drop-zone {{ border-radius:3mm; transition: outline .1s; }}
        .drop-zone.drop-active {{ outline: 2.2pt dashed var(--accent); outline-offset: 2mm; }}
        """
        contact = f'<p class="contact">{escape(contact_line)}</p>' if contact_line else ""
        education_html = []
        for education in educations:
            meta = " · ".join(
                item for item in (education.major, education.degree, education.period) if item
            )
            courses = (
                f'<p class="meta">{copy["courses"]}：'
                + "、".join(escape(item) for item in education.courses)
                + "</p>"
                if education.courses else ""
            )
            education_html.append(
                f'<section class="education"><h3>{escape(education.school)}</h3>'
                f'<p class="meta">{escape(meta)}</p>{courses}</section>'
            )
        work, campus = self._zh_group(experiences)
        groups_html = []
        for heading, group in ((copy["internshipWork"], work), (copy["campusProjects"], campus)):
            if not group:
                continue
            section_html = []
            for experience in group:
                meta = " · ".join(
                    item for item in (experience.organization, experience.period) if item
                )
                bullets = "".join(
                    f"<li>{escape(item)}</li>" for item in experience.bullets
                )
                section_html.append(
                    f'<section class="experience drop-zone" data-section="experience:{experience.id}">'
                    f"<h3>{escape(experience.role)}</h3>"
                    f'<p class="meta">{escape(meta)}</p><ul>{bullets}</ul></section>'
                )
            groups_html.append(f"<h2>{heading}</h2>{''.join(section_html)}")
        skills_html = "".join(f'<span class="skill">{escape(item)}</span>' for item in skills)
        skills_section = f"<h2>{copy['skills']}</h2><div>{skills_html}</div>" if skills else ""
        education_section = (
            f"<h2>{copy['education']}</h2>{''.join(education_html)}" if educations else ""
        )
        body = (
            f'<header><h1>{escape(candidate_name)}</h1>'
            f'<p class="headline">{copy["target"]}：{escape(headline)}</p>'
            f"{contact}</header>"
            f"{education_section}"
            f"{''.join(groups_html)}"
            f"{skills_section}"
        )
        return (
            "<!DOCTYPE html>\n"
            f'<html lang="zh"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{escape(copy["title"])}</title><style>{css}</style></head>'
            f"<body>{body}</body></html>"
        )
```

（`_zh_html` 的 `version` 参数本任务暂不使用，Task 17 将用于片段与自定义区；`data-section="experience:{uuid}"` 落点已就绪。）

- [ ] **Step 5: 更新既有中文断言**

`tests/test_resume_renderer.py` 第 102 行参数化元组：

```python
        ("zh", "实习/工作经历", "简历"),
```

（其余 ja/en 行不动；若还有断言 `## 工作经历` 或 `## 职业概述` 的中文用例，同步改为新标题。ja/en 断言保持原样。）

- [ ] **Step 6: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_resume_renderer.py tests/test_resume_exporters.py tests/test_api_rendering.py -q`
Expected: PASS（ja/en 布局未变；zh 使用新布局）

- [ ] **Step 7: 提交**

```bash
git add resume_agent/rendering/models.py resume_agent/rendering/renderer.py tests/test_resume_renderer.py
git commit -m "feat: zh resume sections for education, skills and typed experience groups"
```

---

### Task 12: 前端默认版本与预览联动

**Files:**
- Modify: `resume_agent/web/questionnaire.js`（`defaultZhVersionName`）
- Modify: `resume_agent/web/app.js`（handleOnboarding 建默认版本；answerQuestionCard 后刷新预览）
- Test: `tests/web/questionnaire.test.mjs`（追加）

**Interfaces:**
- Consumes: Task 9、Task 11
- Produces: 新档案从第一问起右侧就有可更新的中文预览

- [ ] **Step 1: 写失败测试**

`tests/web/questionnaire.test.mjs` 末尾追加：

```js
import { defaultZhVersionName } from "../../resume_agent/web/questionnaire.js";


test("defaultZhVersionName formats the zh version name", () => {
  assert.equal(defaultZhVersionName("数据分析师"), "中文简历 · 数据分析师");
  assert.equal(defaultZhVersionName(""), "中文简历 · 通用岗位");
});
```

- [ ] **Step 2: 运行确认失败**

Run: `node --test tests/web/questionnaire.test.mjs`
Expected: FAIL（导出不存在）

- [ ] **Step 3: 实现**

`resume_agent/web/questionnaire.js` 末尾追加：

```javascript
export function defaultZhVersionName(role) {
  return `中文简历 · ${role || "通用岗位"}`;
}
```

`resume_agent/web/app.js`：

import 行补 `defaultZhVersionName`。

`handleOnboarding` 中 `await activateBase(base);` 之后追加：

```javascript
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
```

`answerQuestionCard` 中 `await refreshQuestionnaire();` 之后追加 `await renderDocument();`，即：

```javascript
    await refreshQuestionnaire();
    await renderDocument();
    renderConversation();
```

- [ ] **Step 4: 回归与人工验证**

Run: `node --test tests/web/*.test.mjs` 和 `.venv/bin/python -m pytest -q`
Expected: 全绿。

启动应用手动验证：新建档案 → 回答基本信息后，右侧预览出现姓名、邮箱；填教育后预览出现「教育背景」章节与核心课程；经历类型/名称/角色/时间逐项回答后预览出现对应分组章节。

- [ ] **Step 5: 提交**

```bash
git add resume_agent/web/questionnaire.js resume_agent/web/app.js tests/web/questionnaire.test.mjs
git commit -m "feat: default zh version creation and live preview updates"
```

### Task 13: 自我评价备选生成（grounding + 离线模板 + 版本 API）

**Files:**
- Create: `resume_agent/domain/grounding.py`
- Create: `resume_agent/application/summary_service.py`
- Modify: `resume_agent/agents/specialists.py`（`StructuredSummaryAgent`）
- Modify: `resume_agent/application/version_service.py`（`set_summary_options`、`set_summary`）
- Modify: `resume_agent/api/schemas.py`（`SummarySetRequest`）
- Modify: `resume_agent/api/app.py`（`summaries` 容器、两个端点、questionnaire answer 的 summary 特例）
- Modify: `resume_agent/agents/runtime.py`、`resume_agent/api/main.py`（summary_writer 装配与能力标志）
- Test: `tests/test_grounding.py`、`tests/test_summary_service.py`、`tests/test_api_summary.py`（均新建）

**Interfaces:**
- Consumes: Task 4（`ResumeVersion.summary_options/selected_summary`）、Task 7（问卷 answer 路由）
- Produces（Task 15 依赖）：
  - `POST /versions/{id}/summary-options/generate` → `{"options": List[str]}`（写入 `summary_options`）
  - `PUT /versions/{id}/summary` `{text}` → ResumeVersion
  - `extract_numbers(text)`、`collect_fact_texts(base, version)`、`offline_summary_options(base, target_role)`
  - 无幻觉规则：备选不得包含事实库之外的数字，违规备选丢弃后以离线模板补齐至 ≥3 条

- [ ] **Step 1: 写失败测试**

创建 `tests/test_grounding.py`：

```python
from resume_agent.domain.grounding import collect_fact_texts, extract_numbers
from resume_agent.domain.models import (
    CareerFactBase, ConfidenceStatus, FactValue, QualityDimension, ResumeVersion,
)


def test_extract_numbers():
    assert extract_numbers("将耗时从 4 小时降到 30 分钟") == {"4", "30"}


def test_collect_fact_texts_uses_selected_experiences():
    base = CareerFactBase()
    selected = base.add_experience("星河科技", "实习生")
    other = base.add_experience("远帆科技", "实习生")
    selected.statements[QualityDimension.ACTION] = [
        FactValue(text="搭建看板", confidence=ConfidenceStatus.CONFIRMED)
    ]
    other.statements[QualityDimension.ACTION] = [
        FactValue(text="写周报", confidence=ConfidenceStatus.CONFIRMED)
    ]
    version = ResumeVersion(
        fact_base_id=base.id, name="默认版本",
        selected_experience_ids=[selected.id],
    )
    texts = collect_fact_texts(base, version)
    assert "搭建看板" in texts
    assert "写周报" not in texts
```

创建 `tests/test_summary_service.py`：

```python
from resume_agent.application.summary_service import (
    SummaryService,
    offline_summary_options,
)
from resume_agent.domain.models import (
    CareerFactBase, ConfidenceStatus, FactValue, QualityDimension, ResumeVersion,
)


class FakeSummaryAgent:
    def __init__(self, options):
        self.options = list(options)

    def generate(self, facts_text, skills, target_role):
        return list(self.options)


def test_offline_summary_has_three_options():
    base = CareerFactBase()
    base.profile.skills = ["SQL"]
    options = offline_summary_options(base, "数据分析师")
    assert len(options) == 3
    assert all(options)


def test_generate_drops_fabricated_numbers():
    base = CareerFactBase()
    base.profile.skills = ["SQL"]
    experience = base.add_experience("星河科技", "实习生")
    experience.statements[QualityDimension.ACTION] = [
        FactValue(text="搭建看板", confidence=ConfidenceStatus.CONFIRMED)
    ]
    version = ResumeVersion(
        fact_base_id=base.id, name="默认版本",
        target_role="数据分析师", selected_experience_ids=[experience.id],
    )
    service = SummaryService(FakeSummaryAgent([
        "将看板效率提升了50个百分点，团队反馈良好，工作扎实可靠，适合数据分析岗位。",
    ]))
    options = service.generate(base, version)
    assert not any("50" in item for item in options)
    assert len(options) >= 3


def test_generate_keeps_grounded_options():
    base = CareerFactBase()
    base.profile.skills = ["SQL"]
    experience = base.add_experience("星河科技", "实习生")
    experience.statements[QualityDimension.ACTION] = [
        FactValue(text="搭建看板", confidence=ConfidenceStatus.CONFIRMED)
    ]
    version = ResumeVersion(
        fact_base_id=base.id, name="默认版本",
        target_role="数据分析师", selected_experience_ids=[experience.id],
    )
    grounded = [
        "具备数据类实习经历，熟悉SQL与看板搭建方法，能够快速融入团队协作节奏，适合数据分析岗位。",
        "目标导向，善于拆解业务问题并用数据分析工具推进落地，注重过程记录与结果验证方法。",
        "学习能力强，乐于承担新挑战，持续在数据分析方向积累实践经验与解决问题的方法论。",
    ]
    service = SummaryService(FakeSummaryAgent(grounded))
    assert service.generate(base, version) == grounded
```

创建 `tests/test_api_summary.py`：

```python
from fastapi.testclient import TestClient

from resume_agent.api.app import create_app


def test_generate_summary_options_offline(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post(
            "/fact-bases", json={"target": {"role": "数据分析师"}}
        ).json()
        version = client.post(
            f"/fact-bases/{base['id']}/versions",
            json={"name": "默认版本", "locale": "zh", "selected_experience_ids": []},
        ).json()
        response = client.post(f"/versions/{version['id']}/summary-options/generate")
        assert response.status_code == 200
        options = response.json()["options"]
        assert len(options) >= 3
        picked = options[0]
        put = client.put(
            f"/versions/{version['id']}/summary", json={"text": picked}
        )
        assert put.status_code == 200
        assert put.json()["selected_summary"] == picked


def test_questionnaire_summary_pick_writes_version_summary(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post(
            "/fact-bases", json={"target": {"role": "数据分析师"}}
        ).json()
        version = client.post(
            f"/fact-bases/{base['id']}/versions",
            json={"name": "默认版本", "locale": "zh", "selected_experience_ids": []},
        ).json()
        options = client.post(
            f"/versions/{version['id']}/summary-options/generate"
        ).json()["options"]
        answer = client.post(
            f"/fact-bases/{base['id']}/questionnaire/answer",
            json={"step_id": "summary:pick", "values": [options[0]]},
        )
        assert answer.status_code == 200
        fetched = client.get(f"/versions/{version['id']}")
        assert fetched.json()["selected_summary"] == options[0]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_grounding.py tests/test_summary_service.py tests/test_api_summary.py -q`
Expected: FAIL（模块不存在 / 路由 404）

- [ ] **Step 3: 实现 grounding 与 summary 服务**

创建 `resume_agent/domain/grounding.py`：

```python
"""Grounding checks for generated self-summary options."""

import re

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def extract_numbers(text: str):
    return set(NUMBER_RE.findall(text))


def collect_fact_texts(base, version):
    texts = []
    selected = set(version.selected_experience_ids or [])
    for experience in base.experiences:
        if selected and experience.id not in selected:
            continue
        for values in experience.statements.values():
            texts.extend(value.text for value in values)
    return texts
```

创建 `resume_agent/application/summary_service.py`：

```python
"""Self-summary candidate generation for zh resumes."""

from resume_agent.domain.grounding import collect_fact_texts, extract_numbers


def offline_summary_options(base, target_role):
    skills = "、".join(base.profile.skills[:3]) or "相关技能"
    count = len([
        experience for experience in base.experiences
        if any(values for values in experience.statements.values())
    ])
    role = target_role or "目标岗位"
    return [
        f"具备{count}段相关实践经历，熟悉{skills}，能快速融入团队协作节奏。",
        f"目标导向，善于拆解问题并用{skills}推进落地，注重用数据与结果说话。",
        f"学习能力强，乐于承担挑战，持续在{role}方向积累经验与方法论。",
    ]


class SummaryService:
    def __init__(self, agent=None):
        self.agent = agent

    def generate(self, base, version):
        facts_text = "\n".join(collect_fact_texts(base, version))
        skills = "、".join(base.profile.skills[:5]) or "相关技能"
        role = version.target_role or base.target.role or "目标岗位"
        allowed = extract_numbers(facts_text)
        options = []
        if self.agent is not None:
            try:
                options = [
                    item for item in self.agent.generate(facts_text, skills, role)
                    if not (extract_numbers(item) - allowed) and 40 <= len(item) <= 70
                ]
            except Exception:
                options = []
        if len(options) < 3:
            options = options + offline_summary_options(base, role)
        return options[:5]
```

- [ ] **Step 4: 实现 Summary Agent**

`resume_agent/agents/specialists.py` 追加：

```python
class SummaryOptionsPayload(BaseModel):
    options: List[str] = Field(min_length=3, max_length=5)


SUMMARY_OPTIONS_PROMPT = """你是简历自我评价撰写顾问。基于给定的已确认经历事实、技能和目标岗位，撰写 3~5 条中文自我评价备选（每条 40~70 字），风格错开（稳重 / 进取 / 技术驱动等）。严格基于给定内容：禁止出现给定事实之外的数字、公司名、职位名。只输出 JSON：{"options": ["备选1", "备选2", ...]}"""


class StructuredSummaryAgent:
    def __init__(self, runner) -> None:
        self.runner = runner

    def generate(self, facts_text: str, skills: str, target_role: str) -> List[str]:
        prompt = (
            f"{SUMMARY_OPTIONS_PROMPT}\n"
            f"目标岗位：{target_role}\n"
            f"技能：{skills}\n"
            f"已确认事实：\n{facts_text}"
        )
        payload = run_structured(self.runner, prompt, SummaryOptionsPayload)
        return [item.strip() for item in payload.options if item.strip()]
```

- [ ] **Step 5: 版本服务与请求模型**

`resume_agent/application/version_service.py` 追加：

```python
    def set_summary_options(self, version_id: UUID, options: List[str]) -> ResumeVersion:
        version = self.repository.get(version_id)
        version.summary_options = list(options)
        return self.save(version)

    def set_summary(self, version_id: UUID, text: str) -> ResumeVersion:
        version = self.repository.get(version_id)
        version.selected_summary = text.strip()
        return self.save(version)
```

`resume_agent/api/schemas.py` 追加：

```python
class SummarySetRequest(BaseModel):
    text: str = Field(min_length=1)
```

- [ ] **Step 6: 端点与装配**

`resume_agent/api/app.py`：

import 补 `SummaryService`、`SummarySetRequest`；`ServiceContainer` 追加 `summaries: SummaryService`；`create_app` 签名追加 `summary_agent=None`；容器构造追加 `summaries=SummaryService(summary_agent),`。

questionnaire answer 路由中，在计算 `version` 之后追加特例：

```python
        if payload.step_id == "summary:pick" and version is not None:
            container.versions.set_summary(
                version.id,
                "；".join(value for value in payload.values if value.strip()),
            )
```

路由区追加：

```python
    @app.post("/versions/{version_id}/summary-options/generate")
    def generate_summary_options(version_id: UUID):
        version = container.version_repository.get(version_id)
        base = container.fact_base_repository.get(version.fact_base_id)
        options = container.summaries.generate(base, version)
        updated = container.versions.set_summary_options(version_id, options)
        return {"options": updated.summary_options}

    @app.put("/versions/{version_id}/summary")
    def set_version_summary(version_id: UUID, payload: SummarySetRequest):
        return container.versions.set_summary(version_id, payload.text)
```

`resume_agent/agents/runtime.py`：`AgentCapabilityStatus` 追加 `summary_options: bool = False` 并在 `ready()` 置 `True`；`MentorRuntime` 追加 `summary_writer: Optional[StructuredSummaryAgent] = None`；`build_mentor_runtime` 中追加：

```python
    summary_runner = FreshAgentRunner(
        lambda: framework.SimpleAgent(
            name="自我评价备选",
            llm=llm,
            system_prompt=SUMMARY_OPTIONS_PROMPT,
            config=_private_agent_config(framework),
        )
    )
```

并在 `MentorRuntime(...)` 构造追加 `summary_writer=StructuredSummaryAgent(summary_runner),`（import 补 `StructuredSummaryAgent`、`SUMMARY_OPTIONS_PROMPT`）。

`resume_agent/api/main.py` 追加 `summary_agent=runtime.summary_writer,`。

- [ ] **Step 7: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_grounding.py tests/test_summary_service.py tests/test_api_summary.py tests/test_api_capabilities.py tests/test_agent_runtime.py -q`
Expected: PASS（若 `test_api_capabilities` 断言了能力字典的精确键集合，把新增键补进断言）

- [ ] **Step 8: 提交**

```bash
git add resume_agent/domain/grounding.py resume_agent/application/summary_service.py resume_agent/agents/specialists.py resume_agent/application/version_service.py resume_agent/api/schemas.py resume_agent/api/app.py resume_agent/agents/runtime.py resume_agent/api/main.py tests/test_grounding.py tests/test_summary_service.py tests/test_api_summary.py
git commit -m "feat: grounded self-summary options with offline templates"
```

---

### Task 14: 渲染自我评价章节

**Files:**
- Modify: `resume_agent/rendering/renderer.py`（`selfSummary` 文案、`self_summary` 字段、zh 布局插入）
- Test: `tests/test_resume_renderer.py`（追加）

**Interfaces:**
- Consumes: Task 11 的 `_zh_markdown`/`_zh_html`、Task 13 的 `version.selected_summary`
- Produces: `RenderedResume.self_summary`；中文简历含「自我评价」章节（求职意向之后、教育之前）

- [ ] **Step 1: 写失败测试**

`tests/test_resume_renderer.py` 末尾追加：

```python
def test_zh_renders_self_summary_when_selected():
    base, first, _ = evidence_fixture()
    version = make_version(base, [first], locale="zh")
    version.selected_summary = "目标导向，数据驱动。"
    rendered = ResumeRenderer().render(base, version)
    assert "## 自我评价" in rendered.markdown
    assert "目标导向，数据驱动。" in rendered.markdown
    assert "自我评价" in rendered.html
    assert rendered.self_summary == "目标导向，数据驱动。"


def test_zh_omits_self_summary_when_empty():
    base, first, _ = evidence_fixture()
    version = make_version(base, [first], locale="zh")
    rendered = ResumeRenderer().render(base, version)
    assert "自我评价" not in rendered.markdown
    assert rendered.self_summary == ""
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_resume_renderer.py -q`
Expected: FAIL（自我评价未渲染）

- [ ] **Step 3: 实现**

`resume_agent/rendering/renderer.py`：

`COPY["zh"]` 追加 `"selfSummary": "自我评价",`。

`render()` 的 `RenderedResume(...)` 构造追加 `self_summary=version.selected_summary,`。

`_zh_markdown` 中，`contact_line` 代码块之后插入：

```python
        if version.selected_summary:
            lines.append(f"## {copy['selfSummary']}")
            lines.append("")
            lines.append(self._markdown_escape(version.selected_summary))
            lines.append("")
```

`_zh_html` 中，`contact` 变量之后插入：

```python
        summary_section = (
            f"<h2>{copy['selfSummary']}</h2><p>{escape(version.selected_summary)}</p>"
            if version.selected_summary else ""
        )
```

`body` 中 `f"{contact}</header>"` 之后插入 `f"{summary_section}"`。

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_resume_renderer.py tests/test_resume_exporters.py tests/test_api_rendering.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add resume_agent/rendering/renderer.py tests/test_resume_renderer.py
git commit -m "feat: render self-summary section in zh resumes"
```

---

### Task 15: 前端自我评价 UI

**Files:**
- Modify: `resume_agent/web/api.js`（2 个方法）
- Modify: `resume_agent/web/app.js`（`questionAreaElement` 扩展、生成按钮、完成卡片）
- Test: `tests/web/api.test.mjs`（追加）

**Interfaces:**
- Consumes: Task 13 端点、Task 9 的 `questionAreaElement`
- Produces: 全部章节完成后的向导收尾体验；自我评价备选以 `summary:pick` 多选卡呈现

- [ ] **Step 1: 写失败测试**

`tests/web/api.test.mjs` 末尾追加：

```js
test("summary endpoints post the right contracts", async () => {
  const calls = [];
  const api = createApi(async (url, init) => {
    calls.push([url, init]);
    return new Response(JSON.stringify({ options: ["备选一"] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });

  await api.generateSummaryOptions("v-1");
  await api.setVersionSummary("v-1", "备选一");

  assert.equal(calls[0][0], "/versions/v-1/summary-options/generate");
  assert.equal(calls[0][1].method, "POST");
  assert.equal(calls[1][0], "/versions/v-1/summary");
  assert.equal(calls[1][1].method, "PUT");
  assert.deepEqual(JSON.parse(calls[1][1].body), { text: "备选一" });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `node --test tests/web/api.test.mjs`
Expected: FAIL（方法不存在）

- [ ] **Step 3: 实现**

`resume_agent/web/api.js` 追加：

```javascript
    generateSummaryOptions: (versionId) => request(
      `/versions/${versionId}/summary-options/generate`,
      { method: "POST" },
    ),
    setVersionSummary: (versionId, text) => request(
      `/versions/${versionId}/summary`,
      { method: "PUT", body: JSON.stringify({ text }) },
    ),
```

`resume_agent/web/app.js`：用下面的版本**替换** Task 9 中的 `questionAreaElement`：

```javascript
function questionAreaElement() {
  const area = element("div", "question-area");
  const card = questionnaireState?.next;
  if (card) {
    area.append(renderQuestionCard(card));
    return area;
  }
  const progress = questionnaireState?.progress || [];
  if (progress.length && progress.every((item) => item.done)) {
    const done = element("article", "question-card complete-card");
    done.append(element(
      "p", "question-prompt",
      "🎉 各章节已收集完毕，可在右侧预览微调并导出 PDF 等格式。",
    ));
    area.append(done);
    return area;
  }
  const summary = progress.find((item) => item.section === "summary");
  if (summary && !summary.done && currentVersion) {
    area.append(summaryGenerateCard());
  }
  return area;
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
  } catch (error) {
    if (!baseActivationGate.isCurrent(baseGeneration)) return;
    showToast(error instanceof ApiError ? error.message : "自我评价生成失败");
  }
}
```

- [ ] **Step 4: 回归与人工验证**

Run: `node --test tests/web/*.test.mjs` 和 `.venv/bin/python -m pytest -q`
Expected: 全绿。

手动验证：走完前五章（技能跳过亦可）→ 出现「生成自我评价备选」→ 点击后显示 chips → 勾选 1~2 条点确定 → 右侧预览出现「自我评价」章节 → 章节导航全绿 → 出现完成卡片。

- [ ] **Step 5: 提交**

```bash
git add resume_agent/web/api.js resume_agent/web/app.js tests/web/api.test.mjs
git commit -m "feat: summary option chips in the wizard"
```

---

### Task 16: 片段卡生成（润色 + 离线退化）

**Files:**
- Modify: `resume_agent/agents/specialists.py`（`StructuredSnippetAgent`）
- Modify: `resume_agent/agents/runtime.py`、`resume_agent/api/main.py`（snippet_writer 装配与能力标志）
- Modify: `resume_agent/api/app.py`（`snippet_agent` 参数与 generate 端点）
- Modify: `resume_agent/web/api.js`（`generateSnippets`）
- Test: `tests/test_api_snippets.py`（新建）、`tests/web/api.test.mjs`（追加）

**Interfaces:**
- Consumes: Task 4（`VersionSnippet.source_fact_ids`）、Task 7（事实库/会话 API）
- Produces（Task 18 依赖）：
  - `POST /fact-bases/{id}/experiences/{exp_id}/snippets/generate` → `{"snippets": [{text, source_fact_ids: [str]}]}`（仅含已确认/估算事实；无事实返回 `[]`；离线 = 事实原话卡）
  - `api.generateSnippets(factBaseId, experienceId)`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_api_snippets.py`：

```python
from fastapi.testclient import TestClient

from resume_agent.api.app import create_app
from tests.fakes import StubAuditAgent, StubQuestionWriter


class FakeSnippetAgent:
    def write(self, experience, facts_text):
        return ["搭建并维护了用户留存看板"]


def build_base_with_confirmed_fact(client):
    base = client.post(
        "/fact-bases", json={"target": {"role": "数据分析师"}}
    ).json()
    base = client.post(
        f"/fact-bases/{base['id']}/experiences",
        json={"organization": "星河科技", "role": "实习生"},
    ).json()
    experience = base["experiences"][0]
    session = client.post(
        "/sessions",
        json={"fact_base_id": base["id"], "active_experience_id": experience["id"]},
    ).json()
    proposal = client.post(
        f"/sessions/{session['id']}/answers", json={"message": "搭建看板"}
    ).json()["proposal"]
    client.post(f"/sessions/{session['id']}/proposals/{proposal['id']}/confirm")
    return base, experience


def test_generate_snippets_offline_returns_fact_cards(tmp_path):
    app = create_app(
        tmp_path / "resume-agent.db",
        fact_audit_agent=StubAuditAgent(),
        question_writer=StubQuestionWriter(),
    )
    with TestClient(app) as client:
        base, experience = build_base_with_confirmed_fact(client)
        response = client.post(
            f"/fact-bases/{base['id']}/experiences/{experience['id']}/snippets/generate"
        )
    assert response.status_code == 200
    snippets = response.json()["snippets"]
    assert [item["text"] for item in snippets] == ["搭建看板"]
    assert snippets[0]["source_fact_ids"]


def test_generate_snippets_with_agent_rewrites(tmp_path):
    app = create_app(
        tmp_path / "resume-agent.db",
        fact_audit_agent=StubAuditAgent(),
        question_writer=StubQuestionWriter(),
        snippet_agent=FakeSnippetAgent(),
    )
    with TestClient(app) as client:
        base, experience = build_base_with_confirmed_fact(client)
        response = client.post(
            f"/fact-bases/{base['id']}/experiences/{experience['id']}/snippets/generate"
        )
    assert response.status_code == 200
    assert [item["text"] for item in response.json()["snippets"]] == [
        "搭建并维护了用户留存看板"
    ]


def test_generate_snippets_without_facts_is_empty(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post(
            "/fact-bases", json={"target": {"role": "数据分析师"}}
        ).json()
        base = client.post(
            f"/fact-bases/{base['id']}/experiences",
            json={"organization": "星河科技", "role": "实习生"},
        ).json()
        experience = base["experiences"][0]
        response = client.post(
            f"/fact-bases/{base['id']}/experiences/{experience['id']}/snippets/generate"
        )
    assert response.status_code == 200
    assert response.json()["snippets"] == []
```

`tests/web/api.test.mjs` 末尾追加：

```js
test("generateSnippets posts to the experience snippets endpoint", async () => {
  const calls = [];
  const api = createApi(async (url, init) => {
    calls.push([url, init]);
    return new Response(JSON.stringify({ snippets: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });

  await api.generateSnippets("base-1", "exp-1");
  assert.equal(calls[0][0], "/fact-bases/base-1/experiences/exp-1/snippets/generate");
  assert.equal(calls[0][1].method, "POST");
});
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_api_snippets.py -q` 和 `node --test tests/web/api.test.mjs`
Expected: FAIL（路由/方法不存在）

- [ ] **Step 3: 实现**

`resume_agent/agents/specialists.py` 追加：

```python
class SnippetPayload(BaseModel):
    snippets: List[str] = Field(min_length=1, max_length=3)


SNIPPET_WRITE_PROMPT = """你是简历经历润色员。基于给定经历与已确认事实，改写合并为 1~3 条可直接写入简历的中文要点（每条一句话、动词开头；保留事实中的数字与原意，禁止新增数字或成果）。只输出 JSON：{"snippets": ["要点1", ...]}"""


class StructuredSnippetAgent:
    def __init__(self, runner) -> None:
        self.runner = runner

    def write(self, experience, facts_text: str) -> List[str]:
        prompt = (
            f"{SNIPPET_WRITE_PROMPT}\n"
            f"经历：{experience.organization} · {experience.role}\n"
            f"已确认事实：\n{facts_text}"
        )
        payload = run_structured(self.runner, prompt, SnippetPayload)
        return [item.strip() for item in payload.snippets if item.strip()]
```

`resume_agent/agents/runtime.py`：`AgentCapabilityStatus` 追加 `snippet_writer: bool = False` 并在 `ready()` 置 `True`；`MentorRuntime` 追加 `snippet_writer: Optional[StructuredSnippetAgent] = None`；`build_mentor_runtime` 追加：

```python
    snippet_runner = FreshAgentRunner(
        lambda: framework.SimpleAgent(
            name="经历片段润色",
            llm=llm,
            system_prompt=SNIPPET_WRITE_PROMPT,
            config=_private_agent_config(framework),
        )
    )
```

并在 `MentorRuntime(...)` 构造追加 `snippet_writer=StructuredSnippetAgent(snippet_runner),`（import 补 `StructuredSnippetAgent`、`SNIPPET_WRITE_PROMPT`）。

`resume_agent/api/main.py` 追加 `snippet_agent=runtime.snippet_writer,`。

`resume_agent/api/app.py`：`create_app` 签名追加 `snippet_agent=None`；`ServiceContainer` 追加 `snippet_agent: object`；容器构造追加 `snippet_agent=snippet_agent,`；import 补 `ConfidenceStatus`；路由区追加：

```python
    @app.post("/fact-bases/{fact_base_id}/experiences/{experience_id}/snippets/generate")
    def generate_experience_snippets(fact_base_id: UUID, experience_id: UUID):
        base = container.fact_bases.get(fact_base_id)
        experience = base.get_experience(experience_id)
        facts = [
            value
            for values in experience.statements.values()
            for value in values
            if value.confidence
            in (ConfidenceStatus.CONFIRMED, ConfidenceStatus.ESTIMATED)
        ]
        if not facts:
            return {"snippets": []}
        texts = [value.text for value in facts]
        if container.snippet_agent is not None:
            try:
                generated = container.snippet_agent.write(experience, "\n".join(texts))
                if generated:
                    texts = generated
            except Exception:
                pass  # 离线/失败时退化为事实原话卡
        return {
            "snippets": [
                {
                    "text": text,
                    "source_fact_ids": [str(value.id) for value in facts],
                }
                for text in texts
            ]
        }
```

`resume_agent/web/api.js` 追加：

```javascript
    generateSnippets: (factBaseId, experienceId) => request(
      `/fact-bases/${factBaseId}/experiences/${experienceId}/snippets/generate`,
      { method: "POST" },
    ),
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_api_snippets.py tests/test_agent_runtime.py -q` 和 `node --test tests/web/api.test.mjs`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add resume_agent/agents/specialists.py resume_agent/agents/runtime.py resume_agent/api/main.py resume_agent/api/app.py resume_agent/web/api.js tests/test_api_snippets.py tests/web/api.test.mjs
git commit -m "feat: generate polished snippet cards with offline fact fallback"
```

---

### Task 17: 版本片段写入、删除与渲染合并

**Files:**
- Modify: `resume_agent/application/version_service.py`（`add_snippet`、`remove_snippet`）
- Modify: `resume_agent/api/schemas.py`（`VersionSnippetAddRequest`）
- Modify: `resume_agent/api/app.py`（两个端点）
- Modify: `resume_agent/rendering/renderer.py`（片段模式、custom_sections、锚点、删除标记）
- Modify: `resume_agent/rendering/models.py`（`RenderedExperience.snippet_ids`）
- Test: `tests/test_api_snippets.py`（追加）、`tests/test_resume_renderer.py`（追加）

**Interfaces:**
- Consumes: Task 11（`_zh_markdown`/`_zh_html`）、Task 16
- Produces（Task 18 依赖）：
  - `POST /versions/{id}/snippets` `{experience_id|null, text, source_fact_ids}` → ResumeVersion；重复文本返回 400
  - `DELETE /versions/{id}/snippets/{snippet_id}` → ResumeVersion
  - 渲染合并：`version.snippets[exp_id]` 非空时该经历用片段文本渲染（替代自动事实 bullets）；`custom_sections` 渲染为「自定义片段」区；HTML 带 `data-section` 落点与 `data-snippet-id` 删除标记

- [ ] **Step 1: 写失败测试**

`tests/test_api_snippets.py` 末尾追加：

```python
def test_add_and_remove_version_snippet(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post(
            "/fact-bases", json={"target": {"role": "数据分析师"}}
        ).json()
        version = client.post(
            f"/fact-bases/{base['id']}/versions",
            json={"name": "默认版本", "locale": "zh", "selected_experience_ids": []},
        ).json()
        added = client.post(
            f"/versions/{version['id']}/snippets",
            json={"experience_id": None, "text": "一段自由补充内容", "source_fact_ids": []},
        )
        assert added.status_code == 200
        snippet = added.json()["custom_sections"][0]
        assert snippet["text"] == "一段自由补充内容"
        duplicate = client.post(
            f"/versions/{version['id']}/snippets",
            json={"experience_id": None, "text": "一段自由补充内容", "source_fact_ids": []},
        )
        assert duplicate.status_code == 400
        removed = client.delete(
            f"/versions/{version['id']}/snippets/{snippet['id']}"
        )
        assert removed.status_code == 200
        assert removed.json()["custom_sections"] == []
```

`tests/test_resume_renderer.py` 末尾追加：

```python
from resume_agent.domain.models import VersionSnippet


def test_zh_snippet_mode_replaces_auto_bullets():
    base, first, _ = evidence_fixture()
    version = make_version(base, [first], locale="zh")
    snippet = VersionSnippet(text="搭建并维护用户留存看板")
    version.snippets[first.id] = [snippet]
    rendered = ResumeRenderer().render(base, version)
    assert "搭建并维护用户留存看板" in rendered.markdown
    assert "搭建用户留存看板" not in rendered.markdown
    assert f'data-section="experience:{first.id}"' in rendered.html
    assert f'data-snippet-id="{snippet.id}"' in rendered.html


def test_zh_custom_snippets_render_and_drop_zone_exists():
    base, first, _ = evidence_fixture()
    version = make_version(base, [first], locale="zh")
    rendered = ResumeRenderer().render(base, version)
    assert 'data-section="custom"' in rendered.html
    version.custom_sections = [VersionSnippet(text="一段自由补充内容")]
    rendered = ResumeRenderer().render(base, version)
    assert "## 自定义片段" in rendered.markdown
    assert "一段自由补充内容" in rendered.markdown
    assert rendered.custom_snippets[0].text == "一段自由补充内容"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_api_snippets.py tests/test_resume_renderer.py -q`
Expected: FAIL（路由 404 / 片段模式未生效）

- [ ] **Step 3: 服务与端点**

`resume_agent/application/version_service.py` 追加：

```python
    def add_snippet(
        self,
        version_id: UUID,
        experience_id: Optional[UUID],
        text: str,
        source_fact_ids: Optional[List[UUID]] = None,
    ) -> ResumeVersion:
        version = self.repository.get(version_id)
        snippet = VersionSnippet(
            text=text, source_fact_ids=list(source_fact_ids or [])
        )
        if experience_id is None:
            if any(item.text == snippet.text for item in version.custom_sections):
                raise ValueError("该片段已在简历中")
            version.custom_sections.append(snippet)
        else:
            # 经历未选入当前版本时自动选入（spec §8.3 落点规则）
            if experience_id not in version.selected_experience_ids:
                version.selected_experience_ids = (
                    list(version.selected_experience_ids) + [experience_id]
                )
            snippets = version.snippets.setdefault(experience_id, [])
            if any(item.text == snippet.text for item in snippets):
                raise ValueError("该片段已在简历中")
            snippets.append(snippet)
        return self.save(version)

    def remove_snippet(self, version_id: UUID, snippet_id: UUID) -> ResumeVersion:
        version = self.repository.get(version_id)
        for experience_id in list(version.snippets.keys()):
            version.snippets[experience_id] = [
                item for item in version.snippets[experience_id]
                if item.id != snippet_id
            ]
            if not version.snippets[experience_id]:
                del version.snippets[experience_id]
        version.custom_sections = [
            item for item in version.custom_sections if item.id != snippet_id
        ]
        return self.save(version)
```

（import 补 `VersionSnippet`。）

`resume_agent/api/schemas.py` 追加：

```python
class VersionSnippetAddRequest(BaseModel):
    experience_id: Optional[UUID] = None
    text: str = Field(min_length=1)
    source_fact_ids: List[UUID] = Field(default_factory=list)
```

`resume_agent/api/app.py`：import 补 `VersionSnippetAddRequest`，路由区追加：

```python
    @app.post("/versions/{version_id}/snippets")
    def add_version_snippet(version_id: UUID, payload: VersionSnippetAddRequest):
        return container.versions.add_snippet(
            version_id,
            payload.experience_id,
            payload.text,
            payload.source_fact_ids,
        )

    @app.delete("/versions/{version_id}/snippets/{snippet_id}")
    def delete_version_snippet(version_id: UUID, snippet_id: UUID):
        return container.versions.remove_snippet(version_id, snippet_id)
```

- [ ] **Step 4: 渲染合并**

`resume_agent/rendering/models.py`：`RenderedExperience` 追加：

```python
    snippet_ids: List[UUID] = Field(default_factory=list)
```

`resume_agent/rendering/renderer.py`：

`_bullets` 改为接收 version 并处理片段模式：

```python
    def _bullets(self, experience, version):
        snippets = version.snippets.get(experience.id)
        if snippets:
            return [snippet.text for snippet in snippets], False, [snippet.id for snippet in snippets]
        bullets: list[str] = []
        seen = set()
        has_estimates = False
        for dimension in DIMENSION_ORDER:
            for value in experience.statements.get(dimension, []):
                if value.confidence is ConfidenceStatus.UNVERIFIED:
                    continue
                has_estimates = (
                    has_estimates or value.confidence is ConfidenceStatus.ESTIMATED
                )
                if value.text not in seen:
                    seen.add(value.text)
                    bullets.append(value.text)
        return bullets, has_estimates, []
```

`_resolve_experiences` 中调用改为：

```python
            bullets, experience_has_estimates, snippet_ids = self._bullets(experience, version)
            has_estimates = has_estimates or experience_has_estimates
```

并在 `RenderedExperience(...)` 构造中补 `snippet_ids=snippet_ids,`。

`render()` 的 `RenderedResume(...)` 构造补 `custom_snippets=version.custom_sections,`。

`_zh_html` 中，bullet 生成改为（含删除标记与 id 对齐）：

```python
                ids = experience.snippet_ids + [None] * max(
                    0, len(experience.bullets) - len(experience.snippet_ids)
                )
                bullets = "".join(
                    self._bullet_html(item, snippet_id)
                    for item, snippet_id in zip(experience.bullets, ids)
                )
```

新增辅助方法（放在 `_zh_html` 之后）：

```python
    @staticmethod
    def _bullet_html(text, snippet_id):
        escaped = html.escape(text, quote=True)
        if snippet_id is None:
            return f"<li>{escaped}</li>"
        return (
            f'<li class="snippet" data-snippet-id="{snippet_id}">{escaped}'
            f'<button class="snippet-remove" data-snippet-id="{snippet_id}" '
            f'type="button" aria-label="删除片段">✕</button></li>'
        )
```

`_zh_html` 中，`skills_section` 之后追加自定义片段区，并把它并入 `body`：

```python
        custom_items = "".join(
            self._bullet_html(item.text, item.id) for item in version.custom_sections
        )
        custom_drop = (
            '<section class="drop-zone custom-snippets" data-section="custom">'
            '<h2>自定义片段</h2>'
            + (f"<ul>{custom_items}</ul>" if custom_items
               else '<p class="meta">可将片段卡拖到此处，形成简历的自定义内容。</p>')
            + "</section>"
        )
```

`body` 末尾（`f"{skills_section}"` 之后）追加 `f"{custom_drop}"`。

`_zh_markdown` 末尾（`skills` 块之后、`return` 之前）追加：

```python
        if version.custom_sections:
            lines.append("## 自定义片段")
            lines.append("")
            lines.extend(
                f"- {self._markdown_escape(item.text)}" for item in version.custom_sections
            )
            lines.append("")
```

`_zh_html` 的 css 中追加（若 Task 11 已含 `.drop-zone` 规则则跳过）：

```css
        .snippet-remove { border: none; background: transparent; color: #9aa3ad; cursor: pointer; margin-left: 1mm; font-size: 8.5pt; }
```

- [ ] **Step 5: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_api_snippets.py tests/test_resume_renderer.py tests/test_resume_exporters.py tests/test_api_rendering.py tests/test_version_service.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add resume_agent/application/version_service.py resume_agent/api/schemas.py resume_agent/api/app.py resume_agent/rendering/renderer.py resume_agent/rendering/models.py tests/test_api_snippets.py tests/test_resume_renderer.py
git commit -m "feat: version snippet overlay with drop anchors and removal"
```

---

### Task 18: 前端片段面板与拖拽

**Files:**
- Modify: `resume_agent/web/api.js`（2 个方法）
- Modify: `resume_agent/web/app.js`（片段卡面板、拖拽落点、删除）
- Modify: `resume_agent/web/styles.css`（片段卡与拖拽样式）
- Test: `tests/web/api.test.mjs`（追加）

**Interfaces:**
- Consumes: Task 16（generate）、Task 17（add/delete + 锚点）
- Produces: 「片段」面板可生成卡片并拖到预览落点写入；预览内可 ✕ 删除；编辑模式停用拖拽

- [ ] **Step 1: 写失败测试**

`tests/web/api.test.mjs` 末尾追加：

```js
test("snippet mutation endpoints post the right contracts", async () => {
  const calls = [];
  const api = createApi(async (url, init) => {
    calls.push([url, init]);
    return new Response(JSON.stringify({ id: "v-1" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });

  await api.addVersionSnippet("v-1", {
    experience_id: "exp-1",
    text: "片段文本",
    source_fact_ids: [],
  });
  await api.deleteVersionSnippet("v-1", "s-1");

  assert.equal(calls[0][0], "/versions/v-1/snippets");
  assert.equal(calls[0][1].method, "POST");
  assert.deepEqual(JSON.parse(calls[0][1].body), {
    experience_id: "exp-1",
    text: "片段文本",
    source_fact_ids: [],
  });
  assert.equal(calls[1][0], "/versions/v-1/snippets/s-1");
  assert.equal(calls[1][1].method, "DELETE");
});
```

- [ ] **Step 2: 运行确认失败**

Run: `node --test tests/web/api.test.mjs`
Expected: FAIL（方法不存在）

- [ ] **Step 3: 实现 API 方法与片段面板**

`resume_agent/web/api.js` 追加：

```javascript
    addVersionSnippet: (versionId, payload) => request(
      `/versions/${versionId}/snippets`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
    deleteVersionSnippet: (versionId, snippetId) => request(
      `/versions/${versionId}/snippets/${snippetId}`,
      { method: "DELETE" },
    ),
```

`resume_agent/web/app.js`：

`renderFactBase` 中，`card.append(grid, deepen);` 改为 `card.append(grid, deepen, snippetCardSection(base, experience));`，并追加以下函数（放在 `renderFactBase` 之后）：

```javascript
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
```

`boot()` 底部既有帧加载监听改为：

```javascript
byId("preview-frame").addEventListener("load", () => {
  if (editMode && editorView === "visual") setEditorView("visual");
  wirePreviewDropTargets();
});
```

（srcdoc 每次重新渲染会重建 iframe 文档，`dataset.dropWired` 防重复绑定依赖的是文档内节点，重渲染后自动重新绑定，无需清理。）

- [ ] **Step 4: 样式**

`resume_agent/web/styles.css` 末尾追加：

```css
.snippet-cards { margin-top: 10px; border-top: 1px dashed var(--border, #d8dde5); padding-top: 10px; }
.snippet-cards h4 { margin: 0 0 4px; }
.snippet-card { border: 1px solid var(--border, #d8dde5); border-radius: 8px; padding: 8px 10px; margin: 8px 0; background: #f8fafc; cursor: grab; }
.snippet-card:hover { border-color: var(--accent, #1d4ed8); box-shadow: 0 1px 4px rgba(0,0,0,.08); }
.snippet-card p { margin: 0; }
```

- [ ] **Step 5: 回归与人工验证**

Run: `node --test tests/web/*.test.mjs` 和 `.venv/bin/python -m pytest -q`
Expected: 全绿。

手动验证：片段面板生成卡片 → 拖到预览某经历段落 → 该经历切换为片段模式且落点高亮 → 预览/导出与事实一致；拖到「自定义片段」区 → 追加渲染；预览中 ✕ 删除 → 恢复；进入编辑模式拖拽被阻止并提示。

- [ ] **Step 6: 提交**

```bash
git add resume_agent/web/api.js resume_agent/web/app.js resume_agent/web/styles.css tests/web/api.test.mjs
git commit -m "feat: draggable snippet cards into the resume preview"
```

---

### Task 19: 评测集补充、README 与全量回归

**Files:**
- Modify: `resume_agent/evaluation/datasets/mentor_v1.jsonl`（追加 3 条中文问题样本）
- Modify: `README.md`（功能与限制更新）

- [ ] **Step 1: 追加中文评测样本**

`resume_agent/evaluation/datasets/mentor_v1.jsonl` 末尾追加三行（每行一个 JSON 对象，格式与既有行一致）：

```json
{"id":"q-zh-context-direct","kind":"question","target":{"role":"数据分析师"},"experience":{"organization":"星河科技","role":"数据分析实习生"},"dimension":"context","escalation":"direct","must_include_any":["背景","问题","目标"],"must_not_include":["编一个","身份证"]}
{"id":"q-zh-action-direct","kind":"question","target":{"role":"产品经理"},"experience":{"organization":"星图网络","role":"产品实习生"},"dimension":"action","escalation":"direct","must_include_any":["具体做了","行动","步骤"],"must_not_include":["肯定","编造"]}
{"id":"q-zh-result-recall","kind":"question","target":{"role":"运营专员"},"experience":{"organization":"青禾电商","role":"运营实习生"},"dimension":"result","escalation":"recall_anchors","must_include_any":["变化","频率","前后"],"must_not_include":["一定有数字"]}
```

验证数据集可加载：

Run: `.venv/bin/python -m pytest tests/test_evaluation_dataset.py -q`
Expected: PASS（若断言了样本数量，同步更新该断言）

- [ ] **Step 2: 更新 README**

`README.md` 的「当前可用功能」列表追加：

```markdown
- 向导式问答工作台：按基本信息 → 求职意向 → 教育背景 → 经历 → 技能 → 自我评价顺序收集，尽量用选项、年月选择器交互。
- 核心课程智能推荐：按专业内置课程词典秒出推荐，配置模型后追加「AI 推荐」课程；技能标签支持提炼候选与自由添加。
- 自我评价备选：根据已确认事实生成 3~5 条备选供勾选，严格无幻觉校验，确认后才写入简历。
- 片段卡拖拽：经历事实可润色成片段卡，拖到预览的经历段落或自定义片段区即写入当前版本，可单独删除。
- 本阶段优先完善中文简历；日/英界面保留原有能力。
```

「当前限制」列表追加：

```markdown
- 向导式问答、课程推荐、自我评价与片段卡当前仅支持中文简历；日文与英文简历沿用原有渲染与收集方式。
```

- [ ] **Step 3: 全量回归**

Run: `.venv/bin/python -m pytest -q` 和 `node --test tests/web/*.test.mjs`
Expected: 全绿（若有失败，逐项修复后再提交；不通过不得宣称完成）

- [ ] **Step 4: 手动验收清单（逐项确认后提交）**

1. 新建档案只填目标岗位即可进入向导。
2. 六章问答全部可用选项/年月选择器完成，跳过与回退正常，刷新页面进度恢复。
3. 离线模式（不配模型）：访谈提示不可用，但课程词典、自我评价模板、事实原话卡均可用。
4. 配置模型：访谈合并调用（每轮 1 个等待点）、AI 课程推荐、自我评价备选、片段润色均工作。
5. 拖拽片段到预览 → 写入、可删、去重提示；编辑模式禁用拖拽。
6. 中文简历预览与 PDF/HTML/Markdown/DOCX 导出包含教育/技能/自我评价/自定义片段。
7. 日/英切换不报错，原有布局不变。

- [ ] **Step 5: 提交**

```bash
git add resume_agent/evaluation/datasets/mentor_v1.jsonl README.md tests/test_evaluation_dataset.py
git commit -m "docs: zh wizard features in readme and eval samples"
```

## 计划自审记录（writing-plans self-review，已修正）

1. **Spec 覆盖**：§4~§9 均有对应任务；唯一弱化项是 §7.3 的 LLM 技能提炼（已并入 Task 10 的 `StructuredSkillAgent`）；自我评价「可微调文字」由预览编辑模式承载（Task 15 注明）。
2. **占位符扫描**：无 TBD/TODO；「若未导入则补 import」类步骤为可执行的条件指令，非占位。
3. **一致性修正（已就地修复）**：
   - `test_engine_skips_steps_marked_skipped` 需清空 target.role 才会停在 `target:role`。
   - 技能候选测试的 base 需补 `country` 与 `educations`，否则会先停在 `target:city`/`education:add`。
   - 自我评价 grounding 测试的备选文案加长至 40~70 字区间，避免被长度过滤器误伤。
   - `VersionService.add_snippet` 补齐「经历未选入版本时自动选入」。
   - 问题卡区域渲染所有类型（含 interview 引导卡），与 Task 15 替换版一致。
   - `handleOnboarding` 创建默认版本后先并入 `versions` 数组再 `chooseVersion`（否则版本切换会被 `versions.some(...)` 拒绝）。
4. **类型一致性**：`RenderedExperience.id/snippet_ids`、`RenderedResume.self_summary/custom_snippets`、`QuestionnaireState.course_options/skill_options` 在定义任务与使用任务间签名一致；步骤 id 约定（`profile:*`/`education:new:school`/`experience:*` 等）贯穿引擎、服务、路由与前端。




