#!/usr/bin/env python3
"""
Script Parser - Parse film/TV scripts and generate reports
Supports FDX (Final Draft) format
"""

import re
import json
import csv
import argparse
import io
from dataclasses import dataclass, field, asdict
from xml.etree import ElementTree as ET
from collections import defaultdict
from typing import List, Dict, Optional
from pathlib import Path


@dataclass
class Scene:
    """Represents a scene in the script"""
    scene_number: int
    slug_line: str
    int_ext: str  # INT, EXT, INT./EXT, UNKNOWN
    location: str
    time_of_day: str  # DAY, NIGHT, DAWN, etc.
    location_normalized: str = ""
    time_of_day_normalized: str = ""
    characters: List[str] = field(default_factory=list)
    line_count: int = 0
    word_count: int = 0
    summary: str = ""


@dataclass
class Character:
    """Represents a character in the script"""
    name_raw: str
    name_canonical: str
    scenes: List[int] = field(default_factory=list)
    total_lines: int = 0
    dialogue_count: int = 0
    first_appearance: int = -1
    last_appearance: int = -1
    highlight_lines: List[str] = field(default_factory=list)


@dataclass
class ScriptData:
    """Main data structure for parsed script"""
    title: str = ""
    scenes: List[Scene] = field(default_factory=list)
    characters: Dict[str, Character] = field(default_factory=dict)
    total_scenes: int = 0
    total_pages: float = 0.0


