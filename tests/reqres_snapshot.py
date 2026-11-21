"""Общие данные чтения classic ReqRes только на время одного прогона pytest."""

from copy import deepcopy

from automation.api.contracts import json_response


class ReqresSnapshot:
    def __init__(self, client):
        self.client = client
        self._pages = {}
        self._users = {}

    def page(self, number):
        if number not in self._pages:
            self._pages[number] = json_response(
                self.client.request("GET", "/api/users", params={"page": number})
            )
        return deepcopy(self._pages[number])

    def user(self, user_id):
        if user_id not in self._users:
            self._users[user_id] = json_response(
                self.client.request("GET", f"/api/users/{user_id}")
            )
        return deepcopy(self._users[user_id])
