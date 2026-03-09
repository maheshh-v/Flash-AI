from __future__ import annotations


ABOUT_US_URL = "https://www.flashspace.ai/about"
VIRTUAL_OFFICE_URL = "https://www.flashspace.ai/Solutions/virtual-office"
COWORKING_URL = "https://www.flashspace.ai/Solutions/coworking-space"
PARTNER_URL = "https://www.flashspace.ai/partner"
BUSINESS_SETUP_URL = "https://www.flashspace.ai/Solutions/business-setup"

SUPPORT_EMAIL = "support@flashspace.co"
SALES_EMAIL = "sales@flashspace.co"
SALES_CONTACT = "8100888777"
PARTNERSHIP_EMAIL = "partner@flashspace.co"


def render_navigation_links() -> str:
    return (
        f"[Virtual Office]({VIRTUAL_OFFICE_URL})\n"
        f"[Coworking Space]({COWORKING_URL})\n"
        f"[Business Setup]({BUSINESS_SETUP_URL})\n"
        f"[Partner Program]({PARTNER_URL})"
    )


def render_primary_contact_block() -> str:
    return (
        f"[About Us]({ABOUT_US_URL})\n"
        f"Support: {SUPPORT_EMAIL}\n"
        f"Sales: {SALES_EMAIL}\n"
        f"Sales Contact: {SALES_CONTACT}\n"
        f"Partnership: {PARTNERSHIP_EMAIL}"
    )


def render_contact_handoff_with_nav() -> str:
    return (
        "I can connect you with the FlashSpace team right away.\n\n"
        f"{render_primary_contact_block()}\n\n"
        "Quick links:\n"
        f"{render_navigation_links()}"
    )


def render_company_info_with_nav() -> str:
    return (
        f"{render_primary_contact_block()}\n\n"
        "Go to:\n"
        f"{render_navigation_links()}"
    )
