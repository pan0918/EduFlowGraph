"use client";

import { useState, type ReactNode } from "react";
import clsx from "clsx";
import {
  BookOpen,
  BookText,
  ChevronRight,
  CircleAlert,
  CircleCheckBig,
  GraduationCap,
  Grid2x2,
  Lightbulb,
  Search,
} from "lucide-react";

type SubjectId =
  | "all"
  | "high-math"
  | "calculus"
  | "linear-algebra"
  | "chinese"
  | "english"
  | "college-physics";

type WeakConceptStatus = "薄弱" | "待提升";

interface SubjectTheme {
  iconShell: string;
  iconText: string;
  iconShadow: string;
  progress: string;
  progressTrack: string;
  topicChip: string;
  topicText: string;
  recommendationIcon: string;
  recommendationText: string;
  percentage: string;
}

interface SubjectMasteryCardData {
  id: Exclude<SubjectId, "all">;
  label: string;
  icon: string;
  overview: string;
  mastery: number;
  topics: string[];
  recommendation: string;
  theme: SubjectTheme;
}

interface WeakConceptData {
  id: string;
  label: string;
  subjectId: Exclude<SubjectId, "all">;
  subjectLabel: string;
  topicLabel: string;
  shortIcon: string;
  iconShell: string;
  status: WeakConceptStatus;
}

const SUBJECT_FILTERS: Array<{ id: SubjectId; label: string }> = [
  { id: "all", label: "全部" },
  { id: "high-math", label: "高中数学" },
  { id: "calculus", label: "微积分" },
  { id: "linear-algebra", label: "线性代数" },
  { id: "chinese", label: "语文" },
  { id: "english", label: "英语" },
  { id: "college-physics", label: "大学物理" },
];

