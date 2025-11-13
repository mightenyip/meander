#!/usr/bin/env python3
"""
Test script for character variant normalization
Tests V.O., O.S., CONT'D, and #2 variants
"""

import json
from pathlib import Path
from script_parser import FDXParser, ReportGenerator


def test_character_variants(file_path: str):
    """Test character variant normalization"""
    print(f"Testing character variants with: {file_path}")
    print("=" * 70)
    
    # Parse the script
    parser = FDXParser(file_path)
    script_data = parser.parse()
    
    print(f"\n📊 Parsing Results:")
    print(f"  Total scenes: {script_data.total_scenes}")
    print(f"  Total characters (after normalization): {len(script_data.characters)}")
    
    # Show raw character names found
    print(f"\n🔍 Character Variants Found (before normalization):")
    print(f"  Note: The parser stores raw character names as they appear in the script")
    
    # Show character normalization
    print(f"\n👥 Character Normalization Results:")
    for char_name, char in sorted(script_data.characters.items()):
        print(f"\n  Character: {char.name_canonical}")
        print(f"    - Raw name: {char.name_raw}")
        print(f"    - Canonical name: {char.name_canonical}")
        print(f"    - Total lines: {char.total_lines}")
        print(f"    - Dialogue count: {char.dialogue_count}")
        print(f"    - Scenes: {char.scenes}")
        print(f"    - First appearance: Scene {char.first_appearance}")
        print(f"    - Last appearance: Scene {char.last_appearance}")
    
    # Show scenes with character variants
    print(f"\n📽️  Scenes with Character Variants:")
    for scene in script_data.scenes:
        print(f"\n  Scene {scene.scene_number}: {scene.slug_line}")
        print(f"    Characters in scene (raw names): {', '.join(scene.characters)}")
        # Show which variants appeared
        variants = []
        for char in scene.characters:
            variants.append(char)
        print(f"    Variants found: {variants}")
    
    # Verify normalization
    print(f"\n✅ Normalization Verification:")
    
    # Check if V.O., O.S., CONT'D variants are merged
    has_vo = False
    has_os = False
    has_contd = False
    has_number = False
    
    for scene in script_data.scenes:
        for char_name in scene.characters:
            if '(V.O.)' in char_name.upper():
                has_vo = True
            if '(O.S.)' in char_name.upper():
                has_os = True
            if "(CONT'D)" in char_name.upper() or "(CONT'D)" in char_name.upper():
                has_contd = True
            if '#' in char_name:
                has_number = True
    
    print(f"  V.O. variant found: {has_vo}")
    print(f"  O.S. variant found: {has_os}")
    print(f"  CONT'D variant found: {has_contd}")
    print(f"  #2 variant found: {has_number}")
    
    # Check if variants are merged correctly
    if len(script_data.characters) == 1:
        main_char = list(script_data.characters.values())[0]
        if main_char.name_canonical == "JOHN DOE":
            print(f"\n  ✓ All variants normalized to: {main_char.name_canonical}")
            print(f"  ✓ Total lines across all variants: {main_char.total_lines}")
            print(f"  ✓ Appears in {len(main_char.scenes)} scenes")
            
            # Verify all scenes are tracked
            expected_scenes = list(range(1, script_data.total_scenes + 1))
            if main_char.scenes == expected_scenes:
                print(f"  ✓ All scenes tracked correctly: {main_char.scenes}")
            else:
                print(f"  ✗ Scene tracking mismatch: {main_char.scenes} vs {expected_scenes}")
        else:
            print(f"  ✗ Unexpected canonical name: {main_char.name_canonical}")
    else:
        print(f"\n  ⚠ Multiple characters found: {len(script_data.characters)}")
        print(f"     This might indicate that '#2' should be treated as a separate character")
        for char_name, char in script_data.characters.items():
            print(f"     - {char.name_canonical}")
    
    # Generate detailed report
    print(f"\n📄 Generating detailed report...")
    report_gen = ReportGenerator(script_data)
    output_dir = Path("test_variants_detailed")
    output_dir.mkdir(exist_ok=True)
    
    json_path = output_dir / "variants_report.json"
    report_gen.generate_json(str(json_path))
    print(f"  ✓ Generated: {json_path}")
    
    print(f"\n" + "=" * 70)
    print("✅ Test complete!")
    
    return script_data


if __name__ == "__main__":
    import sys
    
    file_path = "samples/test_script_variants.fdx"
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    
    if not Path(file_path).exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    
    test_character_variants(file_path)


