#!/usr/bin/env python3
"""
Meander - Script Analyzer (Beta)
Streamlit UI for parsing and analyzing script files
"""

import streamlit as st
import json
import csv
import io
from script_parser import parse_fdx_bytes, parse_pdf_bytes, detect_file_type
from batch_processor import BatchProcessor

st.set_page_config(page_title="Script Analyzer (Beta)", layout="wide")

st.title("Script Analyzer (Beta)")

st.markdown("""
**Speed up your production process!** Parse your scripts to get scene information, character breakdowns, 
and location analysis. Extract insights from your scripts in seconds.
""")

st.markdown("*Developed by Mighten Yip, 2025*")

st.write("")

# Mode selector
mode = st.radio(
    "Select processing mode:",
    ["Single Script", "Batch Process (Multiple Episodes)"],
    horizontal=True
)

st.write("")

if mode == "Single Script":
    st.write("Upload a script draft `.fdx` or `.pdf` file to see the parsed structure.")
    uploaded_file = st.file_uploader("Choose a script file", type=["fdx", "pdf"], key="single_file")
    uploaded_files = None
else:
    st.write("Upload multiple script files (`.fdx` or `.pdf`) to collate scenes across episodes.")
    st.write("**Example:** Upload 8 episode scripts to see location breakdowns across the whole season.")
    uploaded_files = st.file_uploader(
        "Choose script files (multiple)", 
        type=["fdx", "pdf"], 
        accept_multiple_files=True,
        key="batch_files"
    )
    uploaded_file = None

if mode == "Single Script" and uploaded_file is not None:
    st.success(f"Uploaded: {uploaded_file.name}")
    
    # Read file contents as bytes
    file_bytes = uploaded_file.read()
    
    # Detect file type
    try:
        file_type = detect_file_type(filename=uploaded_file.name)
    except ValueError as e:
        st.error(f"Error detecting file type: {e}")
        st.stop()
    
    # Call the appropriate parser
    try:
        with st.spinner("Parsing script..."):
            if file_type == 'fdx':
                result = parse_fdx_bytes(file_bytes)
            elif file_type == 'pdf':
                result = parse_pdf_bytes(file_bytes)
            else:
                st.error(f"Unsupported file type: {file_type}")
                st.stop()
    except Exception as e:
        st.error(f"Error while parsing: {e}")
        import traceback
        st.code(traceback.format_exc())
    else:
        st.success("Parsing complete!")
        
        # Display summary stats
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Scenes", result.get("total_scenes", 0))
        with col2:
            st.metric("Characters", len(result.get("characters", {})))
        with col3:
            title = result.get("title", "").strip()
            if title:
                st.metric("Title", title[:30] + "..." if len(title) > 30 else title)
            else:
                st.metric("Title", "—")
        with col4:
            total_lines = sum(char.get("total_lines", 0) for char in result.get("characters", {}).values())
            st.metric("Total Lines", total_lines)
        
        # Display summary breakdowns
        if "summary" in result:
            st.subheader("Summary")
            summary = result["summary"]
            
            col1, col2 = st.columns(2)
            with col1:
                if "int_ext_breakdown" in summary:
                    st.write("**INT/EXT Breakdown**")
                    st.json(summary["int_ext_breakdown"])
                if "time_of_day_breakdown" in summary:
                    st.write("**Time of Day Breakdown**")
                    st.json(summary["time_of_day_breakdown"])
            
            with col2:
                if "location_breakdown" in summary:
                    st.write("**Location Breakdown**")
                    # TODO: Consider grouping locations hierarchically (e.g., "SCU CAMPUS" as main,
                    # with sub-locations like "MAIN QUAD", "MAIN STREET" listed underneath)
                    # This would help organize locations like:
                    #   "SCU CAMPUS - MAIN QUAD": 1
                    #   "SCU CAMPUS - MAIN QUAD - AERODESIGN BOOTH": 1
                    #   "SCU CAMPUS - MAIN STREET": 1
                    # Into: SCU CAMPUS: 3 scenes
                    #   • MAIN QUAD: 1 scene
                    #   • MAIN QUAD - AERODESIGN BOOTH: 1 scene
                    #   • MAIN STREET: 1 scene
                    # Show top 10 locations
                    locations = sorted(summary["location_breakdown"].items(), key=lambda x: x[1], reverse=True)[:10]
                    st.json(dict(locations))
        
        # Export section
        st.subheader("Export")
        base_name = uploaded_file.name.rsplit('.', 1)[0]
        
        # Helper functions to generate CSV strings
        def generate_scenes_csv(result):
            """Generate CSV string for scenes"""
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "Scene #", "Slug Line", "INT/EXT", "Location", "Time of Day",
                "Characters", "Line Count"
            ])
            
            for scene in result.get("scenes", []):
                characters_str = ", ".join(scene.get("characters", []))
                writer.writerow([
                    scene.get("scene_number", ""),
                    scene.get("slug_line", ""),
                    scene.get("int_ext", ""),
                    scene.get("location", ""),
                    scene.get("time_of_day", ""),
                    characters_str,
                    scene.get("line_count", 0)
                ])
            
            return output.getvalue()
        
        def generate_characters_csv(result):
            """Generate CSV string for characters"""
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "Character", "Canonical Name", "Total Lines", "Dialogue Count",
                "Scenes", "First Appearance", "Last Appearance"
            ])
            
            for char_name, char in sorted(result.get("characters", {}).items()):
                writer.writerow([
                    char.get("name_raw", char_name),
                    char.get("name_canonical", ""),
                    char.get("total_lines", 0),
                    char.get("dialogue_count", 0),
                    len(char.get("scenes", [])),
                    char.get("first_appearance", -1),
                    char.get("last_appearance", -1)
                ])
            
            return output.getvalue()
        
        # Download buttons in columns
        col1, col2, col3 = st.columns(3)
        
        with col1:
            json_str = json.dumps(result, indent=2)
            st.download_button(
                label="📄 Download JSON",
                data=json_str,
                file_name=f"{base_name}_report.json",
                mime="application/json",
            )
        
        with col2:
            if "scenes" in result:
                scenes_csv = generate_scenes_csv(result)
                st.download_button(
                    label="📊 Download Scenes CSV",
                    data=scenes_csv,
                    file_name=f"{base_name}_scenes.csv",
                    mime="text/csv",
                )
        
        with col3:
            if "characters" in result:
                characters_csv = generate_characters_csv(result)
                st.download_button(
                    label="👥 Download Characters CSV",
                    data=characters_csv,
                    file_name=f"{base_name}_characters.csv",
                    mime="text/csv",
                )
        
        st.subheader("Parsed Output")
        
        # Tabs for different views
        tab1, tab2, tab3 = st.tabs(["Full JSON", "Scenes", "Characters"])
        
        with tab1:
            # Pretty JSON view
            st.json(result)
        
        with tab2:
            if "scenes" in result:
                st.write(f"**{len(result['scenes'])} scenes found**")
                for scene in result["scenes"]:
                    with st.expander(f"Scene {scene.get('scene_number', '?')}: {scene.get('slug_line', 'N/A')}"):
                        st.json(scene)
        
        with tab3:
            if "characters" in result:
                st.write(f"**{len(result['characters'])} characters found**")
                # Sort by total lines
                sorted_chars = sorted(
                    result["characters"].items(),
                    key=lambda x: x[1].get("total_lines", 0),
                    reverse=True
                )
                for char_name, char_data in sorted_chars:
                    with st.expander(f"{char_data.get('name_canonical', char_name)} ({char_data.get('total_lines', 0)} lines)"):
                        st.json(char_data)

