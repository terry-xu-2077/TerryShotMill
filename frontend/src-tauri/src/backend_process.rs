use std::io::{BufRead, BufReader, Read};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant};

use serde::Deserialize;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Ready {
    event: String,
    url: String,
}

fn ready_url(line: &str) -> Result<String, String> {
    let ready: Ready = serde_json::from_str(line).map_err(|_| "后端启动响应格式错误")?;
    let port = ready
        .url
        .strip_prefix("http://127.0.0.1:")
        .and_then(|value| value.parse::<u16>().ok())
        .filter(|port| *port != 0);
    if ready.event != "ready" || port.is_none() {
        return Err("后端未返回有效的本机地址".into());
    }
    Ok(format!("http://127.0.0.1:{}", port.unwrap()))
}

pub struct BackendProcess {
    child: Child,
}

impl BackendProcess {
    pub fn start(mut command: Command) -> Result<(Self, String), String> {
        command.stdin(Stdio::piped()).stdout(Stdio::piped());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000); // CREATE_NO_WINDOW
        }
        let child = command
            .spawn()
            .map_err(|error| format!("无法启动本地后端：{error}"))?;
        let mut owner = Self { child };
        let stdout = owner.child.stdout.take().ok_or("无法读取后端启动状态")?;
        let (sender, receiver) = mpsc::channel();
        thread::spawn(move || {
            let mut line = String::new();
            let result = BufReader::new(stdout)
                .take(4096)
                .read_line(&mut line)
                .map_err(|_| "读取后端启动状态失败".to_string())
                .and_then(|_| ready_url(&line));
            let _ = sender.send(result);
        });
        let url = receiver
            .recv_timeout(Duration::from_secs(60))
            .map_err(|_| "本地后端未能及时启动，请查看运行日志".to_string())??;
        if owner.child.try_wait().map_err(|e| e.to_string())?.is_some() {
            return Err("本地后端在启动期间退出".into());
        }
        Ok((owner, url))
    }
}

impl Drop for BackendProcess {
    fn drop(&mut self) {
        // EOF requests graceful ASGI shutdown. Only this owned child may be
        // terminated if it fails to exit; never kill by executable name.
        drop(self.child.stdin.take());
        let deadline = Instant::now() + Duration::from_secs(20);
        loop {
            match self.child.try_wait() {
                Ok(Some(_)) => return,
                Ok(None) if Instant::now() < deadline => thread::sleep(Duration::from_millis(50)),
                _ => break,
            }
        }
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

#[cfg(test)]
mod tests {
    use super::{ready_url, BackendProcess};

    #[test]
    #[cfg(windows)]
    fn launches_real_backend_and_closes_owned_process() {
        use std::{fs, net::TcpStream, path::Path, process::Command, time::SystemTime};
        let root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .parent()
            .unwrap();
        let nonce = SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let fixture =
            std::env::temp_dir().join(format!("shotmill-launcher-{}-{nonce}", std::process::id()));
        let frontend = fixture.join("frontend");
        fs::create_dir_all(&frontend).unwrap();
        fs::write(frontend.join("index.html"), "desktop fixture").unwrap();
        let mut command = Command::new(root.join(".venv/Scripts/python.exe"));
        command
            .arg("-m")
            .arg("shotmill.desktop_runtime")
            .arg("--data-root")
            .arg(fixture.join("data"))
            .arg("--frontend-root")
            .arg(&frontend)
            .env("PYTHONPATH", root.join("backend"))
            .env("PYTHONIOENCODING", "utf-8")
            .current_dir(&fixture);
        let (backend, url) = BackendProcess::start(command).unwrap();
        let address = url.strip_prefix("http://").unwrap();
        assert!(TcpStream::connect(address).is_ok());
        assert!(!fixture.join("data/shotmill.db").exists());
        drop(backend);
        assert!(TcpStream::connect(address).is_err());
        fs::remove_dir_all(&fixture).unwrap();
    }

    #[test]
    fn accepts_only_ready_loopback_ports() {
        assert_eq!(
            ready_url(r#"{"event":"ready","url":"http://127.0.0.1:12345"}"#).unwrap(),
            "http://127.0.0.1:12345"
        );
        for url in [
            "http://127.0.0.1:0",
            "http://127.0.0.1:65536",
            "http://127.0.0.1:80/elsewhere",
            "http://localhost:1234",
            "https://example.com",
            "http://127.0.0.1:80@evil.example",
        ] {
            let message = serde_json::json!({"event": "ready", "url": url});
            assert!(ready_url(&message.to_string()).is_err());
        }
        assert!(ready_url(r#"{"event":"error","url":"http://127.0.0.1:1234"}"#).is_err());
        assert!(ready_url("").is_err());
    }
}
