import sqlite3

conn = sqlite3.connect('track.db')
cur = conn.cursor()

# Check if Comments table exists
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Comments'")
table_exists = cur.fetchone() is not None
print('Comments table exists:', table_exists)

if table_exists:
    # Check if there are any comments
    cur.execute("SELECT COUNT(*) FROM Comments")
    comment_count = cur.fetchone()[0]
    print('Total comments in database:', comment_count)
    
    # Check for meet comments specifically
    cur.execute("SELECT COUNT(*) FROM Comments WHERE page_type='meet'")
    meet_comment_count = cur.fetchone()[0]
    print('Meet comments in database:', meet_comment_count)
    
    # Show some sample comments
    cur.execute("SELECT page_type, page_id, username, content FROM Comments LIMIT 5")
    sample_comments = cur.fetchall()
    print('Sample comments:')
    for comment in sample_comments:
        print(f"  {comment}")

conn.close() 