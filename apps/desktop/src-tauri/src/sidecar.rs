use serde::{Deserialize, Serialize};
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::{self, RecvTimeoutError};
use std::sync::{Arc, Mutex, MutexGuard};
use std::thread;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Manager};
use uuid::Uuid;

const EXPECTED_API_VERSION: &str = crate::generated_version::EXPECTED_API_VERSION;
const HANDSHAKE_PREFIX: &str = "SYSMIND_ENDPOINT ";
/// The backend publishes its endpoint before the HTTP server starts serving. If it is
/// alive but silent for longer than this, startup is treated as failed instead of
/// blocking the reader thread forever.
const HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(20);

#[derive(Clone, Debug, Serialize)]
pub struct BackendEndpoint {
    pub base_url: String,
    pub session_token: String,
    pub api_version: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct BackendSnapshot {
    pub state: &'static str,
    pub endpoint: Option<BackendEndpoint>,
    pub error: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct EndpointHandshake {
    event: String,
    host: String,
    port: u16,
    backend_version: String,
    api_version: String,
}

#[derive(Debug, Deserialize)]
struct HealthProbe {
    status: String,
    api_version: String,
    ready: bool,
}

struct BackendRuntime {
    generation: u64,
    snapshot: BackendSnapshot,
    child: Option<Child>,
    #[cfg(windows)]
    job: Option<WindowsJob>,
}

pub struct BackendManager {
    runtime: Arc<Mutex<BackendRuntime>>,
}

impl BackendManager {
    pub fn new() -> Self {
        Self {
            runtime: Arc::new(Mutex::new(BackendRuntime {
                generation: 0,
                snapshot: BackendSnapshot {
                    state: "disconnected",
                    endpoint: None,
                    error: None,
                },
                child: None,
                #[cfg(windows)]
                job: None,
            })),
        }
    }

    pub fn snapshot(&self) -> BackendSnapshot {
        lock_runtime(&self.runtime).snapshot.clone()
    }

    pub fn start(&self, app: &AppHandle) {
        let generation = {
            let mut runtime = lock_runtime(&self.runtime);
            if runtime.child.is_some() || runtime.snapshot.state == "starting" {
                return;
            }
            runtime.generation = runtime.generation.wrapping_add(1);
            runtime.snapshot = BackendSnapshot {
                state: "starting",
                endpoint: None,
                error: None,
            };
            runtime.generation
        };

        let token = Uuid::new_v4().to_string() + &Uuid::new_v4().to_string();
        let data_dir = std::env::var_os("SYSMIND_DATA_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|| {
                app.path()
                    .app_local_data_dir()
                    .unwrap_or_else(|_| PathBuf::from(".sysmind-data"))
            });
        let launcher = match LauncherCommand::resolve(app) {
            Ok(launcher) => launcher,
            Err(error) => {
                self.fail(generation, error);
                return;
            }
        };
        let mut command = Command::new(&launcher.program);
        command
            .args(&launcher.prefix_args)
            .args(["--host", "127.0.0.1", "--port", "0", "--data-dir"])
            .arg(data_dir)
            .env("SYSMIND_SESSION_TOKEN", &token)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        #[cfg(windows)]
        configure_hidden_window(&mut command);

        let mut child = match command.spawn() {
            Ok(child) => child,
            Err(error) => {
                self.fail(
                    generation,
                    format!(
                        "Could not start the Python sidecar using '{}': {error}",
                        launcher.program.display()
                    ),
                );
                return;
            }
        };

        #[cfg(windows)]
        let job = match WindowsJob::assign(&child) {
            Ok(job) => Some(job),
            Err(error) => {
                let _ = child.kill();
                self.fail(
                    generation,
                    format!("Could not secure the sidecar process in a Windows Job: {error}"),
                );
                return;
            }
        };

        let stdout = child.stdout.take();
        let stderr = child.stderr.take();
        {
            let mut runtime = lock_runtime(&self.runtime);
            if runtime.generation != generation {
                drop(runtime);
                let _ = child.kill();
                let _ = child.wait();
                // A concurrent shutdown may have raced past an empty `child` slot and
                // returned without resetting the snapshot. Clear a stuck "starting"
                // state so the UI can start again without an app restart.
                let mut runtime = lock_runtime(&self.runtime);
                if runtime.child.is_none() && runtime.snapshot.state == "starting" {
                    runtime.snapshot = BackendSnapshot {
                        state: "disconnected",
                        endpoint: None,
                        error: Some("Startup was cancelled.".to_string()),
                    };
                }
                return;
            }
            runtime.child = Some(child);
            #[cfg(windows)]
            {
                runtime.job = job;
            }
        }

        let monitor_shared = Arc::clone(&self.runtime);
        thread::spawn(move || monitor_child_process(monitor_shared, generation));

        let shared = Arc::clone(&self.runtime);
        thread::spawn(move || {
            if let Some(stderr) = stderr {
                thread::spawn(move || {
                    for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                        if line.starts_with("SYSMIND_ERROR ") {
                            eprintln!("SysMind backend startup error: {line}");
                        }
                    }
                });
            }

            let Some(stdout) = stdout else {
                set_failure(
                    &shared,
                    generation,
                    "Backend stdout was not available.".to_string(),
                );
                return;
            };
            // Read stdout on a worker thread and forward each line over a channel so the
            // handshake wait can enforce a wall-clock timeout. Without this a backend that
            // starts but never prints its endpoint (deadlock, dependency stall, unflushed
            // stdout) would block this thread forever and leave the UI spinning.
            let (line_tx, line_rx) = mpsc::channel::<String>();
            thread::spawn(move || {
                for line in BufReader::new(stdout).lines().map_while(Result::ok) {
                    if line_tx.send(line).is_err() {
                        return;
                    }
                }
            });

            let handshake = match await_handshake(&line_rx, HANDSHAKE_TIMEOUT) {
                Ok(handshake) => handshake,
                Err(message) => {
                    set_failure(&shared, generation, message.to_string());
                    return;
                }
            };
            if let Some(error) = handshake_contract_error(&handshake) {
                set_failure(&shared, generation, error);
                return;
            }

            let backend_endpoint = BackendEndpoint {
                base_url: format!("http://127.0.0.1:{}", handshake.port),
                session_token: token,
                api_version: handshake.api_version,
            };
            match wait_until_ready(&backend_endpoint, Duration::from_secs(10)) {
                Ok(()) => publish_ready_endpoint(&shared, generation, backend_endpoint),
                Err(error) => set_failure(&shared, generation, error),
            }
        });
    }

