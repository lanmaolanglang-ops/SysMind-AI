mod sidecar;

use sidecar::{BackendManager, BackendSnapshot};
use std::thread;
use std::time::{Duration, Instant};
use tauri::{Manager, RunEvent};

#[tauri::command]
fn backend_status(manager: tauri::State<'_, BackendManager>) -> BackendSnapshot {
    manager.snapshot()
}

#[tauri::command]
fn restart_backend(
    app: tauri::AppHandle,
    manager: tauri::State<'_, BackendManager>,
) -> Result<BackendSnapshot, String> {
    manager.shutdown();
    manager.start(&app);
    // Startup is asynchronous. A snapshot still in `starting` is not a finished
    // restart, so never report success from that state.
    let deadline = Instant::now() + Duration::from_secs(25);
    loop {
        let snapshot = manager.snapshot();
        match snapshot.state {
            "starting" => {
                if Instant::now() >= deadline {
                    return Err("Backend restart is still starting.".to_string());
                }
                thread::sleep(Duration::from_millis(100));
            }
            "connected" => return Ok(snapshot),
            _ => {
                return Err(snapshot
                    .error
                    .unwrap_or_else(|| "Backend restart failed.".to_string()));
            }
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let manager = BackendManager::new();
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
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
            // ExitRequested can be prevented (e.g. by the updater). Only tear
            // down the sidecar on RunEvent::Exit, which is emitted solely for
            // non-prevented exits.
            if matches!(event, RunEvent::Exit) {
                app_handle.state::<BackendManager>().shutdown();
            }
        });
}
