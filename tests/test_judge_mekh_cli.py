"""Focused tests for the claude-cli judge backend's reply parsing.

These test parse_claude_cli_stdout() directly against canned CLI stdout
strings -- no subprocess is spawned.
"""
import json

import pytest

from scripts.judge_mekh_processes import parse_claude_cli_stdout


def _cli_stdout(result_text: str, model_usage: dict | None = None) -> str:
    payload = {"result": result_text}
    if model_usage is not None:
        payload["modelUsage"] = model_usage
    return json.dumps(payload)


VALID_VERDICT = {
    "process_plausible": True,
    "inputs_outputs_correct": True,
    "hs_codes_correct": False,
    "overall_correct": False,
    "error_mode": "wrong_hs_code",
    "rationale": "The HS code for the product does not match.",
}


def test_parse_valid_json_reply():
    stdout = _cli_stdout(json.dumps(VALID_VERDICT), model_usage={"claude-sonnet-5": {}})
    verdict, actual_model = parse_claude_cli_stdout(stdout)
    assert verdict.overall_correct is False
    assert verdict.hs_codes_correct is False
    assert verdict.error_mode == "wrong_hs_code"
    assert actual_model == "claude-sonnet-5"


def test_parse_fenced_json_reply():
    fenced = "```json\n" + json.dumps(VALID_VERDICT) + "\n```"
    stdout = _cli_stdout(fenced, model_usage={"claude-sonnet-5": {}})
    verdict, actual_model = parse_claude_cli_stdout(stdout)
    assert verdict.process_plausible is True
    assert actual_model == "claude-sonnet-5"


def test_parse_fenced_json_reply_no_language_tag():
    fenced = "```\n" + json.dumps(VALID_VERDICT) + "\n```"
    stdout = _cli_stdout(fenced, model_usage={"claude-sonnet-5": {}})
    verdict, actual_model = parse_claude_cli_stdout(stdout)
    assert verdict.overall_correct is False


def test_parse_missing_model_usage_returns_none():
    stdout = _cli_stdout(json.dumps(VALID_VERDICT))
    verdict, actual_model = parse_claude_cli_stdout(stdout)
    assert actual_model is None


def test_parse_invalid_outer_json_raises():
    with pytest.raises(json.JSONDecodeError):
        parse_claude_cli_stdout("not json at all")


def test_parse_missing_result_field_raises():
    with pytest.raises(ValueError):
        parse_claude_cli_stdout(json.dumps({"modelUsage": {}}))


def test_parse_non_json_result_text_raises():
    stdout = _cli_stdout("Sure, here is my answer: it looks fine.")
    with pytest.raises(json.JSONDecodeError):
        parse_claude_cli_stdout(stdout)


def test_parse_result_missing_required_field_raises():
    incomplete = dict(VALID_VERDICT)
    del incomplete["overall_correct"]
    stdout = _cli_stdout(json.dumps(incomplete))
    with pytest.raises(Exception):  # pydantic.ValidationError
        parse_claude_cli_stdout(stdout)
