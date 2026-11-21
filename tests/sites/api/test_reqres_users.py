from datetime import datetime

import pytest

from automation.api.contracts import json_response

pytestmark = [pytest.mark.api, pytest.mark.regression, pytest.mark.external, pytest.mark.reqres]


@pytest.mark.smoke
@pytest.mark.parametrize("page_number", [1, 2])
def test_users_pagination(reqres_snapshot, page_number):
    body = reqres_snapshot.page(page_number)
    assert body["page"] == page_number
    assert body["total"] > 0
    assert len(body["data"]) == body["per_page"]
    ids = [user["id"] for user in body["data"]]
    assert len(ids) == len(set(ids))
    assert all("@" in user["email"] for user in body["data"])


def test_page_beyond_last_is_empty(reqres_snapshot):
    body = reqres_snapshot.page(999)
    assert body["page"] == 999
    assert body["data"] == []


@pytest.mark.parametrize("user_id", [1, 2])
def test_existing_user(reqres_snapshot, user_id):
    body = reqres_snapshot.user(user_id)
    user = body["data"]
    assert user["id"] == user_id
    assert {"email", "first_name", "last_name", "avatar"} <= user.keys()
    assert user["first_name"]
    assert "@" in user["email"]


def test_unknown_user(reqres):
    response = reqres.request("GET", "/api/users/99999")
    assert response.status_code == 404


def test_create_user_response(reqres):
    payload = {"name": "QA Learner", "job": "automation engineer"}
    body = json_response(reqres.request("POST", "/api/users", json=payload), 201)
    assert body["name"] == payload["name"]
    assert body["job"] == payload["job"]
    assert isinstance(body["id"], (str, int))
    assert str(body["id"]).strip()
    assert datetime.fromisoformat(body["createdAt"].replace("Z", "+00:00")).tzinfo is not None
    # Classic ReqRes не сохраняет пользователя: последующий GET здесь неверен.


@pytest.mark.parametrize("method", ["PUT", "PATCH"])
def test_update_user_response(reqres, method):
    payload = {"name": "QA Learner", "job": "senior automation engineer"}
    body = json_response(reqres.request(method, "/api/users/2", json=payload), 200)
    assert body["name"] == payload["name"]
    assert body["job"] == payload["job"]
    assert datetime.fromisoformat(body["updatedAt"].replace("Z", "+00:00")).tzinfo is not None


def test_delete_user_response(reqres):
    response = reqres.request("DELETE", "/api/users/2")
    assert response.status_code == 204
    assert response.content == b""


def test_pages_do_not_overlap_and_cover_total(reqres_snapshot):
    first = reqres_snapshot.page(1)
    ids = [user["id"] for user in first["data"]]
    for page_number in range(2, first["total_pages"] + 1):
        page = reqres_snapshot.page(page_number)
        assert page["page"] == page_number
        assert page["total"] == first["total"]
        ids.extend(user["id"] for user in page["data"])
    assert len(ids) == len(set(ids)) == first["total"]


def test_list_and_user_detail_agree(reqres_snapshot):
    listing = reqres_snapshot.page(1)
    expected = listing["data"][0]
    detail = reqres_snapshot.user(expected["id"])
    assert detail["data"] == expected
