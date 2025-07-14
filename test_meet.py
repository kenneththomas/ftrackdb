from wavelight import app
from models import Comment

with app.app_context():
    # Test getting comments for the 'breez' meet
    comments = Comment.get_comments('meet', 'breez')
    comment_count = Comment.get_comment_count('meet', 'breez')
    
    print(f"Comments for meet 'breez': {len(comments)}")
    print(f"Comment count: {comment_count}")
    
    for comment in comments:
        print(f"  Comment ID: {comment['comment_id']}")
        print(f"  Username: {comment['username']}")
        print(f"  Content: {comment['content']}")
        print(f"  Created: {comment['created_at']}")
        print(f"  Replies: {len(comment['replies'])}")
        print() 