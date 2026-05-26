#!/bin/bash
# Kali CTF/Pentest Toolchain Setup — full version with sudo

SUDO_PASS="123456"
SUDO="echo '$SUDO_PASS' | sudo -S"

set -e

echo "[+] Updating system..."
$SUDO apt-get update

echo "[+] Installing system tools..."
$SUDO apt-get install -y \
    build-essential git wget curl \
    python3 python3-pip python3-venv \
    openssh-server \
    gdb gdbserver gdb-multiarch \
    radare2 \
    binwalk \
    strace ltrace \
    john hashcat \
    nmap \
    binutils \
    qemu-user-static qemu-system \
    libffi-dev libssl-dev \
    unzip

echo "[+] Creating Python venv..."
VENV_DIR="$HOME/ctf-tools"
python3 -m venv "$VENV_DIR" --system-site-packages
source "$VENV_DIR/bin/activate"

echo "[+] Upgrading pip..."
pip install -U pip setuptools wheel

echo "[+] Installing Python frameworks..."
pip install -U \
    angr claripy \
    pwntools \
    lief \
    capstone keystone-engine unicorn \
    qiling \
    frida-tools \
    r2pipe \
    ropgadget ropper \
    z3-solver \
    pycryptodome gmpy2 owiener \
    requests \
    numpy

echo "[+] Installing RsaCtfTool..."
pip install -U git+https://github.com/RsaCtfTool/RsaCtfTool.git || echo "[!] RsaCtfTool install failed"

echo "[+] Installing SageMath..."
$SUDO apt-get install -y sagemath || echo "[!] SageMath install failed"

echo "[+] Installing Ghidra (headless)..."
GHIDRA_VER="11.2.1"
GHIDRA_ZIP="ghidra_${GHIDRA_VER}_PUBLIC_20241105.zip"
GHIDRA_URL="https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_${GHIDRA_VER}_build/${GHIDRA_ZIP}"

if [ ! -d "/opt/ghidra_${GHIDRA_VER}_PUBLIC" ]; then
    cd /opt
    if [ ! -f "$GHIDRA_ZIP" ]; then
        $SUDO wget -q --show-progress "$GHIDRA_URL" -O "$GHIDRA_ZIP" || echo "[!] Ghidra download failed"
    fi
    if [ -f "$GHIDRA_ZIP" ]; then
        $SUDO unzip -q "$GHIDRA_ZIP" || true
        $SUDO rm -f "$GHIDRA_ZIP"
        $SUDO ln -sf "/opt/ghidra_${GHIDRA_VER}_PUBLIC/support/analyzeHeadless" /usr/local/bin/ghidra-headless
        echo "[+] Ghidra installed"
    fi
else
    echo "[+] Ghidra already installed"
fi

echo "[+] Verifying core installations..."
python -c "import angr; print('  angr:', angr.__version__)" 2>/dev/null || echo "  [!] angr check failed"
python -c "import pwnlib; print('  pwntools: OK')" 2>/dev/null || echo "  [!] pwntools check failed"
python -c "import r2pipe; print('  r2pipe: OK')" 2>/dev/null || echo "  [!] r2pipe check failed"
python -c "import z3; print('  z3: OK')" 2>/dev/null || echo "  [!] z3 check failed"
r2 -v 2>/dev/null || echo "  [!] radare2 check failed"
ghidra-headless | head -1 2>/dev/null || echo "  [!] Ghidra check failed"

echo ""
echo "[+] Done! Kali is fully ready for AI agent operations."
