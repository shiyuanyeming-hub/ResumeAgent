# ResumeAgent — AI 求职导师：把简历"问"出来

**中文** · [English](README.en.md) · [日本語](README.ja.md)

> 一个证据驱动的多智能体简历导师。它不像普通工具那样替你编漂亮话——而是像真正的导师一样，围绕你做过的事一步步追问，把「我负责过 XX」变成有背景、有行动、有结果的证据，确认后才写进简历。
> 它还能按学校模板自动排版，一键导出 PDF。

<p align="center">
  <img src="docs/assets/resume-agent-workbench.png" alt="ResumeAgent 工作台" width="80%"/>
  <br/>
  <em>左：向导式问答与证据进度 · 右：实时简历预览（双栏版式）</em>
</p>

<p align="center">
  <img src="docs/assets/resume-agent-resume.png" alt="简历成品示例" width="42%"/>
  <br/>
  <em>最终导出的简历（虚构示例数据）</em>
</p>

---

## 这个项目解决什么问题

写简历最难的从来不是排版，而是**说不清自己做过什么**。多数人只会写「负责数据分析」，既没有背景、行动，也没有结果——这正是简历被筛掉的原因。

ResumeAgent 的做法是**先面试、后成文**：

1. 你只说目标岗位（如「数据分析师」）；
2. 导师分析岗位看重什么，弹窗里逐步提问（每个问题都有**可点选的选项**，也可自己写，「换一批」会把上一批当反例让模型重新生成）；
3. 回答被模型提炼成**候选事实**，你确认后才进入事实库——**未确认的内容永远不会出现在简历上**；
4. 事实按六个证据维度（背景 / 职责 / 行动 / 方法 / 结果 / 证明）归集，攒够证据即可成文；
5. 简历按 基本信息 → 求职意向 → 教育背景 → 实习/工作经历 → 项目经历 → 技能与证书 → 自我评价 的标准结构自动生成，支持双栏版式、照片、学校模板（HTML 占位符 / 表单 PDF 自动填充），导出 HTML / Markdown / DOCX / PDF。

**全程「答多少算多少」**：随时点「答完了，就用这些」结束，已确认的内容照实写入。

## 核心设计（技术面试时可以展开讲）

### 1. 确定性骨架 + LLM 只出候选（防幻觉）

这是一个刻意的架构选择：

- **什么时候问、问哪个维度、什么能写进简历、版本怎么隔离、怎么渲染**——全部由确定性代码（问卷引擎 + 维度规划器 + 质量门槛 + 渲染器）控制；
- **LLM 只负责生成候选**：候选事实、候选问题、候选选项、自我评价备选；
- 事实经过**用户确认**才落库；自我评价备选有**无幻觉校验**（禁止出现事实之外的数字、公司名、职位名）；
- 每条 LLM 路径都有**离线兜底**，模型挂了流程不中断、功能可降级可用。

好处：可测试（285 个 Python 测试 + 25 个前端测试）、行为可预期，面试时可以明确回答「哪里用了 AI、哪里没有、为什么」。

### 2. 六维证据模型与质量门槛

每段经历的证据按六个维度存储：`context / responsibility / action / method / result / evidence`。质量门槛要求**至少 4 个维度、且包含行动与（结果或证明）**，防止「写了经历却全是空话」。访谈规划器按 缺口严重度 × 岗位相关性 × 区分度 × 可回答性 × 疲劳度 动态选择下一个问题。

### 3. 多智能体协作

运行时基于 HelloAgents 构建 9 个专职智能体，每个都有明确的输入输出契约与离线兜底：

| 智能体 | 职责 |
| --- | --- |
| 事实审计 | 把用户的回答提炼成候选事实（含维度归类） |
| 追问撰写 | 按规划维度与追问阶段（直接 → 回忆线索 → 替代证据）生成问题 |
| 岗位分析 | 生成目标岗位看重的经历与能力要点 |
| 经历选项 / 追问选项 / 岗位选项 | 动态生成可点选的候选答案（支持「换一批」） |
| 课程推荐 / 技能提炼 | 教育课程与技能标签候选 |
| 自我评价 / 片段撰写 | 基于已确认事实生成备选，严格接地 |

