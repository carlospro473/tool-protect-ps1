#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generar_ps1.py  v4.2  (DEFINITIVO — BOM-FIXED)
============================================================
• Genera .ps1 cifrados  : AES-256-CBC + HMAC-SHA256 + PBKDF2-HMAC-SHA256
• Cifra .ps1 existentes : con contrasena manual o generada + ofuscacion
• Autodestruccion        : si la contrasena es incorrecta, el .ps1 se borra
                           y la maquina se apaga con shutdown /s /f /t 0
• Ejecucion en memoria   : sin .ps1 temporal en disco
• Uso del launcher       : .\archivo.ps1 <contrasena>
• Ofuscacion extrema     : gzip + XOR multi-ronda + fragmentacion + state machine
• UI gris avanzada       : spinner, pulse-lines, corner-box, barra con brillo
• Autoproteccion         : opcion para cifrar esta tool (.py) con contrasena
• BOM-safe               : utf-8-sig en lectura/escritura + strip en PS1
"""

import base64
import getpass
import gzip
import os
import random
import re
import secrets
import socket
import string
import subprocess
import sys
import time
from pathlib import Path

# ─── ANSI en Windows ────────────────────────────────────────
if os.name == "nt":
    os.system("")

# ─── cryptography (auto-instala) ────────────────────────────
try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import hashes, hmac, padding
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError:
    print("  Instalando 'cryptography' (una vez)...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install",
             "cryptography", "--quiet", "--disable-pip-version-check"])
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import hashes, hmac, padding
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    except Exception as e:
        print(f"  Error: {e}\n  Ejecuta: pip install cryptography")
        sys.exit(1)

# ─── Helpers BOM-safe ──────────────────────────────────────
def read_text_no_bom(path: Path) -> str:
    """Lee un archivo de texto garantizando que NO haya BOM al inicio."""
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    # Red de seguridad: si hubiese BOM residual(es), quitarlo(s)
    return text.lstrip("\ufeff")

def write_text_with_bom(path: Path, text: str) -> None:
    """Escribe .ps1 con BOM UTF-8 (PS 5.1 lo interpreta como UTF-8)."""
    # Asegurarse de que el string NO tenga BOM al inicio antes de escribir
    text = text.lstrip("\ufeff")
    path.write_text(text, encoding="utf-8-sig")

def strip_bom(s: str) -> str:
    return s.lstrip("\ufeff") if s else s

# ─── ANSI helpers ───────────────────────────────────────────
def rgb(r, g, b):
    return f"\033[38;2;{r};{g};{b}m"

RST  = "\033[0m"
BOLD = "\033[1m"
DIM  = "\033[2m"

# ─── Temas ──────────────────────────────────────────────────
THEMES = {
    "cyberpunk": {
        "name":      "Cyberpunk",
        "primary":   (255, 20, 147),
        "secondary": (0, 255, 255),
        "accent":    (255, 255, 0),
        "ok":        (57, 255, 20),
        "err":       (255, 50, 50),
        "warn":      (255, 140, 0),
        "text":      (230, 230, 255),
        "dim":       (120, 100, 180),
        "border":    (255, 20, 147),
    },
    "mono": {
        "name":      "Gris Avanzado",
        "primary":   (210, 210, 210),
        "secondary": (160, 160, 160),
        "accent":    (250, 250, 250),
        "ok":        (225, 225, 225),
        "err":       (120, 120, 120),
        "warn":      (190, 190, 190),
        "text":      (200, 200, 200),
        "dim":       (85,  85,  85),
        "border":    (130, 130, 130),
    },
}

TH = THEMES["mono"]

def tc(name):
    return rgb(*TH[name])

# ─── Configuracion ─────────────────────────────────────────
ITERACIONES  = 600_000
LONG_SALT    = 32
MIN_LEN      = 8
TYPE_SPEED   = 0.012
NUM_GEN      = 10
LEN_GEN      = 16

# ─── Info del sistema ──────────────────────────────────────
def _username():
    try:    return getpass.getuser()
    except: return os.getenv("USERNAME") or os.getenv("USER") or "user"

def _hostname():
    try:    return socket.gethostname()
    except: return "this machine"

USERNAME = _username()
HOSTNAME = _hostname()

# ─── Traducciones ──────────────────────────────────────────
TX = {
    "es": {
        "menu_title":   "MENU PRINCIPAL",
        "menu_1":       "Generar .ps1 cifrado + ofuscado   (RECOMENDADO)",
        "menu_2":       "Generar .ps1 cifrado   (sin ofuscar)",
        "menu_3":       "Cifrar + ofuscar un .ps1 existente   (contrasena)",
        "menu_4":       "Ofuscar un .ps1 existente   (sin cifrar)",
        "menu_5":       "Proteger esta tool (.py) con contrasena",
        "menu_0":       "Salir",
        "menu_choose":  "Elige una opcion",
        "welcome":      "Hola senor {user}, bienvenido de nuevo.",
        "welcome_sub":  "Usuario: {user}   •   Equipo: {host}",
        "step1_title":  "PASO 1 DE 3  •  NOMBRE DEL ARCHIVO",
        "step1_q":      "Como se llamara tu PS1?",
        "step1_prompt": "Nombre del archivo",
        "step1_saved":  "Se guardara como",
        "step2_title":  "PASO 2 DE 3  •  COMANDOS",
        "step2_desc":   "Estos comandos se cifraran en el .ps1 (AES-256).",
        "step2_first":  "Primer comando",
        "step2_nth":    "Comando #{n}",
        "step2_empty":  "Comando vacio, escribe uno por favor.",
        "step2_ok":     "{label} configurado.",
        "step2_finish": "Quieres terminar los comandos?",
        "step2_total":  "Total de comandos",
        "step3_title":  "PASO 3 DE 3  •  CONTRASENA",
        "step3_menu_title": "METODO DE CONTRASENA",
        "step3_opt1":   "Quiero poner mi propia contrasena",
        "step3_opt2":   "Generar una contrasena aleatoria",
        "step3_choose": "Elige una opcion",
        "step3_own_title":  "CONTRASENA MANUAL",
        "step3_own_desc":   "Minimo {min} caracteres.",
        "step3_pwd":    "Contrasena",
        "step3_conf":   "Confirma la contrasena",
        "step3_min":    "Minimo {min} caracteres.",
        "step3_nomatch":"Las contrasenas no coinciden.",
        "step3_ok":     "Contrasena aceptada.",
        "step3_gen_title":  "CONTRASENAS GENERADAS",
        "step3_gen_desc":   "16 letras aleatorias (A-Z a-z) via secrets.",
        "step3_gen_pick":   "Elige un numero (1-10)",
        "step3_gen_ok":     "Contrasena seleccionada",
        "summary_title":"RESUMEN DE LA CONFIGURACION",
        "sum_file":     "Archivo",
        "sum_algo":     "Cifrado",
        "sum_iter":     "Iteraciones",
        "sum_salt":     "Salt",
        "sum_cmds":     "Comandos",
        "sum_obf":      "Ofuscacion",
        "sum_press":    "Pulsa Enter para generar...",
        "gen_title":    "GENERANDO",
        "gen_label":    "CIFRANDO",
        "gen_obf":      "OFUSCANDO",
        "success_title":"EXITO",
        "success_file": "Archivo generado",
        "how_run":      "Como ejecutar",
        "how_run_secure":"(prompt seguro)",
        "security_title":"Notas de seguridad",
        "sec1":         "Contrasena NUNCA almacenada en el .ps1",
        "sec2":         "Comandos cifrados con AES-256-CBC",
        "sec3":         "Integridad verificada con HMAC-SHA256",
        "sec4":         "KDF PBKDF2-HMAC-SHA256 ({iter:,} iter)",
        "sec5":         "Autodestruccion + apagado si la clave es incorrecta",
        "sec6":         "Ejecucion en memoria (sin .ps1 temporal)",
        "cancelled":    "Cancelado.",
        "yes":          ("s", "si", "sí", "y", "yes"),
        "no":           ("n", "no"),
        "err_yn":       "Responde 's' o 'n'.",
        "err_num":      "Numero invalido.",
        "obf_in_title": "ARCHIVO DE ENTRADA",
        "obf_in_ask":   "Ruta del .ps1",
        "obf_in_ok":    "Archivo cargado",
        "obf_in_err":   "Archivo no existe o no es .ps1",
        "obf_out_ask":  "Ruta de salida (Enter = auto)",
        "obf_out_ok":   "Ruta de salida aceptada",
        "obf_title":    "OFUSCANDO  (NIVEL EXTREMO)",
        "obf_layers":  [
            "Limpiando y normalizando codigo...",
            "Compresion Gzip maxima...",
            "Cifrado multi-ronda + derivacion de claves...",
            "Fragmentacion del payload en bloques...",
            "Construyendo maquina de estados...",
            "Inyectando ruido y predicados opacos...",
            "Generando decoder virtualizado polimorfico...",
            "Empaquetando payload final Extremo...",
        ],
        "obf_success":  "OFUSCACION COMPLETADA",
        "obf_stats":    "Estadisticas",
        "obf_orig":     "Tamano original",
        "obf_new":      "Tamano ofuscado",
        "obf_ratio":    "Ratio",
        "tool_title":   "PROTEGER ESTA TOOL",
        "tool_warn":    "Se guardara como archivo NUEVO, el original se conserva.",
        "tool_pwd":     "Contrasena para la tool",
        "tool_conf":    "Confirma la contrasena",
        "tool_out":     "Nombre de salida (Enter = auto)",
        "tool_ok":      "Tool protegida generada",
        "tool_already": "Ya parece estar protegida (bootstrap detectado).",
        "tool_notpy":   "Solo funciona ejecutando el .py directamente.",
        "press":        "Pulsa Enter para continuar...",
        "exit":         "Saliendo...",
    },
    "en": {
        "menu_title":   "MAIN MENU",
        "menu_1":       "Generate encrypted .ps1 + obfuscated   (RECOMMENDED)",
        "menu_2":       "Generate encrypted .ps1   (no obfuscation)",
        "menu_3":       "Encrypt + obfuscate an existing .ps1   (password)",
        "menu_4":       "Obfuscate an existing .ps1   (no encryption)",
        "menu_5":       "Protect this tool (.py) with password",
        "menu_0":       "Exit",
        "menu_choose":  "Choose an option",
        "welcome":      "Hello sir {user}, welcome back.",
        "welcome_sub":  "User: {user}   •   Machine: {host}",
        "step1_title":  "STEP 1 OF 3  •  FILE NAME",
        "step1_q":      "How will your PS1 be called?",
        "step1_prompt": "File name",
        "step1_saved":  "Will be saved as",
        "step2_title":  "STEP 2 OF 3  •  COMMANDS",
        "step2_desc":   "These commands will be encrypted (AES-256).",
        "step2_first":  "First command",
        "step2_nth":    "Command #{n}",
        "step2_empty":  "Empty command ignored, please enter one.",
        "step2_ok":     "{label} configured.",
        "step2_finish": "Want to finish commands?",
        "step2_total":  "Total commands",
        "step3_title":  "STEP 3 OF 3  •  PASSWORD",
        "step3_menu_title": "PASSWORD METHOD",
        "step3_opt1":   "I want to use my own password",
        "step3_opt2":   "Generate a random password for me",
        "step3_choose": "Choose an option",
        "step3_own_title":  "MANUAL PASSWORD",
        "step3_own_desc":   "Minimum {min} characters.",
        "step3_pwd":    "Password",
        "step3_conf":   "Confirm password",
        "step3_min":    "Minimum {min} characters.",
        "step3_nomatch":"Passwords do not match.",
        "step3_ok":     "Password accepted.",
        "step3_gen_title":  "GENERATED PASSWORDS",
        "step3_gen_desc":   "16 random letters (A-Z a-z) via secrets.",
        "step3_gen_pick":   "Pick a number (1-10)",
        "step3_gen_ok":     "Password selected",
        "summary_title":"CONFIGURATION SUMMARY",
        "sum_file":     "File name",
        "sum_algo":     "Encryption",
        "sum_iter":     "Iterations",
        "sum_salt":     "Salt",
        "sum_cmds":     "Commands",
        "sum_obf":      "Obfuscation",
        "sum_press":    "Press Enter to generate...",
        "gen_title":    "GENERATING",
        "gen_label":    "ENCRYPTING",
        "gen_obf":      "OBFUSCATING",
        "success_title":"SUCCESS",
        "success_file": "File generated",
        "how_run":      "How to run",
        "how_run_secure":"(secure prompt)",
        "security_title":"Security notes",
        "sec1":         "Password NEVER stored in the .ps1",
        "sec2":         "Commands encrypted with AES-256-CBC",
        "sec3":         "Integrity verified with HMAC-SHA256",
        "sec4":         "KDF PBKDF2-HMAC-SHA256 ({iter:,} iter)",
        "sec5":         "Self-destruct + shutdown on wrong password",
        "sec6":         "In-memory execution (no temp .ps1)",
        "cancelled":    "Cancelled.",
        "yes":          ("y", "yes", "s", "si", "sí"),
        "no":           ("n", "no"),
        "err_yn":       "Please answer 'y' or 'n'.",
        "err_num":      "Invalid number.",
        "obf_in_title": "INPUT FILE",
        "obf_in_ask":   "Path of the .ps1",
        "obf_in_ok":    "File loaded",
        "obf_in_err":   "File not found or not a .ps1",
        "obf_out_ask":  "Output path (Enter = auto)",
        "obf_out_ok":   "Output path accepted",
        "obf_title":    "OBFUSCATING  (EXTREME LEVEL)",
        "obf_layers":  [
            "Cleaning and normalizing code...",
            "Maximum Gzip compression...",
            "Multi-round encryption + key derivation...",
            "Fragmenting payload into blocks...",
            "Building state machine...",
            "Injecting noise and opaque predicates...",
            "Generating virtualized polymorphic decoder...",
            "Packaging final Extreme payload...",
        ],
        "obf_success":  "OBFUSCATION COMPLETED",
        "obf_stats":    "Statistics",
        "obf_orig":     "Original size",
        "obf_new":      "Obfuscated size",
        "obf_ratio":    "Ratio",
        "tool_title":   "PROTECT THIS TOOL",
        "tool_warn":    "Will be saved as a NEW file, original is preserved.",
        "tool_pwd":     "Tool password",
        "tool_conf":    "Confirm password",
        "tool_out":     "Output name (Enter = auto)",
        "tool_ok":      "Protected tool generated",
        "tool_already": "Looks already protected (bootstrap detected).",
        "tool_notpy":   "Only works when running the .py directly.",
        "press":        "Press Enter to continue...",
        "exit":         "Exiting...",
    },
}

# ─── UI helpers ────────────────────────────────────────────
def clear():
    os.system("cls" if os.name == "nt" else "clear")

def typewrite(text, delay=TYPE_SPEED, color="", end="\n"):
    for ch in text:
        sys.stdout.write((color + ch + RST) if color else ch)
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write(end)
    sys.stdout.flush()

def typewrite_gradient(text, delay=TYPE_SPEED,
                       start=(120, 220, 255), end=(255, 120, 220)):
    n = max(len(text) - 1, 1)
    for i, ch in enumerate(text):
        t = i / n
        r = int(start[0] + (end[0] - start[0]) * t)
        g = int(start[1] + (end[1] - start[1]) * t)
        b = int(start[2] + (end[2] - start[2]) * t)
        sys.stdout.write(f"{rgb(r, g, b)}{ch}")
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write(RST + "\n")
    sys.stdout.flush()

def typewrite_fade(text, delay=0.018, a=(55, 55, 55), b=(240, 240, 240), end="\n"):
    n = max(len(text) - 1, 1)
    for i, ch in enumerate(text):
        t = i / n
        r = int(a[0] + (b[0] - a[0]) * t)
        g = int(a[1] + (b[1] - a[1]) * t)
        bb = int(a[2] + (b[2] - a[2]) * t)
        sys.stdout.write(f"\033[38;2;{r};{g};{bb}m{ch}")
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write(RST + end)
    sys.stdout.flush()

def spinner(text, duration=0.9, frames=("⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏")):
    end_t = time.time() + duration
    i = 0
    while time.time() < end_t:
        sys.stdout.write(f"\r  {tc('secondary')}{frames[i % len(frames)]}{RST} {tc('text')}{text}{RST}")
        sys.stdout.flush()
        i += 1
        time.sleep(0.06)
    sys.stdout.write("\r" + " " * (len(text) + 12) + "\r")
    sys.stdout.flush()

def pulse_line(width=58, cycles=2, delay=0.03):
    for _ in range(cycles):
        for i in range(width):
            r = int(50 + (200 * (i / width)))
            sys.stdout.write(f"\033[38;2;{r};{r};{r}m─")
        sys.stdout.write(RST + "\n")
        sys.stdout.flush()
        time.sleep(delay)

def corner_box(title, width=58):
    tl, tr, bl, br = "┌", "┐", "└", "┘"
    h = "─"
    print()
    print(f"  {tc('border')}{tl}{h * width}{tr}{RST}")
    pad = (width - len(title) - 2) // 2
    line = " " * pad + " " + title + " " + " " * (width - pad - len(title) - 1)
    for i, ch in enumerate(line):
        k = int(80 + 170 * (1 - abs(i / len(line) - 0.5) * 2))
        sys.stdout.write(f"\033[38;2;{k};{k};{k}m{ch}")
    sys.stdout.write(RST + "\n")
    print(f"  {tc('border')}{bl}{h * width}{br}{RST}")
    print()

def pline(text=""):
    print(text)

def ask(text):
    sys.stdout.write(f"  {tc('primary')}❯{RST} {BOLD}{tc('text')}{text}:{RST} ")
    sys.stdout.flush()
    return input()

def ask_yn(text, lang):
    yn = "[s/n]" if lang == "es" else "[y/n]"
    while True:
        sys.stdout.write(
            f"  {tc('primary')}❯{RST} {tc('text')}{text}{RST} "
            f"{tc('dim')}{yn}{RST}: ")
        sys.stdout.flush()
        r = input().strip().lower()
        if r in TX[lang]["yes"]: return True
        if r in TX[lang]["no"]:  return False
        pline(f"  {tc('err')}✗ {TX[lang]['err_yn']}{RST}")

def ask_number(text, lo, hi, lang):
    while True:
        try:
            v = int(ask(text))
            if lo <= v <= hi: return v
            pline(f"  {tc('err')}✗ {lo}-{hi}{RST}")
        except ValueError:
            pline(f"  {tc('err')}✗ {TX[lang]['err_num']} {lo}-{hi}{RST}")

def header(title):
    bar = "═" * 60
    print()
    print(f"  {tc('border')}╔{bar}╗{RST}")
    print(f"  {tc('border')}║{RST} {tc('primary')}{BOLD}{title.ljust(58)}{RST} {tc('border')}║{RST}")
    print(f"  {tc('border')}╚{bar}╝{RST}")
    print()

def progress_bar_advanced(duration=3.0, width=42, label="GENERATING"):
    start = time.time()
    while True:
        elapsed = time.time() - start
        pct = min(elapsed / duration, 1.0)
        filled = int(width * pct)
        head = min(filled, width - 1)
        bar = ""
        for i in range(width):
            if i < filled:
                d = abs(i - head)
                k = max(70, 255 - d * 22)
                bar += f"\033[38;2;{k};{k};{k}m█"
            else:
                bar += f"{tc('dim')}░"
        sys.stdout.write(
            f"\r  {tc('ok')}{BOLD}✦ {label}{RST}  "
            f"[{bar}{RST}]  {tc('accent')}{int(pct * 100):3d}%{RST}"
        )
        sys.stdout.flush()
        if pct >= 1.0: break
        time.sleep(0.035)
    sys.stdout.write("\n")
    sys.stdout.flush()

def banner():
    clear()
    W = 58
    top = "  ╔" + "═" * W + "╗"
    bot = "  ╚" + "═" * W + "╝"
    mid = "  ║" + " " * W + "║"
    t1  = "  ║" + "SECURE  PS1  GENERATOR".center(W) + "║"
    t2  = "  ║" + "AES-256 · HMAC-SHA256 · PBKDF2 · v4.2".center(W) + "║"
    for l in [top, mid]:
        print(tc("border") + l + RST); time.sleep(0.03)
    print(tc("primary") + BOLD + t1 + RST); time.sleep(0.06)
    print(tc("border") + mid + RST); time.sleep(0.03)
    print(tc("secondary") + DIM + t2 + RST); time.sleep(0.06)
    for l in [mid, bot]:
        print(tc("border") + l + RST); time.sleep(0.03)
    print()

# ─── Criptografia AES-256-CBC + HMAC ──────────────────────
def derive_keys(password, salt, iterations):
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=64,
                     salt=salt, iterations=iterations)
    d = kdf.derive(password.encode("utf-8"))
    return d[:32], d[32:64]

def encrypt_payload(text, password, iterations):
    # Blindaje: sin BOM al inicio antes de cifrar
    text = strip_bom(text)
    salt = os.urandom(LONG_SALT)
    aes_key, mac_key = derive_keys(password, salt, iterations)
    iv = os.urandom(16)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(text.encode("utf-8")) + padder.finalize()
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    enc = cipher.encryptor()
    ct = enc.update(padded) + enc.finalize()
    h = hmac.HMAC(mac_key, hashes.SHA256())
    h.update(iv + ct)
    mac = h.finalize()
    return salt, iv + mac + ct

# ─── Plantilla PS1 (BOM-safe + autodestruccion + memoria) ─
PLANTILLA = r'''<#
.SYNOPSIS
    Lanzador protegido (AES-256-CBC + HMAC-SHA256 + PBKDF2-SHA256).
.DESCRIPTION
    Uso:    .\archivo.ps1 <contrasena>
    Los comandos estan cifrados. Si la contrasena es incorrecta:
      • El .ps1 se autodestruye
      • El equipo se apaga forzadamente (shutdown /s /f /t 0)
    No se escribe ningun .ps1 temporal: la carga se ejecuta en memoria.
.NOTES
    KDF:         PBKDF2-HMAC-SHA256 ({ITER} iteraciones)
    Cifrado:     AES-256-CBC
    Integridad:  HMAC-SHA256 (encrypt-then-MAC)
    Salt:        32 bytes aleatorios
#>
param(
    [Parameter(Position=0)]
    [string]$Pass = ""
)

if ([string]::IsNullOrEmpty($Pass) -and $args.Count -gt 0) {
    $Pass = [string]$args[0]
}

$KdfSaltB64 = "{SALT}"
$KdfIter    = {ITER}
$PayloadB64 = "{PAYLOAD}"

if ([string]::IsNullOrEmpty($Pass)) {
    Write-Host "Contrasena: " -NoNewline
    $secure = Read-Host -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $Pass = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

$salt = [Convert]::FromBase64String($KdfSaltB64)
$blob = [Convert]::FromBase64String($PayloadB64)

$iv     = [byte[]]::new(16)
$mac    = [byte[]]::new(32)
$cipher = [byte[]]::new($blob.Length - 48)
[Array]::Copy($blob, 0,  $iv,     0, 16)
[Array]::Copy($blob, 16, $mac,    0, 32)
[Array]::Copy($blob, 48, $cipher, 0, $blob.Length - 48)

$derive = [System.Security.Cryptography.Rfc2898DeriveBytes]::new(
    $Pass, $salt, $KdfIter,
    [System.Security.Cryptography.HashAlgorithmName]::SHA256)
try {
    $aesKey = $derive.GetBytes(32)
    $macKey = $derive.GetBytes(32)
} finally {
    $derive.Dispose()
}

$Pass = $null

$macInput = [byte[]]::new(16 + $cipher.Length)
[Array]::Copy($iv,     0, $macInput, 0,  16)
[Array]::Copy($cipher, 0, $macInput, 16, $cipher.Length)

$hmac    = [System.Security.Cryptography.HMACSHA256]::new($macKey)
$calcMac = $hmac.ComputeHash($macInput)
$hmac.Dispose()

$diff = 0
for ($i = 0; $i -lt 32; $i++) {
    $diff = $diff -bor ($calcMac[$i] -bxor $mac[$i])
}

if ($diff -ne 0) {
    $aesKey = $null; $macKey = $null; $Pass = $null
    [GC]::Collect(); [GC]::WaitForPendingFinalizers()

    $selfPath = $PSCommandPath
    if ([string]::IsNullOrEmpty($selfPath)) { $selfPath = $MyInvocation.PSCommandPath }
    if ([string]::IsNullOrEmpty($selfPath)) { $selfPath = $MyInvocation.MyCommand.Path }

    if ((-not [string]::IsNullOrEmpty($selfPath)) -and (Test-Path -LiteralPath $selfPath)) {
        try {
            $batPath = Join-Path $env:TEMP ("sd_" + [Guid]::NewGuid().ToString("N") + ".bat")
            $escaped = $selfPath -replace '"', '""'
            $batContent = "@echo off`r`nping 127.0.0.1 -n 2 >nul`r`ndel /f /q `"$escaped`" 2>nul`r`ndel /f /q `"%~f0`" 2>nul`r`n"
            [System.IO.File]::WriteAllText($batPath, $batContent)
            Start-Process -FilePath $batPath -WindowStyle Hidden -ErrorAction SilentlyContinue
        } catch {}
        try { Remove-Item -LiteralPath $selfPath -Force -ErrorAction SilentlyContinue } catch {}
    }

    Write-Host ""
    Write-Host "ERROR: Contrasena incorrecta. Autodestruccion activada." -ForegroundColor Red
    Write-Host ""

    try { Stop-Computer -Force -ErrorAction SilentlyContinue } catch {}
    try { & shutdown.exe /s /f /t 0 | Out-Null } catch {}
    exit 1
}

$aes = [System.Security.Cryptography.Aes]::Create()
try {
    $aes.Mode    = [System.Security.Cryptography.CipherMode]::CBC
    $aes.Padding = [System.Security.Cryptography.PaddingMode]::PKCS7
    $aes.Key     = $aesKey
    $aes.IV      = $iv
    $dec = $aes.CreateDecryptor()
    $plainBytes = $dec.TransformFinalBlock($cipher, 0, $cipher.Length)
    $script = [System.Text.Encoding]::UTF8.GetString($plainBytes)
} finally {
    $aes.Dispose()
    $aesKey = $null; $macKey = $null; [GC]::Collect()
}

# ─── BOM-safe: quitar BOM si el payload lo tuviera ───────
if ($script.Length -gt 0 -and [int][char]$script[0] -eq 0xFEFF) {
    $script = $script.Substring(1)
}

Write-Host ""
Write-Host "Acceso concedido. Ejecutando comandos..." -ForegroundColor Green
Write-Host ""

# ─── Ejecucion en memoria (SIN .ps1 temporal) ─────────────
$sb = [ScriptBlock]::Create($script)
$script     = $null
$plainBytes = $null
[GC]::Collect()

try {
    & $sb
} finally {
    $sb = $null
    [GC]::Collect()
}

Write-Host ""
Write-Host "Aplicacion finalizada." -ForegroundColor Green
exit 0
'''

def render_ps1(salt, blob, iterations):
    ps1 = PLANTILLA
    ps1 = ps1.replace("{SALT}",    base64.b64encode(salt).decode("ascii"))
    ps1 = ps1.replace("{ITER}",    str(iterations))
    ps1 = ps1.replace("{PAYLOAD}", base64.b64encode(blob).decode("ascii"))
    return ps1

# ─── Ofuscador extremo (fragmentado + state machine) ──────
class ExtremeObfuscator:
    def __init__(self):
        self.rng = random.Random(secrets.randbits(128))

    def _n(self, length=11):
        return self.rng.choice(string.ascii_letters) + ''.join(
            self.rng.choice(string.ascii_letters + string.digits) for _ in range(length - 1))

    def _names(self, count, length=11):
        return [self._n(length) for _ in range(count)]

    def _clean(self, code: str) -> str:
        code = re.sub(r'<#.*?#>', '', code, flags=re.DOTALL)
        lines = []
        for line in code.splitlines():
            out, in_s, in_d = [], False, False
            i = 0
            while i < len(line):
                c = line[i]
                if c == "'" and not in_d:
                    in_s = not in_s
                elif c == '"' and not in_s:
                    if not (i > 0 and line[i-1] == '`'):
                        in_d = not in_d
                if c == '#' and not in_s and not in_d:
                    break
                out.append(c)
                i += 1
            lines.append(''.join(out).rstrip())
        code = '\n'.join(lines)
        return re.sub(r'\n{3,}', '\n\n', code).strip()

    def _final_pack(self, code: str) -> str:
        raw        = code.encode("utf-8")
        compressed = gzip.compress(raw, compresslevel=9)
        seed       = secrets.token_bytes(32)

        def make_key(seed_bytes, salt):
            out = bytearray(32)
            for i in range(32):
                out[i] = seed_bytes[i] ^ ((i * 17 + salt * 31) & 0xFF)
            return bytes(out)

        k1, k2, k3 = make_key(seed, 11), make_key(seed, 29), make_key(seed, 47)

        def xor_round(data, key):
            return bytes(b ^ key[i % 32] for i, b in enumerate(data))

        stage = xor_round(xor_round(xor_round(compressed, k1), k2), k3)

        # Base64 al bloque COMPLETO, luego partir el string.
        stage_b64 = base64.b64encode(stage).decode("ascii")
        frag_size = self.rng.randint(48, 96)
        frag_b64  = [stage_b64[i:i + frag_size]
                     for i in range(0, len(stage_b64), frag_size)]

        seed_b64 = base64.b64encode(seed).decode("ascii")

        (v_seed, v_state, v_buf, v_tmp, v_idx,
         v_k1, v_k2, v_k3, v_ms, v_gz, v_sr, v_sb,
         v_parts, v_join, v_len, v_i, v_b,
         d1, d2, d3, d4, d5, d6, d7, d8) = self._names(25, 12)

        frag_init = "\n".join(
            f"${v_parts}[{i}]='{fb}'" for i, fb in enumerate(frag_b64))

        loader = f'''# ofuscateps1 | Extreme+Virtualization
${d1}=$null;${d2}=0;${d3}=$false
${v_seed}=[Convert]::FromBase64String('{seed_b64}')
${v_parts}=New-Object string[] {len(frag_b64)}
{frag_init}
${v_state}=0
${v_buf}=$null
${v_join}=$null
while(${v_state} -ge 0){{
  switch(${v_state}){{
    0 {{
      ${d4}=[math]::Sqrt(0)
      ${v_state}=10
    }}
    10 {{
      ${v_join}=(${v_parts} -join '')
      ${v_b}=[Convert]::FromBase64String(${v_join})
      ${v_state}=20
    }}
    20 {{
      ${v_k1}=New-Object byte[] 32
      ${v_k2}=New-Object byte[] 32
      ${v_k3}=New-Object byte[] 32
      for($n=0;$n -lt 32;$n++){{
        ${v_k1}[$n]=${v_seed}[$n] -bxor (($n*17 + 11*31) -band 255)
        ${v_k2}[$n]=${v_seed}[$n] -bxor (($n*17 + 29*31) -band 255)
        ${v_k3}[$n]=${v_seed}[$n] -bxor (($n*17 + 47*31) -band 255)
      }}
      ${v_state}=30
    }}
    30 {{
      ${v_tmp}=New-Object byte[] ${v_b}.Length
      for($i=0;$i -lt ${v_b}.Length;$i++){{${v_tmp}[$i]=${v_b}[$i] -bxor ${v_k3}[$i%32]}}
      ${v_b}=${v_tmp}
      ${v_state}=40
    }}
    40 {{
      ${v_tmp}=New-Object byte[] ${v_b}.Length
      for($i=0;$i -lt ${v_b}.Length;$i++){{${v_tmp}[$i]=${v_b}[$i] -bxor ${v_k2}[$i%32]}}
      ${v_b}=${v_tmp}
      ${v_state}=50
    }}
    50 {{
      ${v_tmp}=New-Object byte[] ${v_b}.Length
      for($i=0;$i -lt ${v_b}.Length;$i++){{${v_tmp}[$i]=${v_b}[$i] -bxor ${v_k1}[$i%32]}}
      ${v_b}=${v_tmp}
      ${v_state}=60
    }}
    60 {{
      if($false){{${d5}=1}}
      ${v_state}=70
    }}
    70 {{
      ${v_ms}=New-Object IO.MemoryStream(,[byte[]]${v_b})
      ${v_gz}=New-Object IO.Compression.GzipStream(${v_ms},[IO.Compression.CompressionMode]::Decompress)
      ${v_sr}=New-Object IO.StreamReader(${v_gz},[Text.Encoding]::UTF8)
      ${v_sb}=[ScriptBlock]::Create(${v_sr}.ReadToEnd())
      ${v_sr}.Close();${v_gz}.Close();${v_ms}.Close()
      ${v_state}=80
    }}
    80 {{
      ${v_b}=$null;${v_tmp}=$null;${v_join}=$null;${v_parts}=$null
      ${d6}=$null;${d7}=$null
      ${v_state}=90
    }}
    90 {{
      $global:__SELF__ = $PSCommandPath
      if (-not $global:__SELF__) {{ $global:__SELF__ = $MyInvocation.PSCommandPath }}
      & ${v_sb} @args
      ${v_state}=-1
    }}
    default {{
      ${v_state}=-1
    }}
  }}
}}
${d8}=$null
'''
        return loader

    def obfuscate(self, source: str) -> str:
        return self._final_pack(self._clean(strip_bom(source)))

# ─── Protector de la tool (.py) ────────────────────────────
BOOTSTRAP_PY = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tool protegida — payload cifrado (AES-256-CBC + HMAC-SHA256)
"""
import base64, getpass, sys, subprocess
try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import hashes, hmac, padding
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "cryptography", "--quiet", "--disable-pip-version-check"])
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import hashes, hmac, padding
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_SALT = base64.b64decode("{SALT}")
_ITER = {ITER}
_BLOB = base64.b64decode("{PAYLOAD}")

