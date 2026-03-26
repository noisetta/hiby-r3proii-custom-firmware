#!/usr/bin/env python3
"""
merge_arabic_font.py
====================
Merges Arabic Unicode glyphs from Noto Naskh Arabic into HiBy's Thai.ttf
font file, enabling Arabic text rendering on the HiBy R3 Pro II.

Usage:
    python3 merge_arabic_font.py <thai_ttf> <arabic_ttf> <output_ttf>

Example:
    python3 merge_arabic_font.py Thai.ttf NotoNaskhArabic-Regular.ttf thai_arabic.ttf

Requirements:
    sudo apt install fontforge python3-fontforge
"""

import sys
import os
import tempfile

try:
    import fontforge
except ImportError:
    print("ERROR: fontforge Python module not found")
    print("Install with: sudo apt install python3-fontforge")
    sys.exit(1)


def merge_arabic_into_thai(thai_path, arabic_path, output_path):
    """
    Merge Arabic glyphs from Noto Naskh Arabic into Thai.ttf.
    
    The HiBy R3 Pro II uses Thai.ttf as a fallback font for unknown scripts.
    By adding Arabic glyphs to this font, Arabic text renders correctly
    throughout the OS without modifying any binaries.
    
    Key technical details:
    - Thai.ttf has em size 2560
    - Noto Naskh Arabic has em size 1000  
    - Arabic glyphs must be scaled by 2560/1000 = 2.56 to match Thai's metrics
    - Arabic TTF must be converted to CFF format first to avoid outline type mismatch
    """
    
    print(f"Input Thai font:   {thai_path}")
    print(f"Input Arabic font: {arabic_path}")
    print(f"Output font:       {output_path}")
    print()

    # Step 1: Convert Arabic TTF to CFF format
    # This is necessary because Thai.ttf uses CFF outlines and mixing
    # TrueType quadratic beziers with CFF cubic beziers causes issues
    print("Step 1: Converting Arabic TTF to CFF format...")
    with tempfile.NamedTemporaryFile(suffix='.otf', delete=False) as tmp:
        arabic_cff_path = tmp.name

    arabic_src = fontforge.open(arabic_path)
    arabic_src.is_quadratic = False  # Convert to cubic beziers (CFF style)
    arabic_src.generate(arabic_cff_path, flags=("opentype",))
    arabic_src.close()
    print(f"  CFF font size: {os.path.getsize(arabic_cff_path)} bytes")

    # Step 2: Open the Thai base font
    print("Step 2: Opening Thai base font...")
    base = fontforge.open(thai_path)
    thai_em = base.em
    print(f"  Thai glyphs: {len(list(base.glyphs()))}")
    print(f"  Thai em size: {thai_em}")

    # Step 3: Open the converted Arabic font
    print("Step 3: Opening converted Arabic font...")
    arabic = fontforge.open(arabic_cff_path)
    arabic_em = arabic.em
    print(f"  Arabic em size: {arabic_em}")

    # Calculate scale factor to match Thai's em size
    scale = thai_em / arabic_em
    print(f"  Scale factor: {scale:.4f}")

    # Step 4: Copy Arabic glyphs (U+0600 to U+06FF)
    print("Step 4: Copying Arabic glyphs...")
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

    # Step 5: Scale Arabic glyphs to match Thai's em size
    print("Step 5: Scaling Arabic glyphs...")
    scaled = 0
    for glyph in base.glyphs():
        if 0x0600 <= glyph.unicode <= 0x06FF:
            glyph.transform((scale, 0, 0, scale, 0, 0))
            scaled += 1
    print(f"  Scaled {scaled} glyphs by {scale:.4f}x")

    # Step 6: Verify
    print("Step 6: Verifying...")
    arabic_in_base = [g for g in base.glyphs() if 0x0600 <= g.unicode <= 0x06FF]
    thai_in_base = [g for g in base.glyphs() if 0x0E00 <= g.unicode <= 0x0E7F]
    print(f"  Arabic glyphs in merged font: {len(arabic_in_base)}")
    print(f"  Thai glyphs preserved: {len(thai_in_base)}")
    print(f"  Total glyphs: {len(list(base.glyphs()))}")

    # Step 7: Generate output
    print("Step 7: Saving merged font...")
    base.generate(output_path)
    base.close()
    arabic.close()

    # Cleanup temp file
    os.unlink(arabic_cff_path)

    original_size = os.path.getsize(thai_path)
    output_size = os.path.getsize(output_path)
    print(f"  Original Thai size: {original_size:,} bytes")
    print(f"  Merged font size:   {output_size:,} bytes")
    print(f"  Size increase:      {output_size - original_size:,} bytes")
    print()
    print("Done! Arabic glyphs successfully merged into Thai font.")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)

    thai_path = sys.argv[1]
    arabic_path = sys.argv[2]
    output_path = sys.argv[3]

    for path in [thai_path, arabic_path]:
        if not os.path.exists(path):
            print(f"ERROR: File not found: {path}")
            sys.exit(1)

    merge_arabic_into_thai(thai_path, arabic_path, output_path)
