"""ElectricalCalc AI - Streamlit entry point.  Run:  .venv\\Scripts\\streamlit run app.py"""

import streamlit as st

from ecalc import config
from ui.design import design
from ui.farm import farm

st.set_page_config(page_title=config.APP_NAME, page_icon="⚡", layout="wide")

farm_page = st.Page(farm, title="Solar farm", icon="🏭", url_path="farm")
nav = st.navigation([st.Page(design, title="Home solar", icon="🏠", default=True), farm_page])
if st.query_params.get("page") == "farm":   # website links (?page=farm) - the browser build cannot use /farm URLs
    st.query_params.clear()
    st.switch_page(farm_page)
if config.PUBLIC_DEMO:
    st.warning("**Public demo.** Everything you enter is visible to other visitors and may be deleted at any time. "
               "Do not enter confidential client data. Document upload is disabled here.", icon="🌐")
st.sidebar.caption(f"{config.APP_TAGLINE}\n\nPreliminary calculations only - results require review by a "
                   "qualified engineer.")
nav.run()
