#!/usr/bin/env python3
"""
Meander - Script Analyzer
Streamlit UI for parsing and analyzing script files
"""

import streamlit as st
import json
import csv
import io
import os
from script_parser import parse_fdx_bytes, parse_pdf_bytes, detect_file_type

# Paywall features are only active when Supabase env vars are configured
PAYWALL_ENABLED = bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_ANON_KEY"))

if PAYWALL_ENABLED:
    from auth import (
        get_access_level, record_free_usage, is_valid_email,
        can_use_single_script, can_use_batch, AccessLevel
    )
    from stripe_helpers import PLANS, FREE_PLAN, create_checkout_session

st.set_page_config(page_title="Meander – Script Analyzer", layout="wide")

st.title("Meander – Script Analyzer")

st.markdown("""
**Speed up your production process!** Parse your scripts to get scene information, character breakdowns, 
and location analysis. Extract insights from your scripts in seconds.
""")

st.markdown("*Developed by Mighten Yip, 2025*")

# ---------------------------------------------------------------------------
# Access gate
# ---------------------------------------------------------------------------

if PAYWALL_ENABLED:
    # Persist email and access level across reruns in session state
    if "email" not in st.session_state:
        st.session_state.email = ""
    if "access" not in st.session_state:
        st.session_state.access = AccessLevel.NONE

    # Sidebar: email input + plan status
    with st.sidebar:
        st.header("Your Account")
        email_input = st.text_input(
            "Enter your email to get started:",
            value=st.session_state.email,
            placeholder="you@example.com",
            key="email_input"
        )

        if email_input and email_input != st.session_state.email:
            if not is_valid_email(email_input):
                st.error("Please enter a valid email address.")
            else:
                with st.spinner("Checking access..."):
                    st.session_state.email = email_input
                    st.session_state.access = get_access_level(email_input)

        access = st.session_state.access

        # Show current plan badge
        if access == AccessLevel.TEAM:
            st.success("Team plan — full access")
        elif access == AccessLevel.PRO:
            st.success("Pro plan — full access")
        elif access == AccessLevel.FREE_REMAINING:
            st.info("Free tier — 1 parse remaining")
        elif access == AccessLevel.FREE_EXHAUSTED:
            st.warning("Free trial used — upgrade to continue")
        else:
            st.caption("Enter your email above to get started.")

        # Upgrade button
        if access in (AccessLevel.FREE_EXHAUSTED, AccessLevel.NONE, AccessLevel.FREE_REMAINING):
            st.divider()
            st.subheader("Upgrade")
            for plan_key, plan in PLANS.items():
                with st.expander(f"{plan['name']} — {plan['price_display']}"):
                    for feature in plan["features"]:
                        st.write(f"• {feature}")
                    if st.session_state.email and is_valid_email(st.session_state.email):
                        if st.button(f"Subscribe to {plan['name']}", key=f"sub_{plan_key}"):
                            try:
                                app_url = os.environ.get("APP_URL", "http://localhost:8501")
                                checkout_url = create_checkout_session(
                                    email=st.session_state.email,
                                    plan=plan_key,
                                    success_url=app_url,
                                    cancel_url=app_url
                                )
                                st.markdown(f"[Complete payment →]({checkout_url})")
                            except Exception as e:
                                st.error(f"Could not create checkout session: {e}")
                    else:
                        st.caption("Enter your email above to subscribe.")
else:
    # No paywall configured — full access for everyone (dev / self-hosted)
    access = "full"

# ---------------------------------------------------------------------------
# Pricing section (shown when user has no email or is exhausted)
# ---------------------------------------------------------------------------

def show_pricing():
    st.divider()
    st.subheader("Plans")
    col_free, col_pro, col_team = st.columns(3)

    with col_free:
        st.markdown("### Free")
        st.markdown("**$0**")
        for f in FREE_PLAN["features"]:
            st.write(f"• {f}")

    for col, (plan_key, plan) in zip([col_pro, col_team], PLANS.items()):
        with col:
            st.markdown(f"### {plan['name']}")
            st.markdown(f"**{plan['price_display']}**")
            for f in plan["features"]:
                st.write(f"• {f}")


# ---------------------------------------------------------------------------
# Determine which mode to show (single / batch)
# ---------------------------------------------------------------------------

def user_can_proceed_single():
    if not PAYWALL_ENABLED:
        return True
    return can_use_single_script(st.session_state.access)

def user_can_proceed_batch():
    if not PAYWALL_ENABLED:
        return True
    return can_use_batch(st.session_state.access)

# ---------------------------------------------------------------------------
# Mode selector
# ---------------------------------------------------------------------------

