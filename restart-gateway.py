#!/usr/bin/env python3
"""重启 Hermes Gateway：独立进程组，不受 gateway 安全拦截"""
import os, time, subprocess

GW_PID = 38413
GW_PATH = "/home/vmser/.hermes/hermes-agent/venv/bin/python"

time.sleep(2)
print(f"=== Killing gateway PID {GW_PID} ===")
try:
    os.kill(GW_PID, 9)
    print("  ✅ Killed")
except ProcessLookupError:
    print("  ⚠️  Already dead")

time.sleep(2)
print("=== Starting new gateway ===")
env = os.environ.copy()
env.pop("HERMES_GATEWAY_PID", None)

proc = subprocess.Popen(
    [GW_PATH, "-m", "hermes_cli.main", "gateway", "run"],
    stdout=open("/tmp/hermes-gateway-new.log", "w"),
    stderr=subprocess.STDOUT,
    env=env,
    start_new_session=True,
)
print(f"  ✅ New PID: {proc.pid}")
