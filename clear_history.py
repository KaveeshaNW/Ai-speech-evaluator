"""
Speech Evaluation History Purge Utility.
Removes:
- All archived JSON speech reports in reports/
- Latest evaluation_report.json at workspace root
- All recorded speech session history from speech_evaluator.db
Preserves:
- Registered student accounts and login credentials
"""

import glob
import os
import sqlite3
import sys

def clear_all_history():
    print("=" * 60)
    print(" AI SPEECH EVALUATOR - HISTORY PURGE UTILITY")
    print("=" * 60)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    reports_dir = os.path.join(base_dir, "reports")
    db_path = os.path.join(base_dir, "speech_evaluator.db")
    eval_json = os.path.join(base_dir, "evaluation_report.json")

    # 1. Remove JSON files in reports/
    purged_files = 0
    if os.path.exists(reports_dir):
        for f in glob.glob(os.path.join(reports_dir, "*.json")):
            try:
                os.remove(f)
                print(f"[*] Deleted: {os.path.basename(f)}")
                purged_files += 1
            except Exception as e:
                print(f"[!] Error deleting {f}: {e}")

    # 2. Remove root evaluation_report.json
    if os.path.exists(eval_json):
        try:
            os.remove(eval_json)
            print(f"[*] Deleted root evaluation_report.json")
            purged_files += 1
        except Exception as e:
            print(f"[!] Error deleting {eval_json}: {e}")

    # 3. Clear database speech_sessions
    deleted_db_rows = 0
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM speech_sessions")
            deleted_db_rows = cursor.rowcount
            # Reset active speaker to guest
            cursor.execute(
                "UPDATE active_speaker SET username = 'guest', full_name = 'Guest Speaker' WHERE id = 1"
            )
            conn.commit()
            conn.close()
            print(f"[*] Cleared {deleted_db_rows} speech record(s) from speech_evaluator.db")
        except Exception as e:
            print(f"[!] Error clearing database: {e}")
    else:
        print("[*] No speech_evaluator.db database file found.")

    print("-" * 60)
    print(f"[SUCCESS] Complete! Removed {purged_files} file(s) and {deleted_db_rows} database record(s).")
    print("[*] The system is now reset and ready for clean, new speeches.")
    print("=" * 60)

if __name__ == "__main__":
    clear_all_history()
