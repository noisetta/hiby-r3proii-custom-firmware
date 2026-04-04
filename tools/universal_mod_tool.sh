#!/bin/bash

# Stop the script in case of critical errors
set -e

export COLUMNS=1

# --- TERMINAL COLORS ---
RED='\033[1;31m'
GREEN='\033[1;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No color

# Set green color to answer prompt
PS3=$'\033[1;32mEnter your choice (number): \033[0m'

# --- Add homebrew path for macOS ---
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

# ==========================================
# FOLDER MANAGEMENT
# ==========================================
# Identify the script folder (tools) and the root folder (one layer above)
TOOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
PROJECT_DIR="$(cd "$TOOL_DIR/.." >/dev/null 2>&1 && pwd)"

# External working DIRs
FIRMWARE_DIR="$PROJECT_DIR/Firmware"
BINARIES_DIR="$PROJECT_DIR/Binaries"
THEMES_DIR="$PROJECT_DIR/Themes"
WORK_DIR="$PROJECT_DIR/temp"
OUT_DIR="$WORK_DIR/ota_v0"
SQUASH_DIR="$PROJECT_DIR/squashfs-root"

echo -e "${BLUE}#############################################${NC}"
echo -e "${BLUE}###   HIBYOS FIRMWARE MODDER & REPACKER   ###${NC}"
echo -e "${BLUE}#############################################${NC}"
echo ""

# --- INDEPENDENT MAC/LINUX COMPATIBILITY ---
if command -v md5sum >/dev/null 2>&1; then
    get_md5() { md5sum "$1" | awk '{print $1}'; }
else
    get_md5() { md5 -q "$1"; }
fi

if stat -c%s . >/dev/null 2>&1; then
    get_size() { stat -c%s "$1"; } 
else
    get_size() { stat -f%z "$1"; } 
fi

# ==========================================
# 1. FIRMWARE SELECTION AND PREPARATION
# ==========================================
echo -e "${GREEN}Which base firmware do you want to use?${NC}"

if [ ! -d "$FIRMWARE_DIR" ]; then
    echo -e "${RED}Error: The 'Firmware' folder does not exist! Please create it in the main directory and place your .upt files inside.${NC}"
    exit 1
fi

# Find .upt files automatically inside firmware folder
OLD_IFS=$IFS; IFS=$'\n'
FW_ARRAY=($(find "$FIRMWARE_DIR" -maxdepth 1 -name "*.upt" -exec basename {} \;))
IFS=$OLD_IFS

