#!/usr/bin/env python3
"""
Meander - Script Analyzer (Beta)
Streamlit UI for parsing and analyzing script files
"""

import streamlit as st
import json
from script_parser import parse_fdx_bytes, parse_pdf_bytes, detect_file_type

st.set_page_config(page_title="Script Analyzer (Beta)", layout="wide")

st.title("Script Analyzer (Beta)")
st.write("Upload a Final Draft `.fdx` or `.pdf` file to see the parsed structure.")

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
            st.metric("Title", result.get("title", "Untitled")[:30] if result.get("title") else "Untitled")
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
        
        # Download button
        json_str = json.dumps(result, indent=2)
        st.download_button(
            label="Download JSON",
            data=json_str,
            file_name=f"{uploaded_file.name.rsplit('.', 1)[0]}_report.json",
            mime="application/json",
        )

