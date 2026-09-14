"""Lazy browser registrations; listing tools never imports Playwright."""

from code_puppy.tools._lazy import lazy_registration

BROWSER_TOOL_REGISTRY = {
    "browser_initialize": lazy_registration(
        "code_puppy.tools.browser.browser_control", "register_initialize_browser"
    ),
    "browser_close": lazy_registration(
        "code_puppy.tools.browser.browser_control", "register_close_browser"
    ),
    "browser_status": lazy_registration(
        "code_puppy.tools.browser.browser_control", "register_get_browser_status"
    ),
    "browser_new_page": lazy_registration(
        "code_puppy.tools.browser.browser_control", "register_create_new_page"
    ),
    "browser_list_pages": lazy_registration(
        "code_puppy.tools.browser.browser_control", "register_list_pages"
    ),
    "browser_navigate": lazy_registration(
        "code_puppy.tools.browser.browser_navigation", "register_navigate_to_url"
    ),
    "browser_get_page_info": lazy_registration(
        "code_puppy.tools.browser.browser_navigation", "register_get_page_info"
    ),
    "browser_go_back": lazy_registration(
        "code_puppy.tools.browser.browser_navigation", "register_browser_go_back"
    ),
    "browser_go_forward": lazy_registration(
        "code_puppy.tools.browser.browser_navigation", "register_browser_go_forward"
    ),
    "browser_reload": lazy_registration(
        "code_puppy.tools.browser.browser_navigation", "register_reload_page"
    ),
    "browser_wait_for_load": lazy_registration(
        "code_puppy.tools.browser.browser_navigation", "register_wait_for_load_state"
    ),
    "browser_find_by_role": lazy_registration(
        "code_puppy.tools.browser.browser_locators", "register_find_by_role"
    ),
    "browser_find_by_text": lazy_registration(
        "code_puppy.tools.browser.browser_locators", "register_find_by_text"
    ),
    "browser_find_by_label": lazy_registration(
        "code_puppy.tools.browser.browser_locators", "register_find_by_label"
    ),
    "browser_find_by_placeholder": lazy_registration(
        "code_puppy.tools.browser.browser_locators", "register_find_by_placeholder"
    ),
    "browser_find_by_test_id": lazy_registration(
        "code_puppy.tools.browser.browser_locators", "register_find_by_test_id"
    ),
    "browser_xpath_query": lazy_registration(
        "code_puppy.tools.browser.browser_locators", "register_run_xpath_query"
    ),
    "browser_find_buttons": lazy_registration(
        "code_puppy.tools.browser.browser_locators", "register_find_buttons"
    ),
    "browser_find_links": lazy_registration(
        "code_puppy.tools.browser.browser_locators", "register_find_links"
    ),
    "browser_page_snapshot": lazy_registration(
        "code_puppy.tools.browser.browser_page_snapshot", "register_get_page_snapshot"
    ),
    "browser_click_by_role": lazy_registration(
        "code_puppy.tools.browser.browser_semantic_interactions",
        "register_click_by_role",
    ),
    "browser_click_by_text": lazy_registration(
        "code_puppy.tools.browser.browser_semantic_interactions",
        "register_click_by_text",
    ),
    "browser_set_text_by_label": lazy_registration(
        "code_puppy.tools.browser.browser_semantic_interactions",
        "register_set_text_by_label",
    ),
    "browser_click": lazy_registration(
        "code_puppy.tools.browser.browser_interactions", "register_click_element"
    ),
    "browser_double_click": lazy_registration(
        "code_puppy.tools.browser.browser_interactions", "register_double_click_element"
    ),
    "browser_hover": lazy_registration(
        "code_puppy.tools.browser.browser_interactions", "register_hover_element"
    ),
    "browser_set_text": lazy_registration(
        "code_puppy.tools.browser.browser_interactions", "register_set_element_text"
    ),
    "browser_get_text": lazy_registration(
        "code_puppy.tools.browser.browser_interactions", "register_get_element_text"
    ),
    "browser_get_value": lazy_registration(
        "code_puppy.tools.browser.browser_interactions", "register_get_element_value"
    ),
    "browser_select_option": lazy_registration(
        "code_puppy.tools.browser.browser_interactions", "register_select_option"
    ),
    "browser_check": lazy_registration(
        "code_puppy.tools.browser.browser_interactions", "register_browser_check"
    ),
    "browser_uncheck": lazy_registration(
        "code_puppy.tools.browser.browser_interactions", "register_browser_uncheck"
    ),
    "browser_execute_js": lazy_registration(
        "code_puppy.tools.browser.browser_scripts", "register_execute_javascript"
    ),
    "browser_scroll": lazy_registration(
        "code_puppy.tools.browser.browser_scripts", "register_scroll_page"
    ),
    "browser_scroll_to_element": lazy_registration(
        "code_puppy.tools.browser.browser_scripts", "register_scroll_to_element"
    ),
    "browser_set_viewport": lazy_registration(
        "code_puppy.tools.browser.browser_scripts", "register_set_viewport_size"
    ),
    "browser_wait_for_element": lazy_registration(
        "code_puppy.tools.browser.browser_scripts", "register_wait_for_element"
    ),
    "browser_highlight_element": lazy_registration(
        "code_puppy.tools.browser.browser_scripts", "register_browser_highlight_element"
    ),
    "browser_clear_highlights": lazy_registration(
        "code_puppy.tools.browser.browser_scripts", "register_browser_clear_highlights"
    ),
    "browser_screenshot_analyze": lazy_registration(
        "code_puppy.tools.browser.browser_screenshot",
        "register_take_screenshot_and_analyze",
    ),
    "browser_save_workflow": lazy_registration(
        "code_puppy.tools.browser.browser_workflows", "register_save_workflow"
    ),
    "browser_list_workflows": lazy_registration(
        "code_puppy.tools.browser.browser_workflows", "register_list_workflows"
    ),
    "browser_read_workflow": lazy_registration(
        "code_puppy.tools.browser.browser_workflows", "register_read_workflow"
    ),
}
