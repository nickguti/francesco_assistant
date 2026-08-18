import os
import sys

# Rende importabile il package `src` quando pytest viene lanciato dalla root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
