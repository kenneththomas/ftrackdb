import sqlite3

def normalization():
    # Connect to SQLite database (or create it if it doesn't exist)
    conn = sqlite3.connect('track.db')

    # Create a cursor object
    c = conn.cursor()

    #In table Results, find results that start with a 0, and get rid of the 0
    c.execute('SELECT * FROM Results WHERE Result LIKE "0%"')
    results = c.fetchall()
    for result in results:
        result_id = result[0]
        result_time = result[5]
        result_time = result_time[1:]
        c.execute('UPDATE Results SET Result = ? WHERE Result_ID = ?', (result_time, result_id))

    #enforce 2 decimal places in results
    c.execute('SELECT * FROM Results WHERE Result LIKE "%.%"')
    results = c.fetchall()
    for result in results:
        result_id = result[0]
        result_time = result[5] + '00'
        result_time = result_time[:result_time.index('.') + 3]
        #pad with 0s if necessary
        c.execute('UPDATE Results SET Result = ? WHERE Result_ID = ?', (result_time, result_id))

    print('finding invalid sprint times')
    sprintevents = ['60m','100m','200m','400m','60mH','100mH','110mH','400mH']
    # find results where there is a ':' in 400m and delete them as they are not valid
    for event in sprintevents:
        c.execute('SELECT * FROM Results WHERE Event = ? AND Result LIKE "%:%"', (event,))
        results = c.fetchall()
        for result in results:
            print(f'deleting {result}')
            c.execute('DELETE FROM Results WHERE Result_ID = ?', (result[0],))
        
    # Commit the changes and close the connection
    conn.commit()
    conn.close()