class FDXParser:
    """Parser for Final Draft (FDX) format"""
    
    # Regex patterns
    INT_EXT_PATTERN = r'^(INT\.?|EXT\.?|INT\.?/EXT\.?|INT/EXT)\s+'
    TIME_PATTERN = r'[–-]\s*(DAY|NIGHT|DAWN|DUSK|EVENING|MORNING|CONTINUOUS|LATER|SAME)\b'
    LOCATION_PATTERN = r'^(?:INT\.?|EXT\.?|INT\.?/EXT\.?|INT/EXT)\s+(.+?)(?:\s*[–-]\s*(?:DAY|NIGHT|DAWN|DUSK|EVENING|MORNING|CONTINUOUS|LATER|SAME))'
    
    def __init__(self, file_path: str = None, file_bytes: bytes = None):
        if file_path:
            self.file_path = file_path
            self.tree = ET.parse(file_path)
            self.root = self.tree.getroot()
        elif file_bytes:
            self.file_path = None
            # Decode bytes to string for XML parsing
            try:
                xml_string = file_bytes.decode('utf-8')
            except UnicodeDecodeError:
                # Try other common encodings
                xml_string = file_bytes.decode('latin-1')
            self.root = ET.fromstring(xml_string)
        else:
            raise ValueError("Either file_path or file_bytes must be provided")
        self.script_data = ScriptData()
        
    def parse(self) -> ScriptData:
        """Parse the FDX file and return ScriptData"""
        # Extract title if available
        title_elem = self.root.find('.//Title')
        if title_elem is not None:
            self.script_data.title = title_elem.text or ""
        
        # Parse scenes and characters
        current_scene = None
        current_character = None
        scene_number = 0
        
        for paragraph in self.root.iter("Paragraph"):
            p_type = paragraph.attrib.get("Type")
            text = paragraph.findtext("Text") or ""
            
            if p_type == "Scene Heading":
                # Save previous scene if exists
                if current_scene:
                    self.script_data.scenes.append(current_scene)
                
                # Create new scene
                scene_number += 1
                current_scene = self._parse_scene_heading(text, scene_number)
                
            elif p_type == "Character" and current_scene:
                # Character name
                character_name = text.strip().upper()
                current_character = character_name
                
                # Add character to scene if not already present
                if character_name not in current_scene.characters:
                    current_scene.characters.append(character_name)
                
                # Track character in script data
                if character_name not in self.script_data.characters:
                    canonical_name = self._normalize_character_name(character_name)
                    self.script_data.characters[character_name] = Character(
                        name_raw=character_name,
                        name_canonical=canonical_name
                    )
                
                # Update character scene appearances
                char = self.script_data.characters[character_name]
                if scene_number not in char.scenes:
                    char.scenes.append(scene_number)
                    char.scenes.sort()
                
                # Update first/last appearance
                if char.first_appearance == -1:
                    char.first_appearance = scene_number
                char.last_appearance = scene_number
                
            elif p_type == "Dialogue" and current_scene and current_character:
                # Count dialogue lines
                lines = text.strip().split('\n')
                line_count = len([l for l in lines if l.strip()])
                
                if current_character in self.script_data.characters:
                    char = self.script_data.characters[current_character]
                    char.total_lines += line_count
                    char.dialogue_count += 1
                    current_scene.line_count += line_count
                    
            elif p_type == "Action" and current_scene:
                # Count action lines
                lines = text.strip().split('\n')
                current_scene.line_count += len([l for l in lines if l.strip()])
        
        # Add last scene
        if current_scene:
            self.script_data.scenes.append(current_scene)
        
        self.script_data.total_scenes = len(self.script_data.scenes)
        
        # Normalize character names (merge variants)
        self._normalize_characters()
        
        return self.script_data
    
    def _parse_scene_heading(self, text: str, scene_number: int) -> Scene:
        """Parse a scene heading slug line"""
        # Extract INT/EXT
        int_ext = "UNKNOWN"
        int_ext_match = re.search(self.INT_EXT_PATTERN, text, re.IGNORECASE)
        if int_ext_match:
            int_ext_raw = int_ext_match.group(1).upper().rstrip('.')
            if '/' in int_ext_raw or ('INT' in int_ext_raw and 'EXT' in int_ext_raw):
                int_ext = "INT./EXT"
            elif 'INT' in int_ext_raw:
                int_ext = "INT"
            elif 'EXT' in int_ext_raw:
                int_ext = "EXT"
        
        # Extract time of day
        time_of_day = "UNKNOWN"
        time_match = re.search(self.TIME_PATTERN, text, re.IGNORECASE)
        if time_match:
            time_of_day = time_match.group(1).upper()
            # Normalize time
            if time_of_day in ["DAWN", "MORNING"]:
                time_of_day_normalized = "DAY"
            elif time_of_day in ["DUSK", "EVENING"]:
                time_of_day_normalized = "NIGHT"
            else:
                time_of_day_normalized = time_of_day
        else:
            time_of_day_normalized = "UNKNOWN"
        
        # Extract location
        location = ""
        location_match = re.search(self.LOCATION_PATTERN, text, re.IGNORECASE)
        if location_match:
            location = location_match.group(1).strip()
        else:
            # Fallback: try to extract location manually
            parts = text.split('–')
            if len(parts) > 0:
                location_part = parts[0]
                # Remove INT/EXT prefix
                location = re.sub(self.INT_EXT_PATTERN, '', location_part, flags=re.IGNORECASE).strip()
        
        return Scene(
            scene_number=scene_number,
            slug_line=text.strip(),
            int_ext=int_ext,
            location=location,
            time_of_day=time_of_day,
            location_normalized=self._normalize_location(location),
            time_of_day_normalized=time_of_day_normalized
        )
    
    def _normalize_location(self, location: str) -> str:
        """Normalize location name (remove common suffixes, etc.)"""
        # Remove common suffixes and normalize
        location = location.upper()
        # You can add more normalization rules here
        return location
    
    def _normalize_character_name(self, name: str) -> str:
        """Normalize character name (remove V.O., O.S., etc.)"""
        # Remove common suffixes - handle different apostrophe types
        name = re.sub(r'\s*\(V\.O\.\)', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s*\(O\.S\.\)', '', name, flags=re.IGNORECASE)
        # Handle various apostrophe/quotation mark characters in CONT'D
        # Match CONT followed by any single character (apostrophe variants) followed by D
        name = re.sub(r"\s*\(CONT.D\)", '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s*#\d+', '', name)  # Remove "#2", "#3" etc.
        # Remove common non-character patterns
        name = re.sub(r'^\s*(MATCH CUT|CUT TO|FADE|DISSOLVE|SMASH|TITLES?|KNOCK\.?\s*KNOCK\.?)\s*:?\s*$', '', name, flags=re.IGNORECASE)
        return name.strip()
    
    def _normalize_characters(self):
        """Merge character variants (e.g., JOHN, JOHN (V.O.), JOHN #2)"""
        # Group characters by canonical name
        canonical_groups = defaultdict(list)
        for char_name, char_obj in self.script_data.characters.items():
            canonical_groups[char_obj.name_canonical].append((char_name, char_obj))
        
        # Merge characters with same canonical name
        merged_characters = {}
        for canonical_name, variants in canonical_groups.items():
            if len(variants) == 1:
                # Single variant, use as-is
                char_name, char_obj = variants[0]
                merged_characters[canonical_name] = char_obj
            else:
                # Multiple variants, merge them
                primary_name, primary_char = variants[0]
                for variant_name, variant_char in variants[1:]:
                    # Merge scenes
                    primary_char.scenes.extend(variant_char.scenes)
                    primary_char.scenes = sorted(list(set(primary_char.scenes)))
                    # Merge stats
                    primary_char.total_lines += variant_char.total_lines
                    primary_char.dialogue_count += variant_char.dialogue_count
                    # Update first/last appearance
                    if variant_char.first_appearance != -1:
                        if primary_char.first_appearance == -1 or variant_char.first_appearance < primary_char.first_appearance:
                            primary_char.first_appearance = variant_char.first_appearance
                    if variant_char.last_appearance > primary_char.last_appearance:
                        primary_char.last_appearance = variant_char.last_appearance
                
                merged_characters[canonical_name] = primary_char
        
        self.script_data.characters = merged_characters


class PDFParser:
    """Parser for PDF script format"""
    
    # Regex patterns (same as FDXParser)
    INT_EXT_PATTERN = r'^(INT\.?|EXT\.?|INT\.?/EXT\.?|INT/EXT)\s+'
    TIME_PATTERN = r'[–-]\s*(DAY|NIGHT|DAWN|DUSK|EVENING|MORNING|CONTINUOUS|LATER|SAME)\b'
    LOCATION_PATTERN = r'^(?:INT\.?|EXT\.?|INT\.?/EXT\.?|INT/EXT)\s+(.+?)(?:\s*[–-]\s*(?:DAY|NIGHT|DAWN|DUSK|EVENING|MORNING|CONTINUOUS|LATER|SAME))'
    
    # Character name pattern (all caps, centered, not a scene heading)
    CHARACTER_PATTERN = r'^[A-Z][A-Z\s\.\-\']+$'
    
    def __init__(self, file_path: str = None, file_bytes: bytes = None):
        if file_path:
            self.file_path = file_path
        elif file_bytes:
            self.file_path = None
            self.file_bytes = file_bytes
        else:
            raise ValueError("Either file_path or file_bytes must be provided")
        self.script_data = ScriptData()
        
    def parse(self) -> ScriptData:
        """Parse the PDF file and return ScriptData"""
        try:
            import pdfplumber
        except ImportError:
            raise ImportError("pdfplumber is required for PDF parsing. Install it with: pip install pdfplumber")
        
        pdf_source = self.file_path if self.file_path else io.BytesIO(self.file_bytes)
        with pdfplumber.open(pdf_source) as pdf:
            # Extract text from all pages
            lines = []
            total_pages = len(pdf.pages)
            
            for page_num, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text()
                if page_text:
                    # Split into lines and clean up
                    page_lines = [line.strip() for line in page_text.split('\n') if line.strip()]
                    lines.extend(page_lines)
            
            # Try to extract title by looking for "TITLES: ..." pattern
            for line in lines:
                # Look for "TITLES:" or "TITLE:" pattern (case-insensitive)
                match = re.match(r'^TITLES?\s*:\s*(.+)$', line, re.IGNORECASE)
                if match:
                    self.script_data.title = match.group(1).strip()
                    break
            
            # If no "TITLES:" pattern found, don't set a title
            # (previously it was taking the first line, which was incorrect)
            
            # Parse lines into script elements
            self._parse_lines(lines)
            
            # Store page count
            self.script_data.total_pages = float(total_pages)
        
        # Normalize characters
        self._normalize_characters()
        
        self.script_data.total_scenes = len(self.script_data.scenes)
        
        return self.script_data
    
    def _parse_lines(self, lines: List[str]):
        """Parse lines of text into script elements"""
        current_scene = None
        current_character = None
        scene_number = 0
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip empty lines
            if not line:
                i += 1
                continue
            
            # Check if line is a scene heading (INT./EXT. at start)
            if re.match(self.INT_EXT_PATTERN, line, re.IGNORECASE):
                # Save previous scene if exists
                if current_scene:
                    self.script_data.scenes.append(current_scene)
                
                # Create new scene
                scene_number += 1
                current_scene = self._parse_scene_heading(line, scene_number)
                current_character = None
                i += 1
                continue
            
            # If we don't have a scene yet, skip
            if not current_scene:
                i += 1
                continue
            
            # Check if line is a character name (all caps, centered-ish)
            # Character names are typically:
            # - All uppercase
            # - Not too long (usually < 40 chars)
            # - Not a scene heading
            # - Often followed by dialogue
            if self._is_character_name(line):
                character_name = line.upper().strip()
                
                # Normalize character name first to check for false positives
                canonical_name = self._normalize_character_name(character_name)
                
                # Skip if normalization resulted in empty string (false positive like "MATCH CUT TO:")
                if not canonical_name:
                    i += 1
                    continue
                
                current_character = character_name
                
                # Add character to scene if not already present
                if character_name not in current_scene.characters:
                    current_scene.characters.append(character_name)
                
                # Track character in script data
                if character_name not in self.script_data.characters:
                    self.script_data.characters[character_name] = Character(
                        name_raw=character_name,
                        name_canonical=canonical_name
                    )
                
                # Update character scene appearances
                char = self.script_data.characters[character_name]
                if scene_number not in char.scenes:
                    char.scenes.append(scene_number)
                    char.scenes.sort()
                
                # Update first/last appearance
                if char.first_appearance == -1:
                    char.first_appearance = scene_number
                char.last_appearance = scene_number
                
                # Look ahead for dialogue - collect lines until we hit another character/scene
                dialogue_start = i + 1
                dialogue_end = dialogue_start
                
                # Find where dialogue ends
                for j in range(dialogue_start, len(lines)):
                    next_line = lines[j].strip()
                    
                    # Stop if we hit another character name or scene heading
                    if next_line and (self._is_character_name(next_line) or 
                                     re.match(self.INT_EXT_PATTERN, next_line, re.IGNORECASE)):
                        dialogue_end = j
                        break
                    
                    # Stop if we hit a long action line (but allow parentheticals and short lines)
                    if (next_line and 
                        len(next_line) > 60 and 
                        self._is_action_line(next_line) and
                        not (next_line.startswith('(') and next_line.endswith(')'))):
                        dialogue_end = j
                        break
                    
                    dialogue_end = j + 1
                
                # Collect dialogue lines
                dialogue_lines = [lines[k].strip() for k in range(dialogue_start, dialogue_end) if lines[k].strip()]
                
                # Count dialogue lines (excluding parentheticals from line count)
                if dialogue_lines and current_character:
                    # Count non-parenthetical lines
                    actual_dialogue = [l for l in dialogue_lines 
                                     if not (l.startswith('(') and l.endswith(')'))]
                    line_count = len(actual_dialogue)
                    
                    if line_count > 0:
                        char = self.script_data.characters[character_name]
                        char.total_lines += line_count
                        char.dialogue_count += 1
                        current_scene.line_count += line_count
                
                # Move to end of dialogue
                i = dialogue_end
                continue
            
            # Check if line is action (not dialogue, not character, not scene heading)
            if self._is_action_line(line) and current_scene:
                # Count action lines
                current_scene.line_count += 1
                i += 1
                continue
            
            # Default: treat as dialogue or action
            if current_character and current_scene:
                # Likely dialogue continuation
                current_scene.line_count += 1
                if current_character in self.script_data.characters:
                    self.script_data.characters[current_character].total_lines += 1
            elif current_scene:
                # Likely action
                current_scene.line_count += 1
            
            i += 1
        
        # Add last scene
        if current_scene:
            self.script_data.scenes.append(current_scene)
    
    def _is_character_name(self, line: str) -> bool:
        """Check if a line is likely a character name"""
        line = line.strip()
        
        # Must be all caps (or mostly caps)
        if not line:
            return False
        
        # Check if it's a scene heading
        if re.match(self.INT_EXT_PATTERN, line, re.IGNORECASE):
            return False
        
        # Filter out common non-character patterns
        non_character_patterns = [
            r'^(MATCH CUT|CUT TO|FADE|DISSOLVE|SMASH)',
            r'^(TITLES?|TITLE SEQUENCE)',
            r'^(KNOCK\.?\s*KNOCK\.?)',
            r'^(CONTINUED|CONTINUES)',
            r'^(FADE|DISSOLVE)\s+(IN|OUT)',
            r'^(\d+\.?\s*)?(SCENE|ACT)\s+\d+',
        ]
        for pattern in non_character_patterns:
            if re.match(pattern, line, re.IGNORECASE):
                return False
        
        # Character names are typically:
        # - All uppercase
        # - Not too long (< 50 chars)
        # - Not all numbers
        # - Not action lines (which might have mixed case)
        
        # Check if line is mostly uppercase
        upper_ratio = sum(1 for c in line if c.isupper()) / len(line) if line else 0
        
        # Must be mostly uppercase (at least 70%)
        if upper_ratio < 0.7:
            return False
        
        # Should not be too long
        if len(line) > 50:
            return False
        
        # Should not be all numbers or special chars
        if line.replace(' ', '').replace('.', '').replace('-', '').replace("'", '').isdigit():
            return False
        
        # Should not end with colon only (likely a transition or title)
        if line.endswith(':') and len(line.split()) <= 2:
            # But allow names like "JOHN:" if they have more context
            if not re.search(r'\([V]?\.?O\.?S?\.?\)|\(CONT', line, re.IGNORECASE):
                return False
        
        # Common patterns: single word or two words, sometimes with punctuation
        # But not common action words
        action_words = {'FADE', 'CUT', 'DISSOLVE', 'SMASH', 'CONTINUED', 'CONTINUES', 'END', 'THE END'}
        if line.upper() in action_words:
            return False
        
        # Should contain at least one letter
        if not any(c.isalpha() for c in line):
            return False
        
        return True
    
    def _is_action_line(self, line: str) -> bool:
        """Check if a line is likely an action line"""
        line = line.strip()
        
        if not line:
            return False
        
        # Scene headings are not action
        if re.match(self.INT_EXT_PATTERN, line, re.IGNORECASE):
            return False
        
        # Character names are not action
        if self._is_character_name(line):
            return False
        
        # Action lines typically:
        # - Have mixed case
        # - Are longer
        # - Don't start with uppercase-only short words
        
        # If it's all caps and short, probably not action
        if line.isupper() and len(line) < 30:
            return False
        
        return True
    
    def _parse_scene_heading(self, text: str, scene_number: int) -> Scene:
        """Parse a scene heading slug line (same as FDXParser)"""
        # Extract INT/EXT
        int_ext = "UNKNOWN"
        int_ext_match = re.search(self.INT_EXT_PATTERN, text, re.IGNORECASE)
        if int_ext_match:
            int_ext_raw = int_ext_match.group(1).upper().rstrip('.')
            if '/' in int_ext_raw or ('INT' in int_ext_raw and 'EXT' in int_ext_raw):
                int_ext = "INT./EXT"
            elif 'INT' in int_ext_raw:
                int_ext = "INT"
            elif 'EXT' in int_ext_raw:
                int_ext = "EXT"
        
        # Extract time of day
        time_of_day = "UNKNOWN"
        time_match = re.search(self.TIME_PATTERN, text, re.IGNORECASE)
        if time_match:
            time_of_day = time_match.group(1).upper()
            # Normalize time
            if time_of_day in ["DAWN", "MORNING"]:
                time_of_day_normalized = "DAY"
            elif time_of_day in ["DUSK", "EVENING"]:
                time_of_day_normalized = "NIGHT"
            else:
                time_of_day_normalized = time_of_day
        else:
            time_of_day_normalized = "UNKNOWN"
        
        # Extract location
        location = ""
        location_match = re.search(self.LOCATION_PATTERN, text, re.IGNORECASE)
        if location_match:
            location = location_match.group(1).strip()
        else:
            # Fallback: try to extract location manually
            parts = text.split('–')
            if len(parts) > 0:
                location_part = parts[0]
                # Remove INT/EXT prefix
                location = re.sub(self.INT_EXT_PATTERN, '', location_part, flags=re.IGNORECASE).strip()
        
        return Scene(
            scene_number=scene_number,
            slug_line=text.strip(),
            int_ext=int_ext,
            location=location,
            time_of_day=time_of_day,
            location_normalized=self._normalize_location(location),
            time_of_day_normalized=time_of_day_normalized
        )
    
    def _normalize_location(self, location: str) -> str:
        """Normalize location name (same as FDXParser)"""
        location = location.upper()
        return location
    
    def _normalize_character_name(self, name: str) -> str:
        """Normalize character name (same as FDXParser)"""
        # Remove common suffixes - handle different apostrophe types
        name = re.sub(r'\s*\(V\.O\.\)', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s*\(O\.S\.\)', '', name, flags=re.IGNORECASE)
        # Handle various apostrophe/quotation mark characters in CONT'D
        # Match CONT followed by any single character (apostrophe variants) followed by D
        name = re.sub(r"\s*\(CONT.D\)", '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s*#\d+', '', name)  # Remove "#2", "#3" etc.
        # Remove common non-character patterns
        name = re.sub(r'^\s*(MATCH CUT|CUT TO|FADE|DISSOLVE|SMASH|TITLES?|KNOCK\.?\s*KNOCK\.?)\s*:?\s*$', '', name, flags=re.IGNORECASE)
        return name.strip()
    
    def _normalize_characters(self):
        """Merge character variants (same as FDXParser)"""
        # Group characters by canonical name
        canonical_groups = defaultdict(list)
        for char_name, char_obj in self.script_data.characters.items():
            canonical_groups[char_obj.name_canonical].append((char_name, char_obj))
        
        # Merge characters with same canonical name
        merged_characters = {}
        for canonical_name, variants in canonical_groups.items():
            if len(variants) == 1:
                # Single variant, use as-is
                char_name, char_obj = variants[0]
                merged_characters[canonical_name] = char_obj
            else:
                # Multiple variants, merge them
                primary_name, primary_char = variants[0]
                for variant_name, variant_char in variants[1:]:
                    # Merge scenes
                    primary_char.scenes.extend(variant_char.scenes)
                    primary_char.scenes = sorted(list(set(primary_char.scenes)))
                    # Merge stats
                    primary_char.total_lines += variant_char.total_lines
                    primary_char.dialogue_count += variant_char.dialogue_count
                    # Update first/last appearance
                    if variant_char.first_appearance != -1:
                        if primary_char.first_appearance == -1 or variant_char.first_appearance < primary_char.first_appearance:
                            primary_char.first_appearance = variant_char.first_appearance
                    if variant_char.last_appearance > primary_char.last_appearance:
                        primary_char.last_appearance = variant_char.last_appearance
                
                merged_characters[canonical_name] = primary_char
        
        self.script_data.characters = merged_characters


class ReportGenerator:
    """Generate reports from parsed script data"""
    
    def __init__(self, script_data: ScriptData):
        self.script_data = script_data
    
    def generate_json(self, output_path: str):
        """Generate JSON report"""
        output = {
            "title": self.script_data.title,
            "total_scenes": self.script_data.total_scenes,
            "scenes": [asdict(scene) for scene in self.script_data.scenes],
            "characters": {name: asdict(char) for name, char in self.script_data.characters.items()},
            "summary": {
                "int_ext_breakdown": self._get_int_ext_breakdown(),
                "time_of_day_breakdown": self._get_time_of_day_breakdown(),
                "location_breakdown": self._get_location_breakdown(),
                "character_summary": self._get_character_summary()
            }
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
    
    def generate_csv_scenes(self, output_path: str):
        """Generate CSV report for scenes"""
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                "Scene #", "Slug Line", "INT/EXT", "Location", "Time of Day",
                "Characters", "Line Count"
            ])
            
            for scene in self.script_data.scenes:
                writer.writerow([
                    scene.scene_number,
                    scene.slug_line,
                    scene.int_ext,
                    scene.location,
                    scene.time_of_day,
                    ", ".join(scene.characters),
                    scene.line_count
                ])
    
    def generate_csv_characters(self, output_path: str):
        """Generate CSV report for characters"""
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                "Character", "Canonical Name", "Total Lines", "Dialogue Count",
                "Scenes", "First Appearance", "Last Appearance"
            ])
            
            for char_name, char in sorted(self.script_data.characters.items()):
                writer.writerow([
                    char.name_raw,
                    char.name_canonical,
                    char.total_lines,
                    char.dialogue_count,
                    len(char.scenes),
                    char.first_appearance,
                    char.last_appearance
                ])
    
    def generate_text_summary(self, output_path: str):
        """Generate human-readable text summary"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"SCRIPT BREAKDOWN REPORT\n")
            f.write(f"{'=' * 50}\n\n")
            f.write(f"Title: {self.script_data.title or 'Untitled'}\n")
            f.write(f"Total Scenes: {self.script_data.total_scenes}\n\n")
            
            f.write("INT/EXT Breakdown:\n")
            for int_ext, count in sorted(self._get_int_ext_breakdown().items()):
                f.write(f"  {int_ext}: {count}\n")
            
            f.write("\nTime of Day Breakdown:\n")
            for time, count in sorted(self._get_time_of_day_breakdown().items()):
                f.write(f"  {time}: {count}\n")
            
            f.write("\nLocation Breakdown:\n")
            for location, count in sorted(self._get_location_breakdown().items(), key=lambda x: x[1], reverse=True):
                f.write(f"  {location}: {count}\n")
            
            f.write("\nCharacter Summary:\n")
            for char_name, char in sorted(self.script_data.characters.items(), key=lambda x: x[1].total_lines, reverse=True):
                f.write(f"  {char.name_canonical}: {char.total_lines} lines, {len(char.scenes)} scenes\n")
    
    def _get_int_ext_breakdown(self) -> Dict[str, int]:
        """Get INT/EXT breakdown"""
        breakdown = defaultdict(int)
        for scene in self.script_data.scenes:
            breakdown[scene.int_ext] += 1
        return dict(breakdown)
    
    def _get_time_of_day_breakdown(self) -> Dict[str, int]:
        """Get time of day breakdown"""
        breakdown = defaultdict(int)
        for scene in self.script_data.scenes:
            breakdown[scene.time_of_day] += 1
        return dict(breakdown)
    
    def _get_location_breakdown(self) -> Dict[str, int]:
        """Get location breakdown"""
        breakdown = defaultdict(int)
        for scene in self.script_data.scenes:
            location = scene.location_normalized or scene.location
            if location:
                breakdown[location] += 1
        return dict(breakdown)
    
    def _get_character_summary(self) -> Dict[str, Dict]:
        """Get character summary"""
        summary = {}
        for char_name, char in self.script_data.characters.items():
            summary[char_name] = {
                "canonical_name": char.name_canonical,
                "total_lines": char.total_lines,
                "scenes": len(char.scenes),
                "first_appearance": char.first_appearance,
                "last_appearance": char.last_appearance
            }
        return summary


def detect_file_type(file_path: str = None, file_bytes: bytes = None, filename: str = None) -> str:
    """Detect file type from extension"""
    if file_path:
        path = Path(file_path)
        ext = path.suffix.lower()
    elif filename:
        ext = Path(filename).suffix.lower()
    else:
        raise ValueError("Either file_path or filename must be provided")
    
    if ext == '.fdx':
        return 'fdx'
    elif ext == '.pdf':
        return 'pdf'
    elif ext == '.fountain' or ext == '.txt':
        # TODO: Add Fountain parser
        return 'fountain'
    else:
        raise ValueError(f"Unsupported file type: {ext}. Supported types: .fdx, .pdf")


def parse_fdx_bytes(fdx_bytes: bytes) -> dict:
    """Parse FDX file from bytes and return JSON report"""
    parser = FDXParser(file_bytes=fdx_bytes)
    script_data = parser.parse()
    
    report_gen = ReportGenerator(script_data)
    # Generate the report structure
    output = {
        "title": script_data.title,
        "total_scenes": script_data.total_scenes,
        "scenes": [asdict(scene) for scene in script_data.scenes],
        "characters": {name: asdict(char) for name, char in script_data.characters.items()},
        "summary": {
            "int_ext_breakdown": report_gen._get_int_ext_breakdown(),
            "time_of_day_breakdown": report_gen._get_time_of_day_breakdown(),
            "location_breakdown": report_gen._get_location_breakdown(),
            "character_summary": report_gen._get_character_summary()
        }
    }
    return output


def parse_pdf_bytes(pdf_bytes: bytes) -> dict:
    """Parse PDF file from bytes and return JSON report"""
    parser = PDFParser(file_bytes=pdf_bytes)
    script_data = parser.parse()
    
    report_gen = ReportGenerator(script_data)
    # Generate the report structure
    output = {
        "title": script_data.title,
        "total_scenes": script_data.total_scenes,
        "scenes": [asdict(scene) for scene in script_data.scenes],
        "characters": {name: asdict(char) for name, char in script_data.characters.items()},
        "summary": {
            "int_ext_breakdown": report_gen._get_int_ext_breakdown(),
            "time_of_day_breakdown": report_gen._get_time_of_day_breakdown(),
            "location_breakdown": report_gen._get_location_breakdown(),
            "character_summary": report_gen._get_character_summary()
        }
    }
    return output


def main():
    parser = argparse.ArgumentParser(description='Parse script and generate reports')
    parser.add_argument('input_file', help='Input script file (FDX, PDF, or Fountain)')
    parser.add_argument('-o', '--output', help='Output directory (default: ./reports)', default='./reports')
    parser.add_argument('--format', choices=['json', 'csv', 'text', 'all'], default='all',
                       help='Output format (default: all)')
    
    args = parser.parse_args()
    
    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True)
    
    # Detect file type and parse
    print(f"Parsing {args.input_file}...")
    file_type = detect_file_type(args.input_file)
    
    if file_type == 'fdx':
        script_parser = FDXParser(args.input_file)
        script_data = script_parser.parse()
    elif file_type == 'pdf':
        script_parser = PDFParser(args.input_file)
        script_data = script_parser.parse()
    else:
        raise ValueError(f"Parser for {file_type} format not yet implemented")
    
    print(f"Parsed {script_data.total_scenes} scenes and {len(script_data.characters)} characters")
    
    # Generate reports
    report_gen = ReportGenerator(script_data)
    base_name = Path(args.input_file).stem
    
    if args.format in ['json', 'all']:
        json_path = output_dir / f"{base_name}_report.json"
        report_gen.generate_json(str(json_path))
        print(f"Generated JSON report: {json_path}")
    
    if args.format in ['csv', 'all']:
        csv_scenes_path = output_dir / f"{base_name}_scenes.csv"
        csv_chars_path = output_dir / f"{base_name}_characters.csv"
        report_gen.generate_csv_scenes(str(csv_scenes_path))
        report_gen.generate_csv_characters(str(csv_chars_path))
        print(f"Generated CSV reports: {csv_scenes_path}, {csv_chars_path}")
    
    if args.format in ['text', 'all']:
        text_path = output_dir / f"{base_name}_summary.txt"
        report_gen.generate_text_summary(str(text_path))
        print(f"Generated text summary: {text_path}")
    
    print("\nDone!")


if __name__ == "__main__":
    main()

