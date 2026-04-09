#!/bin/bash
set -e
cd ~/Downloads/fw_clean

sudo mksquashfs squashfs-root new_rootfs.squashfs \
  -comp lzo -Xalgorithm lzo1x_999 -Xcompression-level 9 \
  -b 131072 -noappend -no-progress \
  -mkfs-time "2026-01-15 20:45:38"

NEW_MD5=$(md5sum new_rootfs.squashfs | awk '{print $1}')
NEW_SIZE=$(stat -c%s new_rootfs.squashfs)
echo "MD5: $NEW_MD5"
echo "Size: $NEW_SIZE"

CHUNK_SIZE=520997
rm -rf chunks_new && mkdir -p chunks_new
split -b $CHUNK_SIZE new_rootfs.squashfs chunks_new/chunk.

REASSEMBLED_MD5=$(cat $(ls chunks_new/chunk.* | sort) | md5sum | awk '{print $1}')
if [ "$REASSEMBLED_MD5" != "$NEW_MD5" ]; then
  echo "ERROR: chunk mismatch!"; exit 1
fi
echo "Chunks verified OK"

rm -rf ota_v0_new iso_root
cp -r ota_v0_stock ota_v0_new
sudo chmod -R u+w ota_v0_new
sed -i "s/img_md5=f03921029e7451e91ad4fb01b49cdf24/img_md5=$NEW_MD5/" ota_v0_new/ota_update.in
sed -i "s/img_size=33824768/img_size=$NEW_SIZE/" ota_v0_new/ota_update.in

rm -f ota_v0_new/rootfs.squashfs.*
prev_md5=$NEW_MD5
i=0
for f in $(ls chunks_new/chunk.* | sort); do
  num=$(printf "%04d" $i)
  cp "$f" "ota_v0_new/rootfs.squashfs.$num.$prev_md5"
  prev_md5=$(md5sum "$f" | awk '{print $1}')
  let i=i+1
done
echo "Chunks: $(ls ota_v0_new/rootfs.squashfs.* | wc -l)"

rm ota_v0_new/ota_md5_rootfs.squashfs.*
for f in $(ls chunks_new/chunk.* | sort); do
  md5sum "$f" | awk '{print $1}'
done > ota_v0_new/ota_md5_rootfs.squashfs.$NEW_MD5

mkdir -p iso_root
cp ota_config.in iso_root/
cp -r ota_v0_new iso_root/ota_v0
xorriso -as mkisofs -V CDROM -J -r -o r3proii-v1.4-hmod.upt iso_root/

echo "Done: $(md5sum r3proii-v1.4-hmod.upt)"
sha256sum r3proii-v1.4-hmod.upt
