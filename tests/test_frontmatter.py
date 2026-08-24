from voicemd.frontmatter import FrontmatterError, parse_text


def test_plain_markdown():
    metadata, body = parse_text("# VOICE.md\n\nDirect.")
    assert metadata == {}
    assert body.startswith("# VOICE.md")


def test_frontmatter():
    metadata, body = parse_text("---\nvoice_spec: '0.1'\nkind: VoiceContract\nname: X\n---\nBody")
    assert metadata["name"] == "X"
    assert body == "Body"


def test_broken_frontmatter():
    try:
        parse_text("---\nname: X")
    except FrontmatterError:
        return
    raise AssertionError("expected FrontmatterError")