    pub fn shutdown(&self) {
        let (shutdown_generation, endpoint, mut child) = {
            let mut runtime = lock_runtime(&self.runtime);
            runtime.generation = runtime.generation.wrapping_add(1);
            (
                runtime.generation,
                runtime.snapshot.endpoint.clone(),
                runtime.child.take(),
            )
        };

        let Some(mut owned_child) = child.take() else {
            // No child handle yet (start() lost the race before publishing it).
            // Still reset the snapshot so the UI cannot stick on "starting".
            let mut runtime = lock_runtime(&self.runtime);
            if runtime.generation == shutdown_generation && runtime.child.is_none() {
                let previous_error = runtime.snapshot.error.take();
                runtime.snapshot = BackendSnapshot {
                    state: "disconnected",
                    endpoint: None,
                    error: previous_error.or_else(|| Some("Startup was cancelled.".to_string())),
                };
                #[cfg(windows)]
                {
                    runtime.job = None;
                }
            }
            return;
        };
        if let Some(endpoint) = endpoint {
            let _ = send_http_request(&endpoint, "POST", "/internal/shutdown");
        }

        let deadline = Instant::now() + Duration::from_secs(2);
        while Instant::now() < deadline {
            match owned_child.try_wait() {
                Ok(Some(_)) => break,
                Ok(None) => thread::sleep(Duration::from_millis(50)),
                Err(_) => break,
            }
        }
        if matches!(owned_child.try_wait(), Ok(None)) {
            let _ = owned_child.kill();
            let _ = owned_child.wait();
        }

        let mut runtime = lock_runtime(&self.runtime);
        if runtime.generation != shutdown_generation {
            return;
        }
        // Preserve any recorded error (e.g. an unexpected exit) instead of wiping the
        // crash context; a clean shutdown simply keeps `None`.
        let previous_error = runtime.snapshot.error.take();
        runtime.snapshot = BackendSnapshot {
            state: "disconnected",
            endpoint: None,
            error: previous_error,
        };
        #[cfg(windows)]
        {
            runtime.job = None;
        }
    }

