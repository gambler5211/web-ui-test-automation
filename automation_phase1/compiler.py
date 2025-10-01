from __future__ import annotations
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Optional, Tuple
import yaml
from gherkin.token_scanner import TokenScanner
from gherkin.parser import Parser

from .schemas import Step, Scenario, ScenarioMeta, CompileResult, CompileProvenance
from .regex_rules import compile_by_regex
from .llm_client import LLMCompiler, LLMNotConfigured

CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
  key TEXT PRIMARY KEY,
  json TEXT NOT NULL
);
"""

class Compiler:
    def __init__(self, use_llm: bool = False, model: str = "gpt-4o-mini"):
        self.use_llm = use_llm
        self.llm: Optional[LLMCompiler] = None
        if use_llm:
            try:
                self.llm = LLMCompiler(model=model)
            except LLMNotConfigured:
                # Degrade gracefully: caller can still compile via regex
                self.llm = None
        self.conn = None

    def _cache_connect(self, path: Path):
        self.conn = sqlite3.connect(path)
        self.conn.execute(CACHE_SCHEMA)
        self.conn.commit()

    def _cache_get(self, key: str) -> Optional[Step]:
        if not self.conn: return None
        cur = self.conn.execute("SELECT json FROM cache WHERE key=?", (key,))
        row = cur.fetchone()
        if row:
            return Step.model_validate_json(row[0])
        return None

    def _cache_put(self, key: str, step: Step):
        if not self.conn: return
        self.conn.execute("INSERT OR REPLACE INTO cache(key,json) VALUES(?,?)", (key, step.model_dump_json()))
        self.conn.commit()

    @staticmethod
    def _hash(line: str) -> str:
        return hashlib.sha1(line.strip().encode()).hexdigest()

    def _load_overrides(self, overrides_path: Optional[Path]) -> dict[str, dict]:
        if not overrides_path or not overrides_path.exists():
            return {}
        return yaml.safe_load(overrides_path.read_text()) or {}

    def compile_feature(self,
                        feature_path: Path,
                        scenario_name: Optional[str] = None,
                        base_url: Optional[str] = None,
                        overrides_path: Optional[Path] = None,
                        cache_path: Optional[Path] = None
                        ) -> CompileResult:
        feature_text = feature_path.read_text(encoding="utf-8")
        parser = Parser()
        doc = parser.parse(TokenScanner(feature_text))

        # Select first scenario or by name
        gherkin_scenarios = [s for c in doc["feature"]["children"] for s in ([c["scenario"]] if "scenario" in c else [])]
        scenario_node = None
        if scenario_name:
            for s in gherkin_scenarios:
                if s["name"].strip() == scenario_name.strip():
                    scenario_node = s; break
        if not scenario_node:
            scenario_node = gherkin_scenarios[0]

        # Resolve base_url precedence: CLI flag > scenario tag > feature tag
        def _extract_base_url_from_tags(tags: list[dict]) -> Optional[str]:
            for t in tags or []:
                name = (t.get("name") or "").strip()
                if name.startswith("@base_url="):
                    return name.split("@base_url=", 1)[1].strip()
            return None

        feature_tags = doc["feature"].get("tags", [])
        scenario_tags = scenario_node.get("tags", [])
        tag_base_url = _extract_base_url_from_tags(scenario_tags) or _extract_base_url_from_tags(feature_tags)
        effective_base_url = base_url or tag_base_url

        meta = ScenarioMeta(name=scenario_node["name"], base_url=effective_base_url)
        steps_out: list[Step] = []
        provenance: list[CompileProvenance] = []

        overrides = self._load_overrides(overrides_path)
        if cache_path:
            self._cache_connect(cache_path)

        for step in scenario_node["steps"]:
            keyword = step["keyword"].strip()  # Given/When/Then/And/But
            text = step["text"].strip()
            line = f"{text}"  # keep lean; we don't rely on keyword

            # 1) Overrides
            if text in overrides:
                data = overrides[text]
                s = Step.model_validate(data)
                steps_out.append(s)
                provenance.append(CompileProvenance(line=text, source="override", step=s))
                continue

            # 2) Cache
            key = self._hash(line)
            cached = self._cache_get(key) if self.conn else None
            if cached:
                steps_out.append(cached)
                provenance.append(CompileProvenance(line=text, source="regex" if compile_by_regex(line) else "llm", step=cached))
                continue

            # 3) Regex pass
            s = compile_by_regex(line)
            if s:
                # Allow rule to return a single Step or a list[Step]
                if isinstance(s, list):
                    for si in s:
                        steps_out.append(si)
                        provenance.append(CompileProvenance(line=text, source="regex", step=si))
                    # Do not cache multi-step expansions for now
                else:
                    steps_out.append(s)
                    provenance.append(CompileProvenance(line=text, source="regex", step=s))
                    self._cache_put(key, s)
                continue

            # 4) LLM fallback
            if self.llm:
                s = self.llm.compile_step(line)
                steps_out.append(s)
                provenance.append(CompileProvenance(line=text, source="llm", step=s))
                self._cache_put(key, s)
                continue

            # 5) Give up
            raise ValueError(f"Unrecognized step and LLM disabled: {text}")

        scenario = Scenario(meta=meta, steps=steps_out)
        return CompileResult(scenario=scenario, provenance=provenance)


