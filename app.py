"""ElectricalCalc AI - Streamlit entry point.  Run:  .venv\\Scripts\\streamlit run app.py"""

import streamlit as st

from ecalc import config
from ui import pages
from ui.design import design

st.set_page_config(page_title=config.APP_NAME, page_icon="⚡", layout="wide")

nav = st.navigation({
    config.APP_NAME: [st.Page(design, title="New project design", icon="📐", default=True),
                     st.Page(pages.home, title="Home & projects", icon="🏠", url_path="home")],
    "Calculations": [st.Page(pages.solar, title="Solar PV sizing", icon="☀️", url_path="solar"),
                     st.Page(pages.electrical, title="Electrical tools", icon="🔌", url_path="electrical"),
                     st.Page(pages.cable, title="Cable voltage drop", icon="🧵", url_path="cable")],
    "Deliverables": [st.Page(pages.report_page, title="Reports & history", icon="📄", url_path="reports")],
    "AI": [st.Page(pages.assistant, title="AI assistant", icon="🤖", url_path="assistant"),
           st.Page(pages.docs, title="Documents", icon="📚", url_path="documents")],
    "System": [st.Page(pages.settings, title="Settings & providers", icon="⚙️", url_path="settings"),
               st.Page(pages.usage, title="Usage & costs", icon="💲", url_path="usage"),
               st.Page(pages.help_page, title="Help", icon="❓", url_path="help")],
})
if config.PUBLIC_DEMO:
    st.warning("**Public demo.** Everything you enter is visible to other visitors and may be deleted at any time. "
               "Do not enter confidential client data. Document upload is disabled here.", icon="🌐")
st.sidebar.caption(f"{config.APP_TAGLINE}\n\nPreliminary calculations only - results require review by a "
                   "qualified engineer.")
nav.run()
