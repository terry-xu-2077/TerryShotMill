def test_project_cover_can_be_selected_reset_and_not_borrowed_across_projects(client):
    project = client.post("/api/v1/projects", json={"title": "封面"}).json()["id"]
    asset = client.post(f"/api/v1/projects/{project}/assets", files={
        "file": ("cover.png", b"image", "image/png"),
    }).json()
    response = client.patch(f"/api/v1/projects/{project}", json={
        "cover": {"kind": "asset", "assetId": asset["id"]},
    })
    assert response.status_code == 200, response.text
    assert response.json()["coverUrl"].endswith("cover.png")
    settings = client.get(f"/api/v1/projects/{project}/settings").json()
    assert settings["coverAssetId"] == asset["id"]
    deletion = client.delete(f"/api/v1/projects/{project}/assets/{asset['id']}")
    assert deletion.status_code == 409
    other = client.post("/api/v1/projects", json={"title": "其他"}).json()["id"]
    rejected = client.patch(f"/api/v1/projects/{other}", json={
        "cover": {"kind": "asset", "assetId": asset["id"]},
    })
    assert rejected.status_code == 404
    response = client.patch(f"/api/v1/projects/{project}", json={"cover": {"kind": "auto"}})
    assert response.status_code == 200
    assert response.json()["coverUrl"] is None
    assert client.get(f"/api/v1/projects/{project}/settings").json()["coverAssetId"] is None
    assert client.delete(f"/api/v1/projects/{project}/assets/{asset['id']}").status_code == 204


def test_invalid_video_frame_does_not_replace_saved_cover_or_project_title(client):
    project = client.post("/api/v1/projects", json={"title": "原项目"}).json()["id"]
    asset = client.post(f"/api/v1/projects/{project}/assets", files={
        "file": ("broken.mp4", b"broken", "video/mp4"),
    }).json()
    response = client.patch(f"/api/v1/projects/{project}", json={
        "title": "不应保存", "cover": {"kind": "video", "assetId": asset["id"], "seconds": 1},
    })
    assert response.status_code == 422
    assert client.get(f"/api/v1/projects/{project}/settings").json()["title"] == "原项目"
