from flask import Blueprint, request, redirect, url_for, flash, render_template
from models import BoardPost
from forms import BoardPostForm, BoardGenerateForm

# Optional: check if OpenRouter is configured (no import of internal helpers in template)
def _openrouter_available():
    import os
    return bool(os.environ.get("OPENROUTER_API_KEY", "").strip())

board_bp = Blueprint('board', __name__)


def _parse_parent_id(value):
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@board_bp.route('/board', methods=['GET', 'POST'])
def board_page():
    post_form = BoardPostForm()
    generate_form = BoardGenerateForm()
    posts = BoardPost.get_threaded_posts(page_type='global', page_id='')
    openrouter_available = _openrouter_available()

    if request.method == 'POST':
        if post_form.validate_on_submit():
            parent_id = _parse_parent_id(post_form.parent_id.data)
            BoardPost.add_post(
                author_display_name=post_form.author_display_name.data.strip(),
                content=post_form.content.data.strip(),
                parent_id=parent_id,
                is_ai_generated=False,
                ai_prompt=None,
                page_type='global',
                page_id='',
            )
            flash('Post added!', 'success')
            return redirect(url_for('board.board_page'))
        if not post_form.errors:
            flash('Error adding post. Please check your input.', 'error')

    return render_template(
        'board.html',
        board_posts=posts,
        post_form=post_form,
        generate_form=generate_form,
        openrouter_available=openrouter_available,
        post_action_url=url_for('board.board_page'),
        generate_action_url=url_for('board.board_generate'),
        section_title='Message Board',
    )


@board_bp.route('/board/generate', methods=['POST'])
def board_generate():
    generate_form = BoardGenerateForm()
    if not generate_form.validate_on_submit():
        flash('Please provide a prompt (1–500 characters).', 'error')
        return redirect(url_for('board.board_page'))
    prompt = generate_form.prompt.data.strip()
    parent_id = _parse_parent_id(generate_form.parent_id.data)
    try:
        from utils.openrouter import generate_board_post
        result = generate_board_post(prompt)
        BoardPost.add_post(
            author_display_name=result['author_display_name'],
            content=result['content'],
            parent_id=parent_id,
            is_ai_generated=True,
            ai_prompt=prompt,
            page_type='global',
            page_id='',
        )
        flash('AI post added!', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    except Exception as e:
        flash(f'Failed to generate post: {e}', 'error')
    return redirect(url_for('board.board_page'))


@board_bp.route('/meet/<meet_name>/board', methods=['POST'])
def meet_board_post(meet_name):
    post_form = BoardPostForm()
    if not post_form.validate_on_submit():
        flash('Error adding post. Please check your input.', 'error')
        return redirect(url_for('meet.meet_results', meet_name=meet_name))
    parent_id = _parse_parent_id(post_form.parent_id.data)
    BoardPost.add_post(
        author_display_name=post_form.author_display_name.data.strip(),
        content=post_form.content.data.strip(),
        parent_id=parent_id,
        is_ai_generated=False,
        ai_prompt=None,
        page_type='meet',
        page_id=meet_name,
    )
    flash('Post added!', 'success')
    return redirect(url_for('meet.meet_results', meet_name=meet_name))


@board_bp.route('/meet/<meet_name>/board/generate', methods=['POST'])
def meet_board_generate(meet_name):
    generate_form = BoardGenerateForm()
    if not generate_form.validate_on_submit():
        flash('Please provide a prompt (1–500 characters).', 'error')
        return redirect(url_for('meet.meet_results', meet_name=meet_name))
    prompt = generate_form.prompt.data.strip()
    parent_id = _parse_parent_id(generate_form.parent_id.data)
    try:
        from utils.openrouter import generate_board_post
        result = generate_board_post(prompt)
        BoardPost.add_post(
            author_display_name=result['author_display_name'],
            content=result['content'],
            parent_id=parent_id,
            is_ai_generated=True,
            ai_prompt=prompt,
            page_type='meet',
            page_id=meet_name,
        )
        flash('AI post added!', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    except Exception as e:
        flash(f'Failed to generate post: {e}', 'error')
    return redirect(url_for('meet.meet_results', meet_name=meet_name))


@board_bp.route('/athlete/<name>/board', methods=['POST'])
def athlete_board_post(name):
    post_form = BoardPostForm()
    if not post_form.validate_on_submit():
        flash('Error adding post. Please check your input.', 'error')
        return redirect(url_for('athlete.athlete_profile', name=name))
    parent_id = _parse_parent_id(post_form.parent_id.data)
    BoardPost.add_post(
        author_display_name=post_form.author_display_name.data.strip(),
        content=post_form.content.data.strip(),
        parent_id=parent_id,
        is_ai_generated=False,
        ai_prompt=None,
        page_type='athlete',
        page_id=name,
    )
    flash('Post added!', 'success')
    return redirect(url_for('athlete.athlete_profile', name=name))


@board_bp.route('/athlete/<name>/board/generate', methods=['POST'])
def athlete_board_generate(name):
    generate_form = BoardGenerateForm()
    if not generate_form.validate_on_submit():
        flash('Please provide a prompt (1–500 characters).', 'error')
        return redirect(url_for('athlete.athlete_profile', name=name))
    prompt = generate_form.prompt.data.strip()
    parent_id = _parse_parent_id(generate_form.parent_id.data)
    try:
        from utils.openrouter import generate_board_post
        result = generate_board_post(prompt)
        BoardPost.add_post(
            author_display_name=result['author_display_name'],
            content=result['content'],
            parent_id=parent_id,
            is_ai_generated=True,
            ai_prompt=prompt,
            page_type='athlete',
            page_id=name,
        )
        flash('AI post added!', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    except Exception as e:
        flash(f'Failed to generate post: {e}', 'error')
    return redirect(url_for('athlete.athlete_profile', name=name))