const SUBJECT_CARDS: SubjectMasteryCardData[] = [
  {
    id: "high-math",
    label: "高中数学",
    icon: "√x",
    overview: "几何、代数、函数与数列等核心概念",
    mastery: 78,
    topics: ["椭圆", "双曲线", "函数", "数列"],
    recommendation: "加强椭圆与双曲线的综合应用练习",
    theme: {
      iconShell: "from-[#7ca8ea] to-[#3f72c9]",
      iconText: "text-white",
      iconShadow: "shadow-[0_14px_32px_rgba(63,114,201,0.26)]",
      progress: "bg-[#4c7ed3]",
      progressTrack: "bg-[#dce7fa]",
      topicChip: "bg-[#eef4ff]",
      topicText: "text-[#4c6eb5]",
      recommendationIcon: "text-[#b8894b]",
      recommendationText: "text-[#786655]",
      percentage: "text-[#3f72c9]",
    },
  },
  {
    id: "calculus",
    label: "微积分",
    icon: "∫",
    overview: "极限、导数、积分与微分方程",
    mastery: 70,
    topics: ["导数", "极限", "定积分", "微分方程"],
    recommendation: "多做定积分的换元与分部积分练习",
    theme: {
      iconShell: "from-[#a898e3] to-[#7566c7]",
      iconText: "text-white",
      iconShadow: "shadow-[0_14px_32px_rgba(117,102,199,0.22)]",
      progress: "bg-[#8a79d4]",
      progressTrack: "bg-[#ebe7fb]",
      topicChip: "bg-[#f2effe]",
      topicText: "text-[#6f62b7]",
      recommendationIcon: "text-[#9f86db]",
      recommendationText: "text-[#786e95]",
      percentage: "text-[#7566c7]",
    },
  },
  {
    id: "linear-algebra",
    label: "线性代数",
    icon: "[A]",
    overview: "向量空间、矩阵与线性变换等",
    mastery: 65,
    topics: ["正定矩阵", "特征值", "线性变换", "向量空间"],
    recommendation: "重点复习正定矩阵的判定方法",
    theme: {
      iconShell: "from-[#54b8c4] to-[#2d8e9b]",
      iconText: "text-white",
      iconShadow: "shadow-[0_14px_32px_rgba(45,142,155,0.24)]",
      progress: "bg-[#2f9aa8]",
      progressTrack: "bg-[#d9f0f3]",
      topicChip: "bg-[#eaf8fa]",
      topicText: "text-[#2e8590]",
      recommendationIcon: "text-[#2d8e9b]",
      recommendationText: "text-[#5b6c70]",
      percentage: "text-[#2d8e9b]",
    },
  },
  {
    id: "chinese",
    label: "语文",
    icon: "文",
    overview: "文言文、现代文与文学鉴赏",
    mastery: 72,
    topics: ["古文", "修辞手法", "现代文阅读", "诗词鉴赏"],
    recommendation: "积累常见修辞手法并分析例句",
    theme: {
      iconShell: "from-[#d6a46d] to-[#bb7e40]",
      iconText: "text-white",
      iconShadow: "shadow-[0_14px_32px_rgba(187,126,64,0.22)]",
      progress: "bg-[#c98a4a]",
      progressTrack: "bg-[#f5e4d1]",
      topicChip: "bg-[#fcf2e7]",
      topicText: "text-[#b47a40]",
      recommendationIcon: "text-[#b47a40]",
      recommendationText: "text-[#776252]",
      percentage: "text-[#bb7e40]",
    },
  },
  {
    id: "english",
    label: "英语",
    icon: "Aa",
    overview: "语法、阅读、写作与词汇辨析",
    mastery: 68,
    topics: ["时态", "阅读理解", "写作", "词汇辨析"],
    recommendation: "强化阅读理解的长难句分析能力",
    theme: {
      iconShell: "from-[#76bf7b] to-[#479d53]",
      iconText: "text-white",
      iconShadow: "shadow-[0_14px_32px_rgba(71,157,83,0.22)]",
      progress: "bg-[#52a35b]",
      progressTrack: "bg-[#def3e0]",
      topicChip: "bg-[#edf9ee]",
      topicText: "text-[#4b9453]",
      recommendationIcon: "text-[#53a05b]",
      recommendationText: "text-[#60725f]",
      percentage: "text-[#479d53]",
    },
  },
  {
    id: "college-physics",
    label: "大学物理",
    icon: "⚛",
    overview: "力学、电磁学与振动波动等",
    mastery: 60,
    topics: ["牛顿定律", "电场", "动量守恒", "简谐振动"],
    recommendation: "多做电场相关题目巩固概念",
    theme: {
      iconShell: "from-[#f5af63] to-[#f08a20]",
      iconText: "text-white",
      iconShadow: "shadow-[0_14px_32px_rgba(240,138,32,0.24)]",
      progress: "bg-[#f08a20]",
      progressTrack: "bg-[#fde8cf]",
      topicChip: "bg-[#fff2e2]",
      topicText: "text-[#d97a18]",
      recommendationIcon: "text-[#f08a20]",
      recommendationText: "text-[#7b6755]",
      percentage: "text-[#f08a20]",
    },
  },
];

const WEAK_CONCEPTS: WeakConceptData[] = [
  {
    id: "ellipse-area",
    label: "椭圆面积公式",
    subjectId: "high-math",
    subjectLabel: "高中数学",
    topicLabel: "椭圆",
    shortIcon: "数",
    iconShell: "bg-gradient-to-br from-[#79a7eb] to-[#4673ca]",
    status: "薄弱",
  },
  {
    id: "derivative-definition",
    label: "导数定义",
    subjectId: "calculus",
    subjectLabel: "微积分",
    topicLabel: "导数",
    shortIcon: "微",
    iconShell: "bg-gradient-to-br from-[#aa9ce5] to-[#7b6ccb]",
    status: "薄弱",
  },
  {
    id: "positive-definite-check",
    label: "正定矩阵判定",
    subjectId: "linear-algebra",
    subjectLabel: "线性代数",
    topicLabel: "正定矩阵",
    shortIcon: "线",
    iconShell: "bg-gradient-to-br from-[#62bfcb] to-[#2f929f]",
    status: "薄弱",
  },
  {
    id: "ancient-function-words",
    label: "古文实词",
    subjectId: "chinese",
    subjectLabel: "语文",
    topicLabel: "文言文",
    shortIcon: "文",
    iconShell: "bg-gradient-to-br from-[#d4aa77] to-[#b47a40]",
    status: "待提升",
  },
  {
    id: "virtual-grammar",
    label: "虚拟语气",
    subjectId: "english",
    subjectLabel: "英语",
    topicLabel: "语法",
    shortIcon: "英",
    iconShell: "bg-gradient-to-br from-[#7bbe7e] to-[#4b9e55]",
    status: "待提升",
  },
  {
    id: "field-intensity",
    label: "电场强度计算",
    subjectId: "college-physics",
    subjectLabel: "大学物理",
    topicLabel: "电场",
    shortIcon: "物",
    iconShell: "bg-gradient-to-br from-[#f5ad61] to-[#f08a20]",
    status: "待提升",
  },
];

