use serde::{Deserialize, Serialize};
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex, MutexGuard};
use std::thread;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Manager};
use uuid::Uuid;

const EXPECTED_API_VERSION: &str = "1.0";
const HANDSHAKE_PREFIX: &str = "SYSMIND_ENDPOINT ";

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
struct EndpointHandshake {
    host: String,
    port: u16,
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
            let mut endpoint = None;
            for line in BufReader::new(stdout).lines().map_while(Result::ok) {
                if let Some(parsed) = parse_handshake(&line) {
                    endpoint = Some(parsed);
                    break;
                }
            }

            let Some(handshake) = endpoint else {
                set_failure(
                    &shared,
                    generation,
                    "Backend exited before publishing its local endpoint.".to_string(),
                );
                return;
            };
            if handshake.host != "127.0.0.1" {
                set_failure(
                    &shared,
                    generation,
                    "Backend attempted to use a non-loopback host.".to_string(),
                );
                return;
            }
            if handshake.api_version != EXPECTED_API_VERSION {
                set_failure(
                    &shared,
                    generation,
                    format!(
                        "API protocol mismatch: desktop expects {EXPECTED_API_VERSION}, backend reported {}.",
                        handshake.api_version
                    ),
                );
                return;
            }

            let backend_endpoint = BackendEndpoint {
                base_url: format!("http://127.0.0.1:{}", handshake.port),
                session_token: token,
                api_version: handshake.api_version,
            };
            match wait_until_ready(&backend_endpoint, Duration::from_secs(10)) {
                Ok(()) => {
                    let mut runtime = lock_runtime(&shared);
                    if runtime.generation != generation {
                        return;
                    }
                    runtime.snapshot = BackendSnapshot {
                        state: "connected",
                        endpoint: Some(backend_endpoint),
                        error: None,
                    };
                }
                Err(error) => set_failure(&shared, generation, error),
            }
        });
    }

    pub fn shutdown(&self) {
        let (endpoint, mut child) = {
            let mut runtime = lock_runtime(&self.runtime);
            runtime.generation = runtime.generation.wrapping_add(1);
            (runtime.snapshot.endpoint.clone(), runtime.child.take())
        };

        let Some(mut owned_child) = child.take() else {
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
        runtime.snapshot = BackendSnapshot {
            state: "disconnected",
            endpoint: None,
            error: None,
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
    if !headers.starts_with("HTTP/1.1 200") {
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
        let line = r#"SYSMIND_ENDPOINT {"event":"sysmind_endpoint","host":"127.0.0.1","port":43123,"api_version":"1.0"}"#;
        let handshake = parse_handshake(line).expect("valid handshake");
        assert_eq!(handshake.host, "127.0.0.1");
        assert_eq!(handshake.port, 43123);
        assert_eq!(handshake.api_version, EXPECTED_API_VERSION);
    }

    #[test]
    fn rejects_unstructured_startup_output() {
        assert!(parse_handshake("backend ready on port 4000").is_none());
    }

    #[test]
    fn detects_protocol_mismatch() {
        let line = r#"SYSMIND_ENDPOINT {"host":"127.0.0.1","port":43123,"api_version":"2.0"}"#;
        let handshake = parse_handshake(line).expect("valid handshake");
        assert_ne!(handshake.api_version, EXPECTED_API_VERSION);
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
}
