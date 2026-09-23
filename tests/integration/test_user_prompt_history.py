def test_user_history_requires_explicit_archive(client):
    pid = client.post("/api/v1/projects", json={"title": "History"}).json()["id"]
    root = f"/api/v1/projects/{pid}/tasks"
    tid = client.post(root, json={"title": "Task", "userPrompt": "Original"}).json()["id"]
    url = f"{root}/{tid}"

    def current():
        return client.get(url + "/editor").json()

    assert current()["userPromptHistory"] == []
    assert client.patch(url, json={**current(), "userPrompt": "Revised"}).status_code == 200
    assert current()["userPromptHistory"] == []
    assert client.patch(url, json={**current(), "saveUserPromptVersion": True}).status_code == 200
    history = current()["userPromptHistory"]
    assert [h["prompt"] for h in history] == ["Revised"]
    assert client.patch(url, json={**current(), "userPrompt": "Another edit"}).status_code == 200
    assert current()["userPromptHistory"] == history
    assert client.patch(url, json={**current(), "userPrompt": "Revised"}).status_code == 200
    assert current()["userPromptHistory"] == history
    stale = current()
    assert client.patch(url, json={**stale, "saveUserPromptVersion": True}).status_code == 200
    assert client.patch(url, json={**stale, "saveUserPromptVersion": True}).status_code == 409
    assert len(current()["userPromptHistory"]) == 2
