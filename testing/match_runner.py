"""Match execution module for running individual bot vs bot matches."""

import subprocess
import re
from pathlib import Path
from typing import Dict, Optional, Tuple
from datetime import datetime


class MatchResult:
    """Represents the result of a single match."""
    
    def __init__(self, bot1: str, bot2: str, map_name: str, 
                 winner: Optional[str], score: Tuple[int, int],
                 timestamp: datetime, error: Optional[str] = None):
        self.bot1 = bot1
        self.bot2 = bot2
        self.map_name = map_name
        self.winner = winner
        self.score = score  # (bot1_score, bot2_score)
        self.timestamp = timestamp
        self.error = error
    
    def __repr__(self):
        if self.error:
            return f"MatchResult({self.bot1} vs {self.bot2} on {self.map_name}: ERROR - {self.error})"
        return f"MatchResult({self.bot1} vs {self.bot2} on {self.map_name}: Winner={self.winner}, Score={self.score})"


class MatchRunner:
    """Runs individual bot vs bot matches."""
    
    def __init__(self, root_dir: Path):
        """Initialize match runner.
        
        Args:
            root_dir: Root directory of the project
        """
        self.root_dir = root_dir
    
    def run_match(self, bot1: str, bot2: str, map_name: str, seed: int = 1) -> MatchResult:
        """Run a single match between two bots.
        
        Args:
            bot1: Name of first bot
            bot2: Name of second bot
            map_name: Name of the map (without .map26 extension)
            seed: Random seed for the match
            
        Returns:
            MatchResult object with match outcome
        """
        timestamp = datetime.now()
        
        try:
            # Construct full map path
            maps_dir = self.root_dir / "maps"
            map_file = maps_dir / f"{map_name}.map26"
            
            result = subprocess.run(
                ["cambc", "run", bot1, bot2, str(map_file), "--seed", str(seed)],
                cwd=self.root_dir,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            winner, score = self._parse_output(result.stdout, result.stderr, bot1, bot2)
            return MatchResult(bot1, bot2, map_name, winner, score, timestamp)
            
        except subprocess.TimeoutExpired:
            return MatchResult(bot1, bot2, map_name, None, (0, 0), timestamp, error="Timeout")
        except Exception as e:
            return MatchResult(bot1, bot2, map_name, None, (0, 0), timestamp, error=str(e))
    
    def _parse_output(self, stdout: str, stderr: str, bot1: str, bot2: str) -> Tuple[Optional[str], Tuple[int, int]]:
        """Parse cambc output to determine winner and score.
            
        Returns:
            Tuple of (winner_name, (bot1_score, bot2_score))
        """
        winner = None
        bot1_score = 0
        bot2_score = 0
        
        winner_match = re.search(r'Winner:\s+(\S+)', stdout)
        if winner_match:
            winner = winner_match.group(1)
        
        lines = stdout.split('\n')
        header_bots = None
        
        for i, line in enumerate(lines):
            if 'Titanium' in line and i > 0:
                header_line = lines[i-1]
                parts = header_line.split()
                if len(parts) == 2:
                    header_bots = (parts[0], parts[1])
                break
        
        buildings_match = re.search(r'Buildings\s+(\d+)\s+(\d+)', stdout)
        
        if header_bots and buildings_match:
            first_bot, second_bot = header_bots
            first_score = int(buildings_match.group(1))
            second_score = int(buildings_match.group(2))
            
            # Map scores to bot1 and bot2 based on header positions
            if first_bot == bot1:
                bot1_score = first_score
                bot2_score = second_score
            else:
                bot1_score = second_score
                bot2_score = first_score
        
        return winner, (bot1_score, bot2_score)
