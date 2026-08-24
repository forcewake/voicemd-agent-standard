from voicemd.merge import deep_merge


def test_scalar_and_mapping_override():
    result = deep_merge({"response": {"max_words": 100, "tone": "neutral"}}, {"response": {"max_words": 20}})
    assert result == {"response": {"max_words": 20, "tone": "neutral"}}


def test_append_unique_lexicon():
    result = deep_merge(
        {"lexicon": {"forbidden": ["foo"]}},
        {"lexicon": {"forbidden": ["foo", "bar"]}},
    )
    assert result["lexicon"]["forbidden"] == ["foo", "bar"]


def test_rules_merge_by_id_and_disable():
    result = deep_merge(
        {"rules": [{"id": "a", "severity": "warning"}, {"id": "b"}]},
        {"rules": [{"id": "a", "severity": "error"}, {"id": "b", "disabled": True}]},
    )
    assert result["rules"] == [{"id": "a", "severity": "error"}]
