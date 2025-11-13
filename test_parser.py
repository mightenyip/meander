#!/usr/bin/env python3
"""
Test script for script_parser.py
Validates that the parser correctly extracts data from FDX files
"""

import json
import sys
from pathlib import Path
from script_parser import FDXParser, ReportGenerator


def test_parser(file_path: str):
    """Test the parser with a given FDX file"""
    print(f"Testing parser with: {file_path}")
    print("=" * 60)
    
    # Parse the script
    parser = FDXParser(file_path)
    script_data = parser.parse()
    
    # Validate basic structure
    print(f"\n✓ Parsed {script_data.total_scenes} scenes")
    print(f"✓ Found {len(script_data.characters)} characters")
    
    # Validate scenes
    print("\n📽️  Scene Breakdown:")
    int_ext_counts = {}
    time_counts = {}
    location_counts = {}
    
    for scene in script_data.scenes:
        print(f"  Scene {scene.scene_number}: {scene.slug_line}")
        print(f"    - INT/EXT: {scene.int_ext}")
        print(f"    - Location: {scene.location}")
        print(f"    - Time: {scene.time_of_day}")
        print(f"    - Characters: {', '.join(scene.characters) if scene.characters else 'None'}")
        print(f"    - Lines: {scene.line_count}")
        
        # Count stats
        int_ext_counts[scene.int_ext] = int_ext_counts.get(scene.int_ext, 0) + 1
        time_counts[scene.time_of_day] = time_counts.get(scene.time_of_day, 0) + 1
        location_counts[scene.location] = location_counts.get(scene.location, 0) + 1
    
    # Validate statistics
    print("\n📊 Statistics:")
    print(f"  INT/EXT Breakdown:")
    for int_ext, count in sorted(int_ext_counts.items()):
        print(f"    {int_ext}: {count}")
    
    print(f"  Time of Day Breakdown:")
    for time, count in sorted(time_counts.items()):
        print(f"    {time}: {count}")
    
    print(f"  Location Breakdown:")
    for location, count in sorted(location_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"    {location}: {count}")
    
    # Validate characters
    print("\n👥 Character Breakdown:")
    for char_name, char in sorted(script_data.characters.items()):
        print(f"  {char.name_canonical}:")
        print(f"    - Raw name: {char.name_raw}")
        print(f"    - Total lines: {char.total_lines}")
        print(f"    - Dialogue count: {char.dialogue_count}")
        print(f"    - Scenes: {char.scenes}")
        print(f"    - First appearance: Scene {char.first_appearance}")
        print(f"    - Last appearance: Scene {char.last_appearance}")
    
    # Validate scene numbers are sequential
    print("\n✓ Validating scene numbers...")
    scene_numbers = [scene.scene_number for scene in script_data.scenes]
    expected_numbers = list(range(1, len(script_data.scenes) + 1))
    if scene_numbers == expected_numbers:
        print("  ✓ Scene numbers are sequential")
    else:
        print(f"  ✗ Scene numbers mismatch: {scene_numbers} vs {expected_numbers}")
        return False
    
    # Validate character appearances match scenes
    print("\n✓ Validating character appearances...")
    all_valid = True
    for char_name, char in script_data.characters.items():
        # Check that character appears in scenes where they're listed
        for scene_num in char.scenes:
            if scene_num > len(script_data.scenes):
                print(f"  ✗ Character {char_name} references scene {scene_num} which doesn't exist")
                all_valid = False
                continue
            
            scene = script_data.scenes[scene_num - 1]
            if char_name not in scene.characters:
                print(f"  ✗ Character {char_name} not found in scene {scene_num} characters list")
                all_valid = False
    
    if all_valid:
        print("  ✓ All character appearances are valid")
    
    # Test report generation
    print("\n📄 Testing report generation...")
    report_gen = ReportGenerator(script_data)
    
    # Test JSON generation
    test_output = Path("test_output")
    test_output.mkdir(exist_ok=True)
    
    json_path = test_output / "test_report.json"
    report_gen.generate_json(str(json_path))
    
    # Validate JSON is valid
    with open(json_path, 'r') as f:
        json_data = json.load(f)
        if json_data['total_scenes'] == script_data.total_scenes:
            print("  ✓ JSON report generated and validated")
        else:
            print(f"  ✗ JSON report validation failed")
            return False
    
    # Test CSV generation
    csv_scenes_path = test_output / "test_scenes.csv"
    csv_chars_path = test_output / "test_characters.csv"
    report_gen.generate_csv_scenes(str(csv_scenes_path))
    report_gen.generate_csv_characters(str(csv_chars_path))
    
    if csv_scenes_path.exists() and csv_chars_path.exists():
        print("  ✓ CSV reports generated")
    else:
        print("  ✗ CSV reports generation failed")
        return False
    
    # Test text summary
    text_path = test_output / "test_summary.txt"
    report_gen.generate_text_summary(str(text_path))
    
    if text_path.exists():
        print("  ✓ Text summary generated")
    else:
        print("  ✗ Text summary generation failed")
        return False
    
    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_parser.py <path_to_fdx_file>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    if not Path(file_path).exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    
    success = test_parser(file_path)
    sys.exit(0 if success else 1)