### 4. 学校模板与排版

- 内置三套主题的双栏版式（藏青现代 / 经典墨色 / 清新青碧）；
- 上传学校的 **HTML 模板**（占位符 `{{education}} {{experience_work}} ...` 自动填充）；
- 上传**带表单字段的 PDF 模板**，自动识别「姓名 / 电话 / 毕业院校 …」等字段并填充，导出即学校成品版式；
- 照片上传、证书/语言成绩/GPA/排名/研究方向/毕业论文等细节字段；
- 学校名称支持拼音/首字母模糊联想（180+ 国内院校 + 90+ 海外院校），专业按学校类型优先展示。

### 5. 数据与工程

- 后端：Python 3.12 · FastAPI · Pydantic v2 · SQLite（事实库 / 会话 / 版本，JSON 载荷快照 + 乐观并发修订）
- 前端：**零构建**的原生 ES Modules + `<dialog>` 弹窗向导，无框架依赖
- 版本体系：事实库与投递版本分离，版本有修订号与陈旧提示，支持可视化/Markdown 双编辑
- 导出：HTML / Markdown / DOCX（python-docx）/ PDF（无头 Chrome 打印）
- 部署：Docker 一键部署，可选访问口令（`ACCESS_CODE`），可选 Caddy 域名 + 自动 HTTPS

## 技术栈

| 层 | 技术 |
| --- | --- |
| 语言 | Python 3.12 |
| Web 框架 | FastAPI + Uvicorn |
| 数据校验 | Pydantic v2 |
| 存储 | SQLite（JSON 载荷 + 乐观并发） |
| 智能体框架 | HelloAgents（OpenAI 兼容接口，支持 DeepSeek / Qwen 等） |
| 前端 | 原生 HTML / CSS / JavaScript（ES Modules，零构建） |
| 文档处理 | pypdf（表单 PDF 填充）、python-docx、无头 Chrome（PDF 渲染） |
| 部署 | Docker / Docker Compose / Caddy |

## 架构

```text
Browser (vanilla ES modules)
          │  same-origin JSON API
   FastAPI ── application services ── deterministic planner / renderer
          │                                   │
       SQLite                          HelloAgents adapters
   facts / sessions / versions        （9 个专职智能体，全部可离线兜底）
```

## 快速开始

要求 Python 3.10+；PDF 导出需要本机 Chrome/Edge。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[agents]'
cp .env.example .env          # 填入 LLM_API_KEY（OpenAI 兼容，DeepSeek/Qwen 均可）
uvicorn resume_agent.api.main:app --reload
```

打开 <http://127.0.0.1:8000/>。不配置模型时进入离线模式，全部功能可用确定性兜底。

运行测试：

```bash
.venv/bin/python -m pytest -q          # 285 个后端测试
node --test tests/web/*.test.mjs       # 25 个前端测试
```

## 部署到公网

```bash
cp .env.example .env && vim .env       # 填密钥；建议加 ACCESS_CODE=访问口令
chmod +x deploy/deploy.sh && ./deploy/deploy.sh
```

详见 [deploy/README.md](deploy/README.md)：Docker 一键部署、数据备份、域名 + HTTPS、安全组配置。

## 目录结构

```text
resume_agent/api/             FastAPI 入口、访问口令中间件
resume_agent/application/     问卷引擎、访谈服务、版本、渲染、PDF 模板填充
resume_agent/domain/          领域模型、六维质量门槛、学校/课程目录
resume_agent/agents/          HelloAgents 适配器与提示词
resume_agent/rendering/       三语渲染器与导出器
resume_agent/web/             原生前端工作台（零构建）
tests/                        Python 与浏览器客户端测试
evaluation/                   合成导师评测集（检查单问题、维度、证据保留、无幻觉）
deploy/                       Docker 部署套件
```

## Roadmap

- [ ] 注册登录与多用户账号体系
- [ ] 英文 / 日文独立模板体系（不止翻译）
- [ ] 排版型 PDF（无表单字段）的版式识别与填充
- [ ] 基于岗位 JD 的经历匹配与简历打分

## License

[MIT](LICENSE)
