"""
Application launcher forwarding directly to main.py.
Maintains backward compatibility for systems referencing app.py.
"""

from main import main, MainSpeechEvaluator

if __name__ == "__main__":
    main()