st.write("")
mode = st.radio(
    "Select processing mode:",
    ["Single Script", "Batch Process (Multiple Episodes)"],
    horizontal=True
)
st.write("")

# ---------------------------------------------------------------------------
# Single script mode
# ---------------------------------------------------------------------------

if mode == "Single Script":
    if not user_can_proceed_single():
        st.error("Please enter your email to get started, or upgrade your plan to continue.")
        if PAYWALL_ENABLED:
            show_pricing()
        st.stop()

    st.write("Upload a script draft `.fdx` or `.pdf` file to see the parsed structure.")
    uploaded_file = st.file_uploader("Choose a script file", type=["fdx", "pdf"], key="single_file")

    if uploaded_file is not None:
        st.success(f"Uploaded: {uploaded_file.name}")

        file_bytes = uploaded_file.read()

        try:
            file_type = detect_file_type(filename=uploaded_file.name)
        except ValueError as e:
            st.error(f"Error detecting file type: {e}")
            st.stop()

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
            # Record free usage after a successful parse
            if PAYWALL_ENABLED and st.session_state.access == AccessLevel.FREE_REMAINING:
                try:
                    record_free_usage(st.session_state.email, uploaded_file.name)
                    st.session_state.access = get_access_level(st.session_state.email)
                except Exception:
                    pass  # Don't block the user if usage recording fails

            st.success("Parsing complete!")

            # Summary stats
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

            # Summary breakdowns
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
                        # TODO: Consider grouping locations hierarchically
                        locations = sorted(summary["location_breakdown"].items(), key=lambda x: x[1], reverse=True)[:10]
                        st.json(dict(locations))

            # Export section
            st.subheader("Export")
            base_name = uploaded_file.name.rsplit('.', 1)[0]

            def generate_scenes_csv(result):
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow([
                    "Scene #", "Slug Line", "INT/EXT", "Location", "Time of Day",
                    "Characters", "Line Count"
                ])
                for scene in result.get("scenes", []):
                    writer.writerow([
                        scene.get("scene_number", ""),
                        scene.get("slug_line", ""),
                        scene.get("int_ext", ""),
                        scene.get("location", ""),
                        scene.get("time_of_day", ""),
                        ", ".join(scene.get("characters", [])),
                        scene.get("line_count", 0)
                    ])
                return output.getvalue()

            def generate_characters_csv(result):
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

            col1, col2, col3 = st.columns(3)
            with col1:
                st.download_button(
                    label="📄 Download JSON",
                    data=json.dumps(result, indent=2),
                    file_name=f"{base_name}_report.json",
                    mime="application/json",
                )
            with col2:
                if "scenes" in result:
                    st.download_button(
                        label="📊 Download Scenes CSV",
                        data=generate_scenes_csv(result),
                        file_name=f"{base_name}_scenes.csv",
                        mime="text/csv",
                    )
            with col3:
                if "characters" in result:
                    st.download_button(
                        label="👥 Download Characters CSV",
                        data=generate_characters_csv(result),
                        file_name=f"{base_name}_characters.csv",
                        mime="text/csv",
                    )

            st.subheader("Parsed Output")
            tab1, tab2, tab3 = st.tabs(["Full JSON", "Scenes", "Characters"])

            with tab1:
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
                    sorted_chars = sorted(
                        result["characters"].items(),
                        key=lambda x: x[1].get("total_lines", 0),
                        reverse=True
                    )
                    for char_name, char_data in sorted_chars:
                        with st.expander(f"{char_data.get('name_canonical', char_name)} ({char_data.get('total_lines', 0)} lines)"):
                            st.json(char_data)

            # Upsell nudge after free parse
            if PAYWALL_ENABLED and st.session_state.access == AccessLevel.FREE_EXHAUSTED:
                st.divider()
                st.info("You've used your free parse. Upgrade to Pro or Team to continue using Meander.")
                show_pricing()

# ---------------------------------------------------------------------------
# Batch mode (paid only)
# ---------------------------------------------------------------------------