    fn fail(&self, generation: u64, message: String) {
        set_failure(&self.runtime, generation, message);
    }
}

fn lock_runtime(runtime: &Arc<Mutex<BackendRuntime>>) -> MutexGuard<'_, BackendRuntime> {
    runtime
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

fn publish_ready_endpoint(
    runtime: &Arc<Mutex<BackendRuntime>>,
    generation: u64,
    endpoint: BackendEndpoint,
) {
    let mut managed = lock_runtime(runtime);
    if managed.generation != generation || managed.snapshot.state != "starting" {
        return;
    }
    let exit_reason = match managed.child.as_mut() {
        Some(child) => match child.try_wait() {
            Ok(None) => None,
            Ok(Some(status)) => Some(format!("Backend process exited during startup ({status}).")),
            Err(error) => Some(format!(
                "Could not verify backend process during startup: {error}"
            )),
        },
        None => Some("Backend process exited during startup.".to_string()),
    };
    if let Some(error) = exit_reason {
        if let Some(mut child) = managed.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
        #[cfg(windows)]
        {
            managed.job = None;
        }
        managed.snapshot = BackendSnapshot {
            state: "disconnected",
            endpoint: None,
            error: Some(error),
        };
        return;
    }
    managed.snapshot = BackendSnapshot {
        state: "connected",
        endpoint: Some(endpoint),
        error: None,
    };
}

fn set_failure(runtime: &Arc<Mutex<BackendRuntime>>, generation: u64, message: String) {
    eprintln!("SysMind backend lifecycle error: {message}");
    let mut managed = lock_runtime(runtime);
    if managed.generation != generation {
        return;
    }
    if let Some(mut child) = managed.child.take() {
        let _ = child.kill();
        let _ = child.wait();
    }
    #[cfg(windows)]
    {
        managed.job = None;
    }
    managed.snapshot = BackendSnapshot {
        state: "disconnected",
        endpoint: None,
        error: Some(message),
    };
}

fn monitor_child_process(runtime: Arc<Mutex<BackendRuntime>>, generation: u64) {
    loop {
        thread::sleep(Duration::from_millis(250));
        let mut managed = lock_runtime(&runtime);
        if managed.generation != generation {
            return;
        }
        let Some(child) = managed.child.as_mut() else {
            return;
        };
        match child.try_wait() {
            Ok(Some(status)) => {
                managed.child = None;
                #[cfg(windows)]
                {
                    managed.job = None;
                }
                managed.snapshot = BackendSnapshot {
                    state: "disconnected",
                    endpoint: None,
                    error: Some(format!("Backend process exited unexpectedly ({status}).")),
                };
                return;
            }
            Ok(None) => {}
            Err(error) => {
                // Drop the handle so a later start() is not blocked by `child.is_some()`.
                managed.child = None;
                #[cfg(windows)]
                {
                    managed.job = None;
                }
                managed.snapshot = BackendSnapshot {
                    state: "disconnected",
                    endpoint: None,
                    error: Some(format!("Could not monitor the backend process: {error}")),
                };
                return;
            }
        }
    }
}

fn parse_handshake(line: &str) -> Option<EndpointHandshake> {
    let payload = line.strip_prefix(HANDSHAKE_PREFIX)?;
    serde_json::from_str(payload).ok()
}

