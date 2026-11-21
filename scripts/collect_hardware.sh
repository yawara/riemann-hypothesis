#!/usr/bin/env bash
# 検証に使ったハードウェア/OS/ツールの情報を採取する(GPU は検証に無関係なので採取しない)。
# 使い方: scripts/collect_hardware.sh > verification/hardware.txt
set -u
export LC_ALL=C

echo "# collected_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo
echo "## CPU"
lscpu | grep -E '^(Architecture|CPU op-mode|Address sizes|Byte Order|CPU\(s\)|On-line CPU|Vendor ID|Model name|CPU family|Model|Stepping|Thread\(s\) per core|Core\(s\) per socket|Socket\(s\)|CPU max MHz|CPU min MHz|L1d cache|L1i cache|L2 cache|L3 cache|NUMA node\(s\)|NUMA node[0-9]+ CPU)'
echo
echo "## Memory"
grep -E '^(MemTotal|SwapTotal|Hugepagesize)' /proc/meminfo
free -h | sed -n '1,3p'
echo
echo "## Motherboard (DMI)"
for f in sys_vendor product_name board_vendor board_name bios_vendor bios_version bios_date; do
  printf '%s: %s\n' "$f" "$(cat /sys/class/dmi/id/$f 2>/dev/null || echo n/a)"
done
echo
echo "## Storage (block devices, loop devices omitted)"
lsblk -d -o NAME,MODEL,SIZE,ROTA,TRAN 2>/dev/null | grep -v '^loop'
echo
echo "## Filesystems used by this verification"
df -hT "$(dirname "$0")/.." /var/tmp 2>/dev/null
echo
echo "## OS"
grep -E '^(PRETTY_NAME|VERSION_ID)=' /etc/os-release
uname -srvm
echo
echo "## Tools"
echo "elan: $(elan --version 2>/dev/null | head -1)"
echo "git: $(git --version)"
echo "curl: $(curl --version | head -1)"
echo "tar: $(tar --version | head -1)"
echo "gzip: $(gzip --version | head -1)"
echo "sha256sum: $(sha256sum --version | head -1)"
echo "pdftotext: $(pdftotext -v 2>&1 | head -1)"
echo "ripgrep: $(rg --version 2>/dev/null | head -1)"
echo "python3: $(python3 --version 2>&1)"