elif mode == "Batch Process (Multiple Episodes)" and uploaded_files:
    if len(uploaded_files) == 0:
        st.warning("Please upload at least one script file.")
    else:
        st.success(f"Uploaded {len(uploaded_files)} file(s)")
        
        # Process all files
        processor = BatchProcessor()
        errors = []
        
        with st.spinner(f"Processing {len(uploaded_files)} script(s)..."):
            progress_bar = st.progress(0)
            for idx, uploaded_file in enumerate(uploaded_files):
                try:
                    file_bytes = uploaded_file.read()
                    processor.add_episode(uploaded_file.name, file_bytes)
                    progress_bar.progress((idx + 1) / len(uploaded_files))
                except Exception as e:
                    errors.append(f"{uploaded_file.name}: {str(e)}")
                    import traceback
                    st.error(f"Error processing {uploaded_file.name}: {e}")
                    st.code(traceback.format_exc())
        
        if errors:
            st.error(f"Errors occurred while processing {len(errors)} file(s).")
        else:
            st.success("All scripts processed successfully!")
            
            # Collate results
            with st.spinner("Collating results across all episodes..."):
                collated = processor.collate()
            
            st.success("Collation complete!")
            
            # Display batch summary
            st.subheader("Batch Summary")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Episodes", collated.total_episodes)
            with col2:
                st.metric("Total Scenes", collated.total_scenes)
            with col3:
                avg_scenes = collated.total_scenes / collated.total_episodes if collated.total_episodes > 0 else 0
                st.metric("Avg Scenes/Episode", f"{avg_scenes:.1f}")
            with col4:
                st.metric("Total Characters", len(collated.characters))
            
            # Episode breakdown
            st.subheader("Episodes Processed")
            episode_data = []
            for ep in collated.episodes:
                episode_data.append({
                    "Filename": ep.filename,
                    "Title": ep.title or "—",
                    "Scenes": len(ep.script_data.scenes)
                })
            st.dataframe(episode_data, use_container_width=True)
            
            # Collated breakdowns
            st.subheader("Collated Breakdowns")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**INT/EXT Breakdown (All Episodes)**")
                st.json(collated.int_ext_breakdown)
                
                st.write("**Time of Day Breakdown (All Episodes)**")
                st.json(collated.time_of_day_breakdown)
            
            with col2:
                st.write("**Location Breakdown (All Episodes)**")
                st.write("Shows total number of scenes at each location across all episodes.")
                # Show top 20 locations
                top_locations = list(collated.location_breakdown.items())[:20]
                st.json(dict(top_locations))
                
                if len(collated.location_breakdown) > 20:
                    st.info(f"Showing top 20 of {len(collated.location_breakdown)} total locations.")
            
            # Location details
            st.subheader("Scenes by Location")
            st.write("View all scenes at each location across all episodes.")
            
            location_tabs = st.tabs(["Location Summary", "Location Details"])
            
            with location_tabs[0]:
                # Summary table
                location_summary = []
                for location, count in list(collated.location_breakdown.items())[:50]:
                    episodes = set()
                    for scene in collated.scenes_by_location.get(location, []):
                        episodes.add(scene["episode"])
                    location_summary.append({
                        "Location": location,
                        "Total Scenes": count,
                        "Episodes": len(episodes),
                        "Episode List": ", ".join(sorted(episodes))
                    })
                
                st.dataframe(location_summary, use_container_width=True)
            
            with location_tabs[1]:
                # Detailed view - allow filtering by location
                if collated.location_breakdown:
                    selected_location = st.selectbox(
                        "Select a location to view all scenes:",
                        list(collated.location_breakdown.keys()),
                        key="location_selector"
                    )
                    
                    if selected_location:
                        scenes_at_location = collated.scenes_by_location.get(selected_location, [])
                        st.write(f"**{len(scenes_at_location)} scene(s) at {selected_location}**")
                        
                        for scene in scenes_at_location:
                            with st.expander(
                                f"Episode: {scene['episode']} | Scene {scene['scene_number']}: {scene['slug_line']}"
                            ):
                                st.json(scene)
            
            # Characters across episodes
            st.subheader("Characters Across All Episodes")
            if collated.characters:
                # Sort by total lines
                sorted_chars = sorted(
                    collated.characters.items(),
                    key=lambda x: x[1]["total_lines"],
                    reverse=True
                )
                
                char_summary = []
                for char_name, char_data in sorted_chars:
                    first_app = char_data.get("first_appearance", {})
                    last_app = char_data.get("last_appearance", {})
                    first_app_str = f"{first_app.get('episode', '?')}:{first_app.get('scene', '?')}" if first_app.get("episode") else "—"
                    last_app_str = f"{last_app.get('episode', '?')}:{last_app.get('scene', '?')}" if last_app.get("episode") else "—"
                    
                    char_summary.append({
                        "Character": char_name,
                        "Total Lines": char_data["total_lines"],
                        "Scenes": char_data["scene_count"],
                        "Episodes": char_data["episode_count"],
                        "Episode List": ", ".join(char_data["episodes"]),
                        "First Appearance": first_app_str,
                        "Last Appearance": last_app_str
                    })
                
                st.dataframe(char_summary, use_container_width=True)
            
            # Export section
            st.subheader("Export Collated Reports")
            
            # Generate export data
            json_str = processor.generate_collated_json(collated)
            scenes_csv = processor.generate_collated_scenes_csv(collated)
            characters_csv = processor.generate_collated_characters_csv(collated)
            location_details_csv = processor.generate_location_details_csv(collated)
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.download_button(
                    label="📄 Download JSON",
                    data=json_str,
                    file_name="batch_collated_report.json",
                    mime="application/json",
                )
            
            with col2:
                st.download_button(
                    label="📍 Location Summary CSV",
                    data=scenes_csv,
                    file_name="batch_locations_summary.csv",
                    mime="text/csv",
                )
            
            with col3:
                st.download_button(
                    label="👥 Characters CSV",
                    data=characters_csv,
                    file_name="batch_characters.csv",
                    mime="text/csv",
                )
            
            with col4:
                st.download_button(
                    label="📋 Location Details CSV",
                    data=location_details_csv,
                    file_name="batch_location_details.csv",
                    mime="text/csv",
                )
            
            # Full JSON view
            st.subheader("Full Collated Data")
            with st.expander("View Full JSON"):
                st.json(json.loads(json_str))