/// Wait for the first parseable handshake line, bounded by `timeout`.
///
/// Returns `Err` with an operator-facing message when the stream ends first (the
/// process exited) or when the deadline passes while the process is still silent.
fn await_handshake(
    lines: &mpsc::Receiver<String>,
    timeout: Duration,
) -> Result<EndpointHandshake, &'static str> {
    let deadline = Instant::now() + timeout;
    loop {
        let Some(remaining) = deadline.checked_duration_since(Instant::now()) else {
            return Err("Backend did not publish its local endpoint in time.");
        };
        match lines.recv_timeout(remaining) {
            Ok(line) => {
                if let Some(parsed) = parse_handshake(&line) {
                    return Ok(parsed);
                }
            }
            Err(RecvTimeoutError::Timeout) => {
                return Err("Backend did not publish its local endpoint in time.");
            }
            Err(RecvTimeoutError::Disconnected) => {
                return Err("Backend exited before publishing its local endpoint.");
            }
        }
    }
}

/// Enforces the published sidecar handshake contract
/// (contracts/schemas/sidecar-handshake.schema.json) before any connection is trusted.
fn handshake_contract_error(handshake: &EndpointHandshake) -> Option<String> {
    if handshake.event != "sysmind_endpoint" {
        return Some(format!(
            "Backend handshake event mismatch: expected sysmind_endpoint, got {}.",
            handshake.event
        ));
    }
    if handshake.host != "127.0.0.1" {
        return Some("Backend attempted to use a non-loopback host.".to_string());
    }
    if handshake.port == 0 {
        return Some("Backend handshake published an invalid port.".to_string());
    }
    if handshake.backend_version.trim().is_empty() {
        return Some("Backend handshake omitted its backend version.".to_string());
    }
    if handshake.api_version != EXPECTED_API_VERSION {
        return Some(format!(
            "API protocol mismatch: desktop expects {EXPECTED_API_VERSION}, backend reported {}.",
            handshake.api_version
        ));
    }
    None
}

fn wait_until_ready(endpoint: &BackendEndpoint, timeout: Duration) -> Result<(), String> {
    let deadline = Instant::now() + timeout;
    let mut last_error = "Backend has not responded yet.".to_string();
    while Instant::now() < deadline {
        match send_http_request(endpoint, "GET", "/health") {
            Ok(body) => match serde_json::from_str::<HealthProbe>(&body) {
                Ok(health)
                    if health.status == "ok"
                        && health.ready
                        && health.api_version == EXPECTED_API_VERSION =>
                {
                    return Ok(())
                }
                Ok(health) => {
                    last_error = format!(
                        "Backend readiness or API protocol was invalid ({}).",
                        health.api_version
                    );
                }
                Err(error) => last_error = format!("Backend health response was invalid: {error}"),
            },
            Err(error) => last_error = error,
        }
        thread::sleep(Duration::from_millis(100));
    }
    Err(format!("Backend startup timed out. {last_error}"))
}

fn send_http_request(
    endpoint: &BackendEndpoint,
    method: &str,
    path: &str,
) -> Result<String, String> {
    let address = endpoint
        .base_url
        .strip_prefix("http://")
        .ok_or_else(|| "Only loopback HTTP endpoints are supported.".to_string())?;
    if !address.starts_with("127.0.0.1:") {
        return Err("Backend endpoint was not loopback-only.".to_string());
    }
    let socket = address
        .to_socket_addrs()
        .map_err(|error| format!("Invalid backend endpoint: {error}"))?
        .next()
        .ok_or_else(|| "Backend endpoint could not be resolved.".to_string())?;
    let mut stream = TcpStream::connect_timeout(&socket, Duration::from_millis(400))
        .map_err(|error| format!("Backend connection failed: {error}"))?;
    let _ = stream.set_read_timeout(Some(Duration::from_millis(800)));
    let request = format!(
        "{method} {path} HTTP/1.1\r\nHost: {address}\r\nConnection: close\r\nOrigin: tauri://localhost\r\nX-SysMind-Session: {}\r\nContent-Length: 0\r\n\r\n",
        endpoint.session_token
    );
    stream
        .write_all(request.as_bytes())
        .map_err(|error| format!("Backend request failed: {error}"))?;
    let mut response = String::new();
    stream
        .read_to_string(&mut response)
        .map_err(|error| format!("Backend response failed: {error}"))?;
    let (headers, body) = response
        .split_once("\r\n\r\n")
        .ok_or_else(|| "Backend returned a malformed HTTP response.".to_string())?;
    // Parse the status line instead of prefix-matching it, so an unexpected status such
    // as "HTTP/1.1 2000" or a different protocol version cannot be mistaken for success.
    let status_line = headers.lines().next().unwrap_or_default();
    let mut status_parts = status_line.split_whitespace();
    let protocol_ok = matches!(status_parts.next(), Some("HTTP/1.1") | Some("HTTP/1.0"));
    let code_ok = status_parts.next() == Some("200");
    if !protocol_ok || !code_ok {
        return Err("Backend returned a non-success response.".to_string());
    }
    Ok(body.to_string())
}

