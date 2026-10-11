#[cfg(any(not(debug_assertions), test))]
mod backend_process;

#[tauri::command]
fn choose_project_file(save: bool) -> Option<String> {
    let dialog = rfd::FileDialog::new().add_filter("ShotMill 工程", &["shotmill"]);
    let path = if save {
        dialog.set_file_name("未命名工程.shotmill").save_file()
    } else {
        dialog.pick_file()
    };
    path.map(|value| value.to_string_lossy().into_owned())
}

#[tauri::command]
fn choose_asset_files() -> Vec<String> {
    rfd::FileDialog::new()
        .add_filter("媒体文件", &["png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff", "mp4", "mov", "mkv", "webm", "avi", "m4v", "wav", "mp3", "flac", "m4a", "aac", "ogg"])
        .pick_files()
        .unwrap_or_default()
        .into_iter()
        .map(|value| value.to_string_lossy().into_owned())
        .collect()
}

#[cfg(not(debug_assertions))]
fn start_backend(app: &mut tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    use std::{fs, process::Command, sync::Mutex};
    use tauri::Manager;

    let resources = app.path().resource_dir()?;
    let data = app.path().app_local_data_dir()?;
    fs::create_dir_all(&data)?;
    let log = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(data.join("backend.log"))?;
    let mut command = Command::new(resources.join("runtime").join("shotmill-backend.exe"));
    command
        .arg("--data-root")
        .arg(&data)
        .arg("--frontend-root")
        .arg(resources.join("resources"))
        .current_dir(&data)
        .stderr(log);
    let (backend, url) =
        backend_process::BackendProcess::start(command).map_err(std::io::Error::other)?;
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| std::io::Error::other("找不到主窗口"))?;
    window.navigate(url.parse()?)?;
    app.manage(Mutex::new(Some(backend)));
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![choose_project_file, choose_asset_files]);
    #[cfg(not(debug_assertions))]
    let builder = builder.setup(start_backend);
    let app = builder
        .build(tauri::generate_context!())
        .expect("error while running ShotMill");
    app.run(|_handle, _event| {
        #[cfg(not(debug_assertions))]
        if matches!(_event, tauri::RunEvent::Exit) {
            use tauri::Manager;
            if let Some(state) =
                _handle.try_state::<std::sync::Mutex<Option<backend_process::BackendProcess>>>()
            {
                if let Ok(mut backend) = state.lock() {
                    drop(backend.take());
                }
            }
        }
    });
}
