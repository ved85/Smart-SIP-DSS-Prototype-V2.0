"""
Title: Page Footer

MADE BY: VEDANT VARMA
©Vedant Varma | All Rights Reserved
CREATED AT: 05/10/26
"""

import streamlit as st

def inject_footer():
    st.markdown("""
    <style>
        /* Add padding to the main container so content doesn't get hidden behind the footer */
        .block-container { 
            padding-bottom: 5rem !important; 
        }
        
        /* Footer Styling */
        .custom-footer {
            position: fixed;
            bottom: 0;
            left: 0;
            width: 100%;
            background-color: #161b22; /* Matches the dark theme background */
            color: #8b949e;
            text-align: center;
            padding: 12px 0px;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            font-size: 0.85rem;
            font-weight: 500;
            border-top: 1px solid #30363d; /* Subtle top border */
            z-index: 99999; /* Ensures it sits on top of maps and charts */
        }
    </style>

    <div class="custom-footer">
        ©Vedant Varma | All Rights Reserved
    </div>
    """, unsafe_allow_html=True)