struct LauncherCommand {
    program: PathBuf,
    prefix_args: Vec<String>,
}

impl LauncherCommand {
    fn resolve(app: &AppHandle) -> Result<Self, String> {
        // Debug-only escape hatch for iterating on the backend: it lets a developer point
        // the shell at an arbitrary interpreter. It must NOT be honoured in release builds,
        // where a hostile process could preset the variable to launch an arbitrary binary
        // and receive the session token.
        #[cfg(debug_assertions)]
        if let Some(program) = std::env::var_os("SYSMIND_BACKEND_EXECUTABLE") {
            return Ok(Self {
                program: PathBuf::from(program),
                prefix_args: Vec::new(),
            });
        }

        if let Ok(resource_dir) = app.path().resource_dir() {
            let bundled = bundled_backend_path(resource_dir);
            if bundled.is_file() {
                return Ok(Self {
                    program: bundled,
                    prefix_args: Vec::new(),
                });
            }
        }

        if !cfg!(debug_assertions) {
            return Err(
                "The packaged SysMind backend is missing. Reinstall the application from a trusted installer."
                    .to_string(),
            );
        }

        let python = std::env::var_os("SYSMIND_PYTHON")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("python"));
        Ok(Self {
            program: python,
            prefix_args: vec!["-m".to_string(), "sysmind".to_string()],
        })
    }
}

fn bundled_backend_path(resource_dir: PathBuf) -> PathBuf {
    #[cfg(windows)]
    {
        resource_dir.join("backend").join("sysmind-backend.exe")
    }
    #[cfg(not(windows))]
    {
        resource_dir.join("backend").join("sysmind-backend")
    }
}

#[cfg(windows)]
fn configure_hidden_window(command: &mut Command) {
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    command.creation_flags(CREATE_NO_WINDOW);
}

#[cfg(windows)]
struct WindowsJob(windows_sys::Win32::Foundation::HANDLE);

#[cfg(windows)]
unsafe impl Send for WindowsJob {}

#[cfg(windows)]
impl WindowsJob {
    fn assign(child: &Child) -> Result<Self, String> {
        use std::mem::{size_of, zeroed};
        use std::os::windows::io::AsRawHandle;
        use windows_sys::Win32::System::JobObjects::{
            AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
            SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
        };

        unsafe {
            let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
            if job.is_null() {
                return Err(std::io::Error::last_os_error().to_string());
            }
            let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = zeroed();
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            let configured = SetInformationJobObject(
                job,
                JobObjectExtendedLimitInformation,
                &limits as *const _ as *const _,
                size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            );
            if configured == 0 {
                windows_sys::Win32::Foundation::CloseHandle(job);
                return Err(std::io::Error::last_os_error().to_string());
            }
            let assigned = AssignProcessToJobObject(job, child.as_raw_handle() as _);
            if assigned == 0 {
                windows_sys::Win32::Foundation::CloseHandle(job);
                return Err(std::io::Error::last_os_error().to_string());
            }
            Ok(Self(job))
        }
    }
}