def _run():
    pwd = getpass.getpass("Contrasena de la tool: ")
    if not pwd:
        sys.exit(1)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=64,
                     salt=_SALT, iterations=_ITER)
    d = kdf.derive(pwd.encode("utf-8"))
    aes_key, mac_key = d[:32], d[32:64]
    iv, mac, ct = _BLOB[:16], _BLOB[16:48], _BLOB[48:]
    h = hmac.HMAC(mac_key, hashes.SHA256()); h.update(iv + ct)
    try:
        h.verify(mac)
    except Exception:
        print("Contrasena incorrecta."); sys.exit(1)
    aes = Cipher(algorithms.AES(aes_key), modes.CBC(iv)).decryptor()
    padded = aes.update(ct) + aes.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    code = unpadder.update(padded) + unpadder.finalize()
    del pwd, d, aes_key, mac_key, padded
    ns = {"__name__": "__main__", "__file__": __file__}
    exec(compile(code, "<protected>", "exec"), ns)

if __name__ == "__main__":
    _run()
'''

# ─── Selectores iniciales ─────────────────────────────────
def elegir_idioma():
    clear()
    W = 58
    print(tc("border") + "  ╔" + "═"*W + "╗" + RST)
    print(tc("border") + "  ║" + " "*W + "║" + RST)
    print(tc("primary") + BOLD + "  ║" + "LANGUAGE  /  IDIOMA".center(W) + "║" + RST)
    print(tc("border") + "  ║" + " "*W + "║" + RST)
    print(tc("border") + "  ╠" + "═"*W + "╣" + RST)
    print(tc("border") + "  ║" + " "*W + "║" + RST)
    print(tc("border") + "  ║" + RST + f"  {tc('secondary')}[1]{RST}  English".ljust(W + 6) + tc("border") + "║" + RST)
    print(tc("border") + "  ║" + " "*W + "║" + RST)
    print(tc("border") + "  ║" + RST + f"  {tc('secondary')}[2]{RST}  Espanol".ljust(W + 6) + tc("border") + "║" + RST)
    print(tc("border") + "  ║" + " "*W + "║" + RST)
    print(tc("border") + "  ╚" + "═"*W + "╝" + RST)
    print()
    while True:
        sys.stdout.write(f"  {tc('primary')}❯{RST} {BOLD}{tc('text')}Choose / Elige:{RST} ")
        sys.stdout.flush()
        r = input().strip().lower()
        if r in ("1", "en", "english"): return "en"
        if r in ("2", "es", "español", "espanol", "spanish"): return "es"
        pline(f"  {tc('err')}✗ 1 / 2{RST}")

def elegir_tema(lang):
    clear()
    W = 58
    print(tc("border") + "  ╔" + "═"*W + "╗" + RST)
    print(tc("border") + "  ║" + " "*W + "║" + RST)
    t = "THEME" if lang == "en" else "TEMA"
    print(tc("primary") + BOLD + "  ║" + f"{t}".center(W) + "║" + RST)
    print(tc("border") + "  ║" + " "*W + "║" + RST)
    print(tc("border") + "  ╠" + "═"*W + "╣" + RST)
    print(tc("border") + "  ║" + " "*W + "║" + RST)
    line1 = f"  {rgb(255,20,147)}[1]{RST}  Cyberpunk   {rgb(255,20,147)}█{rgb(0,255,255)}█{rgb(255,255,0)}█{RST}"
    line2 = f"  {rgb(210,210,210)}[2]{RST}  Gris Avz.   {rgb(210,210,210)}█{rgb(130,130,130)}█{rgb(60,60,60)}█{RST}"
    print(tc("border") + "  ║" + RST + line1.ljust(W + 2) + tc("border") + "║" + RST)
    print(tc("border") + "  ║" + " "*W + "║" + RST)
    print(tc("border") + "  ║" + RST + line2.ljust(W + 2) + tc("border") + "║" + RST)
    print(tc("border") + "  ║" + " "*W + "║" + RST)
    print(tc("border") + "  ╚" + "═"*W + "╝" + RST)
    print()
    while True:
        sys.stdout.write(f"  {tc('primary')}❯{RST} {BOLD}{tc('text')}1 / 2:{RST} ")
        sys.stdout.flush()
        r = input().strip()
        if r == "1": return "cyberpunk"
        if r == "2": return "mono"
        pline(f"  {tc('err')}✗ 1 / 2{RST}")

def mostrar_bienvenida(lang):
    t = TX[lang]
    clear()
    banner()
    time.sleep(0.2)
    typewrite_gradient(
        "  " + t["welcome"].format(user=USERNAME),
        delay=0.035,
        start=TH["primary"],
        end=TH["secondary"],
    )
    print()
    print(f"  {tc('dim')}{t['welcome_sub'].format(user=USERNAME, host=HOSTNAME)}{RST}")
    print()
    time.sleep(0.9)

# ─── Menu principal ───────────────────────────────────────
def menu_principal(lang):
    t = TX[lang]
    while True:
        clear()
        corner_box(t["menu_title"])
        opts = [
            ("1", t["menu_1"]),
            ("2", t["menu_2"]),
            ("3", t["menu_3"]),
            ("4", t["menu_4"]),
            ("5", t["menu_5"]),
            ("0", t["menu_0"]),
        ]
        for k, v in opts:
            typewrite(f"  {tc('secondary')}[{k}]{RST}  {tc('text')}{v}{RST}",
                      delay=0.006)
        print()
        sys.stdout.write(f"  {tc('primary')}❯{RST} {BOLD}{tc('text')}{t['menu_choose']}:{RST} ")
        sys.stdout.flush()
        r = input().strip()
        if r in ("0", "1", "2", "3", "4", "5"):
            return r

# ─── Pasos generar PS1 ────────────────────────────────────
def pedir_nombre(lang):
    t = TX[lang]
    clear()
    header(t["step1_title"])
    typewrite("  " + t["step1_q"], 0.02, tc("accent") + BOLD)
    print()
    nombre = strip_bom(ask(t["step1_prompt"]).strip())
    if not nombre:
        nombre = "test.ps1"
    if not nombre.lower().endswith(".ps1"):
        nombre += ".ps1"
    print()
    print(f"  {tc('ok')}✓{RST} {t['step1_saved']}: {BOLD}{nombre}{RST}")
    time.sleep(0.5)
    return nombre

def pedir_comandos(lang):
    t = TX[lang]
    clear()
    header(t["step2_title"])
    typewrite("  " + t["step2_desc"], 0.008, tc("dim"))
    print()
    comandos = []
    num = 1
    while True:
        label = t["step2_first"] if num == 1 else t["step2_nth"].format(n=num)
        cmd = strip_bom(ask(f"{tc('ok')}{label}{RST}").strip())
        if cmd == "":
            pline(f"  {tc('err')}✗ {t['step2_empty']}{RST}")
            continue
        comandos.append(cmd)
        print()
        pline(f"  {tc('ok')}✓{RST} {t['step2_ok'].format(label=label)}")
        print()
        if not ask_yn(t["step2_finish"], lang):
            num += 1
            print()
            continue
        break
    print()
    pline(f"  {tc('ok')}✓{RST} {t['step2_total']}: {BOLD}{len(comandos)}{RST}")
    time.sleep(0.6)
    return comandos

def generar_contrasenas(n=NUM_GEN, largo=LEN_GEN):
    alphabet = string.ascii_letters
    return ["".join(secrets.choice(alphabet) for _ in range(largo))
            for _ in range(n)]

def pedir_contrasena(lang):
    t = TX[lang]
    clear()
    header(t["step3_title"])
    pline(f"  {tc('text')}{BOLD}{t['step3_menu_title']}{RST}")
    print()
    typewrite(f"  {tc('secondary')}[1]{RST}  {t['step3_opt1']}", 0.010, "")
    time.sleep(0.2)
    typewrite(f"  {tc('secondary')}[2]{RST}  {t['step3_opt2']}", 0.010, "")
    print()
    opcion = ask_number(t["step3_choose"], 1, 2, lang)

    if opcion == 1:
        clear()
        header(t["step3_own_title"])
        typewrite("  " + t["step3_own_desc"].format(min=MIN_LEN), 0.008, tc("dim"))
        print()
        while True:
            sys.stdout.write(f"  {tc('primary')}❯{RST} {tc('text')}{t['step3_pwd']}:{RST} ")
            sys.stdout.flush()
            p1 = getpass.getpass("")
            if len(p1) < MIN_LEN:
                pline(f"  {tc('err')}✗ {t['step3_min'].format(min=MIN_LEN)}{RST}")
                continue
            sys.stdout.write(f"  {tc('primary')}❯{RST} {tc('text')}{t['step3_conf']}:{RST} ")
            sys.stdout.flush()
            p2 = getpass.getpass("")
            if p1 != p2:
                pline(f"  {tc('err')}✗ {t['step3_nomatch']}{RST}")
                continue
            print()
            pline(f"  {tc('ok')}✓{RST} {t['step3_ok']}")
            time.sleep(0.6)
            return p1
    else:
        clear()
        header(t["step3_gen_title"])
        typewrite("  " + t["step3_gen_desc"], 0.008, tc("dim"))
        print()
        pool = generar_contrasenas()
        for i, pw in enumerate(pool, 1):
            pline(f"    {tc('secondary')}[{i:02d}]{RST}  {tc('text')}{BOLD}{pw}{RST}")
            time.sleep(0.05)
        print()
        idx = ask_number(t["step3_gen_pick"], 1, len(pool), lang)
        elegida = pool[idx - 1]
        print()
        pline(f"  {tc('ok')}✓{RST} {t['step3_gen_ok']}: {tc('accent')}{BOLD}{elegida}{RST}")
        time.sleep(1.0)
        return elegida

def mostrar_resumen(lang, nombre, comandos, ofuscar):
    t = TX[lang]
    clear()
    header(t["summary_title"])
    print(f"  {tc('primary')}{t['sum_file']:<12}{RST}: {BOLD}{nombre}{RST}")
    print(f"  {tc('primary')}{t['sum_algo']:<12}{RST}: AES-256-CBC + HMAC-SHA256")
    print(f"  {tc('primary')}{t['sum_iter']:<12}{RST}: {ITERACIONES:,}")
    print(f"  {tc('primary')}{t['sum_salt']:<12}{RST}: {LONG_SALT} bytes (random)")
    print(f"  {tc('primary')}{t['sum_obf']:<12}{RST}: {'SI (extremo)' if ofuscar else 'NO'}")
    print()
    print(f"  {tc('primary')}{t['sum_cmds']} ({len(comandos)}):{RST}")
    for i, c in enumerate(comandos, 1):
        print(f"    {tc('ok')}{i:02d}.{RST} {c}")
    print()
    typewrite_gradient("  ✦ " + t["sum_press"],
                       delay=0.02,
                       start=TH["warn"],
                       end=TH["primary"])
    input()

# ─── Sistema de archivos ──────────────────────────────────
def carpeta_escritorio():
    home = Path.home()
    for c in [home / "Desktop", home / "Escritorio",
              home / "OneDrive" / "Desktop",
              home / "OneDrive" / "Escritorio"]:
        if c.exists(): return c
    return home

# ─── Flujos ───────────────────────────────────────────────
def flujo_generar(lang, ofuscar):
    t = TX[lang]
    nombre   = pedir_nombre(lang)
    comandos = pedir_comandos(lang)
    password = pedir_contrasena(lang)
    mostrar_resumen(lang, nombre, comandos, ofuscar)

    clear()
    header(t["gen_title"])
    print()

    spinner("Derivando claves PBKDF2-HMAC-SHA256...", 0.5)
    commands_text = "\n".join(comandos)
    salt, blob = encrypt_payload(commands_text, password, ITERACIONES)
    ps1_text = render_ps1(salt, blob, ITERACIONES)

    progress_bar_advanced(2.5, label=t["gen_label"])
    print()

    if ofuscar:
        spinner("Aplicando ofuscacion extrema...", 0.4)
        try:
            ps1_text = ExtremeObfuscator().obfuscate(ps1_text)
        except Exception as e:
            pline(f"  {tc('warn')}! Ofuscacion fallo: {e} — se guarda sin ofuscar.{RST}")
        progress_bar_advanced(3.0, label=t["gen_obf"])
        print()

    destino = carpeta_escritorio()
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / nombre
    write_text_with_bom(ruta, ps1_text)

    header(t["success_title"])
    print(f"  {tc('ok')}✓{RST} {t['success_file']}: {BOLD}{ruta}{RST}")
    print()
    print(f"  {tc('primary')}{t['how_run']}:{RST}")
    print(f"    {tc('dim')}1){RST} cd \"{destino}\"")
    print(f"    {tc('dim')}2){RST} .\\{nombre} MiContrasena")
    print(f"    {tc('dim')}o){RST} .\\{nombre}   {tc('dim')}{t['how_run_secure']}{RST}")
    print()
    print(f"  {tc('warn')}{t['security_title']}:{RST}")
    for k in ("sec1","sec2","sec3","sec4","sec5","sec6"):
        val = t[k].format(iter=ITERACIONES) if "{iter}" in t[k] else t[k]
        print(f"    {tc('ok')}•{RST} {val}")
    print()
    input(f"  {tc('dim')}{t['press']}{RST}")

def flujo_cifrar_existente(lang):
    """Toma un .ps1 existente, lo cifra con contrasena (manual o generada),
    lo ofusca y lo guarda como <stem>_cifrado.ps1 en el Escritorio.
    LEE con utf-8-sig para descartar el BOM (fix critico)."""
    t = TX[lang]
    clear()
    header(t["obf_in_title"])

    # 1) Solo se pide la ruta
    while True:
        p = ask(t["obf_in_ask"]).strip().strip('"').strip("'")
        src = Path(p).expanduser().resolve()
        if src.is_file() and src.suffix.lower() == ".ps1":
            # FIX BOM: leer con utf-8-sig (descarta BOM si existe)
            source = read_text_no_bom(src)
            print()
            print(f"  {tc('ok')}✓{RST} {t['obf_in_ok']}: {src}")
            time.sleep(0.4)
            break
        pline(f"  {tc('err')}✗ {t['obf_in_err']}{RST}")

    # 2) Contrasena (manual o generada)
    password = pedir_contrasena(lang)

    # 3) Resumen
    clear()
    header(t["summary_title"])
    print(f"  {tc('primary')}{t['sum_file']:<14}{RST}: {BOLD}{src.name}{RST}")
    print(f"  {tc('primary')}{t['sum_algo']:<14}{RST}: AES-256-CBC + HMAC-SHA256")
    print(f"  {tc('primary')}{t['sum_iter']:<14}{RST}: {ITERACIONES:,}")
    print(f"  {tc('primary')}{t['sum_salt']:<14}{RST}: {LONG_SALT} bytes (random)")
    print(f"  {tc('primary')}{t['sum_obf']:<14}{RST}: SI (extremo)")
    print()
    typewrite_gradient("  ✦ " + t["sum_press"],
                       delay=0.02, start=TH["warn"], end=TH["primary"])
    input()

    # 4) Cifrar el contenido COMPLETO (ya sin BOM) del .ps1 origen
    clear()
    header(t["gen_title"])
    print()
    spinner("Derivando claves PBKDF2-HMAC-SHA256...", 0.5)
    salt, blob = encrypt_payload(source, password, ITERACIONES)
    ps1_text   = render_ps1(salt, blob, ITERACIONES)
    progress_bar_advanced(2.5, label=t["gen_label"])
    print()

    # 5) Ofuscar el launcher resultante
    spinner("Aplicando ofuscacion extrema...", 0.4)
    try:
        ps1_text = ExtremeObfuscator().obfuscate(ps1_text)
    except Exception as e:
        pline(f"  {tc('warn')}! Ofuscacion fallo: {e} — se guarda sin ofuscar.{RST}")
    progress_bar_advanced(3.0, label=t["gen_obf"])
    print()

    # 6) Guardar en Escritorio como <stem>_cifrado.ps1
    destino = carpeta_escritorio()
    destino.mkdir(parents=True, exist_ok=True)
    nombre_salida = src.stem + "_cifrado.ps1"
    ruta = destino / nombre_salida
    write_text_with_bom(ruta, ps1_text)

    # 7) Exito
    header(t["success_title"])
    print(f"  {tc('ok')}✓{RST} {t['success_file']}: {BOLD}{ruta}{RST}")
    print()
    print(f"  {tc('primary')}{t['how_run']}:{RST}")
    print(f"    {tc('dim')}1){RST} cd \"{destino}\"")
    print(f"    {tc('dim')}2){RST} .\\{nombre_salida} MiContrasena")
    print(f"    {tc('dim')}o){RST} .\\{nombre_salida}   {tc('dim')}{t['how_run_secure']}{RST}")
    print()
    print(f"  {tc('warn')}{t['security_title']}:{RST}")
    for k in ("sec1","sec2","sec3","sec4","sec5","sec6"):
        val = t[k].format(iter=ITERACIONES) if "{iter}" in t[k] else t[k]
        print(f"    {tc('ok')}•{RST} {val}")
    print()
    input(f"  {tc('dim')}{t['press']}{RST}")

def flujo_ofuscar(lang):
    t = TX[lang]
    clear()
    header(t["obf_in_title"])
    while True:
        p = ask(t["obf_in_ask"]).strip().strip('"').strip("'")
        src = Path(p).expanduser().resolve()
        if src.is_file() and src.suffix.lower() == ".ps1":
            source = read_text_no_bom(src)
            print()
            print(f"  {tc('ok')}✓{RST} {t['obf_in_ok']}: {src}")
            time.sleep(0.4)
            break
        pline(f"  {tc('err')}✗ {t['obf_in_err']}{RST}")

    print()
    out_str = ask(t["obf_out_ask"]).strip().strip('"').strip("'")
    if out_str:
        out = Path(out_str).expanduser()
        if out.suffix.lower() != ".ps1":
            out = out.with_suffix(".ps1")
    else:
        out = src.with_name(src.stem + "_obf.ps1")
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        out = Path.cwd() / out.name
    print()
    print(f"  {tc('ok')}✓{RST} {t['obf_out_ok']}: {out}")
    time.sleep(0.3)

    clear()
    corner_box(t["obf_title"])
    for i, label in enumerate(t["obf_layers"], 1):
        progress_bar_advanced(0.7 + random.uniform(0.1, 0.35),
                              label=f"[{i}/8] {label}")

    try:
        result = ExtremeObfuscator().obfuscate(source)
        write_text_with_bom(out, result)
    except Exception as e:
        pline(f"  {tc('err')}✗ {e}{RST}")
        input(f"  {tc('dim')}{t['press']}{RST}")
        return

    clear()
    corner_box(t["obf_success"])
    print(f"  {tc('ok')}✓{RST} {out.resolve()}")
    print()
    pulse_line()
    orig = len(source.encode("utf-8"))
    new  = len(result.encode("utf-8"))
    print(f"  {tc('primary')}{t['obf_stats']}:{RST}")
    print(f"    {tc('dim')}{t['obf_orig']:<18}{RST} {tc('text')}{orig:,} bytes{RST}")
    print(f"    {tc('dim')}{t['obf_new']:<18}{RST} {tc('text')}{new:,} bytes{RST}")
    print(f"    {tc('dim')}{t['obf_ratio']:<18}{RST} {tc('text')}{(new/orig if orig else 0):.2f}x{RST}")
    print()
    input(f"  {tc('dim')}{t['press']}{RST}")

def flujo_proteger_tool(lang):
    t = TX[lang]
    clear()
    header(t["tool_title"])

    this_file = None
    try:
        this_file = Path(__file__).resolve()
    except Exception:
        pass
    if not this_file or this_file.suffix.lower() != ".py" or not this_file.is_file():
        pline(f"  {tc('err')}✗ {t['tool_notpy']}{RST}")
        input(f"  {tc('dim')}{t['press']}{RST}")
        return

    src_text = read_text_no_bom(this_file)
    if "_BLOB = base64.b64decode" in src_text and "_SALT = base64.b64decode" in src_text:
        pline(f"  {tc('err')}✗ {t['tool_already']}{RST}")
        input(f"  {tc('dim')}{t['press']}{RST}")
        return

    pline(f"  {tc('warn')}⚠{RST} {t['tool_warn']}")
    print()

    sys.stdout.write(f"  {tc('primary')}❯{RST} {tc('text')}{t['tool_pwd']}:{RST} ")
    sys.stdout.flush()
    p1 = getpass.getpass("")
    if len(p1) < MIN_LEN:
        pline(f"  {tc('err')}✗ Minimo {MIN_LEN}{RST}")
        input(f"  {tc('dim')}{t['press']}{RST}"); return
    sys.stdout.write(f"  {tc('primary')}❯{RST} {tc('text')}{t['tool_conf']}:{RST} ")
    sys.stdout.flush()
    p2 = getpass.getpass("")
    if p1 != p2:
        pline(f"  {tc('err')}✗ No coinciden{RST}")
        input(f"  {tc('dim')}{t['press']}{RST}"); return

    out_name = ask(t["tool_out"]).strip()
    if out_name:
        out = Path(out_name).expanduser()
        if out.suffix.lower() != ".py":
            out = out.with_suffix(".py")
    else:
        out = this_file.with_name(this_file.stem + "_protected.py")

    print()
    spinner("Cifrando la tool...", 0.6)
    salt, blob = encrypt_payload(src_text, p1, ITERACIONES)
    bootstrap = (BOOTSTRAP_PY
                 .replace("{SALT}",    base64.b64encode(salt).decode("ascii"))
                 .replace("{ITER}",    str(ITERACIONES))
                 .replace("{PAYLOAD}", base64.b64encode(blob).decode("ascii")))
    out.write_text(bootstrap, encoding="utf-8")
    progress_bar_advanced(1.5, label="EMPAQUETANDO")
    print()

    corner_box(t["tool_ok"])
    print(f"  {tc('ok')}✓{RST} {out.resolve()}")
    print()
    input(f"  {tc('dim')}{t['press']}{RST}")

# ─── Main ─────────────────────────────────────────────────
def main():
    global TH
    lang = elegir_idioma()
    TH   = THEMES[elegir_tema(lang)]
    mostrar_bienvenida(lang)

    while True:
        op = menu_principal(lang)
        if op == "0":
            clear()
            typewrite_fade("  " + TX[lang]["exit"], 0.02)
            time.sleep(0.4)
            return
        if op == "1":
            flujo_generar(lang, ofuscar=True)
        elif op == "2":
            flujo_generar(lang, ofuscar=False)
        elif op == "3":
            flujo_cifrar_existente(lang)
        elif op == "4":
            flujo_ofuscar(lang)
        elif op == "5":
            flujo_proteger_tool(lang)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n  {tc('err')}✗ Cancelado.{RST}")
        sys.exit(1)