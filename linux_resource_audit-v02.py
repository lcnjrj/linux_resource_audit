#!/usr/bin/env python3
import psutil
import subprocess
import json
import csv
from datetime import datetime
import math

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

    save_json(report)
    save_csv(report)

    # ===== OUTPUT HUMANO =====
    print("\nAuditoria concluída")
    print("Risco:", ", ".join(risk))

    print("\n--- MEMÓRIA ---")
    print(f"RAM atual: {memory['mem_total_gb']} GB")
    print(f"RAM recomendada: {recommendations['ram_gb_recommended']} GB")

    print("\n--- DISCO (Capacity Planning) ---")
    for mount, data in recommendations["disk_recommendations"].items():
        print(
            f"{mount}: atual {data['current_total_gb']} GB "
            f"→ recomendado {data['recommended_total_gb']} GB"
        )

    print("\n--- LOGS (journald) ---")
    for k, v in recommendations["journald_limits"].items():
        print(f"{k}={v}")

    print("\n--- AÇÕES RECOMENDADAS ---")
    print("1) Limpeza imediata:")
    print("   sudo apt clean")
    print("   sudo du -xh /var | sort -h | tail -20")
    print("   sudo du -xh /home | sort -h | tail -20")

    print("\n2) Limitar logs:")
    print("   Editar /etc/systemd/journald.conf com os valores acima")
    print("   sudo systemctl restart systemd-journald")