const DASHBOARD_SUMMARY = {
  subjectCount: 6,
  conceptCount: 38,
  masteredConceptCount: 24,
  masteryRate: 63,
  weakConceptCount: 8,
  weakConceptRate: 21,
};

const LEARNING_SUGGESTION = {
  title: "学习建议",
  description:
    "根据你的掌握情况，建议优先强化薄弱概念，每日坚持练习，稳步提升整体掌握率。",
  ctaLabel: "生成学习计划",
};

function normalizeText(value: string) {
  return value.trim().toLowerCase();
}

function matchesQuery(query: string, values: string[]) {
  if (!query) return true;
  return values.some((value) => normalizeText(value).includes(query));
}

function metricCards() {
  return [
    {
      label: "学科总数",
      value: DASHBOARD_SUMMARY.subjectCount,
      meta: "",
      icon: <BookOpen className="h-5 w-5 text-[#b8894b]" />,
      shell: "bg-[#faf4e9]",
    },
    {
      label: "概念总数",
      value: DASHBOARD_SUMMARY.conceptCount,
      meta: "",
      icon: <Grid2x2 className="h-5 w-5 text-[#4c7ed3]" />,
      shell: "bg-[#eef4ff]",
    },
    {
      label: "已掌握概念",
      value: DASHBOARD_SUMMARY.masteredConceptCount,
      meta: `${DASHBOARD_SUMMARY.masteryRate}% 掌握率`,
      icon: <CircleCheckBig className="h-5 w-5 text-[#4a9a59]" />,
      shell: "bg-[#edf9ef]",
    },
    {
      label: "薄弱概念",
      value: DASHBOARD_SUMMARY.weakConceptCount,
      meta: `${DASHBOARD_SUMMARY.weakConceptRate}% 需重点关注`,
      icon: <CircleAlert className="h-5 w-5 text-[#df5b4e]" />,
      shell: "bg-[#fdf0ee]",
    },
  ];
}

function statusBadgeClasses(status: WeakConceptStatus) {
  if (status === "薄弱") {
    return "bg-[#fff1ef] text-[#e06254]";
  }
  return "bg-[#fff4e5] text-[#e08a1f]";
}

