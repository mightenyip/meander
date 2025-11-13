import re
from xml.etree import ElementTree as ET
from collections import defaultdict

# Parse the FDX file
tree = ET.parse("samples/test_script.fdx")
root = tree.getroot()

# Counters for scenes
int_ext_counts = defaultdict(int)
time_of_day_counts = defaultdict(int)
total_scenes = 0

# Regex patterns for parsing slug lines
# Match INT/EXT at the start of the line, with optional period and space
int_ext_pattern = r'^(INT\.?|EXT\.?|INT\.?/EXT\.?|INT/EXT)\s'
time_pattern = r'[–-]\s*(DAY|NIGHT|DAWN|DUSK|EVENING|MORNING|CONTINUOUS|LATER|SAME)\b'

# Parse all paragraphs
for paragraph in root.iter("Paragraph"):
    p_type = paragraph.attrib.get("Type")
    
    # Only process scene headings
    if p_type == "Scene Heading":
        text = paragraph.findtext("Text")
        if text:
            total_scenes += 1
            
            # Extract INT/EXT
            int_ext_match = re.search(int_ext_pattern, text, re.IGNORECASE)
            if int_ext_match:
                int_ext = int_ext_match.group(1).upper().rstrip('.')
                # Normalize variations
                if '/' in int_ext or ('INT' in int_ext and 'EXT' in int_ext):
                    int_ext_counts["INT./EXT"] += 1
                elif 'INT' in int_ext:
                    int_ext_counts["INT"] += 1
                elif 'EXT' in int_ext:
                    int_ext_counts["EXT"] += 1
                else:
                    int_ext_counts["UNKNOWN"] += 1
            else:
                int_ext_counts["UNKNOWN"] += 1
            
            # Extract time of day
            time_match = re.search(time_pattern, text, re.IGNORECASE)
            if time_match:
                time_of_day = time_match.group(1).upper()
                time_of_day_counts[time_of_day] += 1
            else:
                time_of_day_counts["UNKNOWN"] += 1

# Print results
print(f"\n=== SCRIPT BREAKDOWN ===")
print(f"Total scenes: {total_scenes}\n")

print("=== INT/EXT Breakdown ===")
for location_type, count in sorted(int_ext_counts.items()):
    print(f"  {location_type}: {count}")

print("\n=== Time of Day Breakdown ===")
for time, count in sorted(time_of_day_counts.items()):
    print(f"  {time}: {count}")