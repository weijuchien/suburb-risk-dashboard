#!/usr/bin/env python3

from src.dashboard import create_app
import sys
import os
from pathlib import Path


current_dir = Path(__file__).parent
src_dir = current_dir / "src"
sys.path.insert(0, str(src_dir))


def main():

    app = create_app()
    app.run(debug=True, host='127.0.0.1', port=8050)


if __name__ == "__main__":
    main()
