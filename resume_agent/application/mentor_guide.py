"""Mentor-guide candidates: job analysis and dynamic answer options."""

OFFLINE_JOB_ANALYSIS = [
    "与目标岗位相关的项目或实习经历",
    "可量化的成果与数据",
    "岗位核心技能与工具",
    "团队协作与沟通能力",
]

OFFLINE_FOLLOWUP_OPTIONS = {
    "role": ["项目负责人", "核心成员", "普通成员", "实习生"],
    "context": ["解决具体业务问题", "完成课程大作业", "社团活动需求", "竞赛题目"],
    "responsibility": ["独立负责一块", "协助团队完成", "主导整个项目"],
    "action": ["搭建或开发", "调研分析", "策划执行", "沟通协调"],
    "method": ["用专业软件", "用编程工具", "用分析框架", "手工流程"],
    "result": ["效率提升", "用户增长", "成本降低", "获得认可"],
    "evidence": ["有数字指标", "有交付物", "有他人反馈", "暂时没有"],
}

# 「换一批」轮换池：首 4 条与初始批次一致，其余用于换出全新选项
OFFLINE_FOLLOWUP_POOLS = {
    "role": ["项目负责人", "核心成员", "普通成员", "实习生",
             "独立开发者", "技术组长", "产品共建人", "指导老师"],
    "context": ["解决具体业务问题", "完成课程大作业", "社团活动需求", "竞赛题目",
                "开源社区需求", "老师课题的子任务", "个人兴趣探索", "实习中的真实需求"],
    "responsibility": ["独立负责一块", "协助团队完成", "主导整个项目",
                      "负责核心模块", "负责测试验收", "负责文档与分享", "负责对外沟通", "参与方案设计"],
    "action": ["搭建或开发", "调研分析", "策划执行", "沟通协调",
               "数据清洗与统计", "写代码实现", "组织活动", "制作材料"],
    "method": ["用专业软件", "用编程工具", "用分析框架", "手工流程",
               "用大模型辅助", "用开源工具", "先小范围验证", "参考成熟方案"],
    "result": ["效率提升", "用户增长", "成本降低", "获得认可",
               "按时交付", "被实际采用", "通过验收", "获得奖项"],
    "evidence": ["有数字指标", "有交付物", "有他人反馈", "暂时没有",
                 "有链接可查", "有对比数据", "有截图记录", "有评价截图"],
}

# 按经历类型区分的岗位选项离线兜底（LLM 失败时使用）
OFFLINE_ROLE_OPTIONS_BY_TYPE = {
    "internship": ["产品实习生", "运营实习生", "数据分析实习生", "市场实习生", "技术实习生"],
    "work": ["产品经理", "运营专员", "数据分析师", "项目经理", "市场专员"],
}


OFFLINE_EXPERIENCE_OPTIONS = [
    {"label": "实习", "type": "internship"},
    {"label": "工作", "type": "work"},
    {"label": "Web 开发项目", "type": "project"},
    {"label": "Agent / AI 项目", "type": "project"},
    {"label": "课程项目", "type": "project"},
    {"label": "校园经历", "type": "campus"},
]

# 「换一批」补充池：与初始批次不重复的经历类型
OFFLINE_EXPERIENCE_OPTIONS_EXTRA = [
    {"label": "社团/学生会经历", "type": "campus"},
    {"label": "竞赛经历", "type": "campus"},
    {"label": "开源贡献", "type": "project"},
    {"label": "自媒体/内容项目", "type": "project"},
    {"label": "研究/实验室项目", "type": "project"},
    {"label": "创业/副业项目", "type": "project"},
]

# 用户未粘贴 JD 时的离线兜底岗位描述（LLM 失败时使用）
OFFLINE_JD = """岗位职责：
1. 负责与岗位相关的核心业务模块的推进与交付；
2. 与产品、设计、研发等团队协作，完成需求分析与方案落地；
3. 跟进数据与反馈，持续优化方案效果；
4. 沉淀工作方法与文档，参与团队知识共享。

任职要求：
1. 相关专业背景，有对应岗位的实习或项目经验；
2. 熟练使用岗位常用工具与技能；
3. 逻辑清晰、沟通顺畅，能推动事情落地；
4. 学习能力强，有自驱力。"""