elif mode == "Batch Process (Multiple Episodes)":
    if not user_can_proceed_batch():
        st.warning("Batch processing is available on the **Pro** and **Team** plans.")
        if PAYWALL_ENABLED:
            show_pricing()
        st.stop()

    from batch_processor import BatchProcessor

    st.write("Upload multiple script files (`.fdx` or `.pdf`) to collate scenes across episodes.")
    st.write("**Example:** Upload 8 episode scripts to see location breakdowns across the whole season.")
    uploaded_files = st.file_uploader(
        "Choose script files (multiple)",
        type=["fdx", "pdf"],
        accept_multiple_files=True,
        key="batch_files"
    )

    if uploaded_files:
        st.success(f"Uploaded {len(uploaded_files)} file(s)")

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

        if not errors:
            st.success("All scripts processed successfully!")

            with st.spinner("Collating results across all episodes..."):
                collated = processor.collate()

            st.success("Collation complete!")

            # Batch summary
            st.subheader("Batch Summary")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Episodes", collated.total_episodes)
            with col2:
                st.metric("Total Scenes", collated.total_scenes)
            with col3:
                avg = collated.total_scenes / collated.total_episodes if collated.total_episodes > 0 else 0
                st.metric("Avg Scenes/Episode", f"{avg:.1f}")
            with col4:
                st.metric("Total Characters", len(collated.characters))

            st.subheader("Episodes Processed")
            st.dataframe(
                [{"Filename": ep.filename, "Title": ep.title or "—", "Scenes": len(ep.script_data.scenes)}
                 for ep in collated.episodes],
                use_container_width=True
            )

            st.subheader("Collated Breakdowns")
            col1, col2 = st.columns(2)
            with col1:
                st.write("**INT/EXT Breakdown (All Episodes)**")
                st.json(collated.int_ext_breakdown)
                st.write("**Time of Day Breakdown (All Episodes)**")
                st.json(collated.time_of_day_breakdown)
            with col2:
                st.write("**Location Breakdown (All Episodes)**")
                top_locations = list(collated.location_breakdown.items())[:20]
                st.json(dict(top_locations))
                if len(collated.location_breakdown) > 20:
                    st.info(f"Showing top 20 of {len(collated.location_breakdown)} total locations.")

            st.subheader("Scenes by Location")
            loc_tab1, loc_tab2 = st.tabs(["Location Summary", "Location Details"])

            with loc_tab1:
                location_summary = []
                for location, count in list(collated.location_breakdown.items())[:50]:
                    episodes = set(s["episode"] for s in collated.scenes_by_location.get(location, []))
                    location_summary.append({
                        "Location": location,
                        "Total Scenes": count,
                        "Episodes": len(episodes),
                        "Episode List": ", ".join(sorted(episodes))
                    })
                st.dataframe(location_summary, use_container_width=True)

            with loc_tab2:
                if collated.location_breakdown:
                    selected_location = st.selectbox(
                        "Select a location to view all scenes:",
                        list(collated.location_breakdown.keys()),
                        key="location_selector"
                    )
                    if selected_location:
                        scenes_here = collated.scenes_by_location.get(selected_location, [])
                        st.write(f"**{len(scenes_here)} scene(s) at {selected_location}**")
                        for scene in scenes_here:
                            with st.expander(f"Episode: {scene['episode']} | Scene {scene['scene_number']}: {scene['slug_line']}"):
                                st.json(scene)

            st.subheader("Characters Across All Episodes")
            if collated.characters:
                sorted_chars = sorted(collated.characters.items(), key=lambda x: x[1]["total_lines"], reverse=True)
                char_rows = []
                for char_name, char_data in sorted_chars:
                    first = char_data.get("first_appearance", {})
                    last = char_data.get("last_appearance", {})
                    char_rows.append({
                        "Character": char_name,
                        "Total Lines": char_data["total_lines"],
                        "Scenes": char_data["scene_count"],
                        "Episodes": char_data["episode_count"],
                        "Episode List": ", ".join(char_data["episodes"]),
                        "First Appearance": f"{first.get('episode','?')}:{first.get('scene','?')}" if first.get("episode") else "—",
                        "Last Appearance": f"{last.get('episode','?')}:{last.get('scene','?')}" if last.get("episode") else "—"
                    })
                st.dataframe(char_rows, use_container_width=True)

            st.subheader("Export Collated Reports")
            json_str = processor.generate_collated_json(collated)
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.download_button("📄 Download JSON", data=json_str,
                                   file_name="batch_collated_report.json", mime="application/json")
            with col2:
                st.download_button("📍 Location Summary CSV",
                                   data=processor.generate_collated_scenes_csv(collated),
                                   file_name="batch_locations_summary.csv", mime="text/csv")
            with col3:
                st.download_button("👥 Characters CSV",
                                   data=processor.generate_collated_characters_csv(collated),
                                   file_name="batch_characters.csv", mime="text/csv")
            with col4:
                st.download_button("📋 Location Details CSV",
                                   data=processor.generate_location_details_csv(collated),
                                   file_name="batch_location_details.csv", mime="text/csv")

            with st.expander("View Full JSON"):
                st.json(json.loads(json_str))
