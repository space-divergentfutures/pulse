"""PyInstaller entry point — absolute imports only (no parent package in frozen bundle)."""
from pulse.app import main

if __name__ == "__main__":
    main()
