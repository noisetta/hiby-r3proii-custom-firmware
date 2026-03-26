#!/bin/bash
# =============================================================================
# HiBy R3 Pro II Custom Firmware Builder
# =============================================================================
# Tested on firmware version: current_version=0 (January 2026)
# Host OS: Ubuntu / Pop!_OS (Linux)
#
# Usage: ./build_upt.sh <path_to_stock_upt> <output_upt>
# Example: ./build_upt.sh firmware/r3proii_stock.upt firmware/r3proii-arabic.upt
#
# Requirements: squashfs-tools, xorriso, fontforge, python3-fontforge
# Install: sudo apt install squashfs-tools xorriso fontforge python3-fontforge
# =============================================================================

set -e

STOCK_UPT="$1"
OUTPUT_UPT="${2:-r3proii-custom.upt}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKDIR="$(mktemp -d)"

# Noto Naskh Arabic font - download if not present
ARABIC_FONT="$SCRIPT_DIR/../fonts/NotoNaskhArabic-Regular.ttf"

echo "============================================="
echo " HiBy R3 Pro II Custom Firmware Builder"
echo "============================================="
echo "Stock UPT:    $STOCK_UPT"
echo "Output UPT:   $OUTPUT_UPT"
echo "Work dir:     $WORKDIR"
echo ""

# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------
if [ -z "$STOCK_UPT" ]; then
    echo "ERROR: No stock UPT specified"
    echo "Usage: $0 <path_to_stock_upt> <output_upt>"
    exit 1
fi

if [ ! -f "$STOCK_UPT" ]; then
    echo "ERROR: Stock UPT not found: $STOCK_UPT"
    exit 1
fi

if [ ! -f "$ARABIC_FONT" ]; then
    echo "ERROR: Arabic font not found at: $ARABIC_FONT"
    echo "Download Noto Naskh Arabic from: https://fonts.google.com/noto/specimen/Noto+Naskh+Arabic"
    echo "Place NotoNaskhArabic-Regular.ttf in the fonts/ directory"
    exit 1
fi

for cmd in unsquashfs mksquashfs xorriso python3 md5sum; do
    if ! command -v $cmd &> /dev/null; then
        echo "ERROR: Required command not found: $cmd"
        echo "Install with: sudo apt install squashfs-tools xorriso python3-fontforge"
        exit 1
    fi
done

# -----------------------------------------------------------------------------
# Step 1: Extract stock firmware
# -----------------------------------------------------------------------------
echo "[1/7] Extracting stock firmware..."
sudo mkdir -p /mnt/upt_build
sudo mount -o loop,ro "$STOCK_UPT" /mnt/upt_build

# Reassemble rootfs from chunks
echo "  Reassembling rootfs from chunks..."
cat $(ls /mnt/upt_build/ota_v0/rootfs.squashfs.*.* | sort) > "$WORKDIR/stock_rootfs.squashfs"
STOCK_MD5=$(md5sum "$WORKDIR/stock_rootfs.squashfs" | awk '{print $1}')
echo "  Stock rootfs MD5: $STOCK_MD5"

# Copy OTA structure
cp /mnt/upt_build/ota_config.in "$WORKDIR/"
cp -r /mnt/upt_build/ota_v0 "$WORKDIR/ota_v0_stock"
sudo umount /mnt/upt_build
echo "  Done"

# -----------------------------------------------------------------------------
# Step 2: Extract squashfs
# -----------------------------------------------------------------------------
echo "[2/7] Extracting squashfs filesystem..."
sudo unsquashfs -d "$WORKDIR/squashfs-root" "$WORKDIR/stock_rootfs.squashfs"
echo "  Done"

# -----------------------------------------------------------------------------
# Step 3: Merge Arabic font into Thai.ttf
# -----------------------------------------------------------------------------
echo "[3/7] Merging Arabic font into Thai.ttf..."

# First convert Arabic TTF to CFF format
python3 << PYEOF
import fontforge
import os
import sys

