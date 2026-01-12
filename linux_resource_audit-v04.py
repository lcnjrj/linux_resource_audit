#!/usr/bin/env python3
import psutil
import subprocess
import json
import csv
from datetime import datetime
import math
import sqlite3
import os

# =========================
# ANSI COLORS (btop-like)
# =========================
class C:
    RED     = "\033[38;5;196m"
    ORANGE  = "\033[38;5;208m"
    YELLOW  = "\033[38;5;226m"
    GREEN   = "\033[38;5;46m"
    CYAN    = "\033[38;5;51m"
    BLUE    = "\033[38;5;39m"
    GRAY    = "\033[38;5;245m"
    BOLD    = "\033[1m"
    RESET   = "\033[0m"

# =========================
# CONFIGURAÇÕES
# =========================
THRESHOLDS = {
    "mem_used_pct": 85,
    "swap_used_pct": 60,
    "disk_used_pct": 80
}

OUTPUT_JSON = "audit_report.json"
OUTPUT_CSV = "audit_report.csv"


DB_FILE = "audit_history.db"

# =========================
# EXTRACT
# =========================
def get_memory_info():
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "mem_total_gb": round(mem.total / 1e9, 2),
        "mem_used_gb": round(mem.used / 1e9, 2),
        "mem_used_pct": mem.percent,
        "swap_total_gb": round(swap.total / 1e9, 2),
        "swap_used_pct": swap.percent
    }

def get_disk_info(mounts=("/", "/var", "/home")):
    disks = {}
    for mount in mounts:
        try:
            usage = psutil.disk_usage(mount)
            disks[mount] = {
                "total_gb": round(usage.total / 1e9, 2),
                "used_gb": round(usage.used / 1e9, 2),
                "used_pct": usage.percent
            }
        except FileNotFoundError:
            disks[mount] = {"error": "mount not found"}
    return disks

def get_critical_logs():
    keywords = [
        "oom", "out of memory", "allocation failure",
        "enospc", "no space left", "memory pressure"
    ]
    cmd = ["journalctl", "--since", "7 days ago", "-k", "--no-pager"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    lines = [
        line for line in result.stdout.splitlines()
        if any(k in line.lower() for k in keywords)
    ]
    return lines[-20:]

# =========================
# TRANSFORM
# =========================
def classify_risk(mem, disks):
    alerts = []

    if mem["mem_used_pct"] >= THRESHOLDS["mem_used_pct"]:
        alerts.append("RAM_CRITICAL")

    if mem["swap_used_pct"] >= THRESHOLDS["swap_used_pct"]:
        alerts.append("SWAP_CRITICAL")

    for mount, data in disks.items():
        if "used_pct" in data and data["used_pct"] >= THRESHOLDS["disk_used_pct"]:
            alerts.append(f"DISK_CRITICAL:{mount}")

    return alerts if alerts else ["OK"]

def color_by_pct(pct):
    if pct >= 90:
        return C.RED
    elif pct >= 80:
        return C.ORANGE
    elif pct >= 70:
        return C.YELLOW
    else:
        return C.GREEN

def color_risk(label):
    if "CRITICAL" in label:
        return C.RED
    return C.GREEN



def recommend_resources(mem, disks):
    recommendations = {}

    # ---- RAM ----
    if mem["mem_used_pct"] >= 80:
        ideal_ram = math.ceil(mem["mem_used_gb"] * 1.5)
    else:
        ideal_ram = math.ceil(mem["mem_total_gb"])

    recommendations["ram_gb_recommended"] = ideal_ram

    # ---- DISCO ----
    disk_reco = {}
    for mount, data in disks.items():
        if "used_gb" in data:
            recommended_size = math.ceil(data["used_gb"] * 1.4)
            disk_reco[mount] = {
                "current_total_gb": data["total_gb"],
                "recommended_total_gb": recommended_size
            }
    recommendations["disk_recommendations"] = disk_reco

    # ---- LOGS ----
    recommendations["journald_limits"] = {
        "SystemMaxUse": "500M",
        "SystemKeepFree": "1G",
        "RuntimeMaxUse": "200M",
        "MaxFileSec": "7day"
    }

    return recommendations

def generate_analysis(risk, mem, disks):
    analysis = []

    if "RAM_CRITICAL" in risk or "SWAP_CRITICAL" in risk:
        analysis.append(
            "Pressão de memória detectada. O sistema opera próximo ao limite, "
            "com risco de congelamentos e latência elevada."
        )

    for mount, data in disks.items():
        if "used_pct" in data and data["used_pct"] >= 80:
            analysis.append(
                f"A partição {mount} está acima de 80% de uso, o que pode causar "
                "falhas de escrita, travamentos de serviços e degradação geral."
            )

    if not analysis:
        analysis.append(
            "O sistema opera dentro de parâmetros aceitáveis, sem indícios de "
            "quase travamento no período analisado."
        )

    return analysis


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS audits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            ram_used_pct REAL,
            swap_used_pct REAL,
            ram_total_gb REAL,
            disk_root_pct REAL,
            disk_var_pct REAL,
            disk_home_pct REAL,
            risk_level TEXT
        )
    """)

    conn.commit()
    conn.close()



# =========================
# LOAD
# =========================
def save_json(report):
    with open(OUTPUT_JSON, "w") as f:
        json.dump(report, f, indent=4)

def save_csv(report):
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "metric", "value"])

        mem = report["memory"]
        for k, v in mem.items():
            writer.writerow([report["timestamp"], k, v])

        for mount, data in report["disks"].items():
            if "used_pct" in data:
                writer.writerow([
                    report["timestamp"],
                    f"disk_used_pct:{mount}",
                    data["used_pct"]
                ])


def save_sqlite(report):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    disks = report["disks"]

    cur.execute("""
        INSERT INTO audits (
            timestamp,
            ram_used_pct,
            swap_used_pct,
            ram_total_gb,
            disk_root_pct,
            disk_var_pct,
            disk_home_pct,
            risk_level
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        report["timestamp"],
        report["memory"]["mem_used_pct"],
        report["memory"]["swap_used_pct"],
        report["memory"]["mem_total_gb"],
        disks.get("/", {}).get("used_pct"),
        disks.get("/var", {}).get("used_pct"),
        disks.get("/home", {}).get("used_pct"),
        ",".join(report["risk_level"])
    ))

    conn.commit()
    conn.close()