function SummaryStatCard({
  icon,
  label,
  meta,
  shell,
  value,
}: {
  icon: ReactNode;
  label: string;
  meta: string;
  shell: string;
  value: number;
}) {
  return (
    <section className="rounded-[28px] border border-[rgba(210,192,165,0.78)] bg-white/82 px-5 py-5 shadow-[0_14px_40px_rgba(132,107,71,0.08)] backdrop-blur-sm">
      <div className="flex items-center gap-4">
        <div
          className={clsx(
            "flex h-14 w-14 shrink-0 items-center justify-center rounded-[20px]",
            shell,
          )}
        >
          {icon}
        </div>
        <div className="min-w-0">
          <div className="text-[2rem] font-semibold leading-none tracking-tight text-[#221c17]">
            {value}
          </div>
          <div className="mt-2 text-sm font-medium text-[#746454]">{label}</div>
          {meta ? (
            <div className="mt-1 text-xs tracking-[0.04em] text-[#9a8977]">
              {meta}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function SubjectFilterPill({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "inline-flex h-10 items-center rounded-full border px-5 text-sm font-medium transition",
        active
          ? "border-[#cea15f] bg-gradient-to-r from-[#cfaa67] to-[#b98b43] text-white shadow-[0_10px_24px_rgba(185,139,67,0.24)]"
          : "border-[rgba(221,211,197,0.85)] bg-white/72 text-[#584838] hover:bg-[#faf3e7]",
      )}
    >
      {label}
    </button>
  );
}

function SubjectMasteryCard({ subject }: { subject: SubjectMasteryCardData }) {
  return (
    <section className="rounded-[30px] border border-[rgba(212,198,176,0.85)] bg-white/84 px-6 py-5 shadow-[0_18px_44px_rgba(142,116,78,0.08)] backdrop-blur-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-4">
          <div
            className={clsx(
              "flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-gradient-to-br text-[1.65rem] font-semibold",
              subject.theme.iconShell,
              subject.theme.iconText,
              subject.theme.iconShadow,
            )}
          >
            {subject.icon}
          </div>
          <div className="min-w-0">
            <h2 className="text-[1.85rem] font-semibold leading-none tracking-tight text-[#221c17]">
              {subject.label}
            </h2>
            <p className="mt-3 text-sm leading-6 text-[#7a6857]">{subject.overview}</p>
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div className={clsx("text-[2rem] font-semibold leading-none", subject.theme.percentage)}>
            {subject.mastery}%
          </div>
          <div className="mt-2 text-sm font-medium text-[#8e7d6c]">掌握率</div>
        </div>
      </div>

      <div className={clsx("mt-5 h-2 rounded-full", subject.theme.progressTrack)}>
        <div
          className={clsx("h-full rounded-full transition-all duration-500", subject.theme.progress)}
          style={{ width: `${subject.mastery}%` }}
        />
      </div>

      <div className="mt-5 flex flex-wrap gap-2.5">
        {subject.topics.map((topic) => (
          <span
            key={`${subject.id}-${topic}`}
            className={clsx(
              "inline-flex rounded-full px-3 py-1.5 text-xs font-medium",
              subject.theme.topicChip,
              subject.theme.topicText,
            )}
          >
            {topic}
          </span>
        ))}
      </div>

      <div className="mt-6 flex items-start gap-3 border-t border-[rgba(226,216,202,0.92)] pt-4">
        <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center">
          <Lightbulb className={clsx("h-4 w-4", subject.theme.recommendationIcon)} />
        </div>
        <p className={clsx("text-sm leading-6", subject.theme.recommendationText)}>
          建议动作：{subject.recommendation}
        </p>
      </div>
    </section>
  );
}

function WeakConceptRow({ concept }: { concept: WeakConceptData }) {
  return (
    <div className="flex items-center gap-3 py-4 first:pt-0 last:pb-0">
      <div
        className={clsx(
          "flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl text-sm font-semibold text-white shadow-[0_10px_26px_rgba(0,0,0,0.08)]",
          concept.iconShell,
        )}
      >
        {concept.shortIcon}
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-lg font-semibold tracking-tight text-[#221c17]">
          {concept.label}
        </div>
        <div className="mt-1 text-sm text-[#8b7b6d]">
          {concept.subjectLabel} · {concept.topicLabel}
        </div>
      </div>
      <span
        className={clsx(
          "inline-flex shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold",
          statusBadgeClasses(concept.status),
        )}
      >
        {concept.status}
      </span>
    </div>
  );
}

function EmptyResult({
  title,
  body,
}: {
  title: string;
  body: string;
}) {
  return (
    <div className="rounded-[28px] border border-dashed border-[rgba(208,192,170,0.9)] bg-white/65 px-6 py-10 text-center">
      <div className="text-lg font-semibold tracking-tight text-[#2a211a]">{title}</div>
      <p className="mx-auto mt-3 max-w-md text-sm leading-7 text-[#8a796a]">{body}</p>
    </div>
  );
}

function LearningSuggestionBanner() {
  return (
    <section className="mt-8 rounded-[30px] border border-[rgba(213,198,174,0.88)] bg-white/70 px-6 py-5 shadow-[0_18px_46px_rgba(140,114,77,0.07)] backdrop-blur-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-start gap-4">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-[20px] bg-[#faf3e7]">
            <GraduationCap className="h-7 w-7 text-[#ccb183]" />
          </div>
          <div>
            <div className="text-[1.2rem] font-semibold tracking-tight text-[#241d17]">
              {LEARNING_SUGGESTION.title}
            </div>
            <p className="mt-2 max-w-3xl text-sm leading-7 text-[#7e6f61]">
              {LEARNING_SUGGESTION.description}
            </p>
          </div>
        </div>
        <button
          type="button"
          className="inline-flex h-11 items-center justify-center gap-2 rounded-full bg-gradient-to-r from-[#caa45c] to-[#b88a3f] px-6 text-sm font-semibold text-white shadow-[0_14px_30px_rgba(184,138,63,0.24)] transition hover:translate-y-[-1px]"
        >
          {LEARNING_SUGGESTION.ctaLabel}
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </section>
  );
}

export function KnowledgeWorkspace() {
  const [activeFilter, setActiveFilter] = useState<SubjectId>("all");
  const [searchQuery, setSearchQuery] = useState("");

  const normalizedQuery = normalizeText(searchQuery);

  const visibleSubjects = SUBJECT_CARDS.filter((subject) => {
    if (activeFilter !== "all" && subject.id !== activeFilter) return false;
    return matchesQuery(normalizedQuery, [
      subject.label,
      subject.overview,
      ...subject.topics,
      subject.recommendation,
    ]);
  });

  const visibleWeakConcepts = WEAK_CONCEPTS.filter((concept) => {
    if (activeFilter !== "all" && concept.subjectId !== activeFilter) return false;
    return matchesQuery(normalizedQuery, [
      concept.label,
      concept.subjectLabel,
      concept.topicLabel,
    ]);
  });

  return (
    <div className="page-shell min-h-screen">
      <section className="relative overflow-hidden rounded-[40px] border border-[rgba(214,198,173,0.9)] bg-[radial-gradient(circle_at_top,#fffdf9_0%,#fef8ef_32%,#fbf4e8_72%,#f6eddc_100%)] px-6 py-6 shadow-[0_28px_80px_rgba(128,103,72,0.10)] lg:px-9 lg:py-8">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(215,188,144,0.16),transparent_24%),radial-gradient(circle_at_right_center,rgba(255,255,255,0.52),transparent_28%)]" />
        <div className="pointer-events-none absolute right-[-1.5rem] top-[-0.75rem] hidden h-[260px] w-[320px] lg:block">
          <div className="absolute right-8 top-7 h-20 w-28 rounded-[24px] border border-[rgba(214,198,173,0.32)] bg-white/18" />
          <div className="absolute right-14 top-14 h-20 w-28 rounded-[24px] border border-[rgba(214,198,173,0.26)] bg-white/14" />
          <div className="absolute right-20 top-[5.5rem] h-20 w-28 rounded-[24px] border border-[rgba(214,198,173,0.22)] bg-white/10" />
          <div className="absolute right-0 top-0 h-20 w-20 rounded-full border border-[rgba(214,198,173,0.2)]" />
          <div className="absolute right-24 top-0 h-3 w-3 rounded-full bg-[rgba(214,198,173,0.26)]" />
          <div className="absolute right-44 top-14 h-2.5 w-2.5 rounded-full bg-[rgba(214,198,173,0.32)]" />
          <div className="absolute right-8 top-28 h-2 w-2 rounded-full bg-[rgba(214,198,173,0.3)]" />
          <div className="absolute right-[7.5rem] top-8 h-24 w-px rotate-[-28deg] bg-[rgba(214,198,173,0.18)]" />
          <div className="absolute right-[8.2rem] top-[1.6rem] h-6 w-3 rotate-[-22deg] rounded-full border border-[rgba(214,198,173,0.22)]" />
          <div className="absolute right-[5.5rem] top-[4.3rem] h-7 w-3 rotate-[18deg] rounded-full border border-[rgba(214,198,173,0.22)]" />
          <div className="absolute right-[10rem] top-[5.5rem] h-6 w-3 rotate-[-18deg] rounded-full border border-[rgba(214,198,173,0.18)]" />
        </div>

        <div className="relative">
          <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
            <div className="max-w-[720px]">
              <div className="text-sm font-medium tracking-[0.18em] text-[#7d6b59]">知识状态</div>
              <h1 className="mt-4 font-serif text-[2.9rem] font-semibold tracking-tight text-[#2b2017] sm:text-[3.35rem]">
                概念掌握面板
              </h1>
              <p className="mt-4 max-w-3xl text-base leading-8 text-[#7c6b5a]">
                汇总各学科下概念的掌握情况，智能识别薄弱点，提供个性化学习建议。
              </p>
            </div>

            <label className="relative block w-full max-w-[370px] shrink-0">
              <Search className="pointer-events-none absolute left-5 top-1/2 h-5 w-5 -translate-y-1/2 text-[#a49588]" />
              <input
                type="text"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="搜索概念、知识点或学科"
                className="h-14 w-full rounded-full border border-[rgba(222,208,186,0.92)] bg-white/72 pl-14 pr-5 text-sm text-[#2f241b] shadow-[inset_0_1px_0_rgba(255,255,255,0.6)] outline-none transition placeholder:text-[#a19386] focus:border-[#cba25e] focus:bg-white"
              />
            </label>
          </div>

          <div className="mt-8 flex flex-wrap gap-3">
            {SUBJECT_FILTERS.map((filter) => (
              <SubjectFilterPill
                key={filter.id}
                active={activeFilter === filter.id}
                label={filter.label}
                onClick={() => setActiveFilter(filter.id)}
              />
            ))}
          </div>

          <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {metricCards().map((card) => (
              <SummaryStatCard key={card.label} {...card} />
            ))}
          </div>

          <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_300px]">
            <div>
              {visibleSubjects.length ? (
                <div className="grid gap-5 lg:grid-cols-2 2xl:grid-cols-3">
                  {visibleSubjects.map((subject) => (
                    <SubjectMasteryCard key={subject.id} subject={subject} />
                  ))}
                </div>
              ) : (
                <EmptyResult
                  title="没有匹配的学科卡片"
                  body="试试切换学科筛选，或者用更短的关键词搜索概念与知识点。"
                />
              )}
            </div>

            <aside className="rounded-[30px] border border-[rgba(212,198,176,0.88)] bg-white/84 px-5 py-5 shadow-[0_18px_46px_rgba(142,116,78,0.08)] backdrop-blur-sm">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-11 w-11 items-center justify-center rounded-[18px] bg-[#faf3e7]">
                    <BookText className="h-5 w-5 text-[#c19a5b]" />
                  </div>
                  <div>
                    <div className="text-[1.25rem] font-semibold tracking-tight text-[#241d17]">
                      待强化概念
                    </div>
                    <div className="mt-1 text-sm text-[#928273]">查看全部</div>
                  </div>
                </div>
              </div>

              <div className="mt-5 space-y-1 divide-y divide-[rgba(229,219,203,0.9)]">
                {visibleWeakConcepts.length ? (
                  visibleWeakConcepts.map((concept) => (
                    <WeakConceptRow key={concept.id} concept={concept} />
                  ))
                ) : (
                  <div className="py-8">
                    <EmptyResult
                      title="没有命中待强化概念"
                      body="当前筛选条件下没有需要重点展示的薄弱概念。"
                    />
                  </div>
                )}
              </div>
            </aside>
          </div>

          <LearningSuggestionBanner />
        </div>
      </section>
    </div>
  );
}