arabic_font_path = "$ARABIC_FONT"
thai_font_path = "$WORKDIR/squashfs-root/usr/resource/fonts/Thai.ttf"
output_path = "$WORKDIR/thai_arabic.ttf"
arabic_cff_path = "$WORKDIR/arabic_cff.otf"

# Step 3a: Convert Arabic TTF to CFF
print("  Converting Arabic TTF to CFF format...")
arabic = fontforge.open(arabic_font_path)
arabic.is_quadratic = False
arabic.generate(arabic_cff_path, flags=("opentype",))
arabic.close()
print(f"  Arabic CFF size: {os.path.getsize(arabic_cff_path)} bytes")

# Step 3b: Open stock Thai font
print("  Opening stock Thai font...")
base = fontforge.open(thai_font_path)
thai_em = base.em
print(f"  Thai em size: {thai_em}")

# Step 3c: Open converted Arabic font
arabic = fontforge.open(arabic_cff_path)
arabic_em = arabic.em
print(f"  Arabic em size: {arabic_em}")
scale = thai_em / arabic_em
print(f"  Scale factor: {scale:.3f}")

# Step 3d: Copy Arabic glyphs
base.encoding = "UnicodeFull"
count = 0
for glyph in arabic.glyphs():
    if 0x0600 <= glyph.unicode <= 0x06FF:
        arabic.selection.select(glyph.unicode)
        arabic.copy()
        base.selection.select(glyph.unicode)
        base.paste()
        count += 1

print(f"  Copied {count} Arabic glyphs")

# Step 3e: Scale Arabic glyphs to match Thai em size
if scale != 1.0:
    for glyph in base.glyphs():
        if 0x0600 <= glyph.unicode <= 0x06FF:
            glyph.transform((scale, 0, 0, scale, 0, 0))
    print(f"  Scaled Arabic glyphs by {scale:.3f}x")

# Step 3f: Verify
verify = [g for g in base.glyphs() if 0x0600 <= g.unicode <= 0x06FF]
print(f"  Verified {len(verify)} Arabic glyphs in merged font")
print(f"  Total glyphs: {len(list(base.glyphs()))}")

# Step 3g: Save
base.generate(output_path)
base.close()
arabic.close()

print(f"  Original Thai: {os.path.getsize(thai_font_path)} bytes")
print(f"  New combined:  {os.path.getsize(output_path)} bytes")
print("  Font merge complete")
PYEOF

# Install merged font
sudo cp "$WORKDIR/thai_arabic.ttf" "$WORKDIR/squashfs-root/usr/resource/fonts/Thai.ttf"
echo "  Done"

# -----------------------------------------------------------------------------
# Step 4: Repack squashfs
# -----------------------------------------------------------------------------
echo "[4/7] Repacking squashfs..."
sudo mksquashfs "$WORKDIR/squashfs-root" "$WORKDIR/new_rootfs.squashfs" \
  -comp lzo -Xalgorithm lzo1x_999 -Xcompression-level 9 \
  -b 131072 -noappend -no-progress \
  -mkfs-time "2026-01-15 20:45:38"

NEW_MD5=$(md5sum "$WORKDIR/new_rootfs.squashfs" | awk '{print $1}')
NEW_SIZE=$(stat -c%s "$WORKDIR/new_rootfs.squashfs")
echo "  New rootfs MD5:  $NEW_MD5"
echo "  New rootfs size: $NEW_SIZE bytes"
echo "  Done"

# -----------------------------------------------------------------------------
# Step 5: Generate chunks with correct chain naming
# -----------------------------------------------------------------------------
echo "[5/7] Generating firmware chunks..."
CHUNK_SIZE=520997
mkdir -p "$WORKDIR/chunks"
split -b $CHUNK_SIZE "$WORKDIR/new_rootfs.squashfs" "$WORKDIR/chunks/chunk."

# Verify chunk reassembly
REASSEMBLED_MD5=$(cat $(ls "$WORKDIR/chunks/chunk."* | sort) | md5sum | awk '{print $1}')
if [ "$REASSEMBLED_MD5" != "$NEW_MD5" ]; then
    echo "ERROR: Chunk reassembly MD5 mismatch!"
    echo "  Expected: $NEW_MD5"
    echo "  Got:      $REASSEMBLED_MD5"
    exit 1
