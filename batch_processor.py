#!/usr/bin/env python3
"""
Batch Processor - Process multiple scripts and collate results
Supports batch processing of episodes/scripts with aggregated analysis
"""

import json
import csv
import io
from collections import defaultdict
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field, asdict
from pathlib import Path

from script_parser import parse_fdx_bytes, parse_pdf_bytes, detect_file_type, ScriptData, Scene, Character


@dataclass
class EpisodeData:
    """Data for a single episode/script"""
    filename: str
    title: str
    script_data: ScriptData
    episode_number: Optional[int] = None


@dataclass
class CollatedData:
    """Collated data across all episodes"""
    episodes: List[EpisodeData] = field(default_factory=list)
    total_episodes: int = 0
    total_scenes: int = 0
    
    # Collated breakdowns
    location_breakdown: Dict[str, int] = field(default_factory=dict)
    int_ext_breakdown: Dict[str, int] = field(default_factory=dict)
    time_of_day_breakdown: Dict[str, int] = field(default_factory=dict)
    
    # Character data across all episodes
    characters: Dict[str, Dict] = field(default_factory=dict)
    
    # Scene details by location
    scenes_by_location: Dict[str, List[Dict]] = field(default_factory=dict)
    
    # Episode-level scene counts
    scenes_per_episode: Dict[str, int] = field(default_factory=dict)


