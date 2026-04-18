import os
import subprocess
import pandas as pd
import re
import sys
from time import sleep
import matplotlib.pyplot as plt

TEAM = "cheesynachos"
# TARGET = "bwaaa"
TARGET = sys.argv[1]

def run_cmd(command, env):
    cmd = "chcp 65001 >nul && " + subprocess.list2cmdline(command)
    result = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        env=env
    )

    return result.stdout

import re
def parse_ascii_table(text):
    rows = []
    lines = text.splitlines()
    
    for line in lines:
        line = line.strip()
        
        # Only process lines that start with "| " and are not the header separator
        if line.startswith("|") and not set(line[1:-1]).issubset({"-", "+"}):
            # Split by | and strip spaces
            parts = [p.strip() for p in line.split("|")]
            
            # There will be empty strings at start/end due to leading/trailing |
            if len(parts) < 7:
                continue
            
            # Skip the header row
            if parts[1] == "#":
                continue
            
            # Parse row
            row = {
                "rank": int(parts[1]),
                "team": parts[2],
                "rating": int(parts[3]),
                "matches": int(parts[4]),
                "category": parts[5],
                "region": parts[6],
            }
            rows.append(row)
    
    return rows

def parse_ascii_tableid(text):
    rows = []

    for line in text.splitlines():
        line = line.strip()
        # Skip border lines and header row
        if line.startswith("+") or line.startswith("|-") or "Team ID" in line:
            continue

        if line.startswith("|"):
            # Split on | and strip spaces
            parts = [p.strip() for p in line.split("|")]

            # Remove empty strings from leading/trailing pipes
            parts = [p for p in parts if p]

            if len(parts) != 6:
                continue  # skip malformed rows

            row = {
                "team_id": parts[0],
                "name": parts[1],
                "category": parts[2],
                "rating": int(parts[3]),
                "matches": int(parts[4]),
                "region": parts[5],
            }
            rows.append(row)

    return rows



command = ["cambc", "team", "search", TARGET]
env = os.environ.copy()
env["COLUMNS"] = "1000"
env["LINES"] = "100000"


output = run_cmd(command, env)
target_data = parse_ascii_tableid(output)[0]

target_id = target_data["team_id"]
if target_id == None:
    print("failed to find team", TARGET)
else:
    for i in range(5):
        command = ["cambc", "match", "unrated", target_id]
        output = run_cmd(command, env)
        print(output)