fi
echo "  Chunk verification: OK"

# Build OTA v0 directory
sudo chmod -R u+w "$WORKDIR/ota_v0_stock"
cp -r "$WORKDIR/ota_v0_stock" "$WORKDIR/ota_v0_new"

# Update ota_update.in
sed -i "s/img_md5=$STOCK_MD5/img_md5=$NEW_MD5/" "$WORKDIR/ota_v0_new/ota_update.in"
sed -i "s/img_size=[0-9]*/img_size=$NEW_SIZE/" "$WORKDIR/ota_v0_new/ota_update.in" 

# Remove old rootfs chunks and manifest
rm -f "$WORKDIR/ota_v0_new/rootfs.squashfs."*
rm -f "$WORKDIR/ota_v0_new/ota_md5_rootfs.squashfs."*

# Create new chunks with chain naming
prev_md5=$NEW_MD5
i=0
for f in $(ls "$WORKDIR/chunks/chunk."* | sort); do
    num=$(printf "%04d" $i)
    cp "$f" "$WORKDIR/ota_v0_new/rootfs.squashfs.$num.$prev_md5"
    prev_md5=$(md5sum "$f" | awk '{print $1}')
    let i=i+1
done
CHUNK_COUNT=$(ls "$WORKDIR/ota_v0_new/rootfs.squashfs."* | wc -l)
echo "  Created $CHUNK_COUNT chunks"

# Generate manifest (MD5 of each chunk's content in order)
for f in $(ls "$WORKDIR/chunks/chunk."* | sort); do
    md5sum "$f" | awk '{print $1}'
done > "$WORKDIR/ota_v0_new/ota_md5_rootfs.squashfs.$NEW_MD5"
echo "  Generated manifest with $CHUNK_COUNT entries"
echo "  Done"

# -----------------------------------------------------------------------------
# Step 6: Package as ISO
# -----------------------------------------------------------------------------
echo "[6/7] Packaging as ISO..."
mkdir -p "$WORKDIR/iso_root"
cp "$WORKDIR/ota_config.in" "$WORKDIR/iso_root/"
cp -r "$WORKDIR/ota_v0_new" "$WORKDIR/iso_root/ota_v0"

xorriso -as mkisofs -V CDROM -o "$WORKDIR/output.upt" "$WORKDIR/iso_root/" 2>/dev/null

# Verify ISO structure
sudo mount -o loop,ro "$WORKDIR/output.upt" /mnt/upt_build
if [ ! -f "/mnt/upt_build/ota_config.in" ] || [ ! -d "/mnt/upt_build/ota_v0" ]; then
    sudo umount /mnt/upt_build
    echo "ERROR: ISO structure verification failed"
    exit 1
fi
sudo umount /mnt/upt_build
echo "  ISO structure verified: OK"
echo "  Done"

# -----------------------------------------------------------------------------
# Step 7: Copy output
# -----------------------------------------------------------------------------
echo "[7/7] Copying output..."
cp "$WORKDIR/output.upt" "$OUTPUT_UPT"
OUTPUT_MD5=$(md5sum "$OUTPUT_UPT" | awk '{print $1}')
OUTPUT_SIZE=$(stat -c%s "$OUTPUT_UPT")

# Cleanup
rm -rf "$WORKDIR"

echo ""
echo "============================================="
echo " Build Complete!"
echo "============================================="
echo "Output file: $OUTPUT_UPT"
echo "MD5:         $OUTPUT_MD5"
echo "Size:        $OUTPUT_SIZE bytes"
echo ""
echo "To flash:"
echo "  1. Copy $OUTPUT_UPT to SD card root as r3proii.upt"
echo "  2. Insert SD card into HiBy R3 Pro II"
echo "  3. Hold Volume Up + press Power to enter updater"
echo "  4. Wait for 'Succeeded' then remove SD card before reboot"
echo "============================================="
