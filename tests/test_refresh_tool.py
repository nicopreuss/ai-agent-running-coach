from unittest.mock import MagicMock, patch

from agent.tools import refresh_data


def _mock_response(source: str, records_inserted: int) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {
        "status": "ok",
        "source": source,
        "records_inserted": records_inserted,
    }
    return resp


def test_refresh_whoop_with_new_record():
    with patch("agent.tools.requests.post", return_value=_mock_response("whoop", 1)) as mock_post:
        result = refresh_data.invoke({"source": "whoop"})

    mock_post.assert_called_once()
    assert "Whoop" in result
    assert "1 new record" in result


def test_refresh_strava_already_up_to_date():
    with patch("agent.tools.requests.post", return_value=_mock_response("strava", 0)):
        result = refresh_data.invoke({"source": "strava"})

    assert "Strava" in result
    assert "already up to date" in result


def test_refresh_all_calls_both_sources():
    responses = [_mock_response("whoop", 1), _mock_response("strava", 2)]
    with patch("agent.tools.requests.post", side_effect=responses):
        result = refresh_data.invoke({"source": "all"})

    assert "Whoop" in result
    assert "Strava" in result
