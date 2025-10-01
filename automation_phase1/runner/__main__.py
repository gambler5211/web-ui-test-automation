from __future__ import annotations
import argparse
import asyncio
from pathlib import Path
from .orchestrator import run_scenario


async def main():
    """CLI for running scenarios."""
    parser = argparse.ArgumentParser(description="Run Playwright scenarios from compiled JSON")
    parser.add_argument("--in", dest="scenario", required=True, help="Path to scenario JSON file")
    parser.add_argument("--out", dest="output", default="proofs", help="Output directory for proofs")
    parser.add_argument("--headed", action="store_true", help="Run in headed mode (show browser)")
    parser.add_argument("--video", action="store_true", help="Record video")
    parser.add_argument("--trace", action="store_true", help="Record Playwright trace")
    parser.add_argument("--har", action="store_true", help="Record network HAR file")
    parser.add_argument("--use-llm-resolver", action="store_true", help="Enable LLM-based target resolver fallback")
    
    args = parser.parse_args()
    
    scenario_path = Path(args.scenario)
    output_dir = Path(args.output)
    
    if not scenario_path.exists():
        print(f"Error: Scenario file not found: {scenario_path}")
        return 1
    
    # Run the scenario
    proofs_dir = await run_scenario(
        scenario_path=scenario_path,
        output_dir=output_dir,
        headed=args.headed,
        video=args.video,
        trace=args.trace,
        har=args.har,
        use_llm_resolver=args.use_llm_resolver
    )
    
    print(f"Scenario execution completed. Proofs saved to: {proofs_dir}")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
