mod sidecar;

use sidecar::{BackendManager, BackendSnapshot};
use tauri::{Manager, RunEvent};

#[tauri::command]
fn backend_status(manager: tauri::State<'_, BackendManager>) -> BackendSnapshot {
    manager.snapshot()
}

#[tauri::command]
fn restart_backend(
    app: tauri::AppHandle,
    manager: tauri::State<'_, BackendManager>,
) -> BackendSnapshot {
    manager.shutdown();
    manager.start(&app);
    manager.snapshot()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let manager = BackendManager::new();
    tauri::Builder::default()
        .manage(manager)
        .setup(|app| {
            let handle = app.handle().clone();
            let state = app.state::<BackendManager>();
            state.start(&handle);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![backend_status, restart_backend])
        .build(tauri::generate_context!())
        .expect("failed to build SysMind AI desktop")
        .run(|app_handle, event| {
            if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {
                app_handle.state::<BackendManager>().shutdown();
            }
        });
}
