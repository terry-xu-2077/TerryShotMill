fn main() {
    tauri_build::try_build(
        tauri_build::Attributes::new().app_manifest(
            tauri_build::AppManifest::new().commands(&["choose_project_file", "choose_asset_files"]),
        ),
    )
    .unwrap();
}
