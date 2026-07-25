import sqlite3
import os

DB_NAME = "edgefinder.db"

print(f"Attempting to connect to {DB_NAME}...")

# 1. Try to dump the data to a backup file using Python
try:
    # Connect to the corrupted DB
    conn = sqlite3.connect(DB_NAME)
    # Open a text file to write the backup to
    with open('backup.sql', 'w') as f:
        # Iterate over the database dump lines
        for line in conn.iterdump():
            f.write(f'{line}\n')
    conn.close()
    print("SUCCESS: Database data successfully dumped to 'backup.sql'.")
except Exception as e:
    print(f"FAILED to dump data. The database might be too damaged to recover. Error: {e}")
    exit()

# 2. Rebuild the database from the backup
try:
    # Rename the bad database file so the script doesn't overwrite it yet
    if os.path.exists(DB_NAME):
        os.rename(DB_NAME, "edgefinder.db.corrupt")
        print("Renamed corrupted 'edgefinder.db' to 'edgefinder.db.corrupt'.")

    # Create a NEW, empty database
    new_conn = sqlite3.connect(DB_NAME)
    new_conn.executescript(open('backup.sql').read())
    new_conn.close()
    
    print("SUCCESS: New 'edgefinder.db' created successfully from the backup.")
    print("\nYou can now run your main program again!")
    
except Exception as e:
    print(f"FAILED to rebuild the database. Error: {e}")
    print("Try restoring 'edgefinder.db.corrupt' back to 'edgefinder.db' if you need to.")