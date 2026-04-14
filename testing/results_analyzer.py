"""Results analysis module for calculating statistics and generating reports."""

import csv
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime
from match_runner import MatchResult


class ResultsAnalyzer:
    """Analyzes match results and generates statistics."""
    
    def __init__(self, results_dir: Path):
        """Initialize results analyzer.
        
        Args:
            results_dir: Directory to save results
        """
        self.results_dir = results_dir
        self.results_dir.mkdir(exist_ok=True)
    
    def analyze_results(self, target_bot: str, results: List[MatchResult]) -> Dict:
        """Analyze match results for a target bot.
        
        Args:
            target_bot: Name of the bot being tested
            results: List of MatchResult objects
            
        Returns:
            Dictionary with statistics
        """
        if not results:
            return {
                'total_matches': 0,
                'wins': 0,
                'losses': 0,
                'errors': 0,
                'win_rate': 0.0,
                'opponents': {}
            }
        
        total_matches = len(results)
        wins = sum(1 for r in results if r.winner == target_bot and not r.error)
        errors = sum(1 for r in results if r.error)
        valid_matches = total_matches - errors
        losses = valid_matches - wins
        
        # Calculate win rate
        win_rate = wins / valid_matches if valid_matches > 0 else 0.0
        
        # Per-opponent statistics
        opponents = {}
        for result in results:
            opponent = result.bot2 if result.bot1 == target_bot else result.bot1
            
            if opponent not in opponents:
                opponents[opponent] = {
                    'matches': 0,
                    'wins': 0,
                    'losses': 0,
                    'errors': 0
                }
            
            opponents[opponent]['matches'] += 1
            if result.error:
                opponents[opponent]['errors'] += 1
            elif result.winner == target_bot:
                opponents[opponent]['wins'] += 1
            else:
                opponents[opponent]['losses'] += 1
        
        # Calculate win rates per opponent
        for opp, stats in opponents.items():
            valid = stats['matches'] - stats['errors']
            stats['win_rate'] = stats['wins'] / valid if valid > 0 else 0.0
        
        return {
            'total_matches': total_matches,
            'wins': wins,
            'losses': losses,
            'errors': errors,
            'win_rate': win_rate,
            'opponents': opponents
        }
    

    def save_to_csv(self, target_bot: str, results: List[MatchResult], 
                    filename: str = None) -> Path:
        """Save results to CSV file.
        
        Args:
            target_bot: Name of the bot being tested
            results: List of MatchResult objects
            filename: Optional custom filename
            
        Returns:
            Path to the created CSV file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{target_bot}_results_{timestamp}.csv"
        
        csv_path = self.results_dir / filename
        
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow(['Timestamp', 'ID', 'Bot1', 'Bot2', 'Map', 'Winner', 
                           'Score_Bot1', 'Score_Bot2', 'Error', 'Command'])
            
            # Data rows
            for result in results:
                writer.writerow([
                    result.timestamp.isoformat(),
                    result.id,
                    result.bot1,
                    result.bot2,
                    result.map_name,
                    result.winner or 'N/A',
                    result.score[0],
                    result.score[1],
                    result.error or '',
                    "cambc run " + result.bot1 + " " + result.bot2 + " --watch maps/" + result.map_name + ".map26",
                ])
        
        return csv_path
    
    def print_summary(self, target_bot: str, stats: Dict, csv_path: Path = None):
        """Print formatted summary of results.
        
        Args:
            target_bot: Name of the bot being tested
            stats: Statistics dictionary from analyze_results
            csv_path: Optional path to CSV file
        """
        print("\n" + "="*60)
        print(f"TEST RESULTS FOR: {target_bot}")
        print("="*60)
        
        print(f"\nOverall Statistics:")
        print(f"  Total Matches:  {stats['total_matches']}")
        print(f"  Wins:           {stats['wins']}")
        print(f"  Losses:         {stats['losses']}")
        print(f"  Errors:         {stats['errors']}")
        print(f"  Win Rate:       {stats['win_rate']:.1%}")
        
        if stats['opponents']:
            print(f"\nPer-Opponent Results:")
            print(f"  {'Opponent':<25} {'Matches':>8} {'Wins':>6} {'Losses':>6} {'Errors':>7} {'Win Rate':>10}")
            print(f"  {'-'*25} {'-'*8} {'-'*6} {'-'*6} {'-'*7} {'-'*10}")
            
            for opp, opp_stats in sorted(stats['opponents'].items()):
                print(f"  {opp:<25} {opp_stats['matches']:>8} {opp_stats['wins']:>6} "
                      f"{opp_stats['losses']:>6} {opp_stats['errors']:>7} {opp_stats['win_rate']:>9.1%}")
        
        if csv_path:
            print(f"\nDetailed results saved to: {csv_path}")
        
        print("="*60 + "\n")