# =========================
# PIPELINE ETL
# =========================

def run_audit():
    timestamp = datetime.now().isoformat()

    memory = get_memory_info()
    disks = get_disk_info()
    logs = get_critical_logs()
    risk = classify_risk(memory, disks)
    recommendations = recommend_resources(memory, disks)
    analysis = generate_analysis(risk, memory, disks)

    report = {
        "timestamp": timestamp,
        "risk_level": risk,
        "analysis": analysis,
        "memory": memory,
        "disks": disks,
        "recommendations": recommendations,
        "log_indicators": logs
    }



    init_db()
    save_sqlite(report)

    # ===== LOAD (persistência) =====
    save_json(report)
    save_csv(report)

    # ===== VIEW (terminal) =====
    print(f"\n{C.BOLD}{C.CYAN}Linux Resource Audit{C.RESET}  {C.GRAY}{timestamp}{C.RESET}")

    print(f"\n{C.BOLD}Risco:{C.RESET}")
    for r in risk:
        print(f"  {color_risk(r)}● {r}{C.RESET}")

    print(f"\n{C.BOLD}Memória:{C.RESET}")
    print(
        f"  RAM: {memory['mem_used_gb']} / {memory['mem_total_gb']} GB "
        f"({color_by_pct(memory['mem_used_pct'])}{memory['mem_used_pct']}%{C.RESET})"
    )
    print(
        f"  Swap: {memory['swap_used_pct']}% "
        f"{color_by_pct(memory['swap_used_pct'])}"
        f"{'CRÍTICO' if memory['swap_used_pct'] >= 60 else 'OK'}{C.RESET}"
    )

    print(f"  {C.BLUE}→ RAM recomendada: {recommendations['ram_gb_recommended']} GB{C.RESET}")

    print(f"\n{C.BOLD}Disco:{C.RESET}")
    for mount, data in disks.items():
        if "used_pct" in data:
            color = color_by_pct(data["used_pct"])
            print(
                f"  {mount:<5} "
                f"{data['used_gb']} / {data['total_gb']} GB "
                f"({color}{data['used_pct']}%{C.RESET})"
            )

            reco = recommendations["disk_recommendations"][mount]
            print(
                f"    {C.BLUE}→ recomendado: {reco['recommended_total_gb']} GB{C.RESET}"
            )

    print(f"\n{C.BOLD}Logs (journald):{C.RESET}")
    for k, v in recommendations["journald_limits"].items():
        print(f"  {C.GRAY}{k}{C.RESET} = {v}")

    print(f"\n{C.BOLD}Análise:{C.RESET}")
    for line in analysis:
        print(f"  {C.GRAY}- {line}{C.RESET}")

    print(f"\n{C.GREEN}✔ Relatório salvo em audit_report.json{C.RESET}")


# =========================
# ENTRYPOINT
# =========================
if __name__ == "__main__":
    run_audit()
