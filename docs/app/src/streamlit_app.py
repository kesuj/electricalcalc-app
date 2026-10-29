"""Entry point of the in-browser (GitHub Pages / stlite) build: same app, PVGIS answered from baked data."""
import runpy

import streamlit as st

import offline_pvgis

offline_pvgis.install()
st.sidebar.info("Browser version: sunshine data is real PVGIS data pre-calculated for 27 Nepal cities "
                "(nearest city and roof angle are used). Nothing you type leaves your computer.")
runpy.run_path("app.py", run_name="__main__")
