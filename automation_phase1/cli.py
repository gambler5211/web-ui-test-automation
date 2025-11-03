from __future__ import annotations
import argparse
import json
from pathlib import Path
from .compiler import Compiler


def main():
    p = argparse.ArgumentParser(description="Compile Gherkin to Steps JSON (regex-first, optional LLM fallback)")
    p.add_argument("--in", dest="feature", required=True, help="Path to .feature file")
    p.add_argument("--scenario", dest="scenario", help="Scenario name (defaults to first)")
    p.add_argument("--out", dest="out", required=True, help="Path to write scenario JSON")
    p.add_argument("--base-url", dest="base_url", default=None, help="Base URL to put in meta")
    p.add_argument("--overrides", dest="overrides", default=None, help="YAML of step text→Step overrides")
    p.add_argument("--cache", dest="cache", default=".compile_cache.sqlite3", help="Path to SQLite cache")
    p.add_argument("--use-llm-compiler", action="store_true", help="Enable LLM fallback for unmatched lines")
    p.add_argument("--llm-model", default="gpt-4o-mini")
    p.add_argument("--natural-language-mode", default="auto", 
                   choices=["auto", "always", "never"],
                   help="Natural language mode: auto=NL agent for unmatched steps, always=treat all as NL, never=fail on unmatched (default: auto)")

    args = p.parse_args()
    compiler = Compiler(use_llm=args.use_llm_compiler, model=args.llm_model, natural_language_mode=args.natural_language_mode)

    res = compiler.compile_feature(
        feature_path=Path(args.feature),
        scenario_name=args.scenario,
        base_url=args.base_url,
        overrides_path=Path(args.overrides) if args.overrides else None,
        cache_path=Path(args.cache) if args.cache else None,
    )

    out_path = Path(args.out)
    # write without nulls for cleaner output
    out_path.write_text(json.dumps(res.scenario.model_dump(exclude_none=True), indent=2), encoding="utf-8")

    # Also write provenance next to it for debugging
    prov_path = out_path.with_suffix(".provenance.json")
    prov_path.write_text(json.dumps([p.model_dump(exclude_none=True) for p in res.provenance], indent=2), encoding="utf-8")

    print(f"Wrote {out_path} and {prov_path}")

if __name__ == "__main__":
    main()


