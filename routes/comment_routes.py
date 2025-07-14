from flask import Blueprint, request, redirect, url_for, flash, jsonify
from models import Comment
from forms import CommentForm

# Create blueprint
comment_bp = Blueprint('comment', __name__)

@comment_bp.route('/comment/<page_type>/<page_id>', methods=['POST'])
def add_comment(page_type, page_id):
    """Add a comment to any page type"""
    form = CommentForm()
    if form.validate_on_submit():
        parent_id = form.parent_id.data if form.parent_id.data else None
        Comment.add_comment(
            page_type=page_type,
            page_id=page_id,
            username=form.username.data,
            content=form.content.data,
            parent_id=parent_id
        )
        flash('Comment added!', 'success')
    else:
        flash('Error adding comment. Please check your input.', 'error')
    
    # Redirect back to the appropriate page
    if page_type == 'meet':
        return redirect(url_for('meet.meet_results', meet_name=page_id))
    elif page_type == 'athlete':
        return redirect(url_for('athlete.athlete_profile', name=page_id))
    elif page_type == 'team':
        return redirect(url_for('team.team_results', team_name=page_id))
    else:
        # Default fallback
        return redirect(url_for('home'))

@comment_bp.route('/comment/<page_type>/<page_id>/<int:comment_id>/delete', methods=['POST'])
def delete_comment(page_type, page_id, comment_id):
    """Delete a comment"""
    Comment.delete_comment(comment_id)
    flash('Comment deleted!', 'success')
    
    # Redirect back to the appropriate page
    if page_type == 'meet':
        return redirect(url_for('meet.meet_results', meet_name=page_id))
    elif page_type == 'athlete':
        return redirect(url_for('athlete.athlete_profile', name=page_id))
    elif page_type == 'team':
        return redirect(url_for('team.team_results', team_name=page_id))
    else:
        # Default fallback
        return redirect(url_for('home'))

@comment_bp.route('/api/comments/<page_type>/<page_id>')
def get_comments_api(page_type, page_id):
    """API endpoint to get comments for a page"""
    comments = Comment.get_comments(page_type, page_id)
    comment_count = Comment.get_comment_count(page_type, page_id)
    return jsonify({
        'comments': comments,
        'count': comment_count
    }) 