def offline_experience_options():
    """离线兜底：实习/工作 + 互联网类项目（Web、Agent 等）。"""
    return [dict(item) for item in OFFLINE_EXPERIENCE_OPTIONS]


def _fresh_text_options(options, pool, previous, min_count=4):
    """过滤上一批选项并用轮换池补足，保证「换一批」确实换出不同内容。"""
    previous = [item for item in (previous or []) if item]
    if not previous:
        return list(options)
    seen = set(previous)
    fresh = [item for item in options if item not in seen]
    for item in pool:
        if len(fresh) >= min_count:
            break
        if item not in seen:
            fresh.append(item)
            seen.add(item)
    return fresh if fresh else list(options)


class MentorGuideService:
    """Job analysis and dynamic options; every LLM path has an offline fallback."""

    def __init__(
        self,
        job_advisor=None,
        experience_advisor=None,
        followup_advisor=None,
        jd_advisor=None,
    ):
        self.job_advisor = job_advisor
        self.experience_advisor = experience_advisor
        self.followup_advisor = followup_advisor
        self.jd_advisor = jd_advisor

    def generate_jd(self, target_role, company=""):
        """用户未提供 JD 时，根据岗位+公司生成岗位描述（失败走离线模板）。"""
        if self.jd_advisor is not None:
            try:
                jd = self.jd_advisor.run(target_role, company)
                if jd:
                    return jd
            except Exception:
                pass
        return OFFLINE_JD

    def analyze_job(self, target_role, jd=""):
        if self.job_advisor is not None:
            try:
                analysis = self.job_advisor.analyze(target_role, jd)
                if analysis:
                    return analysis
            except Exception:
                pass  # 离线或失败降级为模板
        return list(OFFLINE_JOB_ANALYSIS)

    def experience_options(self, target_role, previous=None, jd=""):
        if self.experience_advisor is not None:
            try:
                if previous:
                    options = self.experience_advisor.options(
                        target_role, previous=previous, jd=jd
                    )
                else:
                    options = self.experience_advisor.options(target_role, jd=jd)
                if options:
                    return self._fresh_experience_options(options, previous)
            except Exception:
                pass
        return self._fresh_experience_options(offline_experience_options(), previous)

    @staticmethod
    def _fresh_experience_options(options, previous):
        previous_labels = {item for item in (previous or []) if item}
        if not previous_labels:
            return [dict(item) for item in options]
        seen = set(previous_labels)
        fresh = [dict(item) for item in options if item["label"] not in seen]
        seen.update(item["label"] for item in fresh)
        for extra in OFFLINE_EXPERIENCE_OPTIONS_EXTRA:
            if len(fresh) >= 4:
                break
            if extra["label"] not in seen:
                fresh.append(dict(extra))
                seen.add(extra["label"])
        return fresh if fresh else [dict(item) for item in options]

    def followup_options(self, target_role, experience_text, dimension, previous=None):
        if self.followup_advisor is not None:
            try:
                if previous:
                    options = self.followup_advisor.options(
                        target_role, experience_text, dimension, previous=previous
                    )
                else:
                    options = self.followup_advisor.options(
                        target_role, experience_text, dimension
                    )
                if options:
                    pool = OFFLINE_FOLLOWUP_POOLS.get(
                        dimension, OFFLINE_FOLLOWUP_OPTIONS.get(dimension, [])
                    )
                    return _fresh_text_options(options, pool, previous)
            except Exception:
                pass
        pool = OFFLINE_FOLLOWUP_POOLS.get(
            dimension, OFFLINE_FOLLOWUP_OPTIONS.get(dimension, [])
        )
        base_options = list(OFFLINE_FOLLOWUP_OPTIONS.get(dimension, []))
        return _fresh_text_options(base_options, pool, previous)