if [ ${#FW_ARRAY[@]} -eq 0 ]; then
    echo -e "${RED}Error: No .upt files found in $FIRMWARE_DIR${NC}"
    exit 1
fi

select UPT_FILE in "${FW_ARRAY[@]}"; do
    if [ -n "$UPT_FILE" ] && [ -f "$FIRMWARE_DIR/$UPT_FILE" ]; then
        echo "You selected: $UPT_FILE"
        break
    else
        echo -e "${RED}Invalid selection. Please try again.${NC}"
    fi
done

# Clean up previous operations
rm -rf "$WORK_DIR" "$SQUASH_DIR" "$PROJECT_DIR/rootfs_original.squashfs"
mkdir -p "$WORK_DIR"

echo "Extracting original firmware to temp folder..."
7z x "$FIRMWARE_DIR/$UPT_FILE" -o"$WORK_DIR" -y > /dev/null

echo "Merging original squashfs chunks..."
cd "$OUT_DIR"
cat rootfs.squashfs.* > "$PROJECT_DIR/rootfs_original.squashfs"
cd "$TOOL_DIR"

echo "Extracting filesystem (rootfs)..."
unsquashfs -f -d "$SQUASH_DIR" "$PROJECT_DIR/rootfs_original.squashfs" > /dev/null
rm "$PROJECT_DIR/rootfs_original.squashfs"

echo "Cleaning up old squashfs files from ota_v0 folder..."
rm -f "$OUT_DIR/ota_md5_rootfs.squashfs."*
rm -f "$OUT_DIR/rootfs."*

echo ""

# ==========================================
# 2. PATCHED BINARY SELECTION
# ==========================================
echo -e -n "${GREEN}Do you want to replace the hiby_player binary with a patched one? (y/n): ${NC}"
read PATCH_BIN

if [[ "$PATCH_BIN" =~ ^[Yy]$ ]]; then
    if [ -d "$BINARIES_DIR" ]; then
        echo -e "${GREEN}Select the binary to apply:${NC}"
        
        # Find all the nested folders that contain the file 'hiby_player'
        VALID_BIN_PATHS=()
        VALID_BIN_NAMES=()
        OLD_IFS=$IFS; IFS=$'\n'
        for file in $(find "$BINARIES_DIR" -type f -name "hiby_player" | sort); do
            dir=$(dirname "$file")
            VALID_BIN_PATHS+=("$dir")
            VALID_BIN_NAMES+=("$(basename "$dir")")
        done
        IFS=$OLD_IFS
        
        if [ ${#VALID_BIN_NAMES[@]} -eq 0 ]; then
            echo "No patched 'hiby_player' binaries found in $BINARIES_DIR."
        else
            select BIN_CHOICE in "${VALID_BIN_NAMES[@]}"; do
                if [ -n "$BIN_CHOICE" ]; then
                    INDEX=$((REPLY - 1))
                    BIN_PATH="${VALID_BIN_PATHS[$INDEX]}"
                    
                    echo "Applying binary: $BIN_CHOICE..."
                    cp -a "$BIN_PATH/hiby_player" "$SQUASH_DIR/usr/bin/hiby_player"
                    chmod +x "$SQUASH_DIR/usr/bin/hiby_player"
                    break
                else
                    echo -e "${RED}Invalid selection.${NC}"
                fi
            done
        fi
    else
        echo "Binaries folder not found. Skipping this step."
    fi
fi
echo ""

# ==========================================
# 3. THEME SELECTION
# ==========================================
echo -e -n "${GREEN}Do you want to apply a custom theme? (y/n): ${NC}"
read PATCH_THEME

if [[ "$PATCH_THEME" =~ ^[Yy]$ ]]; then
    if [ -d "$THEMES_DIR" ]; then
        echo -e "${GREEN}Select the theme to apply:${NC}"
        
        VALID_THEME_PATHS=()
        VALID_THEME_NAMES=()
        OLD_IFS=$IFS; IFS=$'\n'
        
        for dir in $(find "$THEMES_DIR" -type d | sort); do
            if [ "$dir" == "$THEMES_DIR" ]; then continue; fi
            
            is_sub=false
            for added in "${VALID_THEME_PATHS[@]}"; do
                if [[ "$dir" == "$added/"* ]] || [[ "$dir" == "$added" ]]; then
                    is_sub=true
                    break
                fi
            done
            
            if [ "$is_sub" == true ]; then continue; fi
            
            # Check if folder contains "usr" o "etc"
            if [ -d "$dir/usr" ] || [ -d "$dir/etc" ]; then
                VALID_THEME_PATHS+=("$dir")
                VALID_THEME_NAMES+=("$(basename "$dir")") # Displayed name
            fi
        done
        IFS=$OLD_IFS
        
        if [ ${#VALID_THEME_NAMES[@]} -eq 0 ]; then
            echo "No valid themes found in $THEMES_DIR."
        else
            select THEME_CHOICE in "${VALID_THEME_NAMES[@]}"; do
                if [ -n "$THEME_CHOICE" ]; then
                    # Retrieve the exact path using the index of the choice
                    INDEX=$((REPLY - 1))
                    THEME_PATH="${VALID_THEME_PATHS[$INDEX]}"
                    
                    echo "Applying theme: $THEME_CHOICE..."
                    cp -a "$THEME_PATH"/* "$SQUASH_DIR/"
                    break
                else
                    echo -e "${RED}Invalid selection.${NC}"
                fi
            done
        fi
    else
        echo "Themes folder not found. Skipping this step."
    fi
fi
echo ""

# ==========================================
# 4. CLEANUP AND SQUASHFS REPACK
# ==========================================
echo -e "${YELLOW}#####################################${NC}"
echo -e "${YELLOW}### GENERATING NEW SQUASHFS FILES ###${NC}"
echo -e "${YELLOW}#####################################${NC}"
echo ""

echo "Cleaning up invisible macOS junk (.DS_Store / ._*)..."
find "$SQUASH_DIR" -name '.DS_Store' -type f -delete 2>/dev/null || true
find "$SQUASH_DIR" -name '._*' -type f -delete 2>/dev/null || true

ROOTFS_NEW="$OUT_DIR/rootfs.squashfs"

echo "Creating new filesystem..."
mksquashfs "$SQUASH_DIR" "$ROOTFS_NEW" -comp lzo -all-root > /dev/null

ORIGINAL_SUM=$(get_md5 "$ROOTFS_NEW")
SIZE=$(get_size "$ROOTFS_NEW")

echo "Updating ota_update.in..."
X_SIZE=$(grep -A 3 'img_name=xImage' "$OUT_DIR/ota_update.in" | grep 'img_size' | cut -d= -f2 | tr -d '\r ' )
X_MD5=$(grep -A 3 'img_name=xImage' "$OUT_DIR/ota_update.in" | grep 'img_md5' | cut -d= -f2 | tr -d '\r ' )

cat > "$OUT_DIR/ota_update.in" <<EOF
ota_version=0

img_type=kernel
img_name=xImage
img_size=$X_SIZE
img_md5=$X_MD5

img_type=rootfs
img_name=rootfs.squashfs
img_size=$SIZE
img_md5=$ORIGINAL_SUM
EOF

echo "Splitting into chunks and creating MD5 chain..."

split -b 524288 -a 4 "$ROOTFS_NEW" "$OUT_DIR/temp_chunk_"
rm "$ROOTFS_NEW"

MD5_FILE="$OUT_DIR/ota_md5_rootfs.squashfs.$ORIGINAL_SUM"
> "$MD5_FILE"

count=0
CURRENT_SUM=$ORIGINAL_SUM

for f in "$OUT_DIR/temp_chunk_"*; do
    [ -e "$f" ] || continue 
    
    suffix=$(printf "%04d" $count)
    
    NEW_FILENAME="$OUT_DIR/rootfs.squashfs.$suffix.$CURRENT_SUM"
    mv "$f" "$NEW_FILENAME"
    
    CURRENT_SUM=$(get_md5 "$NEW_FILENAME")
    
    echo "$CURRENT_SUM" >> "$MD5_FILE"
    
    count=$((count + 1))
done

# ==========================================
# 5. GENERATE FIRMWARE FILE (.upt)
# ==========================================
echo -e "${YELLOW}#################################${NC}"
echo -e "${YELLOW}### GENERATING FIRMWARE FILE  ###${NC}"
echo -e "${YELLOW}#################################${NC}"
echo ""

cd "$PROJECT_DIR"

# Remove the previous r3proii.upt file if it exists
rm -f "r3proii.upt"

# Generate the .upt firmware file
mkisofs -o "r3proii.upt" -J -r ./temp/ > /dev/null 2>&1

rm -rf "$WORK_DIR" "$SQUASH_DIR"

echo ""
echo ""
echo -e "${GREEN}###########################${NC}"
echo -e "${GREEN}### REPACKING COMPLETE! ###${NC}"
echo -e "${GREEN}###########################${NC}"
echo ""
echo "Firmware image saved as r3proii.upt in $PROJECT_DIR"
echo ""
echo -e "${GREEN} --- Ready to be copied to the SD card! --- ${NC}"
echo ""

# ==========================================
# 6. OPEN DESTINATION FOLDER
# ==========================================
echo "Opening destination folder..."
sleep 1

if [ "$(uname)" == "Darwin" ]; then
    open "$PROJECT_DIR"
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$PROJECT_DIR"
else
    echo "Could not open folder automatically. You can find your file in: $PROJECT_DIR"
fi