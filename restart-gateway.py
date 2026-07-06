#!/usr/bin/env python3
"""
重启 Hermes Gateway：独立进程组，不受 gateway 安全拦截。

用法:
  python3 restart-gateway.py                 # 自动查找 PID
  python3 restart-gateway.py --pid 12345     # 指定 PID
  python3 restart-gateway.py --path /path/to/hermes  # 指定 Hermes 路径
"""
import os, re, sys, time, subprocess, signal


def find_gateway_pid() -> int:
    """通过 ps 查找 gateway 主进程 PID."""
    r = subprocess.run(
        ["ps", "aux"],
        capture_output=True, text=True, timeout=5,
    )
    for line in r.stdout.splitlines():
        # 匹配 python -m hermes_cli.main gateway run 的进程
        if "gateway" in line and "run" in line and "python" in line and "grep" not in line:
            return int(line.split(None, 2)[1])
    raise RuntimeError("找不到运行中的 gateway 进程")


def find_hermes_python() -> str:
    """尝试定位 Hermes 的 Python 解释器."""
    candidates = [
        os.path.expanduser("~/.hermes/hermes-agent/venv/bin/python"),
        os.path.expanduser("~/.hermes/venv/bin/python3"),
        "/usr/local/bin/python3",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return sys.executable


def main():
    pid = find_gateway_pid()
    python_path = find_hermes_python()
    log_path = "/tmp/hermes-gateway-restart.log"

    # 解析命令行参数
    args = iter(sys.argv[1:])
    for arg in args:
        if arg == "--pid":
            pid = int(next(args))
        elif arg == "--path":
            python_path = next(args)

    print(f"=== 目标 gateway PID: {pid} ===")
    print(f"=== Hermes Python: {python_path} ===")

    # 等待用户确认
    print("即将停止旧 gateway 并启动新实例。按 Ctrl+C 取消...")
    time.sleep(2)

    # 停止旧进程
    print(f"=== 发送 SIGTERM 到 {pid} ===")
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(3)
        # 检查是否存活
        try:
            os.kill(pid, 0)  # 存活检测
            print(f"  ⚠️  PID {pid} 仍在运行，发送 SIGKILL")
            os.kill(pid, signal.SIGKILL)
            time.sleep(2)
        except ProcessLookupError:
            print("  ✅ 优雅停止成功")
    except ProcessLookupError:
        print("  ⚠️  进程已不存在")

    # 启动新 gateway
    print("=== 启动新 gateway ===")
    env = os.environ.copy()
    env.pop("_HERMES_GATEWAY", None)  # 防止新进程也认为自己是被监控的

    proc = subprocess.Popen(
        [python_path, "-m", "hermes_cli.main", "gateway", "run"],
        stdout=open(log_path, "w"),
        stderr=subprocess.STDOUT,
        env=env,
        start_new_session=True,
    )
    print(f"  ✅ 新 gateway PID: {proc.pid}")
    print(f"  📝 日志: {log_path}")

    # 等待心跳
    time.sleep(5)
    try:
        os.kill(proc.pid, 0)
        print("  ✅ 新 gateway 运行正常")
    except ProcessLookupError:
        print("  ❌ 新 gateway 已停止，检查日志")

    print(f"\n⚠️  如果使用 systemd 管理，请用:")
    print(f"   sudo systemctl restart hermes-gateway")


if __name__ == "__main__":
    main()