class BatchProcessor:
    """Process multiple scripts and collate results"""
    
    def __init__(self):
        self.episodes: List[EpisodeData] = []
    
    def add_episode(self, filename: str, file_bytes: bytes) -> EpisodeData:
        """Parse and add an episode to the batch"""
        # Detect file type
        file_type = detect_file_type(filename=filename)
        
        # Parse the script
        if file_type == 'fdx':
            result = parse_fdx_bytes(file_bytes)
        elif file_type == 'pdf':
            result = parse_pdf_bytes(file_bytes)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")
        
        # Convert result dict back to ScriptData structure
        script_data = self._dict_to_script_data(result)
        
        # Create episode data
        episode = EpisodeData(
            filename=filename,
            title=result.get("title", ""),
            script_data=script_data
        )
        
        self.episodes.append(episode)
        return episode
    
    def _dict_to_script_data(self, result: dict) -> ScriptData:
        """Convert result dict back to ScriptData object"""
        script_data = ScriptData()
        script_data.title = result.get("title", "")
        script_data.total_scenes = result.get("total_scenes", 0)
        
        # Convert scenes
        for scene_dict in result.get("scenes", []):
            scene = Scene(
                scene_number=scene_dict.get("scene_number", 0),
                slug_line=scene_dict.get("slug_line", ""),
                int_ext=scene_dict.get("int_ext", ""),
                location=scene_dict.get("location", ""),
                time_of_day=scene_dict.get("time_of_day", ""),
                location_normalized=scene_dict.get("location_normalized", ""),
                time_of_day_normalized=scene_dict.get("time_of_day_normalized", ""),
                characters=scene_dict.get("characters", []),
                line_count=scene_dict.get("line_count", 0),
                word_count=scene_dict.get("word_count", 0),
                summary=scene_dict.get("summary", "")
            )
            script_data.scenes.append(scene)
        
        # Convert characters
        for char_name, char_dict in result.get("characters", {}).items():
            char = Character(
                name_raw=char_dict.get("name_raw", char_name),
                name_canonical=char_dict.get("name_canonical", ""),
                scenes=char_dict.get("scenes", []),
                total_lines=char_dict.get("total_lines", 0),
                dialogue_count=char_dict.get("dialogue_count", 0),
                first_appearance=char_dict.get("first_appearance", -1),
                last_appearance=char_dict.get("last_appearance", -1),
                highlight_lines=char_dict.get("highlight_lines", [])
            )
            script_data.characters[char_name] = char
        
        return script_data
    
    def collate(self) -> CollatedData:
        """Collate all episodes into aggregated data"""
        collated = CollatedData()
        collated.episodes = self.episodes
        collated.total_episodes = len(self.episodes)
        
        # Aggregate all scenes
        location_counter = defaultdict(int)
        int_ext_counter = defaultdict(int)
        time_counter = defaultdict(int)
        character_aggregate = defaultdict(lambda: {
            "name_canonical": "",
            "total_lines": 0,
            "dialogue_count": 0,
            "scenes": [],
            "episodes": set(),
            "first_appearance": {"episode": None, "episode_idx": None, "scene": None},
            "last_appearance": {"episode": None, "episode_idx": None, "scene": None}
        })
        scenes_by_location = defaultdict(list)
        
        for episode_idx, episode in enumerate(self.episodes):
            episode_name = episode.filename
            collated.scenes_per_episode[episode_name] = len(episode.script_data.scenes)
            collated.total_scenes += len(episode.script_data.scenes)
            
            for scene in episode.script_data.scenes:
                # Count by location
                location = scene.location_normalized or scene.location
                if location:
                    location_counter[location] += 1
                    scenes_by_location[location].append({
                        "episode": episode_name,
                        "episode_title": episode.title,
                        "scene_number": scene.scene_number,
                        "slug_line": scene.slug_line,
                        "int_ext": scene.int_ext,
                        "time_of_day": scene.time_of_day,
                        "characters": scene.characters,
                        "line_count": scene.line_count
                    })
                
                # Count INT/EXT
                int_ext_counter[scene.int_ext] += 1
                
                # Count time of day
                time_counter[scene.time_of_day] += 1
                
                # Aggregate characters
                for char_name in scene.characters:
                    if char_name in episode.script_data.characters:
                        char = episode.script_data.characters[char_name]
                        char_key = char.name_canonical or char_name
                        
                        if not character_aggregate[char_key]["name_canonical"]:
                            character_aggregate[char_key]["name_canonical"] = char.name_canonical
                        
                        character_aggregate[char_key]["total_lines"] += char.total_lines
                        character_aggregate[char_key]["dialogue_count"] += char.dialogue_count
                        character_aggregate[char_key]["episodes"].add(episode_name)
                        
                        # Track scene appearances (with episode context)
                        for scene_num in char.scenes:
                            scene_key = f"{episode_name}:{scene_num}"
                            if scene_key not in character_aggregate[char_key]["scenes"]:
                                character_aggregate[char_key]["scenes"].append(scene_key)
                        
                        # Track first/last appearance
                        if char.first_appearance != -1:
                            stored_first = character_aggregate[char_key]["first_appearance"]
                            if (stored_first["episode"] is None or
                                stored_first["episode_idx"] is None or
                                episode_idx < stored_first["episode_idx"] or
                                (episode_idx == stored_first["episode_idx"] and
                                 char.first_appearance < stored_first["scene"])):
                                character_aggregate[char_key]["first_appearance"] = {
                                    "episode": episode_name,
                                    "episode_idx": episode_idx,
                                    "scene": char.first_appearance
                                }
                        
                        if char.last_appearance != -1:
                            stored_last = character_aggregate[char_key]["last_appearance"]
                            if (stored_last["episode"] is None or
                                stored_last["episode_idx"] is None or
                                episode_idx > stored_last["episode_idx"] or
                                (episode_idx == stored_last["episode_idx"] and
                                 char.last_appearance > stored_last["scene"])):
                                character_aggregate[char_key]["last_appearance"] = {
                                    "episode": episode_name,
                                    "episode_idx": episode_idx,
                                    "scene": char.last_appearance
                                }
        
        # Convert to regular dicts
        collated.location_breakdown = dict(sorted(location_counter.items(), key=lambda x: x[1], reverse=True))
        collated.int_ext_breakdown = dict(int_ext_counter)
        collated.time_of_day_breakdown = dict(time_counter)
        collated.scenes_by_location = {loc: scenes for loc, scenes in scenes_by_location.items()}
        
        # Convert character aggregate to final format
        for char_key, char_data in character_aggregate.items():
            # Remove episode_idx from first/last appearance (only used for internal comparison)
            first_app = char_data["first_appearance"].copy()
            last_app = char_data["last_appearance"].copy()
            if "episode_idx" in first_app:
                del first_app["episode_idx"]
            if "episode_idx" in last_app:
                del last_app["episode_idx"]
            
            collated.characters[char_key] = {
                "name_canonical": char_data["name_canonical"],
                "total_lines": char_data["total_lines"],
                "dialogue_count": char_data["dialogue_count"],
                "scenes": sorted(char_data["scenes"]),
                "episodes": sorted(list(char_data["episodes"])),
                "episode_count": len(char_data["episodes"]),
                "scene_count": len(char_data["scenes"]),
                "first_appearance": first_app,
                "last_appearance": last_app
            }
        
        return collated
    
    def generate_collated_json(self, collated: CollatedData) -> str:
        """Generate JSON report for collated data"""
        output = {
            "batch_summary": {
                "total_episodes": collated.total_episodes,
                "total_scenes": collated.total_scenes,
                "episodes": [
                    {
                        "filename": ep.filename,
                        "title": ep.title,
                        "scene_count": len(ep.script_data.scenes)
                    }
                    for ep in collated.episodes
                ]
            },
            "collated_breakdowns": {
                "location_breakdown": collated.location_breakdown,
                "int_ext_breakdown": collated.int_ext_breakdown,
                "time_of_day_breakdown": collated.time_of_day_breakdown
            },
            "characters": collated.characters,
            "scenes_by_location": collated.scenes_by_location,
            "scenes_per_episode": collated.scenes_per_episode
        }
        return json.dumps(output, indent=2, ensure_ascii=False)
    
    def generate_collated_scenes_csv(self, collated: CollatedData) -> str:
        """Generate CSV report for collated scenes by location"""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Location", "Scene Count", "Episodes", "Episode List"
        ])
        
        for location, count in sorted(collated.location_breakdown.items(), key=lambda x: x[1], reverse=True):
            # Get unique episodes for this location
            episodes = set()
            for scene in collated.scenes_by_location.get(location, []):
                episodes.add(scene["episode"])
            
            writer.writerow([
                location,
                count,
                len(episodes),
                ", ".join(sorted(episodes))
            ])
        
        return output.getvalue()
    
    def generate_collated_characters_csv(self, collated: CollatedData) -> str:
        """Generate CSV report for collated characters"""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Character", "Total Lines", "Dialogue Count", "Scene Count",
            "Episode Count", "Episodes", "First Appearance", "Last Appearance"
        ])
        
        for char_name, char_data in sorted(collated.characters.items(), key=lambda x: x[1]["total_lines"], reverse=True):
            first_app = char_data.get("first_appearance", {})
            last_app = char_data.get("last_appearance", {})
            
            first_app_str = f"{first_app.get('episode', '?')}:{first_app.get('scene', '?')}" if first_app.get("episode") else "—"
            last_app_str = f"{last_app.get('episode', '?')}:{last_app.get('scene', '?')}" if last_app.get("episode") else "—"
            
            writer.writerow([
                char_name,
                char_data["total_lines"],
                char_data["dialogue_count"],
                char_data["scene_count"],
                char_data["episode_count"],
                ", ".join(char_data["episodes"]),
                first_app_str,
                last_app_str
            ])
        
        return output.getvalue()
    
    def generate_location_details_csv(self, collated: CollatedData) -> str:
        """Generate detailed CSV showing all scenes at each location"""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Location", "Episode", "Scene #", "Slug Line", "INT/EXT",
            "Time of Day", "Characters", "Line Count"
        ])
        
        for location in sorted(collated.location_breakdown.keys(), key=lambda x: collated.location_breakdown[x], reverse=True):
            for scene in collated.scenes_by_location.get(location, []):
                writer.writerow([
                    location,
                    scene["episode"],
                    scene["scene_number"],
                    scene["slug_line"],
                    scene["int_ext"],
                    scene["time_of_day"],
                    ", ".join(scene["characters"]),
                    scene["line_count"]
                ])
        
        return output.getvalue()