#[cfg(windows)]
impl Drop for WindowsJob {
    fn drop(&mut self) {
        unsafe {
            windows_sys::Win32::Foundation::CloseHandle(self.0);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_loopback_endpoint_handshake() {
        let line = r#"SYSMIND_ENDPOINT {"event":"sysmind_endpoint","host":"127.0.0.1","port":43123,"backend_version":"0.1.0","api_version":"1.0"}"#;
        let handshake = parse_handshake(line).expect("valid handshake");
        assert_eq!(handshake.event, "sysmind_endpoint");
        assert_eq!(handshake.host, "127.0.0.1");
        assert_eq!(handshake.port, 43123);
        assert_eq!(handshake.backend_version, "0.1.0");
        assert_eq!(handshake.api_version, EXPECTED_API_VERSION);
        assert!(handshake_contract_error(&handshake).is_none());
    }

    #[test]
    fn rejects_unstructured_startup_output() {
        assert!(parse_handshake("backend ready on port 4000").is_none());
    }

    #[test]
    fn rejects_handshake_missing_event() {
        let line = r#"SYSMIND_ENDPOINT {"host":"127.0.0.1","port":43123,"backend_version":"0.1.0","api_version":"1.0"}"#;
        assert!(parse_handshake(line).is_none());
    }

    #[test]
    fn rejects_handshake_with_unknown_fields() {
        let line = r#"SYSMIND_ENDPOINT {"event":"sysmind_endpoint","host":"127.0.0.1","port":43123,"backend_version":"0.1.0","api_version":"1.0","extra":1}"#;
        assert!(parse_handshake(line).is_none());
    }

    #[test]
    fn rejects_zero_port_handshake() {
        let line = r#"SYSMIND_ENDPOINT {"event":"sysmind_endpoint","host":"127.0.0.1","port":0,"backend_version":"0.1.0","api_version":"1.0"}"#;
        let handshake = parse_handshake(line).expect("parseable handshake");
        assert_eq!(
            handshake_contract_error(&handshake).as_deref(),
            Some("Backend handshake published an invalid port.")
        );
    }

    #[test]
    fn rejects_wrong_event_name() {
        let line = r#"SYSMIND_ENDPOINT {"event":"other","host":"127.0.0.1","port":43123,"backend_version":"0.1.0","api_version":"1.0"}"#;
        let handshake = parse_handshake(line).expect("parseable handshake");
        assert!(handshake_contract_error(&handshake)
            .as_deref()
            .unwrap_or_default()
            .contains("event mismatch"));
    }

    #[test]
    fn detects_protocol_mismatch() {
        let line = r#"SYSMIND_ENDPOINT {"event":"sysmind_endpoint","host":"127.0.0.1","port":43123,"backend_version":"0.1.0","api_version":"2.0"}"#;
        let handshake = parse_handshake(line).expect("valid handshake");
        assert_ne!(handshake.api_version, EXPECTED_API_VERSION);
        assert_eq!(
            handshake_contract_error(&handshake).as_deref(),
            Some("API protocol mismatch: desktop expects 1.0, backend reported 2.0.")
        );
    }

    #[test]
    fn handshake_without_backend_version_is_not_parseable() {
        let line = r#"SYSMIND_ENDPOINT {"event":"sysmind_endpoint","host":"127.0.0.1","port":43123,"api_version":"1.0"}"#;
        assert!(parse_handshake(line).is_none());

        let blank = r#"SYSMIND_ENDPOINT {"event":"sysmind_endpoint","host":"127.0.0.1","port":43123,"backend_version":"  ","api_version":"1.0"}"#;
        let handshake = parse_handshake(blank).expect("parseable handshake");
        assert!(handshake_contract_error(&handshake).is_some());
    }

    #[test]
    fn non_loopback_handshake_fails_the_contract() {
        let line = r#"SYSMIND_ENDPOINT {"event":"sysmind_endpoint","host":"0.0.0.0","port":43123,"backend_version":"0.1.0","api_version":"1.0"}"#;
        let handshake = parse_handshake(line).expect("parseable handshake");
        assert_eq!(
            handshake_contract_error(&handshake).as_deref(),
            Some("Backend attempted to use a non-loopback host.")
        );
    }

    #[test]
    fn bundled_backend_uses_private_resource_directory() {
        let path = bundled_backend_path(PathBuf::from("C:/Program Files/SysMind/resources"));

        assert!(path.ends_with(PathBuf::from("backend/sysmind-backend.exe")));
    }

    #[test]
    fn stale_generation_cannot_publish_failure() {
        let runtime = Arc::new(Mutex::new(BackendRuntime {
            generation: 2,
            snapshot: BackendSnapshot {
                state: "starting",
                endpoint: None,
                error: None,
            },
            child: None,
            #[cfg(windows)]
            job: None,
        }));

        set_failure(&runtime, 1, "stale startup failed".to_string());

        let snapshot = lock_runtime(&runtime).snapshot.clone();
        assert_eq!(snapshot.state, "starting");
        assert!(snapshot.error.is_none());
    }

    #[test]
    fn late_handshake_cannot_resurrect_disconnected_child() {
        let runtime = Arc::new(Mutex::new(BackendRuntime {
            generation: 2,
            snapshot: BackendSnapshot {
                state: "disconnected",
                endpoint: None,
                error: Some("Backend process exited unexpectedly.".to_string()),
            },
            child: None,
            #[cfg(windows)]
            job: None,
        }));

        publish_ready_endpoint(
            &runtime,
            2,
            BackendEndpoint {
                base_url: "http://127.0.0.1:43123".to_string(),
                session_token: "test".to_string(),
                api_version: EXPECTED_API_VERSION.to_string(),
            },
        );

        let snapshot = lock_runtime(&runtime).snapshot.clone();
        assert_eq!(snapshot.state, "disconnected");
        assert!(snapshot.endpoint.is_none());
        assert_eq!(
            snapshot.error.as_deref(),
            Some("Backend process exited unexpectedly.")
        );
    }

    #[cfg(windows)]
    #[test]
    fn ready_handshake_checks_that_child_is_still_alive() {
        let mut child = Command::new("cmd")
            .args(["/C", "exit", "0"])
            .spawn()
            .expect("start disposable child");
        child.wait().expect("child exits");
        let runtime = Arc::new(Mutex::new(BackendRuntime {
            generation: 1,
            snapshot: BackendSnapshot {
                state: "starting",
                endpoint: None,
                error: None,
            },
            child: Some(child),
            job: None,
        }));

        publish_ready_endpoint(
            &runtime,
            1,
            BackendEndpoint {
                base_url: "http://127.0.0.1:43123".to_string(),
                session_token: "test".to_string(),
                api_version: EXPECTED_API_VERSION.to_string(),
            },
        );

        let snapshot = lock_runtime(&runtime).snapshot.clone();
        assert_eq!(snapshot.state, "disconnected");
        assert!(snapshot.endpoint.is_none());
        assert!(snapshot
            .error
            .as_deref()
            .unwrap_or_default()
            .contains("exited during startup"));
    }

    #[test]
    fn await_handshake_returns_first_parseable_line() {
        let (tx, rx) = mpsc::channel();
        tx.send("backend ready on port 4000".to_string()).unwrap();
        tx.send(
            r#"SYSMIND_ENDPOINT {"event":"sysmind_endpoint","host":"127.0.0.1","port":43123,"backend_version":"0.1.0","api_version":"1.0"}"#
                .to_string(),
        )
        .unwrap();

        let handshake = await_handshake(&rx, Duration::from_secs(1)).expect("handshake");
        assert_eq!(handshake.port, 43123);
    }

    #[test]
    fn await_handshake_times_out_when_backend_is_silent() {
        let (_tx, rx) = mpsc::channel::<String>();

        let result = await_handshake(&rx, Duration::from_millis(50));

        assert_eq!(
            result.err(),
            Some("Backend did not publish its local endpoint in time.")
        );
    }

    #[test]
    fn await_handshake_reports_early_exit_when_stream_closes() {
        let (tx, rx) = mpsc::channel::<String>();
        drop(tx);

        let result = await_handshake(&rx, Duration::from_secs(1));

        assert_eq!(
            result.err(),
            Some("Backend exited before publishing its local endpoint.")
        );
    }
}
