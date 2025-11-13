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

st.set_page_config(page_title="Script Analyzer (Beta)", layout="wide")

st.title("Script Analyzer (Beta)")

st.markdown("""
**Speed up your production process!** Parse your scripts to get scene information, character breakdowns, 
and location analysis. Extract insights from your scripts in seconds.
""")

st.markdown("*Developed by Mighten Yip, 2025*")

st.write("")
st.write("Upload a script draft `.fdx` or `.pdf` file to see the parsed structure.")

uploaded_file = st.file_uploader("Choose a script file", type=["fdx", "pdf"])

if uploaded_file is not None:
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

