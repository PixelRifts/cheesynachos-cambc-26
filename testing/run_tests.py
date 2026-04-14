"""Main test runner for bot testing system.

This script reads test settings from testing/test_config.toml and runs tests
using multi-threaded execution.
"""

import sys
import os
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import tomllib

from match_runner import MatchRunner, MatchResult
from results_analyzer import ResultsAnalyzer


def _load_toml_config(config_path: Path) -> dict:
    """Load and parse a TOML config file."""
    with config_path.open("rb") as f:
        return tomllib.load(f)


def _discover_bots_and_maps(root_dir: Path, project_cfg: dict) -> tuple[list[str], list[str], Path]:
    """Discover bots and maps based on cambc.toml settings."""
    bots_dir = root_dir / project_cfg.get("bots_dir", "bots")
    maps_dir = root_dir / project_cfg.get("maps_dir", "maps")

    bots = sorted([p.name for p in bots_dir.iterdir() if p.is_dir()]) if bots_dir.exists() else []
    maps = sorted([p.stem for p in maps_dir.glob("*.map26")]) if maps_dir.exists() else []

    return bots, maps, bots_dir


def run_match_task(runner: MatchRunner, bot1: str, bot2: str, 
                   map_name: str, seed: int) -> MatchResult:
    """Task function for running a single match.
    
    Args:
        runner: MatchRunner instance
        bot1: First bot name
        bot2: Second bot name
        map_name: Map name
        seed: Random seed
        
    Returns:
        MatchResult object
    """
    return runner.run_match(bot1, bot2, map_name, seed)


def main():
    """Main entry point for the test runner - reads config from TOML."""
    print("="*60)
    print("Cambridge Battlecode Bot Testing System")
    print("="*60)
    
    try:
        testing_dir = Path(__file__).resolve().parent
        root_dir = testing_dir.parent
        test_cfg_path = testing_dir / "test_config.toml"
        project_cfg_path = root_dir / "cambc.toml"

        if not test_cfg_path.exists():
            print(f"Error: Missing config file: {test_cfg_path}")
            return 1

        if not project_cfg_path.exists():
            print(f"Error: Missing project config: {project_cfg_path}")
            return 1

        test_cfg = _load_toml_config(test_cfg_path)
        project_cfg = _load_toml_config(project_cfg_path)

        # Get available bots and maps from cambc.toml paths
        bots, maps, bots_dir = _discover_bots_and_maps(root_dir, project_cfg)
        
        if not bots:
            print("Error: No bots found in bots directory!")
            return 1
        
        if not maps:
            print("Error: No maps found in maps directory!")
            return 1
        
        print(f"\nFound {len(bots)} bots and {len(maps)} maps")
        
        # Read test settings from testing/test_config.toml
        target_bot = test_cfg.get("target_bot", bots[0])
        if target_bot not in bots:
            print(f"Error: target_bot '{target_bot}' not found in {bots_dir}")
            return 1

        raw_opponents = test_cfg.get("opponents", ["all"])
        if "all" in raw_opponents:
            opponents = [b for b in bots if b != target_bot]
        else:
            opponents = [b for b in raw_opponents if b in bots and b != target_bot]
            if not opponents:
                opponents = [b for b in bots if b != target_bot]

        raw_maps = test_cfg.get("maps", ["all"])
        if "all" in raw_maps:
            test_maps = maps
        elif "sample10" in raw_maps:
            test_maps = random.sample(maps, 10)
        elif "sample20" in raw_maps:
            test_maps = random.sample(maps, 20)
        elif "sample30" in raw_maps:
            test_maps = random.sample(maps, 30)
        elif "sample40" in raw_maps:
            test_maps = random.sample(maps, 40)
        else:
            test_maps = [m for m in raw_maps if m in maps]
            if not test_maps:
                print("Invalid maps value")
                return

        threads = int(test_cfg.get("threads", min(os.cpu_count() or 4, 8)))
        matches_per = int(test_cfg.get("matches_per", 1))
        seed = int(test_cfg.get("seed", int(project_cfg.get("seed", 1))))
        save_csv = bool(test_cfg.get("save_csv", True))
        results_dir = testing_dir / str(test_cfg.get("results_dir", "results"))
        
        print("\n" + "="*60)
        print("TEST CONFIGURATION (from config)")
        print("="*60)
        print(f"Target Bot:     {target_bot}")
        print(f"Opponents:      {len(opponents)} bots")
        print(f"Maps:           {len(test_maps)} maps")
        print(f"Matches/combo:  {matches_per}")
        print(f"Total Matches:  {len(opponents) * len(test_maps) * matches_per}")
        print(f"Threads:        {threads}")
        print(f"Save CSV:       {save_csv}")
        print("="*60)
        
        # Initialize components
        runner = MatchRunner(root_dir)
        analyzer = ResultsAnalyzer(results_dir)
        
        # Build task list
        tasks = []
        for opponent in opponents:
            for map_name in test_maps:
                for match_num in range(matches_per):
                    test_seed = seed + match_num
                    if match_num % 2 == 0:
                        tasks.append((target_bot, opponent, map_name, test_seed))
                    else:
                        tasks.append((opponent, target_bot, map_name, test_seed))
        
        print(f"\n\nRunning {len(tasks)} matches...")
        print("Progress: ", end='', flush=True)
        
        # Execute matches in parallel
        results = []
        completed = 0
        total = len(tasks)
        
        with ThreadPoolExecutor(max_workers=threads) as executor:
            # Submit all tasks
            futures = {
                executor.submit(run_match_task, runner, bot1, bot2, map_name, test_seed): (bot1, bot2, map_name)
                for bot1, bot2, map_name, test_seed in tasks
            }
            
            # Collect results as they complete
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                    completed += 1
                    
                    # Progress indicator
                    # if completed % max(1, total // UPDATE_RESOLUTION) == 0 or completed == total:
                    pct = (completed / total) * 100
                    print(f"\rProgress: {completed}/{total} ({pct:.0f}%)", end='', flush=True)
                    
                except Exception as e:
                    print(f"\nError in match: {e}")
        
        print("\n\nAll matches completed!")
        
        stats = analyzer.analyze_results(target_bot, results)
        
        csv_path = None
        if save_csv:
            csv_path = analyzer.save_to_csv(target_bot, results)
        
        # Print summary
        analyzer.print_summary(target_bot, stats, csv_path)
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        return 1
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
