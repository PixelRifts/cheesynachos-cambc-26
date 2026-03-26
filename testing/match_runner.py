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
            map_name: Name of the map
            seed: Random seed for the match
            
        Returns:
            MatchResult object with match outcome
        """
        #Needs to be implemented later. For now it returns a dummy value.
        timestamp = datetime.now()
        return MatchResult(bot1, bot2, map_name, None, (0, 0), timestamp)
    
    def _parse_output(self, stdout: str, stderr: str, bot1: str, bot2: str) -> Tuple[Optional[str], Tuple[int, int]]:
        """Parse cambc output to determine winner and score. Needs to be implemented later.
            
        Returns:
            Tuple of (winner_name, (bot1_score, bot2_score))
        """
        
        return None, (0, 0)
