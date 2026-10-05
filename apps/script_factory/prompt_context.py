"""Story canon for AI requests, without nested review diagnostics or approval state."""
from apps.script_factory.models import StoryBible


def story_prompt_data(bible: StoryBible, *, include_outline: bool = True):
    excluded = {'adaptation_context', 'story_qc_report', 'status', 'approved_at', 'approved_by'}
    if not include_outline:
        excluded.add('scene_outline')
    # Source context is provided separately by writer_context. Never truncate
    # the canonical story, its locked facts or a source to reduce request size.
    return {key: value for key, value in bible.to_dict().items() if key not in excluded}
