import test from "node:test";
import assert from "node:assert/strict";

import {
  answerPayload,
  defaultZhVersionName,
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


test("defaultZhVersionName formats the zh version name", () => {
  assert.equal(defaultZhVersionName("数据分析师"), "中文简历 · 数据分析师");
  assert.equal(defaultZhVersionName(""), "中文简历 · 通用岗位");
});
