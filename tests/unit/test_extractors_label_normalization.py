# T3-3: gangbiao label normalization rules.

from app.extractors.spreadsheet import _normalize_gangbiao_labels


def test_normalize_purpose_and_result_labels():
    source = "目的: 提升质量\n成果：按时上线\n成果（其他）: 达成目标"
    normalized = _normalize_gangbiao_labels(source)

    assert "任务目的：提升质量" in normalized
    assert "任务成果（预算、交期、完成度）：按时上线" in normalized
    assert "任务成果（预算、交期、完成度）：达成目标" in normalized
