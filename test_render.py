from wavelight import app
from models import Result, Team, Database, TeamScore, AthleteRanking, Comment
from forms import MeetResultForm, CommentForm

with app.test_request_context():
    meet_name = 'breez'
    
    # Create forms
    form = MeetResultForm()
    comment_form = CommentForm()
    
    # Get results
    raw_results = Result.get_meet_results(meet_name)
    print(f"Raw results count: {len(raw_results)}")
    
    # Get comments
    comments = Comment.get_comments('meet', meet_name)
    comment_count = Comment.get_comment_count('meet', meet_name)
    print(f"Comments count: {comment_count}")
    print(f"Comments: {comments}")
    
    # Try to render template
    try:
        from flask import render_template
        html = render_template('meet.html', 
                             meet_name=meet_name, 
                             events={}, 
                             team_logos={}, 
                             form=form, 
                             sorted_teams=[],
                             comment_form=comment_form,
                             comments=comments,
                             comment_count=comment_count)
        print("Template rendered successfully!")
        print(f"HTML length: {len(html)}")
        
        # Check if comments section is in the HTML
        if 'Comments (1)' in html:
            print("Comments section found in HTML!")
        else:
            print("Comments section NOT found in HTML!")
            
    except Exception as e:
        print(f"Error rendering template: {e}")
        import traceback
        traceback.print_exc() 