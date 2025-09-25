import os, yaml
from pathlib import Path

def load_config(path=Path('config.yaml')):
    cfg = {}
    if path.exists():
        cfg = yaml.safe_load(path.read_text())
    # overlay env
    return cfg
