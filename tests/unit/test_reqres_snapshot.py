from unittest.mock import Mock

import pytest

from tests.reqres_snapshot import ReqresSnapshot
from tests.unit.test_api_client import response


def test_snapshot_reuses_reads_and_returns_independent_copies():
    client = Mock()
    result = response()
    result._content = b'{"data": [{"id": 1}]}'
    client.request.return_value = result
    snapshot = ReqresSnapshot(client)
    snapshot.page(1)["data"][0]["id"] = 999
    assert snapshot.page(1)["data"] == [{"id": 1}]
    assert client.request.call_count == 1
    snapshot.page(2)
    snapshot.user(1)
    snapshot.user(1)
    assert client.request.call_count == 3
    # Новый прогон не использует ранее полученный ответ.
    ReqresSnapshot(client).page(1)
    assert client.request.call_count == 4


@pytest.mark.parametrize("status", [429, 500])
def test_error_response_is_not_saved_as_successful_snapshot(status):
    client = Mock()
    client.request.side_effect = [response(status=status), response()]
    snapshot = ReqresSnapshot(client)
    with pytest.raises(AssertionError, match=f"получен {status}"):
        snapshot.page(1)
    assert client.request.call_count == 1  # Нет автоматического retry.
    assert snapshot.page(1) == {"id": 1}
    assert client.request.call_count == 2
