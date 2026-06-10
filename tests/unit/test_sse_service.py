from app.services.sse_service import build_delta_event, build_done_event, build_error_event, format_sse_event


def test_format_sse_event_uses_data_prefix_and_double_newline():
    out = format_sse_event({"type": "delta", "delta": "你好"})
    assert out.startswith("data: ")
    assert out.endswith("\n\n")


def test_build_events_return_expected_shapes():
    delta = build_delta_event("x")
    err = build_error_event("boom")
    done = build_done_event("ok", [{"role": "assistant", "content": "ok"}])

    assert '"type": "delta"' in delta
    assert '"delta": "x"' in delta
    assert '"type": "error"' in err
    assert '"error": "boom"' in err
    assert '"type": "done"' in done
    assert '"reply": "ok"' in done
